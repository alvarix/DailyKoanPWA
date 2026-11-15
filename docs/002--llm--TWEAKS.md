# Daily Koan PWA — Tweaks Spec (Doc 002)

Version: 002 — llm
Status: PARTIALLY EXECUTED — Tweaks 2 & 3 shipped in 0.1.5. Tweak 1 (held-koan mode) remains to be implemented.

## Implementation Status

| Tweak | Status | Note |
| 1 | pending | Held-koan mode + daily/held toggle; needs fresh session |
| 2 | done (0.1.5) | `push_sender.py` now sends body-only payload with UTF-8 byte-safe truncate |
| 3 | done (0.1.5) | `templates/index.html` and `mockup.html` updated: all commentary + verse collapsed by default |

## Known Warnings / Next-Pass Items

These are pre-existing or architectural items surfaced by diagnostics, not blockers for Tweaks 2 & 3. Resolve when Tweak 1 is implemented or in a dedicated cleanup pass:

- CDN script tags lack `integrity` subresource-integrity attributes (`templates/index.html`, `mockup.html`). Per frontend ADR this is accepted under the zero-build CDN strategy, but add hashes if offline-first hardening becomes a goal.
- `alert()` calls in template JS may be replaced with an in-page notification element for a calmer UX.
- Console logging in `templates/index.html` SW registration and error blocks may be removed or gated in a future cleanup.


Peer-reviewed (plan-review): `google/gemini-2.5-pro` + `openai/gpt-5`, both responded 2026-11-16. Findings folded in below; see Peer Review section.

---

## Scope — Three Tweaks

| # | Tweak | One-line summary |
| 1 | Held-koan mode | Same koan served to everyone until someone taps "Next Koan" on the site; a switch restores the current daily-rotation behavior |
| 2 | Bare alert | Push notification carries no text other than the koan body itself |
| 3 | Hidden by default | Commentary and verse both collapsed when the page opens |

---

## Current State (verified 2026-11-16, not assumed)

