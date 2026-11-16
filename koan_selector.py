"""
Shared koan-selection and settings state for Daily Koan.

Both the Flask app (gunicorn, long-lived) and push_sender.py (systemd timer,
once a day) import this module, so there is exactly ONE code path that decides
which koan is current — the "same koan for everyone" logic from doc 002 is
componentized here instead of being duplicated (see docs/003--llm--KOAN_
PROGRESSION.md, section "Componentizing the same-koan logic").

Design rules (from the data-model ADR and doc 002 peer review):
  - daily mode is STATELESS: index = sha256(UTC date) % len(koans), computed
    fresh on every call; `current_index` is only meaningful in held mode.
  - writes that combine a read and a write (advance) serialize with
    BEGIN IMMEDIATE, not "WAL + hope".
  - every connection sets WAL + busy_timeout (two processes share the file).
  - migration is idempotent so app startup and push runs can both execute it.
  - all dates are UTC YYYY-MM-DD; never a local date.
"""

import hashlib
import json
import os
import random
import sqlite3
import time

DB_PATH = os.path.join(os.path.dirname(__file__), "subscriptions.db")
KOANS_PATH = os.path.join(os.path.dirname(__file__), "koans.json")

# Settings table schema version; bump when the settings rows change shape.
SETTINGS_VERSION = 1

# Phase-1 progression: canonical text order (doc 003). Anything unlisted ranks
# last, sorted by its own `order` field, then title.
GROUP_RANK = {
    "Mumonkan": 0,
    "Blue Cliff Record": 1,
    "Book of Serenity": 2,
}

# Keys allowed through POST /api/settings, with validators.
VALID_MODES = ("held", "daily")
VALID_PROGRESSIONS = ("ordered", "random")


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
    """Create/upgrade the settings table. Idempotent and additive-only.

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
                ("mode", "held"),
                ("current_index", seed),
                ("progression", "ordered"),
                ("push_time", "08:00"),
                ("last_push_date", ""),
                ("last_push_index", ""),
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
                "PRAGMA user_version = 1"
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
    every machine, in both app and push processes (002 review: no drift
    between the koan the push announces and the koan the site serves).

    Args:
        total: number of koans in progression order.
        date: UTC date string (YYYY-MM-DD) for tests; defaults to today.
    """
    if total <= 0:
        raise ValueError("total must be positive")
    d = date or time.strftime("%Y-%m-%d", time.gmtime())
    return int(hashlib.sha256(d.encode()).hexdigest(), 16) % total


def current_index(settings, total, date=None):
    """The koan index everyone should be shown right now.

    daily mode: computed fresh from the date (never reads current_index).
    held mode: the stored pointer, clamped with modulo so a shrunk/reordered
    koans.json can never produce an out-of-range index.
    """
    if settings.get("mode") == "daily":
        return daily_index(total, date)
    try:
        pointer = int(settings.get("current_index") or 0)
    except (TypeError, ValueError):
        pointer = 0
    return pointer % total


def advance(db_path=None, total=None, rng=None):
    """Advance the global held-mode pointer; returns the new index.

    Serialized with BEGIN IMMEDIATE so two concurrent taps cannot read the
    same old value and both write the same "next" (the 002 review's lost-tap
    race). In random progression the pointer jumps to a random *other* koan;
    in ordered progression it takes the next step modulo total, so the
    sequence wraps instead of running off the end.

    Returns:
        int: the new current_index.
    """
    rng = rng or random
    if total is None:
        total = len(load_koans())
    conn = connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        settings = {
            row["key"]: row["value"]
            for row in conn.execute("SELECT key, value FROM settings")
        }
        cur = current_index(settings, total)
        if settings.get("progression") == "random":
            others = [i for i in range(total) if i != cur]
            nxt = rng.choice(others) if others else cur
        else:
            nxt = (cur + 1) % total
        conn.execute(
            "UPDATE settings SET value = ? WHERE key = 'current_index'",
            (str(nxt),),
        )
        conn.commit()
        return nxt
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def set_values(db_path=None, **values):
    """Persist one or more settings values in a single transaction.

    Mode switches clear BOTH dedupe keys (last_push_date, last_push_index):
    a switch is a semantic change of "what is current", so the next timer run
    pushes once in the new mode instead of being silenced by a stale dedupe
    key from the old one (002 review: define mode-switch transitions).
    """
    conn = connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        for key, value in values.items():
            if key not in ("mode", "progression", "push_time"):
                raise ValueError(f"cannot write setting: {key}")
            conn.execute(
                "UPDATE settings SET value = ? WHERE key = ?", (str(value), key)
            )
        if "mode" in values:
            conn.execute("UPDATE settings SET value = '' WHERE key = 'last_push_date'")
            conn.execute("UPDATE settings SET value = '' WHERE key = 'last_push_index'")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def mark_pushed(db_path=None, index=None, date=None):
    """Record that a push just went out for `index` on UTC `date`.

    Called by push_sender AFTER the send loop, in its own transaction, so a
    crash mid-broadcast leaves the dedupe keys untouched (a rerun may
    double-push, which is recoverable; a silent skip is not observable).
    """
    date = date or time.strftime("%Y-%m-%d", time.gmtime())
    conn = connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        if date is not None:
            conn.execute(
                "UPDATE settings SET value = ? WHERE key = 'last_push_date'",
                (date,),
            )
        if index is not None:
            conn.execute(
                "UPDATE settings SET value = ? WHERE key = 'last_push_index'",
                (str(index),),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def select_push(koans, settings, date=None):
    """Decide which koan (if any) a timer run should push.

    Returns:
        tuple[int, dict] | None: (index, koan) to push, or None when the
        dedupe keys say nothing new has happened since the last push.

    Dedupe rules (push-pipeline ADR):
        daily mode: skip if last_push_date == today (Persistent=true may
            double-run the timer; the date key absorbs it).
        held mode:  skip if last_push_index == the current pointer (nothing
            has advanced since the last push).
    """
    total = len(koans)
    mode = settings.get("mode")
    today = date or time.strftime("%Y-%m-%d", time.gmtime())
    idx = current_index(settings, total, today)
    if mode == "daily":
        if settings.get("last_push_date") == today:
            return None
    elif settings.get("last_push_index") == str(idx):
        return None
    return idx, koans[idx]
