# Step-Back Analysis

## Phase 1: Step-Back Analysis

### 1. Problem Classification
This is a **scheduled notification + static content delivery** problem. The core challenge is reliably triggering a daily push notification to subscribed iOS devices with random content from a JSON dataset, while serving a lightweight PWA to view the full text when the notification payload is truncated.

### 2. Governing Principles
- **KISS (Keep It Simple, Stupid):** The user explicitly requested simplicity and ease of maintenance.
- **Single Responsibility:** Each component (scheduler, pusher, server, frontend) does one thing.
- **Idempotency:** The "daily koan" should be deterministic per day (same seed/date = same koan), not truly random, so all users see the same koan on the same day.
- **Progressive Enhancement:** Core functionality works without push; push is an enhancement.

### 3. Data Structures & Complexity
- **Data source:** `koans.json` (14 records). O(1) read, O(1) lookup by index.
- **Subscriptions:** SQLite table `subscriptions` with `endpoint`, `p256dh`, `auth`, `created_at`. O(n) scan for broadcast.
- **Deterministic daily selection:** `koan_index = hash(date) % count(koans)`. O(1).
- **Push broadcast:** Sequential loop over subscriptions. O(n) where n = subscriber count.

## Phase 2: Edge Cases & Architecture

### Edge Cases
1. **iOS Web Push limitations:** Safari iOS 16.4+ only; requires PWA installed to Home Screen; notification payload max ~4KB. We must truncate gracefully and link to the web page.
2. **Expired/invalid subscriptions:** Subscriptions can become invalid (user disabled notifications, uninstalled PWA). We must catch `GoneException`/`InvalidState` and remove dead subscriptions.
3. **No subscribers on notification time:** The scheduler fires, but if zero subscriptions exist, it should noop cleanly without error.
4. **Service worker updates:** Browser may cache old service worker. We must use `skipWaiting`/`clientsClaim` and version the SW.
5. **HTTPS requirement:** Web Push requires HTTPS on iOS. Local dev must use a tunnel or localhost exception, and prod must have valid TLS.

### Architectural Pattern
**Server-Push PWA with Cron Scheduler.** A lightweight Python Flask backend serves the PWA and API, stores push subscriptions in SQLite, and a systemd timer triggers a daily script to broadcast the koan via Web Push (VAPID). The frontend is a minimal PWA using Tailwind, HTMX, and Alpine.js.

## Phase 3: Optimized Implementation

### Stack
- **Backend:** Python 3.11+, Flask, pywebpush, gunicorn
- **Database:** SQLite (subscriptions)
- **Frontend:** Tailwind CSS (CDN), Alpine.js (CDN), HTMX (CDN)
- **Push:** Web Push API (VAPID)
- **Deployment:** Ubuntu 24.04, nginx, systemd, certbot, cron/systemd timer

### Code
See project root for implementation.

### Summary
This implementation honors the Step-Back Analysis by keeping the stack minimal (Flask + SQLite + CDN libs), using deterministic daily koan selection so all users see the same teaching, and handling iOS Web Push constraints (truncated payloads with deep links, HTTPS, PWA requirements) through a service worker with explicit `skipWaiting`. The scheduler is a standalone script decoupled from the web server, allowing independent scaling and failure isolation.
