# Forge Deployment Checklist

## Pre-Deployment

- [x] Create site in Forge UI
- [x] Clone repo to server (Forge auto-cloned to `~/dailykoan.on-forge.com/current/`)
- [ ] Verify domain DNS points to droplet IP
- [ ] Verify `koan.alvarsirlin.dev` resolves correctly

## Environment Setup

- [ ] Fix directory ownership (if needed)
- [ ] Create Python virtual environment **outside** `current/` (in `~/dailykoan.on-forge.com/venv/`)
- [ ] Install Python dependencies (`pip install -r requirements.txt`)
- [ ] Verify Python 3 + venv available on server

## Asset Generation

- [ ] Run `init_vapid.py` → generates `vapid_private.pem` + `vapid_public.pem`
- [ ] Run `init_db.py` → creates `subscriptions.db`
- [ ] Run `init_icons.py` → generates `static/icon-*.png` + `static/badge-72.png`
- [ ] Verify all generated files exist in `current/`

## nginx Configuration

- [ ] Edit nginx config in Forge UI → replace `location /` with reverse proxy
- [ ] Update static file alias to point to `current/static/`
- [ ] Update manifest/service worker alias to `current/static/`
- [ ] Verify `include forge-conf/{ID}/server/*` line preserved
- [ ] Click Update → nginx validates and reloads
- [ ] Verify no nginx syntax errors

## Gunicorn + Systemd

- [ ] Create `/etc/systemd/system/dailykoan.service`
- [ ] Point `ExecStart` to `~/dailykoan.on-forge.com/venv/bin/gunicorn`
- [ ] Point `WorkingDirectory` to `~/dailykoan.on-forge.com/current/`
- [ ] Set `BASE_URL=https://koan.alvarsirlin.dev/`
- [ ] `systemctl daemon-reload`
- [ ] `systemctl enable dailykoan`
- [ ] `systemctl start dailykoan`
- [ ] `systemctl status dailykoan` → running without errors
- [ ] Verify app responds on `127.0.0.1:8001`

## SSL (Forge)

- [ ] In Forge UI → Site → SSL → Let's Encrypt
- [ ] Verify certbot obtains certificate for `koan.alvarsirlin.dev`
- [ ] Verify HTTPS redirect auto-injected into nginx config
- [ ] Test `curl -I https://koan.alvarsirlin.dev/api/today`
- [ ] Verify SSL auto-renewal scheduled

## Daily Push Timer

- [ ] Create `/etc/systemd/system/dailykoan-push.service`
- [ ] Create `/etc/systemd/system/dailykoan-push.timer`
- [ ] Set `OnCalendar` to desired time (default: `*-*-* 08:00:00`)
- [ ] `systemctl daemon-reload`
- [ ] `systemctl enable dailykoan-push.timer`
- [ ] `systemctl start dailykoan-push.timer`
- [ ] `systemctl list-timers` → timer shows as active
- [ ] Test manual push: `sudo systemctl start dailykoan-push.service`

## End-to-End Testing

- [ ] Open `https://koan.alvarsirlin.dev` in Safari (iOS 16.4+)
- [ ] Verify page loads, koan displays, commentaries toggle
- [ ] Tap Share → Add to Home Screen
- [ ] Open from Home Screen (now in standalone PWA mode)
- [ ] Tap bell icon → allow notifications
- [ ] Verify subscription stored: `curl https://koan.alvarsirlin.dev/api/subscriptions/count`
- [ ] Trigger test push and receive notification on device
- [ ] Tap notification → opens correct koan page

## Documentation Updates

- [ ] Update `docs/001--llm--status.md` with completion status
- [ ] Update `CHANGELOG.md` if any deployment fixes needed
- [ ] Record any deviations from `001--llm--FORGE_DEPLOYMENT.md`

## Post-Deployment

- [ ] Verify existing Statamic site unaffected
- [ ] Verify other Forge-managed sites unaffected
- [ ] Set up manual deploy command or GitHub Action
- [ ] Add `BASE_URL` and `FLASK_DEBUG` to server environment notes
