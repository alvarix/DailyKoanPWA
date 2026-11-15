# ADR: Push Pipeline

Status: Accepted (timer mechanism, retention policy) / Proposed (held-mode logic — 002 spec)
Date: 2026-11-16
Related: docs/adr/data-model.md, docs/002--llm--TWEAKS.md, docs/001.2--llm--STANDALONE_DROPLET_DEPLOYMENT.md

## Context

Push is the product: a koan arrives on the phone without opening anything. The pipeline was built during the
2026-11-15 live deployment and fixed three times that night — every fix is a decision this ADR records.

## Decision

**One push mechanism: the systemd timer.** `dailykoan-push.timer` (OnCalendar 08:00:00 UTC, Persistent=true)
fires `dailykoan-push.service` (oneshot), which runs `push_sender.py` as `koan`. Nothing else sends pushes.

**No push from request handlers — ever.** The rejected alternative: broadcasting from inside
`POST /api/next` "so subscribers learn immediately". Both plan-reviewers flagged it, and it is right to
reject on architecture grounds, not scale: a request handler must return fast, but a broadcast is
unbounded latency (per-subscriber network calls) with partial-failure semantics the request cannot
express. The timer *is* the decoupling. Consequence: in held mode (proposed), a Next-koan tap at 14:00
pushes at next 08:00 — for a personal app whose only subscriber is the tapper, correct behavior (002
records this as an open decision, default accept).

**push_sender.py reads state at run time — no memory, no arguments.** Mode, current index, dedupe keys
all come from the `settings` table when the run starts (proposed; today it reads koans + subscriptions
fresh each run). Every run decides fresh: daily mode → deterministic koan, dedupe on `last_push_date`;
held mode → `current_index` when `last_push_index` differs, else exit quietly.

**Retention policy — the night's hardest lesson.** Only a confirmed 404/410 from the endpoint may delete
a subscription. The original code treated *any* send failure as dead-subscription and deleted the row:
a bytes-vs-str bug then produced `'bytes' object has no attribute 'encode'`, which deleted a valid iOS
subscription on its first real send. A 403 BadJwtToken (key drift) then deleted another. Two valid
subscriptions destroyed by one class of bug. Tri-state returns: `True` sent, `False` confirmed-gone
(only 404/410), `None` error (keep the row, log it).

**VAPID key handling — one pair per install.** `webpush()` receives the PEM *path string* (pywebpush
loads via `Vapid.from_file`), never raw bytes. The pair on disk is authoritative for signing;
`app.py` loads the *public* key once at gunicorn start into memory — therefore **any** key change
requires `systemctl restart dailykoan` plus re-subscribe of every device (drift = 403 BadJwtToken,
hit live). Rotation is an event, never casual. Claims: real contact (`mailto:alvarix@gmail.com`), not
a reserved `.example` TLD.

**Payload:** title + truncated body (120 chars) today; 002 (proposed) drops the title and keeps a
byte-safe body truncate (~3000 bytes post-encryption budget). The SW's fallbacks
(`data.title || 'Daily Koan'`) stay — empty title is expected to render the app name as the system
title line on iOS.

**Delivery verification:** the journal is the log (`Done. Sent: N, Removed dead: N, Failed (kept): N`);
nginx access log proves subscribe POSTs (gunicorn's journal does not log successful requests — another
live lesson). "Sent: 1 and no alert" means phone-side or stale-endpoint; "403" means key drift; the
matrix lives in 001.2's notes.

## Consequences

- Timer stays armed in every mode; behavior switches are data, not operations — no systemctl games on mode change.
- Push latency in held mode is up to ~24h (08:00 UTC boundary); accepted, revisit only if a second subscriber appears.
- Failure of a *send* is observable in the journal but never destructive to subscriptions; failure of *keys* is recoverable only by re-subscribe — which is why key handling is the most protected path in the codebase.
