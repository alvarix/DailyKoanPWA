# pyright: reportMissingImports=false
"""Serve stateless koan pages and manage push delivery and subscriptions."""

import os
import re
import warnings
from urllib.parse import urlparse

from flask import Flask, jsonify, render_template, request, send_from_directory

import delivery_trace
import koan_selector
from koan_selector import (
    daily_index,
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

# Idempotent settings migration (data-model ADR). Safe to run at
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


def _render_koan(koans, idx, *, is_home=False, held_missing=False):
    """Render a koan with delivery preferences and the read-only legacy seed."""
    settings = get_settings()
    try:
        seed = int(settings.get("current_index", 0)) % len(koans)
    except (TypeError, ValueError):
        seed = 0
    return render_template(
        "index.html",
        koan=koans[idx],
        koan_index=idx,
        total_koans=len(koans),
        is_home=is_home,
        held_seed=seed,
        held_missing=held_missing,
        vapid_public_key=VAPID_PUBLIC_KEY,
        notification_texts=[koan["koan_text"] for koan in koans],
        push_time=settings.get("push_time", "08:00"),
        push_timezone=settings.get("push_timezone", "America/New_York"),
    )


@app.route("/")
def index():
    """Serve today's UTC-date koan; the browser may resume its bookmark."""
    koans = load_koans()
    return _render_koan(koans, daily_index(len(koans)), is_home=True)


@app.route("/koan/<int:index>")
def koan_by_index(index):
    """Render a deep link without changing any bookmark."""
    koans = load_koans()
    if 0 <= index < len(koans):
        return _render_koan(koans, index)
    if request.args.get("resume") == "1":
        return _render_koan(
            koans, daily_index(len(koans)), is_home=True, held_missing=True
        ), 404
    return jsonify({"error": "Koan not found"}), 404


@app.route("/api/today")
def api_today():
    """Return today's deterministic UTC-date koan."""
    koans = load_koans()
    idx = daily_index(len(koans))
    return jsonify(koan=koans[idx], index=idx, total=len(koans))


@app.route("/api/koan/<int:index>")
def api_koan(index):
    """API: return a specific koan as JSON."""
    koans = load_koans()
    if 0 <= index < len(koans):
        return jsonify({"koan": koans[index], "index": index, "total": len(koans)})
    return jsonify({"error": "Koan not found"}), 404


@app.route("/api/next", methods=["POST"])
@app.route("/api/mode", methods=["POST"])
def retired_progression():
    """Tell stale clients that server-side progression is gone."""
    return jsonify(error="Koan progression is now device-local"), 410


@app.route("/api/settings", methods=["GET"])
def api_settings_get():
    """API: the current global settings (all values are non-sensitive)."""
    return jsonify(get_settings())


@app.route("/api/settings", methods=["POST"])
def api_settings_post():
    """Update only push delivery time and timezone."""
    if not same_origin():
        return jsonify({"error": "Cross-origin request rejected"}), 403
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or data.keys() - {"push_time", "push_timezone"}:
        return jsonify(error="Only push_time and push_timezone can be updated"), 400
    updates = {}
    if "push_time" in data:
        value = data["push_time"]
        if not isinstance(value, str) or not PUSH_TIME_RE.match(value):
            return jsonify({"error": "push_time must be HH:MM (24h)"}), 400
        updates["push_time"] = value
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


@app.post("/api/push-receipt")
def push_receipt():
    """Accept a bounded, capability-authenticated worker receipt."""
    if not same_origin() or request.content_length is None or request.content_length > 256:
        return "", 400
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return "", 400
    return "", 204 if delivery_trace.receipt(data.get("token"), data.get("stage")) else 404


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
