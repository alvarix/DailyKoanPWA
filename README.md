# Daily Koan PWA

A minimal, Zen-inspired progressive web app that delivers a different koan every day via push notification to your iOS Home Screen. No accounts, no tracking, just a single moment of clarity.

## Features

- **Daily Koan**: Deterministically selected every day so all subscribers see the same teaching
- **Push Notifications**: iOS Safari 16.4+ and modern browsers via Web Push API
- **Full Koan Page**: Title, source, dual commentary, and verse — all served in a calm, readable dark theme
- **Offline-First**: Add to Home Screen; works offline via service worker
- **Modern Stack, Zero Build Step**: Tailwind, Alpine.js, and HTMX served from CDN; no npm build required
- **Self-Hostable**: < $6/mo on a DigitalOcean droplet

## Getting Started

1. Clone the repo
2. Create a virtualenv: `python3 -m venv venv && source venv/bin/activate`
3. Install deps: `pip install -r requirements.txt`
4. Generate icons: `python3 init_icons.py`
5. Generate VAPID keys: `python3 init_vapid.py`
6. Initialize the database: `python3 init_db.py`
7. Start the dev server: `FLASK_DEBUG=1 python3 app.py`
8. Open `http://127.0.0.1:5000` in Safari, add to Home Screen, then tap **Notify me**

## Project Structure

```
DailyKoanPWA/
├── app.py              # Flask backend (koans, subscriptions, push)
├── push_sender.py      # Daily push broadcast script
├── init_db.py          # Create subscriptions.db
├── init_vapid.py       # Generate VAPID keys for Web Push
├── init_icons.py       # Generate placeholder PWA icons
├── koans.json          # Source data (14 Zen koans with commentary & verse)
├── requirements.txt    # Python dependencies
├── mockup.html         # Standalone design mockup
├── templates/
│   └── index.html      # Koan page (Tailwind + Alpine + HTMX)
├── static/
│   ├── manifest.json   # PWA manifest
│   └── sw.js           # Service worker (push + offline)
└── docs/
    ├── 001--llm--DEPLOYMENT.md                  # subdomain-on-an-existing-droplet guide
    ├── 001.1--llm--FORGE_DEPLOYMENT.md          # Forge deploy + Oct-24 nginx postmortem (mandatory reading)
    ├── 001.2--llm--STANDALONE_DROPLET_DEPLOYMENT.md  # separate-droplet deploy (isolated failure domain)
    ├── 001.3--usr--standalone-droplet-checklist.md   # 001.2 execution checklist
    ├── 001.11--llm--MIGRATE_TO_FORGE.md             # standalone -> Forge, same-as-wmw, with rollback
    ├── 001.12--usr--migrate-to-forge-checklist.md    # 001.11 execution checklist
    └── 001--*--spec/status files                 # specs, status, briefs
```

## Deployment

Three runbooks, in execution order:

1. [docs/001.2--llm--STANDALONE_DROPLET_DEPLOYMENT.md](docs/001.2--llm--STANDALONE_DROPLET_DEPLOYMENT.md) — deploy on a fresh, isolated DigitalOcean droplet (recommended path; a mistake cannot touch the Forge droplet or its client sites). Execution checklist: docs/001.3--usr--standalone-droplet-checklist.md
2. [docs/001.11--llm--MIGRATE_TO_FORGE.md](docs/001.11--llm--MIGRATE_TO_FORGE.md) — later, once stable: switch the standalone droplet to the Forge-managed droplet, configured the same way as wmw. Execution checklist: docs/001.12--usr--migrate-to-forge-checklist.md
3. [docs/001.1--llm--FORGE_DEPLOYMENT.md](docs/001.1--llm--FORGE_DEPLOYMENT.md) — the 2026-10-24 nginx postmortem; its Section B safety rules are mandatory reading before any Forge nginx edit

## Requirements

- Python 3.11+
- iOS 16.4+ for Web Push notifications (must be installed as Home Screen PWA)
- HTTPS in production (required by Web Push API)

## License

MIT
# DailyKoanPWA
