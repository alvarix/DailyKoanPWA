/**
 * Service Worker for Daily Koan PWA.
 * Handles push notifications and basic caching.
 */

const CACHE_NAME = 'daily-koan-v5';
const urlsToCache = [
  '/',
  '/static/manifest.json'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(urlsToCache))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', event => {
  // Network-first for navigation, cache for static assets
  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request).catch(() => caches.open(CACHE_NAME).then(cache => cache.match('/')))
    );
    return;
  }
  event.respondWith(
    caches.open(CACHE_NAME).then(cache => cache.match(event.request)).then(response => {
      return response || fetch(event.request);
    })
  );
});

/** Report a capability-bound stage without delaying display. */
async function reportPush(token, stage) {
  if (typeof token !== 'string' || !/^[a-f0-9]{48}$/.test(token)) return;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 3000);
  try {
    await fetch('/api/push-receipt', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token, stage }), credentials: 'omit', signal: controller.signal
    });
  } catch { /* A missing receipt does not imply a missing notification. */ }
  finally { clearTimeout(timer); }
}

/** Resolve the notification locally, including while the app is closed. */
async function showKoanNotification(event) {
  let data = {};
  try { data = event.data?.json() || {}; } catch {
    data = { body: event.data?.text() };
  }

  const received = reportPush(data.trace, 'received');
  let body = data.body || 'Your koan awaits.';
  try {
    const cache = await caches.open('daily-koan-notification-v1');
    const record = await cache.match('/__dk_notification__');
    const snapshot = record && await record.json();
    if (snapshot?.mode === 'held' && snapshot.body) body = snapshot.body;
    if (snapshot?.mode === 'daily' && data.dailyBody) body = data.dailyBody;
  } catch { /* Still show a visible notification if storage was cleared. */ }

  try {
    await self.registration.showNotification('', {
    body,
    icon: data.icon || '/static/icon-192.png',
    badge: data.badge || '/static/badge-72.png',
    data: { url: '/' },
    tag: 'daily-koan',
    renotify: false,
    requireInteraction: false
    });
  } catch (error) {
    await Promise.all([received, reportPush(data.trace, 'display_failed')]);
    throw error;
  }
  await Promise.all([received, reportPush(data.trace, 'display_requested')]);
}

self.addEventListener('push', event => {
  event.waitUntil(showKoanNotification(event));
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  const url = event.notification.data?.url || '/';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(clientList => {
      for (const client of clientList) {
        if (client.url === url && 'focus' in client) {
          return client.focus();
        }
      }
      if (clients.openWindow) {
        return clients.openWindow(url);
      }
    })
  );
});
