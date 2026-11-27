"""Best-effort, short-lived Web Push evidence without subscription credentials."""

import hashlib
import re
import secrets
from contextlib import closing

from koan_selector import connect

TOKEN = re.compile(r"[a-f0-9]{48}")


def trace_id(token):
    """Hash the receipt capability; only the digest is stored or reported."""
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def begin(subscription_id):
    """Record an attempt before sending so even a fast worker can report."""
    token = secrets.token_hex(24)
    with closing(connect()) as db, db:
        db.execute("""CREATE TABLE IF NOT EXISTS push_trace (
            id TEXT PRIMARY KEY, subscription_id INTEGER NOT NULL,
            attempted_at INTEGER NOT NULL, outcome TEXT NOT NULL DEFAULT 'pending',
            received_at INTEGER, display_requested_at INTEGER, display_failed_at INTEGER
        )""")
        db.execute(
            "DELETE FROM push_trace WHERE attempted_at < CAST(strftime('%s','now') AS INTEGER) - 604800"
        )
        db.execute(
            "INSERT INTO push_trace (id, subscription_id, attempted_at) VALUES (?, ?, CAST(strftime('%s','now') AS INTEGER))",
            (trace_id(token), subscription_id),
        )
    return token


def finish(token, result):
    """Record the transport outcome without overwriting worker evidence."""
    outcome = "accepted" if result is True else "gone" if result is False else "failed"
    with closing(connect()) as db, db:
        db.execute(
            "UPDATE push_trace SET outcome = ? WHERE id = ?", (outcome, trace_id(token))
        )


def receipt(token, stage):
    """Accept an idempotent worker receipt only for a recent known capability."""
    if not isinstance(token, str) or not TOKEN.fullmatch(token):
        return False
    if stage not in ("received", "display_requested", "display_failed"):
        return False
    with closing(connect()) as db, db:
        if (
            db.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'push_trace'"
            ).fetchone()
            is None
        ):
            return False
        cursor = db.execute(
            """UPDATE push_trace SET
            received_at = COALESCE(received_at, CAST(strftime('%s','now') AS INTEGER)),
            display_requested_at = CASE WHEN ? = 'display_requested'
                THEN COALESCE(display_requested_at, CAST(strftime('%s','now') AS INTEGER)) ELSE display_requested_at END,
            display_failed_at = CASE WHEN ? = 'display_failed'
                THEN COALESCE(display_failed_at, CAST(strftime('%s','now') AS INTEGER)) ELSE display_failed_at END
            WHERE id = ? AND attempted_at >= CAST(strftime('%s','now') AS INTEGER) - 604800""",
            (stage, stage, trace_id(token)),
        )
        return cursor.rowcount == 1
