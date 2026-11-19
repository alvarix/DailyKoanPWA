# pyright: reportMissingImports=false
"""
Flask application for Daily Koan PWA.

Serves the PWA frontend and API endpoints for koans, push subscriptions, and
the global settings that control koan selection (docs/002).

All koan-selection state lives in koan_selector.py — the one shared code path
imported by both this app (gunicorn) and push_sender.py (systemd timer) — so
the site and the push can never disagree about which koan is current
(push-pipeline ADR; docs/003 "Componentizing the same-koan logic").
"""

import os
import re
import warnings
from urllib.parse import urlparse

from flask import Flask, jsonify, render_template, request, send_from_directory

import koan_selector
from koan_selector import (
    VALID_MODES,
    VALID_PROGRESSIONS,
    advance,
    current_index,
    ensure_settings,
    get_settings,
    load_koans,
    set_values,
    valid_timezone,
)

# Load VAPID public key if available
VAPID_PUBLIC_KEY = None
vapid_public_path = os.path.join(os.path.dirname(__file__), "vapid_public.pem")
if os.path.exists(vapid_public_path):
    try:
        from cryptography.hazmat.primitives import serialization
        from py_vapid import b64urlencode

        with open(vapid_public_path, "rb") as f:
            key = serialization.load_pem_public_key(f.read())
        VAPID_PUBLIC_KEY = b64urlencode(
            key.public_bytes(
                encoding=serialization.Encoding.X962,
                format=serialization.PublicFormat.UncompressedPoint,
            )
        )
    except Exception as e:
        warnings.warn(f"Failed to load VAPID public key: {e}", stacklevel=2)
        VAPID_PUBLIC_KEY = None

app = Flask(__name__)

# Idempotent, additive settings migration (data-model ADR). Safe to run at
# every process start: creates the settings table and seeds defaults if the
# schema version is behind. push_sender.py runs the same function.
ensure_settings()

# Time-of-day accepted by POST /api/settings (HH:MM, 24h).
PUSH_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


# ----------- Helpers -----------


def get_db():
    """Connection with the per-connection PRAGMAs both processes rely on."""
    return koan_selector.connect()


def same_origin():
    """Trivial CSRF guard for the state-changing endpoints (docs/002).

    True unless a browser-supplied Origin/Referer names a different host.
    There is no auth to lean on here: the endpoints are global by design
    (personal PWA, single operator — documented property, not a bug).
    Browsers always send Origin on cross-origin POSTs, so an absent header
    means a non-browser client (curl, systemd, tests) and is allowed.
    """
    origin = request.headers.get("Origin") or request.headers.get("Referer")
    if not origin:
        return True
    netloc = urlparse(origin).netloc
    return not netloc or netloc == request.host


def _current_state():
    """Return (koans, settings, current_index) — everything selection needs."""
    koans = load_koans()
    settings = get_settings()
    return koans, settings, current_index(settings, len(koans))


def _page_context(koan, idx, cur):
    """Template context shared by / and /koan/<idx> (deep links)."""
    settings = get_settings()
    return {
        "koan": koan,
        "koan_index": idx,
        "total_koans": len(load_koans()),
        "mode": settings.get("mode", "held"),
        "progression": settings.get("progression", "ordered"),
        "push_time": settings.get("push_time", "08:00"),
        "push_timezone": settings.get("push_timezone", "America/New_York"),
        "current_index": cur,
        "viewing_current": idx == cur,
        "vapid_public_key": VAPID_PUBLIC_KEY,
    }


# ----------- Routes -----------


@app.route("/")
def index():
    """Serve the main PWA page with the currently-selected koan."""
    koans, _settings, cur = _current_state()
    return render_template("index.html", **_page_context(koans[cur], cur, cur))


@app.route("/koan/<int:index>")
def koan_by_index(index):
    """Deep link to a specific koan. Per-visitor navigation only.

    Deliberately does NOT move the global pointer — only POST /api/next
    (held mode) or the date (daily mode) changes what everyone sees
    (docs/002).
    """
    koans, _settings, cur = _current_state()
    if 0 <= index < len(koans):
        return render_template("index.html", **_page_context(koans[index], index, cur))
    return jsonify({"error": "Koan not found"}), 404


@app.route("/api/today")
def api_today():
    """API: the current koan (mode-aware) as JSON."""
    koans, settings, cur = _current_state()
    return jsonify(
        {
            "koan": koans[cur],
            "index": cur,
            "total": len(koans),
            "mode": settings.get("mode", "held"),
            "current_index": cur,
        }
    )


@app.route("/api/koan/<int:index>")
def api_koan(index):
    """API: return a specific koan as JSON."""
    koans = load_koans()
    if 0 <= index < len(koans):
        return jsonify({"koan": koans[index], "index": index, "total": len(koans)})
    return jsonify({"error": "Koan not found"}), 404


