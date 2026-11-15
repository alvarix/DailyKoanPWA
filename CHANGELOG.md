# Changelog

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
