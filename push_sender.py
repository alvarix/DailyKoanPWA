#!/usr/bin/env python3
"""Hourly push job: send a notification trigger once per delivery-zone day."""

import json
import os
import sys
from datetime import datetime, timezone

from pywebpush import WebPushException, webpush

import koan_selector
from koan_selector import (
    daily_index,
    delivery_window,
    ensure_settings,
    get_settings,
    is_delivery_time,
    load_koans,
    mark_pushed,
    select_push,
)

# PEM path string — pywebpush loads it via Vapid.from_file. NEVER raw bytes:
# bytes fell into Vapid.from_string() and crashed the first real live send
# ('bytes' object has no attribute 'encode' — CHANGELOG 0.1.3).
VAPID_PRIVATE_PATH = os.path.join(os.path.dirname(__file__), "vapid_private.pem")

def get_subscriptions():
    """All active push subscriptions (endpoint, p256dh, auth)."""
    conn = koan_selector.connect()
    cursor = conn.cursor()
    cursor.execute("SELECT endpoint, p256dh, auth FROM subscriptions")
    rows = cursor.fetchall()
    conn.close()
    return rows


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


def build_payload(daily_body):
    """Build a trigger with public Daily text, never a held bookmark."""
    return {
        "body": "Your koan awaits.",
        "dailyBody": daily_body,
        "icon": "/static/icon-192.png",
        "badge": "/static/badge-72.png",
        "data": {"url": "/"},
    }


def main():
    """Timer entry point. Sends a nudge when the delivery gate allows."""
    if not os.path.exists(VAPID_PRIVATE_PATH):
        print(f"ERROR: VAPID private key not found at {VAPID_PRIVATE_PATH}")
        print("Run: python init_vapid.py")
        sys.exit(1)

    vapid_private_key = VAPID_PRIVATE_PATH  # path string, see module docstring

    # Same idempotent migration the app runs at startup — this process may be
    # the first to touch the DB after a deploy (0.1.3/A: never rely on the
    # other process having started first).
    ensure_settings()

    settings = get_settings()
    now = datetime.now(timezone.utc)
    local_date, local_hhmm = delivery_window(settings, now)
    if not select_push(settings, now):
        if not is_delivery_time(settings, now):
            print(f"Before delivery: local time {local_hhmm}, scheduled {settings['push_time']}.")
        else:
            print(f"Already delivered today — dedupe (local_date={local_date}).")
        print("Done. Sent: 0, Removed dead: 0, Failed (kept): 0")
        return

    koans = load_koans()
    payload = build_payload(koans[daily_index(len(koans), now.date().isoformat())]["koan_text"])
    subscriptions = get_subscriptions()
    print(f"Sending to {len(subscriptions)} subscription(s)...")
    print(f"Daily notification trigger for {local_date} ({settings['push_timezone']}).")

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
    # 0.1.8: date is the LOCAL delivery date in push_timezone (one push per
    # local day — the hourly ticks after the first delivery all dedupe here).
    mark_pushed(date=local_date)

    print(f"Done. Sent: {sent}, Removed dead: {dead}, Failed (kept): {failed}")


if __name__ == "__main__":
    main()
