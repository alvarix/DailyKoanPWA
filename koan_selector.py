"""Corpus ordering, legacy bookmark migration, and push delivery settings."""

import hashlib
import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

DB_PATH = os.path.join(os.path.dirname(__file__), "subscriptions.db")
KOANS_PATH = os.path.join(os.path.dirname(__file__), "koans.json")

# Settings table schema version; bump when the settings rows change shape.
# 2 (0.1.8): added push_timezone — delivery time became data (docs/002).
SETTINGS_VERSION = 3

# Phase-1 progression: canonical text order (doc 003). Anything unlisted ranks
# last, sorted by its own `order` field, then title.
GROUP_RANK = {
    "Mumonkan": 0,
    "Blue Cliff Record": 1,
    "Book of Serenity": 2,
}

def load_koans():
    """Load koans.json and return it in progression order.

    Sort key is (text rank, `order` within the text, title). The FILE order is
    deliberately NOT load-bearing — after a reorder or reformat, selection still
    follows the explicit `group`/`order` metadata (002 peer review: "the
    application logic must not depend on the file order").

    Raises:
        RuntimeError: koans.json is missing or corrupt (fail loudly, never
            serve an empty koan).
    """
    try:
        with open(KOANS_PATH, encoding="utf-8") as f:
            koans = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise RuntimeError(f"Failed to load koans: {e}") from e
    return sorted(
        koans,
        key=lambda k: (
            GROUP_RANK.get(k.get("group", ""), 99),
            k.get("order", 9999),
            k.get("title", ""),
        ),
    )


