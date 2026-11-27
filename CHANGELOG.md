# Changelog

## [Unreleased]

- Add short-lived per-subscription push tracing and best-effort worker receipts without logging subscription secrets.

- Hold now saves a bookmark on each device. Next advances it in order; Random and deep links leave it alone. The server no longer accepts shared progression changes.
- Push notifications show the held koan’s text from the device (or today’s text in Daily mode). No custom title is set; tapping opens the app.
- Settings migration v3 preserves the old bookmark as a one-time seed and leaves delivery settings, dedupe dates, and subscriptions intact.

## [0.2.0] — Push title = koan title (002.2 follow-up)

### Changed
- `push_sender.py`: payload now carries `title: <koan title>` instead of omitting the title. The service worker fallback was the app name, producing a duplicate "Daily Koan" / "From Koan" line on iOS. The OS-level app header is still unavoidable; the second line now shows the koan title instead.
- `static/sw.js`: title fallback changed from `'Daily Koan'` to `''`. If a malformed payload arrives, the notification body still renders with an empty title instead of a duplicate app name.
- `push_sender.py`: refactored payload construction into `build_payload(idx, koan)` so the title/body shape is unit-testable without the full send loop.

### Fixed
- `truncate_utf8_bytes`: account for the ellipsis bytes so the returned text always fits within `max_bytes` (previously 3003 bytes for a 3000-byte limit).

### Added
- `tests/test_koan_selector.py`: `TestPushDecision` cases for payload title and byte-safe body truncation.

## [0.1.8] — Delivery as data: local-time cadence (missed-push follow-up)

### Changed
- **Push cadence is settings data, not timer config** (user decision 2026-11-19: "in held mode I should still receive the notification — the same koan until I advance, every day"): both modes deliver exactly once per **local** delivery day (`push_time` + new `push_timezone`, DST-correct via `zoneinfo`). Held mode re-announces the current koan every day until Next advances it — `last_push_index` no longer suppresses sends; `last_push_date` holds the *local* date.
- `push_sender.py`: every hourly run journals why it exits (before the delivery moment / already delivered today / completed send loop) — the missed push of Nov 18-19 was silent in held mode by design; now nothing exits without a reason on record.
- `templates/index.html`: drawer shows the delivery timezone; it auto-syncs from the device on load (`Intl.DateTimeFormat().resolvedOptions().timeZone` → `POST /api/settings`), and the "Use my device timezone" tap re-syncs on demand with a toast.

### Added
- `settings` row `push_timezone` (default `America/New_York`); `SETTINGS_VERSION = 2` — additive migration, existing DBs upgrade on next app start / push run (insert-or-ignore preserves operator values).
- `POST /api/settings` accepts `push_timezone` (must be a loadable IANA zone, `app.valid_timezone`); garbage zone falls back to UTC and garbage `push_time` to 08:00 at decision time.
- `koan_selector.py`: `resolve_now`, `delivery_window`, `is_delivery_time`, `valid_timezone`; `select_push` takes `now`/`date` injection params (pure core, tests are clock-free).
- `tests/test_koan_selector.py` + `tests/test_app.py`: **56 tests** — delivery gate open/close boundary, UTC→EST conversion, garbage fallbacks (time + zone), held re-announce, per-local-day dedupe in both modes, timezone API round-trip + 400s.

### Ops (droplet, Mode-1 — same window as the deploy)
- `dailykoan-push.timer` `OnCalendar=*-*-* 08:00:00` → `*-*-* *:00:00` (hourly tick; the settings gate decides which tick sends). `daemon-reload` + timer restart; see deployment runbook §7 and §9.2 — this unit edit is the last timer ops step: future cadence moves are drawer-only.

## [0.1.7] — Bell toggle redesign (user request 2026-11-17)

