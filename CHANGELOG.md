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

### Fixed
- 001.2/001.3 sudo gate corrected: `ssh -t` + `sudo -v` (prompts alvar's own password) replaces `sudo -n`, which can never pass on stock Ubuntu (%sudo is passworded; NOPASSWD is not default)
