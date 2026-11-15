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
- Standalone droplet deployment guide (docs/002--llm--STANDALONE_DROPLET_DEPLOYMENT.md): fresh, isolated DigitalOcean droplet with hardening gates, paired usr checklist (docs/002--usr--standalone-droplet-checklist.md)
- Forge migration guide (docs/003--llm--MIGRATE_TO_FORGE.md): later switch from standalone droplet to Forge-managed alfaForge, same body-only-fragment pattern as wmw, zero-downtime-ordered cutover with exact rollback commands, paired usr checklist (docs/003--usr--migrate-to-forge-checklist.md)
- Postmortem-derived safety gates applied throughout: nginx -t before every reload, reload-never-restart, client-site curl 200 baselines before and after
- Safe SQLite backup procedure (sqlite3 .backup) and off-droplet VAPID key backup guidance
- README deployment pointers updated to the versioned docs

### Changed
- docs/001--llm--status.md: Phase 2 section added (deployment paths planned)