### Changed
- `templates/index.html`: notifications get a proper switch in the settings drawer (first section, `role="switch"` + `aria-checked`), and the floating bell gains an explicit ON badge dot — the gold bell alone was not a clear enough state signal. Both share the same `subscribed` state and toggle path.
- All `alert()` popups in the toggle path replaced by a brief in-page toast (`showToast`, bottom-center, ~2.6s): unsupported browser, permission blocked, error, and explicit "Notifications on/off" after every flip. 002 known-warnings item resolved.
- Bell `aria-label` is Alpine-bound and states the current position ("Notifications on — tap to turn off").
- Push-time drawer caption clarified: preferred delivery time (local) vs the actual server clock (ops step).

### Added
- `tests/test_app.py`: 4 template regression tests (switch present, badge + toast present, zero `alert('` call sites, no static aria-label) — 47 total.

## [0.1.6] — 002 Tweak 1: held-koan mode + settings drawer

### Added
- `koans.json`: per-koan `group` (text), `order` (case number), `id` (stable slug); `koans.json` file order is no longer load-bearing.
- `settings` table (key/value) in `subscriptions.db`: `mode` (`held` | `daily`), `current_index`, `last_push_date`, `last_push_index`, `progression` (`ordered` | `random`), `push_time`. Idempotent `ensure_settings` migration; `current_index` seeds from today's deterministic index on first run.
- `koan_selector.py`: shared koan-selection + settings module (both processes import it — no drift). `daily_index`, `current_index` (bounds-clamped), `advance` (atomic, `BEGIN IMMEDIATE`), `set_values`, `select_push` + `mark_pushed` (mode-aware dedupe).
- `POST /api/next`: atomic pointer advance; **409 in daily mode**.
- `POST /api/mode`: explicit `held`/`daily`; clears dedupe keys so the new mode pushes fresh.
- `GET/POST /api/settings`: `push_time` (validated `HH:MM`) and `progression`; `mode` readable here too.
- `GET /koan/<index>`: deep links — per-visitor views that never move the global pointer.
- Same-origin guard on state-changing routes (Origin/Referer host check) — trivial CSRF defense, no auth to lean on.
- `templates/index.html`: header (site name + attribution), settings drawer (mode, order, push time, night mode), Random Koan button, pre-paint theme bootstrap (`dk-theme` in localStorage; system default), Tailwind `darkMode: 'class'`.
- `tests/test_koan_selector.py` + `tests/test_app.py`: 43 tests total (migration idempotency, daily/held selection, atomic advance, mode-switch dedupe clearing, push dedupe both modes, route behavior, deep-link immutability, CSRF guard).

### Changed
- `push_sender.py`: decides from `settings` at run time — daily dedupes on `last_push_date`, held on `last_push_index`; quiet exit (with journal reason) when nothing is new.
- `init_db.py`: also runs `ensure_settings`.
- `static/sw.js`: `CACHE_NAME` bumped to `daily-koan-v2`.
- `pyproject.toml`: ruff target `py39` (venv runs 3.9.6); `datetime.UTC` → `time.strftime(time.gmtime())` for the same compatibility reason.

### Notes
- Migration is additive and automatic on next `git pull && systemctl restart dailykoan`; no manual DB step. Suggested `sqlite3 subscriptions.db ".backup subscriptions.db.bak"` before the deploy as routine care.
- `mockup.html` is stale relative to 0.1.6 (header, drawer, Random button, theme bootstrap); it remains the 0.1.5 design reference. Template is the source of truth.
- Analysis follow-up (gates/levels, corpus fill-out, componentization verdict): `docs/003--llm--KOAN_PROGRESSION.md`.
- File map — mermaid runtime + push-decision diagrams: `docs/000--diagram--llm.md`. 002 front matter gained a plain-English summary, hours-to-implement estimates, and a done/pending task tracker.
- Determinism componentization analysis (ability + status; companion to 003 §5): `docs/002--llm--deterministic-componentization.md`.

## [0.1.5] — Tweaks 2 & 3 (partial 002 execution)

