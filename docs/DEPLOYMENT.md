# Daily Koan PWA — Deployment Guide

## Prerequisites

- A fresh Ubuntu 24.04 LTS DigitalOcean droplet (or any VPS)
- A domain name pointing to the droplet's IP (`A` and `AAAA` records)
- SSH access with root or sudo privileges
- `doctl` CLI (optional) or DigitalOcean web console

---

## 1. Create the Droplet

1. In the DigitalOcean dashboard, create a new droplet:
   - Distribution: Ubuntu 24.04 (LTS)
   - Plan: Basic, $6/mo (1 CPU / 512MB RAM is fine for this low-traffic app)
   - Region: closest to your users
   - Add your SSH key
2. Note the public IPv4 address.
3. (Optional) Add a firewall rule: allow inbound TCP on 22, 80, 443 only.

---

## 2. Domain Setup

Point your domain's A record to the droplet IP:
```
# DNS A record
your-domain.com     A     <DROPLET_IP>
www.your-domain.com CNAME your-domain.com
```

Replace all occurrences of `your-domain.com` in configs below with your actual domain.

---

## 3. Server Setup (SSH)

SSH into your droplet:
```bash
ssh root@your-domain.com
```

Install dependencies:
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-venv nginx git certbot python3-certbot-nginx
```

Create the app user and directory:
```bash
sudo useradd -r -s /bin/false koan
sudo mkdir -p /opt/dailykoan
sudo chown -R koan:koan /opt/dailykoan
```

---

## 4. Deploy the Application

Clone the repo (or scp your local files):
```bash
git clone https://github.com/YOUR_USERNAME/DailyKoanPWA.git /opt/dailykoan
```

Set up the virtual environment:
```bash
cd /opt/dailykoan
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Generate VAPID keys (if not committed):
```bash
python3 init_vapid.py
```

Initialize the database:
```bash
python3 init_db.py
```

Set correct ownership:
```bash
sudo chown -R koan:koan /opt/dailykoan
sudo chmod 600 /opt/dailykoan/vapid_private.pem
```

---

## 5. Gunicorn Systemd Service

Create `/etc/systemd/system/dailykoan.service`:
```ini
[Unit]
Description=Daily Koan PWA
After=network.target

[Service]
User=koan
Group=koan
WorkingDirectory=/opt/dailykoan
Environment="PATH=/opt/dailykoan/venv/bin"
# Set FLASK_HOST=127.0.0.1 and no debug for production
Environment="FLASK_HOST=127.0.0.1"
Environment="FLASK_DEBUG=0"
# Update BASE_URL for the push sender
Environment="BASE_URL=https://your-domain.com/"
ExecStart=/opt/dailykoan/venv/bin/gunicorn app:app -b 127.0.0.1:8000 --workers 1 --timeout 30
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

## 6. Daily Push Timer

The push sender must run every day at your preferred time (e.g., 08:00 UTC).

Create `/etc/systemd/system/dailykoan-push.service`:
```ini
[Unit]
Description=Daily Koan Push Sender

[Service]
Type=oneshot
User=koan
WorkingDirectory=/opt/dailykoan
Environment="PATH=/opt/dailykoan/venv/bin"
Environment="BASE_URL=https://your-domain.com/"
ExecStart=/opt/dailykoan/venv/bin/python push_sender.py
```

Create `/etc/systemd/system/dailykoan-push.timer`:
```ini
[Unit]
Description=Daily Koan Push Timer

[Timer]
OnCalendar=*-*-* 08:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable dailykoan-push.timer
sudo systemctl start dailykoan-push.timer
systemctl list-timers dailykoan-push.timer
```

---

## 7. Nginx & HTTPS

Create `/etc/nginx/sites-available/dailykoan`:
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
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

Enable:
```bash
sudo ln -s /etc/nginx/sites-available/dailykoan /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

Obtain SSL certificate:
```bash
sudo certbot --nginx -d your-domain.com -d www.your-domain.com
```

Certbot will auto-configure HTTPS redirect and certificate renewal.

---

## 8. Test the PWA & Push

1. Open `https://your-domain.com` in Safari on iOS 16.4+.
2. Tap Share -> Add to Home Screen.
3. Open the app from the Home Screen.
4. Tap **Notify me** and allow notifications.
5. Verify: `https://your-domain.com/api/subscriptions/count` should show `1`.
6. (Optional) Manually run the push to test immediately:
   ```bash
   sudo -u koan bash -c 'cd /opt/dailykoan && source venv/bin/activate && BASE_URL=https://your-domain.com/ python push_sender.py'
   ```

---

## 9. Update on Push (CI/CD Preview)

Phase 2 will wire automatic deployment. For now, after pushing code:

```bash
ssh root@your-domain.com 'cd /opt/dailykoan && git pull && sudo systemctl restart dailykoan'
```

Or add a simple `deploy.sh` script and run it from GitHub Actions.

---

## Maintenance Commands

```bash
# View logs
sudo journalctl -u dailykoan -f
sudo journalctl -u dailykoan-push.service -f

# Restart services
sudo systemctl restart dailykoan
sudo systemctl restart dailykoan-push.timer

# Update certbot auto-renewal (usually automatic)
sudo certbot renew --dry-run
```
