# ADR: Data Model

Status: Accepted (subscriptions, retention) / Proposed (settings table — 002 spec, not executed)
Date: 2026-11-16
Related: docs/002--llm--TWEAKS.md, docs/adr/push-pipeline.md

## Context

Daily Koan stores all mutable state in a single SQLite file (`subscriptions.db`). Two processes write
to it: the Flask app (gunicorn, subscribe/unsubscribe) and `push_sender.py` (systemd timer, send runs).
The repo is public on GitHub; a keys-in-history incident (2026-11-15) proved what must never enter it.

## Decision

**Schema — subscriptions (accepted, live):**

```sql
CREATE TABLE subscriptions (
  endpoint TEXT PRIMARY KEY,
  p256dh   TEXT NOT NULL,
  auth     TEXT NOT NULL
);
```

- `endpoint` is the Web Push endpoint URL (Apple/Google/Mozilla) and the natural primary key.
- Subscribe is `INSERT OR REPLACE` — re-subscribing from the same device is an idempotent upsert.

**Schema — settings (proposed in 002, not yet executed):**

```sql
CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
```

Rows: `mode` (`held` | `daily`), `current_index`, `last_push_date`, `last_push_index`. Migration is
idempotent (`CREATE TABLE IF NOT EXISTS` + `INSERT OR IGNORE` defaults, `PRAGMA user_version`) so app
startup and push_sender runs can both execute it safely. `current_index` advances only via atomic
single-statement `UPDATE ... CAST(value AS INTEGER) + 1` — never read-modify-write.

**Retention policy (accepted after live incident):** only a confirmed 404/410 response from the push
endpoint may delete a subscription row. Transport errors, 403s, rate limits, and code bugs must not —
the 2026-11-15 incidents deleted two valid iOS subscriptions this way before the policy existed.

**Concurrency:** `PRAGMA journal_mode=WAL` + `busy_timeout` on every connection (two writers share the
file). Traffic is one real subscriber; WAL is cheap insurance, not scale engineering.

**Irreplaceable state:** the VAPID key pair (`vapid_private.pem`, `vapid_public.pem`) is *not* in the
database and must never be in git. Rotating it silently invalidates every subscription (403 BadJwtToken,
hit live). One pair per install; off-droplet backup mandatory (001.2 9.3).

**Koan selection (accepted):** `sha256(UTC-date) % len(koans)` — deterministic, global (all visitors see
the same koan), stateless. In held mode (proposed) selection becomes `settings.current_index`, and the
deterministic function seeds its initial value on mode switch.

## Consequences

- One file to back up (`subscriptions.db`) + two PEMs; no DB server to run.
- Schema growth is additive (new tables/columns) — no destructive migrations yet; `user_version` gates them.
- Positional koan indices (`koans.json` order) are load-bearing; bounds-check on read, revisit if the list grows.
- Public repo means generated keys are burned keys — regenerate, never commit (enforced by .gitignore).