def connect(db_path=None):
    """Open the SQLite DB with the per-connection PRAGMAs both processes need.

    WAL + busy_timeout are connection settings; setting them only in a
    migration helper would leave other connections without them (002 review).
    WAL requires a local filesystem (true on the droplet and in dev).
    """
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def ensure_settings(db_path=None, total_koans=None, today=None):
    """Create/upgrade the settings table. Idempotent and transactional.

    Safe to run from any process (app startup, every push run). Defaults are
    explicit — no undefined state. `current_index` seeds from today's
    deterministic daily index so a brand-new install starts somewhere sane.

    Args:
        db_path: optional override (tests).
        total_koans: total koan count used for the seed; loaded if omitted.
        today: optional UTC date override for the seed (tests).
    """
    conn = connect(db_path)
    try:
        # CREATE TABLE IF NOT EXISTS + INSERT OR IGNORE inside one transaction;
        # BEGIN IMMEDIATE takes the write lock first so concurrent starts
        # (gunicorn import + 08:00 push run) cannot interleave.
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS settings ("
            "  key TEXT PRIMARY KEY,"
            "  value TEXT NOT NULL"
            ")"
        )
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version < SETTINGS_VERSION:
            if total_koans is None:
                total_koans = len(load_koans())
            seed = str(daily_index(total_koans, today))
            defaults = [
                ("current_index", seed),
                ("push_time", "08:00"),
                ("push_timezone", "America/New_York"),
                ("last_push_date", ""),
            ]
            for key, value in defaults:
                # One parameterized INSERT per row (not executemany): every
                # SQL statement in this file stays a literal with bound
                # parameters — no dynamic SQL anywhere.
                conn.execute(
                    "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                    (key, value),
                )
            conn.execute(
                "DELETE FROM settings WHERE key IN ('mode', 'progression', 'last_push_index')"
            )
            conn.execute(
                "PRAGMA user_version = 3"
                # keep this literal in sync with SETTINGS_VERSION; PRAGMA
                # values cannot be bound parameters (sqlite rejects "?").
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_settings(db_path=None):
    """Return the settings table as a plain dict."""
    conn = connect(db_path)
    try:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        return {row["key"]: row["value"] for row in rows}
    finally:
        conn.close()


def daily_index(total, date=None):
    """Deterministic global daily index: sha256(UTC date) % total.

    Stateless by design — the same UTC day always yields the same index on
    every machine.

    Args:
        total: number of koans in progression order.
        date: UTC date string (YYYY-MM-DD) for tests; defaults to today.
    """
    if total <= 0:
        raise ValueError("total must be positive")
    d = date or time.strftime("%Y-%m-%d", time.gmtime())
    return int(hashlib.sha256(d.encode()).hexdigest(), 16) % total


# --- Delivery gating (0.1.8): cadence is data; the timer just ticks hourly ---


def resolve_now(now=None, tz_name=None):
    """Resolve the wall clock for delivery gating.

    Args:
        now: optional aware datetime to inject (tests); defaults to UTC now.
        tz_name: IANA zone name; falls back to UTC when missing or invalid
            (a garbage push_timezone row must never crash the send loop).

    Returns:
        tuple[datetime, ZoneInfo]: (the moment, the delivery zone).
    """
    if now is None:
        now = datetime.now(timezone.utc)
    if tz_name is None:
        tz_name = "UTC"
    try:
        tz = ZoneInfo(str(tz_name))
    except Exception:
        tz = timezone.utc
    return now, tz


def delivery_window(settings, now=None, tz_name=None):
    """The run's local moment in the delivery zone.

    Args:
        settings: the settings dict (push_timezone is read here).
        now: optional aware datetime to inject (tests).
        tz_name: explicit zone override (tests); settings wins when absent.

    Returns:
        tuple[str, str]: (local YYYY-MM-DD, local HH:MM) — floored to the
        minute; the hourly timer makes second-level noise meaningless.
    """
    zone = tz_name or settings.get("push_timezone") or "UTC"
    now, tz = resolve_now(now, zone)
    local = now.astimezone(tz)
    return local.strftime("%Y-%m-%d"), local.strftime("%H:%M")


def is_delivery_time(settings, now=None, tz_name=None):
    """True once the local wall clock has reached push_time today.

    push_time garbage (anything not ``HH:MM`` ints) falls back to 08:00 —
    the API validates the format, so this only guards a hand-edited row.
    """
    _date, local_hhmm = delivery_window(settings, now, tz_name)
    try:
        hh, mm = (
            int(p) for p in str(settings.get("push_time", "08:00")).split(":")[:2]
        )
        if not (0 <= hh <= 23 and 0 <= mm <= 59):
            hh, mm = 8, 0
    except ValueError:
        hh, mm = 8, 0
    lh, lm = (int(p) for p in local_hhmm.split(":"))
    return lh * 60 + lm >= hh * 60 + mm


def set_values(db_path=None, **values):
    """Persist only delivery settings in a single transaction."""
    conn = connect(db_path)
    try:
        with conn:
            for key, value in values.items():
                if key not in ("push_time", "push_timezone"):
                    raise ValueError(f"cannot write setting: {key}")
                conn.execute(
                    "UPDATE settings SET value = ? WHERE key = ?", (str(value), key)
                )
    finally:
        conn.close()


def mark_pushed(db_path=None, date=None):
    """Record the local delivery date after the sender completes its loop."""
    if date is None:
        date, _ = delivery_window(get_settings(db_path))
    conn = connect(db_path)
    try:
        with conn:
            conn.execute(
                "UPDATE settings SET value = ? WHERE key = 'last_push_date'", (date,)
            )
    finally:
        conn.close()


def valid_timezone(name):
    """True when `name` is a loadable IANA zone (settings validation).

    The API accepts any string here; this keeps garbage out of push_timezone,
    where it would otherwise silently shift delivery to UTC forever (the
    gate falls back, but the user's chosen local time would never apply).
    """
    try:
        ZoneInfo(str(name))
        return True
    except Exception:
        return False


def select_push(settings, now=None):
    """Return whether a nudge is due at the given moment, in the delivery zone."""
    if now is None:
        now = datetime.now(timezone.utc)
    local_date, _ = delivery_window(settings, now)
    return is_delivery_time(settings, now) and settings.get("last_push_date") != local_date
