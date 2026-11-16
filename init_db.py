#!/usr/bin/env python3
"""Initialize the SQLite database for push subscriptions and settings.

Idempotent. The settings half of the schema is created by
koan_selector.ensure_settings — the same function app.py runs at startup and
push_sender.py runs before every send — so this script only owns the
subscriptions table.
"""

import os
import sqlite3

import koan_selector

DB_PATH = os.path.join(os.path.dirname(__file__), "subscriptions.db")


def init_db():
    """Create the subscriptions table and ensure the settings table exists."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            endpoint TEXT NOT NULL UNIQUE,
            p256dh TEXT NOT NULL,
            auth TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()
    print(f"Subscriptions table initialized at {DB_PATH}")

    # settings table + seeded defaults (idempotent; shared with app/push).
    koan_selector.ensure_settings()
    print("Settings table ensured (koan_selector.ensure_settings)")


if __name__ == "__main__":
    init_db()