### Changed
- `push_sender.py`: push notification payload now carries only the koan body, no title. The OS/app-name title line remains as a fallback handled by `static/sw.js`. Body truncated with a UTF-8 byte-safe guard (`~3000` bytes) instead of the previous 120-character cut.
- `templates/index.html`: commentary 1 and the verse now start collapsed by default, matching commentary 2. All three use native `<details>/<summary>` for accessibility.
- `mockup.html`: updated to reflect the new collapsed-by-default verse and commentary 1 so the UI can be previewed locally without starting the Flask server.

### Added
- `tests/test_push_sender.py`: unit tests for `truncate_utf8_bytes` covering short text, exact-limit text, long ASCII, multibyte boundary, and empty input cases.

### Notes
- Tweak 1 (held-koan mode + daily/held toggle, settings table, `/api/next`, `/api/mode`) remains specified in `docs/002--llm--TWEAKS.md` and is not implemented in this release.
- No database migrations or configuration changes are required for this release.

## [0.1.0] — Phase 1: Daily Koan PWA

### Added
- Flask backend with SQLite subscription storage
- Deterministic daily koan selection (SHA-256 hash of date)
- Web Push API subscription/unsubscription endpoints
- VAPID key generation (`init_vapid.py`)
- PWA manifest and service worker with offline support
- iOS Safari push notification compatibility (requires iOS 16.4+, Home Screen PWA)
- Standalone daily push sender script (`push_sender.py`)
- Systemd service and timer configuration for production deployment
- HTML mockup of the koan page for design review (`mockup.html`)
- Placeholder PWA icons generator (`init_icons.py`)
- Deployment guide (`docs/DEPLOYMENT.md`)

### Stack
- Backend: Python 3, Flask, gunicorn, pywebpush, SQLite
- Frontend: Tailwind CSS (CDN), Alpine.js (CDN), HTMX (CDN)
- Infrastructure: nginx, systemd, certbot, DigitalOcean droplet

## [0.1.1] — Deployment runbooks

### Added
- Standalone droplet deployment guide (docs/001.2--llm--STANDALONE_DROPLET_DEPLOYMENT.md): fresh, isolated DigitalOcean droplet with hardening gates, paired usr checklist (docs/001.3--usr--standalone-droplet-checklist.md)
- Forge migration guide (docs/001.11--llm--MIGRATE_TO_FORGE.md): later switch from standalone droplet to Forge-managed alfaForge, same body-only-fragment pattern as wmw, zero-downtime-ordered cutover with exact rollback commands, paired usr checklist (docs/001.12--usr--migrate-to-forge-checklist.md)
- Postmortem-derived safety gates applied throughout: nginx -t before every reload, reload-never-restart, client-site curl 200 baselines before and after
- Safe SQLite backup procedure (sqlite3 .backup) and off-droplet VAPID key backup guidance
- README deployment pointers updated to the versioned docs

### Changed
- docs/001--llm--status.md: Phase 2 section added (deployment paths planned)

## [0.1.2] — Provider-domain runbooks

### Changed
- Runbooks 001.2 / 001.3 / 001.11 / 001.12 now target `dailykoan.duckdns.org` — free DuckDNS subdomain (no custom domain owned at this time) — replacing `koan.alvarsirlin.dev`
- DNS phases rewritten for DuckDNS (web panel / update API; TTL short and fixed, so the migration cutover drops all TTL pre-lowering)
- Historical docs (001--, 001.1) keep `koan.alvarsirlin.dev` as a record of past plans

### Notes
- Let's Encrypt issues duckdns.org subdomains without issue; duckdns.org sits on the Public Suffix List, so each subdomain counts as its own registered domain for LE quotas

## [0.1.4] — Architecture decision records

