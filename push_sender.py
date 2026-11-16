#!/usr/bin/env python3
"""
Standalone push sender (dailykoan-push.service, fired by the 08:00 UTC timer).

The timer is the ONLY push mechanism (push-pipeline ADR): nothing in the Flask
app ever broadcasts. This script decides at run time — via koan_selector, the
same shared module the app imports — which koan (if any) goes out today:

  daily mode:  today's deterministic koan, deduped on last_push_date
               (Persistent=true may double-fire the timer; the date key
               absorbs the rerun).
  held mode:   the current global pointer, but only when it moved since the
               last push (last_push_index dedupe); otherwise exit quietly.

Nothing is sent until the decision is made, and the dedupe keys are only
written AFTER a completed send loop (koan_selector.mark_pushed), so a crash
mid-broadcast re-sends rather than silently skipping a day.
"""

import json
import os
import sys

from pywebpush import WebPushException, webpush

import koan_selector
from koan_selector import (
    ensure_settings,
    get_settings,
    load_koans,
    mark_pushed,
    select_push,
)

# PEM path string — pywebpush loads it via Vapid.from_file. NEVER raw bytes:
# bytes fell into Vapid.from_string() and crashed the first real live send
# ('bytes' object has no attribute 'encode' — CHANGELOG 0.1.3).
VAPID_PRIVATE_PATH = os.path.join(os.path.dirname(__file__), "vapid_private.pem")

# Public name from the deployment ADR; override for local/ngrok testing.
DEFAULT_BASE_URL = "https://dailykoan.duckdns.org/"


def get_subscriptions():
    """All active push subscriptions (endpoint, p256dh, auth)."""
    conn = koan_selector.connect()
    cursor = conn.cursor()
    cursor.execute("SELECT endpoint, p256dh, auth FROM subscriptions")
    rows = cursor.fetchall()
    conn.close()
    return rows


def truncate_utf8_bytes(text, max_bytes=3000):
    """Truncate text to fit within max_bytes UTF-8 bytes without splitting a codepoint.

    Web Push payloads must stay under the client's encrypted-size budget. A plain
    character count can overshoot because multi-byte codepoints and JSON escaping
    both cost bytes. This function works on the UTF-8 byte representation and backs
    up to the last complete codepoint before appending an ellipsis.
    """
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    # UTF-8 sequences are at most 4 bytes; back up at most 3 bytes from the cut.
    for end in range(max_bytes, max(0, max_bytes - 4), -1):
        try:
            return encoded[:end].decode("utf-8") + "…"
        except UnicodeDecodeError:
            continue
    # Should never reach here for valid UTF-8 input, but the fallback is safe.
    return text[:max_bytes] + "…"


def send_push(subscription, payload, vapid_private_key):
    """Send one Web Push. Returns True (sent), False (confirmed gone), None (keep).

    Retention policy (data-model ADR): only a confirmed 404/410 may delete a
    subscription. 403 BadJwtToken, 429 rate limits, and network errors KEEP the
    row — the 2026-11-15 live incidents deleted two valid iOS subscriptions
    before this tri-state existed.
    """
    try:
        webpush(
            subscription_info={
                "endpoint": subscription[0],
                "keys": {"p256dh": subscription[1], "auth": subscription[2]},
            },
            data=json.dumps(payload),
            vapid_private_key=vapid_private_key,
            vapid_claims={
                "sub": "mailto:alvarix@gmail.com"
            },  # real contact; the old .example reserved TLD was an Apple-rejection suspect
            ttl=86400,  # 24 hours
        )
        return True
    except WebPushException as e:
        if e.response and e.response.status_code in (404, 410):
            # Subscription confirmed gone (endpoint says so) - caller may remove it.
            return False
        # 403 BadJwtToken, 429 rate-limit, network failure: KEEP, just report.
        print(f"Push error: {e}")
        return None
    except Exception as e:
        print(f"Unexpected push error: {e}")
        return None


def remove_subscription(endpoint):
    """Delete a subscription row (only called on confirmed 404/410)."""
    conn = koan_selector.connect()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM subscriptions WHERE endpoint = ?", (endpoint,))
    conn.commit()
    conn.close()
    print(f"Removed dead subscription: {endpoint[:60]}...")


def main():
    """Timer entry point. Sends the current koan if the dedupe keys allow."""
    if not os.path.exists(VAPID_PRIVATE_PATH):
        print(f"ERROR: VAPID private key not found at {VAPID_PRIVATE_PATH}")
        print("Run: python init_vapid.py")
        sys.exit(1)

    vapid_private_key = VAPID_PRIVATE_PATH  # path string, see module docstring

    # Same idempotent migration the app runs at startup — this process may be
    # the first to touch the DB after a deploy (0.1.3/A: never rely on the
    # other process having started first).
    ensure_settings()

    koans = load_koans()
    settings = get_settings()
    picked = select_push(koans, settings)

    if picked is None:
        # Quiet exit — but say why, so a missed koan is diagnosable in the
        # journal (push-pipeline ADR: the journal is the log).
        mode = settings.get("mode")
        print(
            "Nothing new to push "
            f"(mode={mode}, current_index={settings.get('current_index')}, "
            f"last_push_date={settings.get('last_push_date') or '-'!r}, "
            f"last_push_index={settings.get('last_push_index') or '-'!r})."
        )
        print("Done. Sent: 0, Removed dead: 0, Failed (kept): 0")
        return

    idx, koan = picked
    body = truncate_utf8_bytes(koan["koan_text"])
    url = os.environ.get("BASE_URL", DEFAULT_BASE_URL)
    koan_url = f"{url.rstrip('/')}/koan/{idx}"

    # Title is intentionally omitted; the service worker falls back to the app
    # name, so the visible notification is just the koan body (002 tweak 2).
    payload = {
        "body": body,
        "icon": "/static/icon-192.png",
        "badge": "/static/badge-72.png",
        "data": {"url": koan_url},
    }

    subscriptions = get_subscriptions()
    print(f"Sending to {len(subscriptions)} subscription(s)...")
    print(f"Koan to push: {koan['title']} (index {idx}, mode={settings.get('mode')})")

    sent = dead = failed = 0
    for sub in subscriptions:
        ok = send_push(sub, payload, vapid_private_key)
        if ok:
            sent += 1
        elif ok is False:
            # Only 404/410 (endpoint confirmed gone) may delete a subscription.
            dead += 1
            remove_subscription(sub[0])
        else:
            # Error (network, key, crypto): KEEP the subscription, just report.
            failed += 1

    # Dedupe keys only after a completed send loop (crash => re-send, not skip).
    mark_pushed(index=idx)

    print(f"Done. Sent: {sent}, Removed dead: {dead}, Failed (kept): {failed}")


if __name__ == "__main__":
    main()
