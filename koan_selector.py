"""
Shared koan-selection and settings state for Daily Koan.

Both the Flask app (gunicorn, long-lived) and push_sender.py (systemd timer,
hourly) import this module, so there is exactly ONE code path that decides
which koan is current — the "same koan for everyone" logic from doc 002 is
componentized here instead of being duplicated (see docs/003--llm--KOAN_
PROGRESSION.md, section "Componentizing the same-koan logic").

Design rules (from the data-model ADR and doc 002 peer review):
  - daily mode is STATELESS: index = sha256(UTC date) % len(koans), computed
    fresh on every call; `current_index` is only meaningful in held mode.
  - 0.1.8: PUSH CADENCE IS DATA — both modes deliver once per push-day.
    Held mode re-announces the current koan every day until Next advances it
    (user decision 2026-11-19: "the same koan until I advance, every day");
    daily mode announces the date-hash koan as before. The delivery moment is
    settings push_time + push_timezone (auto-detected from the device), so
    the drawer controls delivery without any unit edit.
  - selection dates are UTC (the site's hash); delivery-gating dates are
    LOCAL in push_timezone — never mix the two.
  - writes that combine a read and a write (advance) serialize with
    BEGIN IMMEDIATE, not "WAL + hope".
  - every connection sets WAL + busy_timeout (two processes share the file).
  - migration is idempotent so app startup and push runs can both execute it.
"""

import hashlib
import json
import os
import random
import sqlite3
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

DB_PATH = os.path.join(os.path.dirname(__file__), "subscriptions.db")
KOANS_PATH = os.path.join(os.path.dirname(__file__), "koans.json")

# Settings table schema version; bump when the settings rows change shape.
# 2 (0.1.8): added push_timezone — delivery time became data (docs/002).
SETTINGS_VERSION = 2

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
                ("push_timezone", "America/New_York"),
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
                "PRAGMA user_version = 2"
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
            if key not in ("mode", "progression", "push_time", "push_timezone"):
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
    """Record that a push just went out.

    `date` is the LOCAL delivery date in push_timezone (0.1.8: the dedupe
    key is "one push per local day"); defaults to today there if omitted.
    `index` is the selection that was announced (held-mode bookkeeping).

    Called by push_sender AFTER the send loop, in its own transaction, so a
    crash mid-broadcast leaves the dedupe keys untouched (a rerun may
    double-push, which is recoverable; a silent skip is not observable).
    """
    if date is None:
        date, _hhmm = delivery_window(get_settings(db_path))
    else:
        _hhmm = None  # no clock read needed when the date is explicit
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


def select_push(koans, settings, date=None, now=None):
    """Decide which koan (if any) a timer run should push.

    0.1.8 cadence — BOTH modes deliver exactly once per local push-day
    (user decision 2026-11-19: "the same koan until I advance, every day"):
        daily mode: the UTC-date-hash koan (selection date stays UTC — the
            site and the push must agree on which koan is "today's").
        held mode:  the current global pointer, RE-ANNOUNCED every day until
            Next advances it. The pointer no longer suppresses the push.

    The hourly timer ticks; this gate decides. Returns None when:
        - before push_time in push_timezone (retry next hour), or
        - already delivered today (last_push_local_date == today).

    Args:
        koans: progression-ordered koan list.
        settings: the settings dict (mode, current_index, push_time,
            push_timezone, last_push_date).
        date: optional UTC selection-date override (tests; daily mode hash).
        now: optional aware datetime to inject (tests); the delivery gate
            reads the wall clock otherwise. Pure function of its inputs.
    """
    total = len(koans)
    today = date or time.strftime("%Y-%m-%d", time.gmtime())
    if not is_delivery_time(settings, now):
        return None
    local_date, _hhmm = delivery_window(settings, now)
    if str(settings.get("last_push_date", "")) == local_date:
        return None
    idx = current_index(settings, total, today)
    return idx, koans[idx]
