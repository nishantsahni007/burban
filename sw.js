// Burban service worker: offline support + a daily background check for alerts.
const CACHE = 'burban-v2';
const SHELL = ['./', 'index.html', 'manifest.webmanifest', 'icons/icon-192.png', 'icons/icon-512.png'];
const GROUP_LIVE = { live: true, likely: true };

self.addEventListener('install', e => { e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL))); self.skipWaiting(); });
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))));
  self.clients.claim();
});

// App shell from cache; data always tried fresh first (falls back to cache when offline).
self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.origin !== location.origin) return;
  if (url.pathname.includes('/data/')) {
    e.respondWith(fetch(e.request).then(r => { if (r.ok) { const c = r.clone(); caches.open(CACHE).then(x => x.put(e.request, c)); } return r; })
      .catch(() => caches.match(e.request)));
    return;
  }
  e.respondWith(caches.match(e.request).then(hit => hit || fetch(e.request)));
});

// ---- alerts: same data the page saves, kept in IndexedDB so this worker can read it ----
function idb() { return new Promise((res, rej) => { const r = indexedDB.open('burban', 1); r.onupgradeneeded = () => r.result.createObjectStore('kv'); r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error); }); }
async function kv(key, value) {
  const db = await idb();
  return new Promise((res, rej) => {
    const t = db.transaction('kv', value === undefined ? 'readonly' : 'readwrite'), s = t.objectStore('kv');
    const r = value === undefined ? s.get(key) : s.put(value, key);
    t.oncomplete = () => res(r.result); t.onerror = () => rej(t.error);
  });
}

async function checkAlerts() {
  const alerts = (await kv('alerts')) || [];
  const pending = alerts.filter(a => !a.done);
  if (!pending.length) return;
  const files = {};
  let changed = false;
  for (const a of pending) {
    try {
      files[a.cid] = files[a.cid] || await fetch(`data/city/${a.cid}.json`, { cache: 'no-cache' }).then(r => r.ok ? r.json() : { d: {}, a: {} });
      const f = files[a.cid], v = (f.a[a.pid] || {})[a.sid] || f.d[a.sid] || ['no'];
      if (GROUP_LIVE[v[0]]) {
        a.done = true; a.doneAt = Date.now(); changed = true;
        await self.registration.showNotification('Now available near you', {
          body: `${a.svc} is now available in ${a.place}`, icon: 'icons/icon-192.png',
          tag: a.sid + '@' + a.pid, data: { url: './#' + a.pid } });
      }
    } catch (e) { /* offline or file missing: try again next time */ }
  }
  if (changed) await kv('alerts', alerts);
}

self.addEventListener('periodicsync', e => { if (e.tag === 'burban-check') e.waitUntil(checkAlerts()); });

self.addEventListener('notificationclick', e => {
  e.notification.close();
  const url = new URL((e.notification.data && e.notification.data.url) || './', self.registration.scope).href;
  e.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(list => {
    for (const c of list) { if ('focus' in c) { c.navigate(url); return c.focus(); } }
    return self.clients.openWindow(url);
  }));
});
