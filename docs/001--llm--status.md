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

## Phase 2 — Deployment runbooks (2026-11-05)

### Completed
- [x] Step-back analysis + peer review (plan-review: gemini-2.5-pro, 1 of 2 reviewers; all critiques incorporated)
- [x] docs/002--llm--STANDALONE_DROPLET_DEPLOYMENT.md — fresh separate-droplet deploy, isolated from alfaForge; paired usr checklist created
- [x] docs/003--llm--MIGRATE_TO_FORGE.md — later switch standalone -> Forge, same-as-wmw pattern (body-only fragment, Forge SSL), zero-downtime-ordered with exact rollback; paired usr checklist created

### In Progress (execution, separate sessions)
- [ ] Execute 002: create droplet, deploy, end-to-end iOS push test
- [ ] After 2+ boring weeks on the standalone droplet: decide whether to execute 003 (re-enters Forge shared failure domain to save $6/mo)

### Blockers
None. Unknowns flagged inside each doc (DNS provider, GitHub repo URL, wmw project type in Forge UI, Forge template re-render behavior).

## Notes
- iOS Web Push requires iOS 16.4+, Safari, and PWA added to Home Screen.
- Notification payload limit on iOS is approximately 4KB. Long koans will be truncated with a "Read more" link.
- PWA install is required on iOS for push notifications to work.
