# Daily Koan PWA — Status

## Phase 1

### Feedback
Mockup: 
- very good
- add tiny h1 at top: Daily Koan 
- h6 by Alvar Sirlin link to alvarsirlin.dev
- All commentary and verse closed by default.
- Add Night mode
- why does the mockup look different from index.html?
  the mockup is better. Never use emoji.

### Completed
- [x] Step-back analysis and spec created
- [x] User spec with checkboxes created
- [x] Backend implementation (Flask + SQLite + Web Push)
- [x] Frontend PWA (Tailwind + Alpine + HTMX) — matching warm paper design
- [x] Service worker and manifest
- [x] VAPID setup
- [x] Daily push sender script
- [x] Deployment automation (systemd + nginx configs described in DEPLOYMENT.md)
- [x] HTML mockup created + refined (warm paper theme)
- [x] Template synced to mockup design
- [x] Local run instructions (RUN.md)
- [x] README + CHANGELOG created

### In Progress
- [ ] Create GitHub repo
- [ ] Create DigitalOcean droplet
- [ ] Push and configure droplet
- [ ] Test end-to-end notification on iOS

### Pending User Feedback
- [ ] Confirm h1 "Daily Koan" + h6 author link design
- [ ] Confirm all commentaries/verse closed by default
- [ ] Confirm night mode toggle
- [ ] Approve before proceeding to deployment

### Blockers
None.

## Notes
- iOS Web Push requires iOS 16.4+, Safari, and PWA added to Home Screen.
- Notification payload limit on iOS is approximately 4KB. Long koans will be truncated with a "Read more" link.
- PWA install is required on iOS for push notifications to work.
