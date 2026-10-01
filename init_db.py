#!/usr/bin/env python3
"""Initialize the SQLite database for push subscriptions."""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'subscriptions.db')


def init_db():
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
    print(f"Database initialized at {DB_PATH}")


if __name__ == '__main__':
    init_db()
