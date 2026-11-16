# Daily Koan PWA — Android Notification Brief (Doc 004)

Version: 004 — llm  
Status: ANALYSIS + RECOMMENDATIONS — no code changes yet.  
Answers the question: how does the current Web Push pipeline behave on Android, and what small, scoped changes would make it behave better?  
Related: `static/sw.js`, `push_sender.py`, `static/manifest.json`, docs/adr/push-pipeline.md, docs/adr/frontend.md, docs/002--llm--TWEAKS.md.

---

## Phase 1: Step-Back Analysis

### 1. Problem Classification

This is a **mobile operating-system notification-delivery problem** for a Web Push PWA. The app does not control Android's notification surface directly; it sends a signed Web Push payload to the browser's push endpoint, and Android (via Chrome's notification channel or the installed WebAPK) renders the resulting system notification. The work is therefore not "build an Android notification" but **tune the Web Push payload and service-worker options so Android renders the alert the way the user expects**.

### 2. Governing Principles

- **Progressive enhancement** — notifications still work in the browser tab; installed-PWA polish is an improvement, not a gate.
- **Least surprise** — one koan per day, one alert; the user should hear/feel the arrival and land on the right koan when tapping.
- **OS-channel semantics** — `tag`, `renotify`, `requireInteraction`, `vibrate`, and icon assets are the actual levers on Android, not the payload content alone.
- **Do not outrun the evidence** — this is a single-subscriber personal PWA; native-Android/FCM work is over-engineering until that changes.

### 3. Data Structures & Complexity

- **Payload:** plain JSON object `{ body, icon, badge, data: { url } }`, built by `push_sender.py` and byte-truncated to ~3000 UTF-8 bytes.
- **Notification options:** object in `static/sw.js` `push` handler; O(1) to construct.
- **Android channel behavior:** determined by the browser/OS pairing (Chrome channel vs. WebAPK channel), not by app code.
- **Click handling:** `notificationclick` in the SW finds or opens the target URL; O(1) URL lookup.

---

## Phase 2: Edge Cases & Architecture

### Edge Cases

1. **Same-tag suppression.** `static/sw.js` currently uses `tag: 'daily-koan'` and `renotify: false`. On Android, replacing an existing notification with the same tag and `renotify: false` produces **no sound, vibration, or heads-up alert**. A user who leaves yesterday's koan in the shade may not notice today's arrival.
2. **Browser-vs-installed-PWA channel mismatch.** If the user has not added the PWA to the Home Screen, Android routes the alert through Chrome's notification channel. If it is installed, the alert uses the app's own WebAPK channel. Permission prompts, importance levels, and icon treatment differ between the two.
3. **Adaptive icon cropping.** Android launchers and the notification shade crop icons to manufacturer-specific shapes (circle, squircle, rounded rectangle). The current `/static/icon-192.png` may lose content around the edges if it was designed for a square canvas with tight margins.
4. **Battery/background restrictions.** Samsung, Xiaomi, OnePlus, and others throttle or suspend background browser processes. A Web Push event that reaches the device can still be dropped if Chrome cannot wake the service worker before the OS kills it.
5. **Badge color/contrast.** The `/static/badge-72.png` is used as the status-bar icon. Android expects a small, high-contrast, mostly-white-on-transparent monochrome icon. A colorful or detailed badge renders as an indistinct gray blob on some devices.

### Architectural Pattern

**Standard Web Push + defensive client rendering.** Keep the server-side pipeline exactly as the push-pipeline ADR specifies (timer is the only sender, `push_sender.py` builds the payload, VAPID signs it). All Android-specific tuning lives inside `static/sw.js`, which is the single place the notification is actually shown. This matches the existing pattern: the server is push-agnostic; the SW owns the UX surface.

---

## Phase 3: Optimized Implementation / Recommendations

### Current State (verified against 0.1.6)

| Piece | Today | File |
| --- | --- | --- |
| Push payload | `body` only; `icon`, `badge`, `data.url` | `push_sender.py` |
| Notification options | `tag: 'daily-koan'`, `renotify: false`, `requireInteraction: false` | `static/sw.js` |
| Click behavior | Focus existing tab matching `data.url`, else `clients.openWindow(url)` | `static/sw.js` |
| Manifest | `display: standalone`, `theme_color`/`background_color` `#1c1917` | `static/manifest.json` |

This already works on Android; the recommendations below are tuning, not surgery.

### Recommendation 1: make each day's alert re-alert

Use a date-derived tag (`daily-koan-YYYY-MM-DD`) so today's notification is a **new** notification, and set `renotify: true` as a fallback. Either change fixes the silent-replacement problem. A dated tag is preferred because it is explicit and preserves the mental model of "one new item per day."

```js
const today = new Date().toISOString().slice(0, 10);
const options = {
  body: data.body || 'A new koan awaits.',
  icon: data.icon || '/static/icon-192.png',
  badge: data.badge || '/static/badge-72.png',
  data: data.data || { url: '/' },
  tag: `daily-koan-${today}`,
  renotify: true,
  requireInteraction: false,
  // vibrate: [200, 100, 200] // optional; see Rec 3
};
```

### Recommendation 2: test and possibly replace the badge asset

The badge must survive being scaled to ~24dp and rendered in Android's status bar. Borrow a real device test: send a push, pull down the shade, and inspect the small icon. If it is muddy, provide a simplified white silhouette at 96x96 or 72x72 with transparent background.

### Recommendation 3: add a short, conservative vibration pattern

`vibrate: [200, 100, 200]` adds tactile signal without being intrusive. It is ignored on devices that have vibration disabled and harmless elsewhere. Keep it optional or make it a follow-on preference only if the user asks; default vibration for a daily koan is reasonable.

### Recommendation 4: keep the deep-link click handler as is

The existing `notificationclick` handler is correct for Android: focus an already-open tab or open the koan URL. No change needed. If Recommendation 1 is adopted, the `data.url` already points to `/koan/{idx}` today.

### Recommendation 5: verify the app icon under adaptive cropping

Check `/static/icon-192.png` and `/static/icon-512.png` on an actual Android Home Screen. If the cat icon or text gets cropped, add safe padding or provide a dedicated maskable icon (`purpose: "maskable"` in the manifest) so Android uses it for notifications and launcher icons. This is the only recommendation that touches the manifest:

```json
{
  "src": "/static/icon-192-maskable.png",
  "sizes": "192x192",
  "type": "image/png",
  "purpose": "maskable"
}
```

### What Not to Do

- **Do not add a native Android app or FCM.** Web Push is the right abstraction for one subscriber; FCM adds backend complexity and a Google dependency for no reliability gain at this scale.
- **Do not add action buttons yet.** There is no clear action other than "Open," and Android action buttons add UI clutter. Revisit if the app later supports "Mark read" or "Share."

### Testing Classification (per repo rule)

These changes are **Mode 1 — needs remote testing on a real Android device**. Badge, icon cropping, vibration, and tag/renotify behavior cannot be verified in the desktop browser or the unit suite. After any code change: document, commit, push, then run a device-side checklist.

### Rollout / Runbook Suggestion

1. Make the `sw.js` and optional manifest changes in a local branch.
2. Run the existing unit suite: `venv/bin/python -m unittest discover -s tests`.
3. Deploy to dkStandalone using runbook 9.2 (DB backup, `git pull`, `systemctl restart dailykoan`).
4. On an Android phone:
   - Open the PWA, ensure notifications are allowed.
   - Trigger a test push (via `sudo systemctl start dailykoan-push` or a manual `python push_sender.py` run).
   - Verify: sound/vibration occurs, status-bar badge is crisp, shade icon is not cropped, tap opens `/koan/{idx}`.
   - Leave the notification overnight and confirm the next day's push produces a second, new alert (not a silent update).

### Summary

Android notification behavior for Daily Koan is governed almost entirely by the Web Notification API options inside `static/sw.js`, where the current same-tag/renotify-false combination risks silently suppressing new daily alerts. The smallest high-value fix is to use a date-stamped tag plus `renotify: true`, verify the badge and icon assets on a real device, and optionally add a short vibration pattern. This keeps the server-side push-pipeline ADR untouched while giving Android users the audible, tactile arrival the design intends.

---

## For Dummies

The phone gets a daily text message from the website through the browser's push system. Right now, if yesterday's message is still sitting in the notification shade, Android thinks today's message is the same old thing and might not buzz or beep. The fix is to label each day's message with the date so Android treats it as brand new. Then we check that the little icon in the status bar looks crisp and that the big icon doesn't get its ears chopped off by the phone's round-corner cropping. No new app store, no Google Firebase, no big rewrite — just the service-worker file and maybe one new icon.
