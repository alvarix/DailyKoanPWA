# Deploying to a Laravel Forge-Managed Droplet

## The Short Answer

Yes, this is safe — **if you add the new app as a Forge site** rather than manually editing nginx configs behind Forge's back. Forge won't interfere with things it doesn't manage, and it can happily co-exist with a Python app.

---

## What Forge Manages (Don't Touch Manually)

Forge owns these. If you edit them directly, Forge may overwrite your changes during deployments or when you change settings in the UI:

- `/etc/nginx/sites-available/forge-*` (site configs)
- `/etc/nginx/nginx.conf` (main nginx config)
- PHP-FPM pools and versions
- SSL certificates (via certbot, automated by Forge)
- Supervisor / systemd services **that Forge created**

## What Forge Does NOT Manage (Safe To Add)

- Additional system packages (`python3`, `python3-venv`, etc.)
- Your own systemd services
- Files in `/opt/` or `/home/forge/` that Forge didn't create
- Custom nginx configs **outside** the `sites-available` directory
- Firewall rules (unless you configured UFW through Forge)

---

## The Recommended Approach: Forge-Managed Site + Reverse Proxy

Instead of manually creating nginx configs, add the koan app as a **new site** in Forge. Then use Forge's Nginx customization to reverse-proxy to your Python app.

### Step 1: Add a New Site in Forge

**What "root directory" means here:** The server's filesystem root is still `/`. Forge creates sites under `/home/forge/{domain}/`. The nginx `root` directive points to each site's public web directory — not the system root. In our reverse-proxy setup, this directive is largely irrelevant since all requests get proxied to Python, but Forge expects it to exist.

1. Log into Forge
2. Go to your server → Sites → **New Site**
3. Configure:
   - **Domain**: `koan.alvarsirlin.dev`
   - **Project Type**: "Static HTML" or "Custom"
   - **Web Directory**: `/public` (or whatever — we'll override this in nginx)
4. Create the site

### Step 2: Customize the Nginx Config

1. In Forge, click the new site → **Nginx**
2. Click **Edit Nginx Configuration**
3. Replace the relevant location blocks with a reverse proxy to your Python app

Forge's default config looks like this (your site ID number will differ):

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name koan.alvarsirlin.dev;
    root /home/forge/koan.alvarsirlin.dev/public;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_dhparam /etc/nginx/dhparams.pem;

    add_header X-Frame-Options "SAMEORIGIN";
    add_header X-XSS-Protection "1; mode=block";
    add_header X-Content-Type-Options "nosniff";

    index index.html index.htm;

    charset utf-8;

    # FORGE CONFIG (DO NOT REMOVE!)
    include forge-conf/3430825/server/*;

    location / {
        try_files $uri $uri/ =404;
    }

    location = /favicon.ico { access_log off; log_not_found off; }
    location = /favicon.svg { access_log off; log_not_found off; }
    location = /robots.txt  { access_log off; log_not_found off; }

    access_log off;
    error_log  /var/log/nginx/3430825-error.log error;

    location ~ /\.(?!well-known).* {
        deny all;
    }
}
```

**What to change:** replace the `location /` block with three new blocks. Leave every other directive untouched.

```nginx
    # Static files served directly by nginx
    location /static {
        alias /opt/dailykoan/static;
        expires 30d;
        access_log off;
    }

    # Manifest and service worker
    location ~ ^/(manifest\.json|sw\.js)$ {
        alias /opt/dailykoan/static/$1;
    }

    # Everything else proxied to Python app
    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
```

The final config should look like this:

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name koan.alvarsirlin.dev;
    root /home/forge/koan.alvarsirlin.dev/public;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_dhparam /etc/nginx/dhparams.pem;

    add_header X-Frame-Options "SAMEORIGIN";
    add_header X-XSS-Protection "1; mode=block";
    add_header X-Content-Type-Options "nosniff";

    index index.html index.htm;
    charset utf-8;

    # FORGE CONFIG (DO NOT REMOVE!)
    include forge-conf/3430825/server/*;

    # Static files served directly by nginx
    location /static {
        alias /opt/dailykoan/static;
        expires 30d;
        access_log off;
    }

    # Manifest and service worker
    location ~ ^/(manifest\.json|sw\.js)$ {
        alias /opt/dailykoan/static/$1;
    }

    # Everything else proxied to Python app
    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location = /favicon.ico { access_log off; log_not_found off; }
    location = /favicon.svg { access_log off; log_not_found off; }
    location = /robots.txt  { access_log off; log_not_found off; }

    access_log off;
    error_log  /var/log/nginx/3430825-error.log error;

    location ~ /\.(?!well-known).* {
        deny all;
    }
}
```

Click **Update** — Forge will validate and reload nginx automatically.

### Step 3: Deploy the Python App

SSH into the droplet:

```bash
ssh forge@<DROPLET_IP>
```

Create the app directory and set up the environment:

```bash
sudo mkdir -p /opt/dailykoan
sudo chown -R forge:forge /opt/dailykoan
cd /opt/dailykoan

# If deploying from git
git clone https://github.com/YOUR_USERNAME/DailyKoanPWA.git .

# Or rsync from laptop
cd /opt/dailykoan
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 init_vapid.py
python3 init_db.py
python3 init_icons.py
```

### Step 4: Create a Systemd Service for Gunicorn

Forge doesn't manage this, so we create it manually. This is safe — Forge ignores services it didn't create.

`/etc/systemd/system/dailykoan.service`:
```ini
[Unit]
Description=Daily Koan PWA
After=network.target

[Service]
User=forge
Group=forge
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

### Step 5: Add SSL via Forge

1. In Forge, click the site → **SSL**
2. Click **Let's Encrypt**
3. Forge handles certbot, nginx SSL injection, and auto-renewal automatically

No manual certbot needed. Forge will update the nginx config with the SSL block.

### Step 6: Daily Push Timer

Create the systemd timer (same as standalone deployment):

`/etc/systemd/system/dailykoan-push.service`:
```ini
[Unit]
Description=Daily Koan Push Sender

[Service]
Type=oneshot
User=forge
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
```

---

## What About Deployments?

You have two options:

### Option A: Manual Deploy

```bash
ssh forge@<DROPLET_IP> 'cd /opt/dailykoan && git pull && sudo systemctl restart dailykoan'
```

### Option B: Forge Deployment Hook (Advanced)

If you want Forge to trigger the deployment, you could:
1. Create a small deployment script at `/home/forge/koan.alvarsirlin.dev/deploy.sh`
2. Add a Forge deployment hook that SSHes to localhost and runs it

But since the app isn't a Forge-managed project type, manual deploys are simpler.

---

## Summary: Why This Is Safe

| Concern | Answer |
|---|---|
| Will installing Python break Forge? | No. Forge uses Python internally. |
| Will Forge overwrite my nginx config? | No — if you use Forge's UI to edit it, Forge knows about it. |
| Will my Statamic site be affected? | No. The new site is isolated by `server_name`. |
| Will SSL renewal break anything? | No. Forge manages SSL for each site independently. |
| Can Forge auto-deploy my Python app? | Not natively, but manual deploy is one command. |

---

## Alternative: Manual Nginx Config (Not Recommended)

If you really want to avoid Forge's UI, you can create a config file that Forge doesn't know about:

```bash
sudo nano /etc/nginx/conf.d/koan.conf
```

But if Forge ever regenerates its nginx configs (e.g., you add a site, change PHP version, or renew SSL), it runs `nginx -t && systemctl reload nginx`. It won't delete `conf.d/koan.conf`, but if there's a syntax conflict, nginx will fail to reload. **Use the Forge-managed site approach instead.**
