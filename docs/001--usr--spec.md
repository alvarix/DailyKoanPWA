# Daily Koan PWA — User Specification

Derived from `001--usr--brief.md`

## Phase 1: Daily iOS Notification

- [x] Create an HTML mockup of the koan page for feedback
- [ ] Search existing software (excluded bloated solutions)
- [ ] Serve a random koan daily at a set time as an iOS notification
- [ ] If full text cannot fit in notification, link to a webpage with full text
- [ ] Host on DigitalOcean droplet
- [ ] Stack: Tailwind, HTMX, Alpine, JSON/SQLite (simplicity first)
- [x] Implement PWA (manifest, service worker, offline support)
- [x] Web Push subscription flow (iOS Safari 16.4+)
- [x] Deterministic daily koan selection (same day = same koan)
- [x] VAPID key generation and configuration
- [x] Daily push sender script and cron/systemd wiring
- [ ] HTTPS with nginx + certbot

## Phase 2: Koan Page Enhancements

- [ ] Display metadata: source, commentary, historical context, verse
- [ ] "Next Koan" button
- [ ] Automatic deployment on push (CI/CD)

## Phase 3: Settings & Multi-User

- [ ] Change notification time per user
- [ ] User accounts (simple, no auth complexity)
- [ ] Android push support

## Phase 4: Community Koans

- [ ] Add new koans UI
- [ ] Review process for submitted koans
- [ ] Attribution and commentary by submitter

## Phase 5: Commentary

- [ ] User commentary on any koan
- [ ] Show/hide commentary UI

## Deployment

- [ ] Create GitHub repo
- [ ] Create DigitalOcean droplet
- [ ] Push and configure droplet
- [ ] Test end-to-end notification on iOS
