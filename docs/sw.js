// Permite abrir la app sin internet mostrando los últimos datos guardados.
const CACHE = "trading-v11";
const BASE = ["./", "index.html", "manifest.json", "icono-192.png", "icono-512.png", "icono-maskable-512.png", "apple-touch-icon.png"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(BASE)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  // siempre intenta la red primero (datos y app nuevos); si no hay internet, usa lo guardado
  const clave = url.pathname.endsWith("data.json") ? new Request(url.origin + url.pathname) : e.request;
  e.respondWith(
    fetch(e.request).then(r => {
      if (r.ok) { const copia = r.clone(); caches.open(CACHE).then(c => c.put(clave, copia)); }
      return r;
    }).catch(() => caches.match(clave).then(r => r || caches.match("index.html")))
  );
});
