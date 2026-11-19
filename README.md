# Daily Koan PWA

A minimal, Zen-inspired progressive web app that delivers a different koan every day via push notification to your iOS Home Screen. No accounts, no tracking, just a single moment of clarity.

## Features

- **Held or Daily koan**: Hold mode serves everyone the same koan until someone taps Next — and re-announces it every day until then; Daily mode rotates deterministically by date. One tap in the settings drawer flips it
- **Delivery as data**: the push arrives once a day at your chosen local time (`push_time` + `push_timezone` in the drawer, DST-correct); the systemd timer ticks hourly and the settings gate decides which tick sends
- **Ordered progression**: koans walk the classic texts (Mumonkan → Blue Cliff Record → others) case by case; a Random mode jumps instead
- **Push Notifications**: iOS Safari 16.4+ and modern browsers via Web Push API; the alert carries the koan body itself
- **Full Koan Page**: Title, source, dual commentary, and verse — collapsed by default, calm to open
- **Night Mode**: follows your system appearance by default; System/Light/Dark per device in the drawer
- **Offline-First**: Add to Home Screen; works offline via service worker
- **Modern Stack, Zero Build Step**: Tailwind, Alpine.js, and HTMX served from CDN; no npm build required
- **Self-Hostable**: < $6/mo on a DigitalOcean droplet

## Getting Started

1. Clone the repo
2. Create a virtualenv: `python3 -m venv venv && source venv/bin/activate`
3. Install deps: `pip install -r requirements.txt`
4. Generate icons: `python3 init_icons.py`
5. Generate VAPID keys: `python3 init_vapid.py`
6. Initialize the database: `python3 init_db.py` (also seeds the `settings` table)
7. Start the dev server: `FLASK_DEBUG=1 python3 app.py`
8. Open `http://127.0.0.1:5000` in Safari, add to Home Screen, then tap the **bell**

## Project Structure

```
DailyKoanPWA/
├── app.py              # Flask backend (routes, subscriptions, push)
├── koan_selector.py    # Shared koan selection + settings state (app & push sender)
├── push_sender.py      # Timer-run push broadcast
├── init_db.py           # Create subscriptions.db + settings defaults
├── init_vapid.py       # Generate VAPID keys for Web Push
├── init_icons.py       # Generate placeholder PWA icons
├── koans.json          # Source data (14 koans, group/order/id metadata)
├── requirements.txt    # Python dependencies
├── mockup.html         # Standalone design mockup (0.1.5 reference)
├── templates/
│   └── index.html      # Koan page (Tailwind + Alpine; drawer w/ notifications switch, bell ON badge, toast)
├── static/
│   ├── manifest.json   # PWA manifest
│   └── sw.js           # Service worker (push + offline)
├── tests/
│   ├── test_app.py           # Route tests (mode, next, settings, deep links)
│   ├── test_koan_selector.py # Selection/settings state tests
│   └── test_push_sender.py   # Payload truncate tests
└── docs/
    ├── 000--diagram--llm.md                        # file map (mermaid: runtime + push decision)
    ├── 002--usr--TWEAKS.md   / 002--llm--TWEAKS.md    # executed tweak spec
    ├── 003--llm--KOAN_PROGRESSION.md                   # progression analysis (gates, corpus, componentization)
    ├── 001.2--llm--STANDALONE_DROPLET_DEPLOYMENT.md    # separate-droplet deploy (isolated failure domain)
    ├── 001.3--usr--standalone-droplet-checklist.md      # 001.2 execution checklist
    ├── 001.11--llm--MIGRATE_TO_FORGE.md                  # standalone -> Forge, with rollback
    ├── 001.12--usr--migrate-to-forge-checklist.md        # 001.11 execution checklist
    └── adr/                                             # architecture decision records (why, not how)
```

Run the tests: `venv/bin/python -m unittest discover -s tests` (47 tests).

## Deployment

Three runbooks, in execution order:

1. [docs/001.2--llm--STANDALONE_DROPLET_DEPLOYMENT.md](docs/001.2--llm--STANDALONE_DROPLET_DEPLOYMENT.md) — deploy on a fresh, isolated DigitalOcean droplet (recommended path; a mistake cannot touch the Forge droplet or its client sites). Execution checklist: docs/001.3--usr--standalone-droplet-checklist.md
2. [docs/001.11--llm--MIGRATE_TO_FORGE.md](docs/001.11--llm--MIGRATE_TO_FORGE.md) — later, once stable: switch the standalone droplet to the Forge-managed droplet, configured the same way as wmw. Execution checklist: docs/001.12--usr--migrate-to-forge-checklist.md
3. [docs/001.1--llm--FORGE_DEPLOYMENT.md](docs/001.1--llm--FORGE_DEPLOYMENT.md) — the 2026-10-24 nginx postmortem; its Section B safety rules are mandatory reading before any Forge nginx edit

## Requirements

- Python 3.9+ (venv runs 3.9.6; pyproject/ruff target `py39`)
- iOS 16.4+ for Web Push notifications (must be installed as Home Screen PWA)
- HTTPS in production (required by Web Push API)

## License

MIT
# DailyKoanPWA
