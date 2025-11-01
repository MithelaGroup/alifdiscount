const CACHE = 'sds-v1';
const ASSETS = [
  '/', '/dashboard',
  '/static/styles.css',
  '/static/app.js',
  '/static/manifest.webmanifest'
];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(ASSETS)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', e => {
  e.respondWith(
    caches.match(e.request).then(r => r || fetch(e.request).then(resp => {
      // Cache GETs
      if (e.request.method === 'GET' && resp.status === 200 && resp.type === 'basic') {
        const copy = resp.clone();
        caches.open(CACHE).then(c => c.put(e.request, copy));
      }
      return resp;
    }).catch(() => caches.match('/dashboard')))
  );
});

// Show push notifications
self.addEventListener('push', event => {
  let data = {};
  try { data = event.data.json(); } catch(e) {}
  const title = data.title || 'Special Discount';
  const body = data.body || '';
  const url = data.url || '/dashboard';
  event.waitUntil(self.registration.showNotification(title, { body, data: { url } }));
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  const url = event.notification.data?.url || '/dashboard';
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(clientList => {
      for (const client of clientList) {
        if (client.url.includes(url) && 'focus' in client) return client.focus();
      }
      if (clients.openWindow) return clients.openWindow(url);
    })
  );
});