| Piece | Today | File |
| Koan selection | `get_todays_koan()` = `sha256(UTC-date) % 14` — deterministic, GLOBAL (all visitors see the same koan), stateless | `app.py` |
| Next Koan button | Plain `<a href="/koan/(idx+1) % 14">` — per-visitor navigation, nothing persists server-side | `templates/index.html` |
| Commentary 1 | `<details open>` — **expanded** by default | `templates/index.html` |
| Commentary 2 | `<details>` — collapsed | `templates/index.html` |
| Verse | No `<details>` at all — always visible | `templates/index.html` |
| Push payload | `title = "Daily Koan: <koan title>"`, `body = truncated koan text (120 chars)` | `push_sender.py` |
| Push trigger | `dailykoan-push.timer` 08:00 UTC → `push_sender.py` reads DB, sends to all | systemd |
| DB | `subscriptions.db`, single table `subscriptions(endpoint, p256dh, auth)` | `init_db.py` |
| Service worker | `push` handler: `data.title \|\| 'Daily Koan'`, `data.body \|\| 'A new koan awaits.'` — missing fields fall back to app name | `static/sw.js` |
| Deployment | dkStandalone, gunicorn `--workers 1`, one real subscriber (Alvar's phone) | 001.2 |

Everything below is designed for THIS deployment: one worker, one real subscriber, personal app, no auth. Where a reviewer finding matters only at scale (N >> 1), it is noted as such, not over-engineered.

---

## Tweak 1 — Held-Koan Mode + Toggle

### Intended behavior

- **Held mode (new default?):** `/` and `/api/todays` serve koan `current_index` — a GLOBAL pointer stored server-side. It does not move on its own. It advances ONLY when a visitor taps "Next Koan" on the site.
- **Daily mode (today's behavior):** deterministic per-date rotation, `sha256(date) % 14`.
- **The switch:** a control on the page toggles the mode. Mode + pointer persist server-side; every visitor/device sees the same thing (no accounts — this is global by design).

### Approach

**Storage — new `settings` table, additive migration:**

```sql
CREATE TABLE IF NOT EXISTS settings (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
```

Rows: `mode` (`'held'` \| `'daily'`), `current_index` (`'0'..`), `last_push_date` (`'YYYY-MM-DD'`), `last_push_index`.

Migration function in `app.py` (and imported by `push_sender.py` — same code path, no drift):

- `PRAGMA user_version` bump; inside one transaction: `CREATE TABLE IF NOT EXISTS` + `INSERT OR IGNORE` defaults (`mode='daily'`, `current_index` seeded from today's deterministic index — explicit default, no undefined state).
- Idempotent (`INSERT OR IGNORE`) so the one gunicorn worker and any push_sender run can both execute it safely. At `--workers 1` the multi-worker startup race is theoretical, but idempotent init costs nothing and removes the class of bug.
- `PRAGMA journal_mode=WAL` + `busy_timeout` in the connection helper — cheap insurance now that two processes (app, push_sender) share the file.

**Routes:**

- `GET /` — serve `current_index`'s koan in held mode, deterministic-daily in daily mode. Template context gains `mode` and `current_index` (the frontend needs it — see Frontend below).
- `POST /api/next` — advance `current_index`. **Atomic SQL, not read-modify-write:** `UPDATE settings SET value = CAST(value AS INTEGER) + 1 WHERE key='current_index'` (single statement = atomic under SQLite's write lock; kills the concurrent-tap race both reviewers flagged). Validate bounds (`% 14`). Returns the new index. **409 in daily mode** — the endpoint only means something in held mode.
- `POST /api/mode` — explicit set (`{"mode": "held"}` or `{"mode": "daily"}`), NOT a toggle — idempotent, no double-flip races. Same-origin check (`Origin`/`Referer` host match) — trivial CSRF guard; there is no auth to lean on (flagged: any visitor can flip mode or advance the pointer; acceptable for a personal PWA, noted as a known property, not a bug).

**Push — ONE mechanism, the timer. No push from request handlers.**

Both reviewers flagged push-broadcast-inside-`POST /api/next` as the worst idea in the draft: it blocks the worker for the whole broadcast, partial-fails on client disconnect, and does not scale. Instead `push_sender.py` becomes the single push brain, reading `settings` at run time:

- `mode='daily'` → current behavior: push today's deterministic koan; dedupe on `last_push_date == today` (protects against `Persistent=true` catch-up double-runs).
- `mode='held'` → push `current_index`'s koan only if `last_push_index != current_index` (someone advanced it since the last push); otherwise exit quietly ("nothing new, 0 sent").
- The timer keeps running in both modes; no operator action ever needed to switch behavior. Mode flip mid-day is safe because every decision is made fresh at run time from the table.

**Known trade-off (flagged, needs Alvar's call):** in held mode, a "Next Koan" tap at 14:00 does not push until the next 08:00 timer run. For a personal app whose only subscriber is the person who just tapped Next (and is staring at the new koan), that is arguably correct behavior, not a deficiency. If immediate broadcast ever matters, the escape hatch is a systemd path/`systemd-run` detached trigger — do NOT put pywebpush in the Flask handler. Default recommendation: live with timer-latency; revisit only if a second subscriber appears.

**Frontend (`templates/index.html`, Alpine):**

- Server passes `mode`; render the correct control per mode:
  - daily → keep the existing per-visitor `<a>` link (current behavior, unchanged)
  - held → button posting `/api/next`, then **reload/update state** (reviewer catch: without this the tap advances the server but the screen still shows the old koan)
- Mode switch control likewise posts `/api/mode` then reloads.
- Debounce/throttle rapid taps client-side; server-side the atomic UPDATE plus idempotent UI refresh handles it anyway.

### Issues / risks (Tweak 1)

| Issue | Severity | Handling |
| Concurrent /api/next taps race | HIGH (at scale) | Atomic single-statement UPDATE; moot at N=1 but correct anyway |
| Push inside request handler | HIGH (at scale) | Rejected — timer is the only push mechanism |
| Migration race / undefined defaults | MEDIUM | Idempotent transactional init + explicit seeded defaults + `user_version` |
| Unauthenticated mode-flip / index-advance by any visitor | ACCEPTED (personal app) | Same-origin check added; documented property |
| `/koan/<idx>` deep links bypass held mode | LOW | Advisory only — deep links keep working; documented, not enforced |
| Worker restarts lose nothing | - | State lives in SQLite, not memory (the 001.2 key-drift lesson applied early this time) |
| `subscriptions.db` written by two processes | LOW | WAL + busy_timeout; N=1 traffic |
| Koan list grows/reorders → stored index stale | LOW | Bounds-check on read; koans.json is static at 14 for now |

---

## Tweak 2 — Bare Alert (koan body only)

### Intended behavior

The notification shows the koan's own text — not "Daily Koan: <title>" plus a preview. Just the teaching.

### Approach

- `push_sender.py` payload: omit `title` (or set `''`), `body` = full koan text with a **byte-safe truncate** (~3000 bytes, not 120 chars — reviewer catch: encryption overhead makes the practical limit ~3-3.5KB, and today's 120-char cut would mangle the whole point of the tweak).
- `static/sw.js` already falls back `data.title || 'Daily Koan'` → the OS shows the app name as the small title line.

### Issues / the honest limit (flagged, both reviewers)

**A completely text-less title is not achievable on iOS.** A push notification renders *some* title line; if the payload omits it, the app name ("Daily Koan") appears there. Best achievable: title line = app name (small, system-styled), body = the koan itself. If Alvar wants zero visible text beyond the koan, that is an OS constraint, not an implementation choice — the doc says so now rather than the fresh session discovering it.

Cross-platform test items (reviewer: not just iOS): Chrome desktop/Android with empty title may render origin URL or "Untitled" — verify before shipping; the SW's `'A new koan awaits.'` body-fallback stays for malformed payloads.

---

## Tweak 3 — Commentary and Verse Hidden by Default

### Current vs desired

| Element | Today | After |
| Commentary 1 | `<details open>` (expanded) | `<details>` (collapsed) |
| Commentary 2 | `<details>` (collapsed) | unchanged |
| Verse | not collapsible, always visible | wrapped in collapsed `<details>` with a proper `<summary>` ("Verse by …") matching commentary styling |

### Approach

Template-only change — no backend, no DB, no push impact:

1. Remove `open` from commentary 1's `<details>`.
2. Wrap the verse block in `<details class="group">` + `<summary>` mirroring the commentary summary markup (caret rotation classes already used).

### Issues (flagged)

- **This is a product change, not just plumbing** (reviewer catch): verse goes from always-visible to click-to-see. That IS the request ("commentary and verse hidden by default"), but the doc records the delta so it is a decision, not an accident.
- `<details>`/`<summary>` are keyboard- and screen-reader-accessible natively; keep the `cursor-pointer list-none` pattern already in use.
- Alpine state does not need to know — native `<details>` needs none.

---

## Suggested Implementation Order (fresh session)

1. **Tweak 3 first** — template-only, zero risk, immediate visual result to live with.
2. **Tweak 2 second** — push_sender payload + truncate guard; test on the phone (and one desktop Chrome if handy).
3. **Tweak 3 last** — no, **Tweak 1 last** — settings table + migration + routes + push_sender mode logic + frontend. Biggest surface; benefits from the review cycle of its own session.
4. Each tweak = its own commit; deploy per 001.2 §9.2 (`sudo -u koan git pull && sudo systemctl restart dailykoan`); migration runs itself at startup.

## Open Decisions for Alvar (answer in the fresh session)

1. Which mode is the default after this ships — start in `held` or keep `daily` until toggled?
2. Timer-latency on held-mode advance (next 08:00) — acceptable? (Recommended: yes, revisit if a second subscriber appears.)
3. Bare-alert title line = app name (the OS floor) — confirmed acceptable?
4. Verse hidden by default — confirmed (recorded above as deliberate product change)?

## For Dummies (Plain English)

Three changes. First, today the app picks the koan by the date — like a page-a-day calendar. The new mode is a bookmark instead: everyone sees the same page, and it only turns when you physically tap "Next Koan". A switch on the page flips back to calendar mode. Second, the phone alert currently says "Daily Koan: <title>" followed by a snippet. Afterward it just says the koan itself (the phone will always show the app's name in tiny letters above — phones insist). Third, the commentary and verse currently pop open on the page; after, everything starts folded, like the rest of the app's calm.

## Peer Review

| Item | Status |
| Reviewer models | `google/gemini-2.5-pro` + `openai/gpt-5` (2 of 2 responded, 2026-11-16) |
| Flagged - high | non-atomic index advance → atomic single-statement UPDATE; push broadcast inside request handler → rejected, timer stays the single mechanism; startup-migration race/undefined defaults → idempotent transactional init with seeded defaults + user_version |
| Flagged - medium | frontend unaware of mode → template context carries mode; dual push mechanisms → unified push_sender logic; daily-mode Next semantics → per-visitor link stays in daily, POST /api/next 409s; dedupe by index breaks (wrap/collisions) → dedupe by date (daily) and index (held); toggle endpoint races/CSRF → explicit set + same-origin check |
| Flagged - low | empty-title rendering varies per platform → test item list; UI refresh after /api/next → reload step included; payload byte limit → 3000-byte guard; verse collapsibility is a product change → recorded as such; stable koan IDs vs positional index → bounds check, revisit if koans.json grows; WAL/busy_timeout → adopted; SW cache coherence → network-first already, reload after advance |
| Over-engineering rejected | queues/background workers for N=1 subscriber; full CSRF token machinery (same-origin check is enough for a personal PWA); API versioning (`/api/v1/`) — three routes, no clients |
| Changes made | all HIGH/MEDIUM folded into Approach sections; LOW items recorded as test items or accepted properties |