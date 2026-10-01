/**
 * Service Worker for Daily Koan PWA.
 * Handles push notifications and basic caching.
 */

const CACHE_NAME = 'daily-koan-v1';
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
      fetch(event.request).catch(() => caches.match('/'))
    );
    return;
  }
  event.respondWith(
    caches.match(event.request).then(response => {
      return response || fetch(event.request);
    })
  );
});

self.addEventListener('push', event => {
  let payload;
  try {
    payload = event.data.json();
  } catch (e) {
    payload = event.data.text();
  }

  const data = typeof payload === 'string' ? { title: 'Daily Koan', body: payload } : payload;

  const title = data.title || 'Daily Koan';
  const options = {
    body: data.body || 'A new koan awaits.',
    icon: data.icon || '/static/icon-192.png',
    badge: data.badge || '/static/badge-72.png',
    data: data.data || { url: '/' },
    tag: 'daily-koan',
    renotify: false,
    requireInteraction: false
  };

  event.waitUntil(
    self.registration.showNotification(title, options)
  );
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
