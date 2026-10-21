# Local Development

## Quick Start

```bash
# 1. Enter the project directory
cd /Users/alvarsirlin/Sites/apps/DailyKoanPWA

# 2. Activate the virtual environment (already created)
source venv/bin/activate

# 3. Start the Flask dev server
python3 app.py
```

Then open **http://127.0.0.1:5000** in your browser.

The dev server auto-reloads when you edit files.

## What Works Locally

| Feature | Local (http://127.0.0.1:5000) | Notes |
|---|---|---|
| Browse koans | ✅ Yes | All pages and navigation work |
| Toggle commentaries | ✅ Yes | Collapsible details panels |
| "Next Koan" button | ✅ Yes | Rotates through all 14 koans |
| API endpoints | ✅ Yes | `/api/today`, `/api/koan/N` testable |

## What Does NOT Work Locally

| Feature | Why? | How to Test |
|---|---|---|
| Push notifications | Safari requires HTTPS for Web Push | Deploy to DigitalOcean + HTTPS, or use ngrok (see below) |
| Service Worker registration | May work on `localhost`, but iOS Web Push requires Home Screen app + HTTPS | Same as above |
| Install as PWA | Needs a real HTTPS domain and valid manifest | Deploy |

## Testing Push with ngrok (Quick HTTPS Tunnel)

If you want to test push notifications on your actual iPhone before deploying:

```bash
# Install ngrok if you haven't
brew install ngrok   # macOS

# In one terminal, start the app
source venv/bin/activate
FLASK_DEBUG=0 FLASK_HOST=127.0.0.1 python3 app.py

# In another terminal, tunnel
ngrok http 5000
```

Ngrok will give you a `https://XXXX.ngrok-free.app` URL. Use that on your iPhone, add to Home Screen, tap the bell, and subscribe. You can then manually trigger a push from the server:

```bash
# In yet another terminal
export BASE_URL="https://XXXX.ngrok-free.app/"
source venv/bin/activate
python3 push_sender.py
```

## Resetting Data

```bash
# Delete subscriptions (start fresh)
rm subscriptions.db && python3 init_db.py

# Regenerate VAPID keys
python3 init_vapid.py
```
