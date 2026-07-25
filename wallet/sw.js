const CACHE = "larzwallet-v1";
const ASSETS = ["./","index.html","wallet.js","larzwallet_crypto.js","manifest.webmanifest","icon-192.png","icon-512.png"];
self.addEventListener("install", e => { e.waitUntil(caches.open(CACHE).then(c => c.addAll(ASSETS))); self.skipWaiting(); });
self.addEventListener("activate", e => { e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k!==CACHE).map(k => caches.delete(k))))); self.clients.claim(); });
self.addEventListener("fetch", e => {
  const u = new URL(e.request.url);
  if (u.pathname.includes("/larzchain/rpc")) return;         // never cache node API
  e.respondWith(caches.match(e.request).then(r => r || fetch(e.request)));
});
