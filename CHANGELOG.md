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
