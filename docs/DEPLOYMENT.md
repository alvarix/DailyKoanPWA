# Daily Koan PWA — Deployment Guide

## Option: Existing Droplet + Subdomain (Recommended)

If you already have a DigitalOcean droplet running a low-traffic site, the cheapest and simplest path is to host the Daily Koan app **on the same droplet** under a subdomain like `koan.alvarsirlin.dev`.

Your existing site continues to run undisturbed. The new app runs on a different local port, and nginx routes by subdomain.

---

## Prerequisites

- An existing Ubuntu droplet with nginx already running
- A domain with DNS managed where you can add an A record
- SSH access as root or a sudo user
- Your existing site should be using nginx (check with `sudo nginx -t`)

---

## 1. DNS Setup

Add an A record for your subdomain pointing to the same droplet IP:

```text
koan.alvarsirlin.dev     A     <DROPLET_IP>
```

Wait a few minutes, then verify:
```bash
dig +short koan.alvarsirlin.dev
```

---

## 2. SSH In & Prep

```bash
ssh root@<DROPLET_IP>
```

Ensure you have the basics:
```bash
sudo apt update
sudo apt install -y python3-pip python3-venv git certbot python3-certbot-nginx
```

Create the app user and directory:
```bash
sudo useradd -r -s /bin/false koan 2>/dev/null || true
sudo mkdir -p /opt/dailykoan
sudo chown -R koan:koan /opt/dailykoan
```

---

## 3. Deploy the Code

Option A — clone from GitHub (preferred):
```bash
git clone https://github.com/YOUR_USERNAME/DailyKoanPWA.git /opt/dailykoan
```

Option B — if you haven't created the repo yet:
```bash
# From your laptop, copy files to the droplet
rsync -avz --exclude=venv --exclude=subscriptions.db --exclude=.git \
  /Users/alvarsirlin/Sites/apps/DailyKoanPWA/ root@<DROPLET_IP>:/opt/dailykoan/
```

Set up the virtual environment:
```bash
cd /opt/dailykoan
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Generate VAPID keys:
```bash
python3 init_vapid.py
```

Initialize the database:
```bash
python3 init_db.py
```

Generate icons:
```bash
python3 init_icons.py
```

Lock down permissions:
```bash
sudo chown -R koan:koan /opt/dailykoan
sudo chmod 600 /opt/dailykoan/vapid_private.pem
```

---

## 4. Gunicorn on a Free Port

Check what ports your existing app uses:
```bash
sudo ss -tlnp | grep -E ':\d+'
```

Pick an **unused** port (e.g., `8001` if `8000` is taken). Create the systemd service file:

`/etc/systemd/system/dailykoan.service`:
```ini
[Unit]
Description=Daily Koan PWA
After=network.target

[Service]
User=koan
Group=koan
WorkingDirectory=/opt/dailykoan
Environment="PATH=/opt/dailykoan/venv/bin"
Environment="FLASK_HOST=127.0.0.1"
Environment="FLASK_DEBUG=0"
Environment="BASE_URL=https://koan.alvarsirlin.dev/"
ExecStart=/opt/dailykoan/venv/bin/gunicorn app:app -b 127.0.0.1:8001 --workers 1 --timeout 30
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable dailykoan
sudo systemctl start dailykoan
sudo systemctl status dailykoan
```

---

## 5. nginx Subdomain Config

Create a new server block. **Do not touch your existing site's config.**

`/etc/nginx/sites-available/koan`:
```nginx
server {
    listen 80;
    server_name koan.alvarsirlin.dev;

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static {
        alias /opt/dailykoan/static;
        expires 30d;
        access_log off;
    }
}
```

Enable it:
```bash
sudo ln -s /etc/nginx/sites-available/koan /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

## 6. HTTPS with certbot

Let certbot handle the subdomain SSL:
```bash
sudo certbot --nginx -d koan.alvarsirlin.dev
```

Certbot will:
1. Detect the new server block
2. Obtain a certificate
3. Auto-inject the HTTPS redirect and SSL params
4. Set up auto-renewal

Verify:
```bash
sudo certbot certificates
```

---

## 7. Daily Push Timer

Create the systemd timer that sends the daily koan at 08:00 UTC.

`/etc/systemd/system/dailykoan-push.service`:
```ini
[Unit]
Description=Daily Koan Push Sender

[Service]
Type=oneshot
User=koan
WorkingDirectory=/opt/dailykoan
Environment="PATH=/opt/dailykoan/venv/bin"
Environment="BASE_URL=https://koan.alvarsirlin.dev/"
ExecStart=/opt/dailykoan/venv/bin/python push_sender.py
```

`/etc/systemd/system/dailykoan-push.timer`:
```ini
[Unit]
Description=Daily Koan Push Timer

[Timer]
OnCalendar=*-*-* 08:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

Enable:
```bash
sudo systemctl daemon-reload
sudo systemctl enable dailykoan-push.timer
sudo systemctl start dailykoan-push.timer
systemctl list-timers dailykoan-push.timer
```

---

## 8. Test the PWA & Push

1. Open `https://koan.alvarsirlin.dev` in Safari on iOS 16.4+.
2. Tap Share → Add to Home Screen.
3. Open from Home Screen.
4. Tap the bell and allow notifications.
5. Verify subscription count:
   ```text
   https://koan.alvarsirlin.dev/api/subscriptions/count
   ```
6. Manually trigger a test push:
   ```bash
   sudo -u koan bash -c 'cd /opt/dailykoan && source venv/bin/activate && BASE_URL=https://koan.alvarsirlin.dev/ python push_sender.py'
   ```

---

## Maintenance Commands

```bash
# View app logs
sudo journalctl -u dailykoan -f

# View push sender logs
sudo journalctl -u dailykoan-push.service -f

# Restart app after code changes
sudo systemctl restart dailykoan

# Renew SSL dry run
sudo certbot renew --dry-run

# List active timers
systemctl list-timers

# Quick health check
curl -s https://koan.alvarsirlin.dev/api/today | python3 -m json.tool
```

---

## Updating After Code Changes

Once your repo is on GitHub, a simple deploy command from your laptop:

```bash
ssh root@<DROPLET_IP> 'cd /opt/dailykoan && git pull && sudo systemctl restart dailykoan'
```

Or wire it into a GitHub Action for Phase 2 CI/CD.

---

## Why Not Vercel?

Vercel's serverless model makes this project significantly more complex:

- **No persistent SQLite** — subscription database would vanish on cold starts
- **No native cron** — you'd need an external scheduler (e.g., GitHub Actions cron calling a Vercel function)
- **Web Push state** — VAPID keys and subscriptions need external storage (Supabase, Upstash, etc.)
- **Python/Flask** — not a first-class runtime; requires serverless adapter wrappers

Your existing droplet + subdomain is the simplest, cheapest path.
