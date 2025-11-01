const CACHE_NAME = "alif-discount-v1";
const CORE = ["/", "/static/app.css", "/static/pwa.js", "/static/manifest.webmanifest"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE_NAME).then((c) => c.addAll(CORE)));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))))
  );
});
self.addEventListener("fetch", (e) => {
  const { request } = e;
  if (request.method !== "GET") return;
  e.respondWith(
    caches.match(request).then((hit) => hit || fetch(request).then((res) => {
      const resClone = res.clone();
      caches.open(CACHE_NAME).then((c) => c.put(request, resClone));
      return res;
    }).catch(() => hit))
  );
});
