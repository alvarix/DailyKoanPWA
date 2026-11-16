# ADR: Data Model

Status: Accepted (subscriptions, retention, settings table — executed 0.1.6)
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

**Schema — settings (accepted, live since 0.1.6):**

```sql
CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
```

Rows: `mode` (`held` | `daily`), `current_index`, `last_push_date`, `last_push_index`, `progression`,
`push_time`. Migration lives in `koan_selector.ensure_settings` — idempotent (`CREATE TABLE IF NOT EXISTS`
+ `INSERT OR IGNORE` defaults) so app startup and push_sender runs can both execute it safely; both
processes import the same module, so no drift. `current_index` advances only via `advance()` —
`BEGIN IMMEDIATE` + single-statement `UPDATE ... CAST(value AS INTEGER) + 1`, never read-modify-write.
Mode switches clear the dedupe keys so the new mode pushes fresh.

**Retention policy (accepted after live incident):** only a confirmed 404/410 response from the push
endpoint may delete a subscription row. Transport errors, 403s, rate limits, and code bugs must not —
the 2026-11-15 incidents deleted two valid iOS subscriptions this way before the policy existed.

**Concurrency:** `PRAGMA journal_mode=WAL` + `busy_timeout` on every connection (two writers share the
file). Traffic is one real subscriber; WAL is cheap insurance, not scale engineering.

**Irreplaceable state:** the VAPID key pair (`vapid_private.pem`, `vapid_public.pem`) is *not* in the
database and must never be in git. Rotating it silently invalidates every subscription (403 BadJwtToken,
hit live). One pair per install; off-droplet backup mandatory (001.2 9.3).

**Koan selection (accepted):** `sha256(UTC-date) % len(koans)` — deterministic, global (all visitors see
the same koan), stateless; this is Daily mode. In held mode selection is `settings.current_index`.
Selection lives in `koan_selector.py`, shared by both processes — the same-koan property is one
deterministic function, defined once. `koans.json` carries `group`/`order`/`id` metadata; sort is by
`(text rank, case order)`, so the file's physical order is not load-bearing.

## Consequences

- One file to back up (`subscriptions.db`) + two PEMs; no DB server to run.
- Schema growth is additive (new tables/columns) — no destructive migrations yet; `ensure_settings` seeds missing rows so new settings keys ship without a manual step.
- Koan identity is `group`/`order`/`id` metadata, not file position; stored `current_index` is bounds-clamped by modulo on read, so a corpus that grows or reorders degrades gracefully (reseed on fill-out deploys is a UX nicety — docs/003 §4.4).
- Public repo means generated keys are burned keys — regenerate, never commit (enforced by .gitignore).
