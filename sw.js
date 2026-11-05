/* Geedo's app shell, kept for offline opening. Network first: a page or a
   file comes from the Hub when it can, from the cache when it cannot. The
   manifests and animations are never cached here - the robot's own copies
   are the ones that matter, and the page asks the Hub fresh every time. */
const SHELL = 'geedo-shell-v1';
const FILES = ['settings.html', 'assets/geedo.css', 'assets/geedolink.js', 'assets/logo.png', 'assets/favicon.png',
               'assets/app/icon-192.png', 'assets/app/icon-512.png'];
self.addEventListener('install', e => {
  e.waitUntil(caches.open(SHELL).then(c => c.addAll(FILES)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== SHELL).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.origin !== location.origin) return;
  if (/\/animations\/|\/firmware\//.test(url.pathname)) return;        // always fresh
  e.respondWith(fetch(e.request).then(r => {
    if (r.ok) caches.open(SHELL).then(c => c.put(e.request, r.clone()));
    return r;
  }).catch(() => caches.match(e.request)));
});
