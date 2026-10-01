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
    ├── DEPLOYMENT.md   # Step-by-step server setup
    ├── 001--usr--spec.md
    └── 001--llm--spec.md
```

## Deployment

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for full droplet setup, nginx, HTTPS, and systemd timer configuration.

## Requirements

- Python 3.11+
- iOS 16.4+ for Web Push notifications (must be installed as Home Screen PWA)
- HTTPS in production (required by Web Push API)

## License

MIT
# DailyKoanPWA
