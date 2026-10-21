# Hosting Multiple Domains on a Single Droplet

## The Short Answer

Yes. One droplet can serve as many domains and subdomains as you want. nginx routes incoming requests by the `Host` header (the domain name in the browser's address bar). Your existing site continues to work on its current domain, and the new app gets its own domain or subdomain.

---

## How It Works

When a browser requests `https://koan.alvarsirlin.dev`, the DNS lookup resolves to your droplet's IP. nginx receives the request, sees the `Host: koan.alvarsirlin.dev` header, and routes it to the correct backend.

```
DNS: koan.alvarsirlin.dev → A → <DROPLET_IP>
                       ↓
                 nginx (port 80/443)
                       ↓
            server_name koan.alvarsirlin.dev
                       ↓
            proxy_pass to 127.0.0.1:8001
```

Your existing site's nginx config is completely untouched.

---

## The Two Domain Scenarios

### Scenario A: You Own Both Domains

You own `existingdomain.com` (current site) and `alvarsirlin.dev` (your personal domain).

- `existingdomain.com` → nginx server block for existing site (already works)
- `koan.alvarsirlin.dev` → new nginx server block for Daily Koan app
- Both point to the same droplet IP via DNS A records

### Scenario B: You Only Own the Existing Domain

If you don't own a second domain, options:

| Option | Cost | Notes |
|---|---|---|
| Buy a cheap domain (e.g., `dailykoan.app`) | ~$10/yr | Clean, branded |
| Use a free subdomain service (e.g., `*.duckdns.org`, `*.nip.io`) | Free | Messy, not great for PWA |
| Use a DigitalOcean App Platform domain | Free | But that means moving off your droplet |

**Recommendation:** If you already own `alvarsirlin.dev` or any domain, adding a subdomain is free and instant. If not, buying a cheap domain is the cleanest path.

---

## DNS Setup for Scenario A

You need access to wherever your DNS is managed (Cloudflare, Namecheap, your registrar, etc.).

### If `alvarsirlin.dev` is your domain

Add one A record:

```text
koan.alvarsirlin.dev    A    <DROPLET_IP>
```

No changes needed to `existingdomain.com` — it keeps pointing to the same IP as before.

### Verify DNS

```bash
dig +short koan.alvarsirlin.dev
# Should return your droplet IP
```

DNS propagation is usually instant but can take up to a few minutes.

---

## nginx Configuration

Your droplet likely already has a default nginx server block for `existingdomain.com`. You add a second one.

### Existing site (already configured — do not touch)

`/etc/nginx/sites-available/existing`:
```nginx
server {
    listen 80;
    server_name existingdomain.com www.existingdomain.com;
    # ... existing config ...
}
```

### New site (Daily Koan)

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

## HTTPS with certbot

certbot can handle multiple certificates on one droplet:

```bash
# Existing site (already done, but here's the pattern)
sudo certbot --nginx -d existingdomain.com -d www.existingdomain.com

# New site
sudo certbot --nginx -d koan.alvarsirlin.dev
```

certbot will:
1. Detect the new server block
2. Obtain a separate certificate for `koan.alvarsirlin.dev`
3. Auto-inject HTTPS redirect and SSL params into `/etc/nginx/sites-available/koan`
4. Set up auto-renewal for both certificates

Verify both certs:
```bash
sudo certbot certificates
```

---

## What About the Default Server Block?

nginx uses the **first server block** as the default for any request that doesn't match a `server_name`. If someone visits your droplet by raw IP, they get whichever site is listed first alphabetically in `sites-enabled/`.

To be explicit, you can set a default catch-all:

```nginx
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;
    return 444;  # Drop the connection
}
```

Or redirect to your main site:
```nginx
server {
    listen 80 default_server;
    server_name _;
    return 301 https://existingdomain.com$request_uri;
}
```

---

## Firewall Considerations

Your droplet's firewall (UFW or DigitalOcean cloud firewall) should already allow ports 80 and 443. No additional rules needed — both domains share the same HTTP/HTTPS ports.

Verify:
```bash
sudo ufw status
sudo ufw allow 'Nginx Full'
```

---

## Summary

| Concern | Answer |
|---|---|
| Same droplet, different domains? | Yes, unlimited |
| Same IP, different sites? | Yes, nginx routes by `Host` header |
| Separate SSL certificates? | Yes, one per domain |
| Can I add a subdomain of an unrelated domain? | Yes, any domain/subdomain pointing to the IP works |
| Will this break my existing site? | No, configs are isolated |
| Cost? | $0 beyond the domain you already own |

---

## Next Steps

1. Check if you own a domain you can use for a subdomain (e.g., `alvarsirlin.dev`)
2. Add the A record at your DNS provider
3. Follow the subdomain deployment steps in `DEPLOYMENT.md`
