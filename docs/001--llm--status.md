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

### In Progress
- [ ] Backend implementation (Flask + SQLite + Web Push)
- [ ] Frontend PWA (Tailwind + Alpine + HTMX)
- [ ] Service worker and manifest
- [ ] VAPID setup
- [ ] Deployment automation

### Blockers
None.

## Notes
- iOS Web Push requires iOS 16.4+, Safari, and PWA added to Home Screen.
- Notification payload limit on iOS is approximately 4KB. Long koans will be truncated with a "Read more" link.