### Added
- docs/adr/ — five ADRs + index recording the *why* behind the shipped system: deployment.md (isolated droplet over Forge, DuckDNS domain, hard gates), data-model.md (SQLite schema, 404/410-only retention, settings table proposal, VAPID-as-irreplaceable-state), filesystem.md (alvar/koan users, /opt/dailykoan layout, generated-state-vs-git rules, dubious-ownership pulls), frontend.md (zero-build CDN stack, server-rendered + Alpine islands, details/summary, SW strategy), push-pipeline.md (timer as the only push mechanism, run-time state reads, retention tri-state, VAPID single-pair policy). Status markers distinguish Accepted (live) from Proposed (002 spec, not executed).

## [0.1.3] — Tweaks spec (not executed)

### Added
- docs/002--llm--TWEAKS.md — spec for three tweaks: (1) held-koan mode with global server-side pointer + toggle back to daily rotation, (2) push alert carrying only the koan body, (3) commentary and verse hidden by default. Peer-reviewed (gemini-2.5-pro + gpt-5, 2/2 responded); high/medium findings folded in (atomic index advance, timer as single push mechanism, idempotent migration). Deliberately not executed — Alvar lives with the app first; implementation in a fresh session. Open decisions listed in the doc.

### Fixed
- 001.2/001.3 sudo gate corrected: `ssh -t` + `sudo -v` (prompts alvar's own password) replaces `sudo -n`, which can never pass on stock Ubuntu (%sudo is passworded; NOPASSWD is not default)
- 001.2 Phase 2 rewritten with a shell legend (LAPTOP# / ROOT# / ALVAR#), per-block Shell labels through Phase 9, when each shell can be closed, and plain-English briefs per step; 001.3 gates tagged with their shell
- 001.2/001.11: all backslash line-continuations in shell blocks joined to single lines - multi-line pastes over SSH were dropping the continuation line (the 99-hardening.conf write silently became a no-op twice)
- requirements.txt: py-vapid==1.9.2 (stale freeze pin) breaks with modern cryptography 50.x on the droplet (TypeError: curve must be an EllipticCurve instance, hit live on deploy); bumped to py-vapid==1.9.6 and pinned cryptography==50.0.2 - the local known-good pair; 001.2 Phase 3.3 documents the on-droplet fix and the stale-Step-4.4 ref corrected to Phase 3.3
- 001.2 Phase 3.2: documented git dubious-ownership refusal when pulling as alvar in the koan-owned repo (hit live); fix is sudo -u koan git pull, matching 9.2
- 001.2: editor references updated from nano to vim (usr editor); noted optional removal of the nginx default site (raw-IP welcome page leak)
- 001.2: push-service journalctl commands now run under sudo - the unit executes as koan, so unprivileged alvar reads no entries from its journal (hit live); same sudo requirement noted for 9.4 log checks
- push_sender.py: vapid_private_key passed to webpush() as raw bytes fell into Vapid.from_string() and crashed
- push_sender.py: 403 BadJwtToken from web.push.apple.com traced to VAPID key-pair drift - app.py loads the public key ONCE at gunicorn start, while push_sender signs with the on-disk pair at each run, so any init_vapid.py run between a subscribe and a send invalidates every subscription (multiple regenerations happened live during debugging); retention fix completed: WebPushException non-404/410 responses (403 BadJwtToken, 429, network) no longer delete subscriptions - only a confirmed 404/410 may; vapid_claims sub changed from reserved-TLD mailto:admin@dailykoan.example to a real contact (mailto:alvarix@gmail.com); 001.2 notes the key-at-start trap and the restart-after-key-change rule ('bytes' object has no attribute 'encode', hit live on first real send) - now the PEM path string is passed and pywebpush loads it via Vapid.from_file; a send error previously counted the subscription as dead and deleted it (one valid iOS subscription destroyed during the incident) - now only a confirmed 404/410 removes a subscription, other errors are kept and reported; deprecated datetime.utcnow() replaced with time.gmtime(); load_koans() exits with a clear error on missing/corrupt koans.json