@app.route("/api/next", methods=["POST"])
def api_next():
    """Advance the global held-mode pointer to the next koan.

    409 in daily mode — the endpoint only means something when the pointer
    is the source of truth (docs/002). The advance itself is atomic and
    wraps around the end of the list (koan_selector.advance).
    """
    settings = get_settings()
    if settings.get("mode") != "held":
        return jsonify({"error": "Next is only available in held mode"}), 409
    if not same_origin():
        return jsonify({"error": "Cross-origin request rejected"}), 403
    koans = load_koans()
    nxt = advance(total=len(koans))
    return jsonify({"success": True, "index": nxt, "total": len(koans)})


@app.route("/api/mode", methods=["POST"])
def api_mode():
    """Explicitly set held/daily mode (idempotent — never a blind toggle).

    Switching clears both push-dedupe keys so the next 08:00 timer run pushes
    once in the new mode instead of being silenced by a stale key
    (koan_selector.set_values; push-pipeline ADR).
    """
    if not same_origin():
        return jsonify({"error": "Cross-origin request rejected"}), 403
    data = request.get_json(silent=True) or {}
    mode = data.get("mode")
    if mode not in VALID_MODES:
        return jsonify({"error": "mode must be 'held' or 'daily'"}), 400
    set_values(mode=mode)
    return jsonify({"success": True, "mode": mode})


@app.route("/api/settings", methods=["GET"])
def api_settings_get():
    """API: the current global settings (all values are non-sensitive)."""
    return jsonify(get_settings())


@app.route("/api/settings", methods=["POST"])
def api_settings_post():
    """API: update settings — push_time (HH:MM) and progression.

    push_time is the recorded daily-push preference; the systemd timer
    currently fires at 08:00 UTC, so actually moving delivery time is an ops
    step (docs/003 "Open items"; the UI says this rather than lying).
    """
    if not same_origin():
        return jsonify({"error": "Cross-origin request rejected"}), 403
    data = request.get_json(silent=True) or {}
    updates = {}
    if "push_time" in data:
        value = data["push_time"]
        if not isinstance(value, str) or not PUSH_TIME_RE.match(value):
            return jsonify({"error": "push_time must be HH:MM (24h)"}), 400
        updates["push_time"] = value
    if "progression" in data:
        if data["progression"] not in VALID_PROGRESSIONS:
            return jsonify({"error": "progression must be 'ordered' or 'random'"}), 400
        updates["progression"] = data["progression"]
    if "push_timezone" in data:
        # 0.1.8: delivery time became data. The client auto-syncs its IANA
        # zone here (single operator — the device zone IS the right zone);
        # the drawer also offers a manual "use my device timezone" tap.
        value = data["push_timezone"]
        if not isinstance(value, str) or not valid_timezone(value):
            return jsonify(
                {"error": "push_timezone must be an IANA zone (e.g. America/New_York)"}
            ), 400
        updates["push_timezone"] = value
    if not updates:
        return jsonify({"error": "No valid settings in request"}), 400
    set_values(**updates)
    return jsonify({"success": True, **updates})


@app.route("/api/subscribe", methods=["POST"])
def api_subscribe():
    """Store a push subscription from the browser."""
    data = request.get_json()
    if not data or "endpoint" not in data or "keys" not in data:
        return jsonify({"error": "Invalid subscription data"}), 400

    endpoint = data["endpoint"]
    p256dh = data["keys"].get("p256dh")
    auth = data["keys"].get("auth")

    if not p256dh or not auth:
        return jsonify({"error": "Missing keys"}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO subscriptions (endpoint, p256dh, auth) VALUES (?, ?, ?)",
        (endpoint, p256dh, auth),
    )
    conn.commit()
    conn.close()

    return jsonify({"success": True}), 201


@app.route("/api/unsubscribe", methods=["POST"])
def api_unsubscribe():
    """Remove a push subscription."""
    data = request.get_json()
    endpoint = data.get("endpoint") if data else None
    if not endpoint:
        return jsonify({"error": "Missing endpoint"}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM subscriptions WHERE endpoint = ?", (endpoint,))
    conn.commit()
    conn.close()

    return jsonify({"success": True})


@app.route("/manifest.json")
def manifest():
    """Serve the PWA manifest."""
    return send_from_directory("static", "manifest.json")


@app.route("/sw.js")
def service_worker():
    """Serve the service worker."""
    return send_from_directory("static", "sw.js")


@app.route("/api/subscriptions/count")
def subscription_count():
    """Admin/debug: count active subscriptions."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM subscriptions")
    count = cursor.fetchone()[0]
    conn.close()
    return jsonify({"count": count})


# --- Error handlers ---


@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404


if __name__ == "__main__":
    app.run(
        host=os.environ.get("FLASK_HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", 5000)),
        debug=os.environ.get("FLASK_DEBUG", "1") == "1",
    )
