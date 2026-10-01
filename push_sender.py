#!/usr/bin/env python3
"""
Standalone push sender script.

Intended to be run daily by cron or systemd timer.
Loads today's koan and sends it to all active subscriptions via Web Push.
"""

import os
import sys
import json
import sqlite3
from datetime import datetime
from pywebpush import webpush, WebPushException

# Must match DB path in app.py
DB_PATH = os.path.join(os.path.dirname(__file__), 'subscriptions.db')
KOANS_PATH = os.path.join(os.path.dirname(__file__), 'koans.json')
VAPID_PRIVATE_PATH = os.path.join(os.path.dirname(__file__), 'vapid_private.pem')

# Domain must match the subscription endpoint domain
VAPID_CLAIMS = {
    'sub': 'mailto:admin@dailykoan.example'
}


def load_koans():
    with open(KOANS_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_todays_koan():
    """Return a deterministic koan based on today's date."""
    import hashlib
    koans = load_koans()
    today = datetime.utcnow().strftime('%Y-%m-%d')
    idx = int(hashlib.sha256(today.encode()).hexdigest(), 16) % len(koans)
    return koans[idx], idx, len(koans)


def get_subscriptions():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT endpoint, p256dh, auth FROM subscriptions')
    rows = cursor.fetchall()
    conn.close()
    return rows


def truncate(text, length=120):
    """Truncate text with ellipsis."""
    if len(text) <= length:
        return text
    return text[:length].rsplit(' ', 1)[0] + '...'


def send_push(subscription, payload, vapid_private_key):
    try:
        webpush(
            subscription_info={
                'endpoint': subscription[0],
                'keys': {
                    'p256dh': subscription[1],
                    'auth': subscription[2]
                }
            },
            data=json.dumps(payload),
            vapid_private_key=vapid_private_key,
            vapid_claims=VAPID_CLAIMS,
            ttl=86400  # 24 hours
        )
        return True
    except WebPushException as e:
        if e.response and e.response.status_code in (404, 410):
            # Subscription gone; will be cleaned up by caller
            return False
        print(f"Push error: {e}")
        return False
    except Exception as e:
        print(f"Unexpected push error: {e}")
        return False


def remove_subscription(endpoint):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM subscriptions WHERE endpoint = ?', (endpoint,))
    conn.commit()
    conn.close()
    print(f"Removed dead subscription: {endpoint[:60]}...")


def main():
    if not os.path.exists(VAPID_PRIVATE_PATH):
        print(f"ERROR: VAPID private key not found at {VAPID_PRIVATE_PATH}")
        print("Run: python init_vapid.py")
        sys.exit(1)

    with open(VAPID_PRIVATE_PATH, 'rb') as f:
        vapid_private_key = f.read()

    koan, idx, total = get_todays_koan()
    title = f"Daily Koan: {koan['title']}"
    body = truncate(koan['koan_text'])
    url = os.environ.get('BASE_URL', 'https://your-domain.com/')
    koan_url = f"{url}koan/{idx}"

    payload = {
        'title': title,
        'body': body,
        'icon': '/static/icon-192.png',
        'badge': '/static/badge-72.png',
        'data': {
            'url': koan_url
        }
    }

    subscriptions = get_subscriptions()
    print(f"Sending to {len(subscriptions)} subscription(s)...")
    print(f"Today's koan: {koan['title']}")

    sent = 0
    dead = 0
    for sub in subscriptions:
        ok = send_push(sub, payload, vapid_private_key)
        if ok:
            sent += 1
        else:
            dead += 1
            remove_subscription(sub[0])

    print(f"Done. Sent: {sent}, Removed dead: {dead}")


if __name__ == '__main__':
    main()
