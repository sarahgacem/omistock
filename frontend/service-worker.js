const CACHE_NAME = 'omistock-v1';
const STATIC_ASSETS = [
  '/app/dashboard.html',
  '/app/inventory.html',
  '/app/sales.html',
  '/app/reports.html',
  '/app/logs.html',
  '/app/suppliers.html',
  '/app/settings.html',
  '/app/mobile_scan.html',
  '/app/index.html',
  '/app/manifest.json'
];

// Installation : mise en cache des ressources statiques
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      return cache.addAll(STATIC_ASSETS);
    })
  );
  self.skipWaiting();
});

// Activation : suppression des anciens caches
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

// Fetch : stratégie Network First pour l'API, Cache First pour les statiques
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // Requêtes API → toujours réseau (pas de cache)
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/token')) {
    return;
  }

  // Ressources statiques → Cache First avec fallback réseau
  event.respondWith(
    caches.match(event.request).then(cached => {
      if (cached) return cached;
      return fetch(event.request).then(response => {
        if (response && response.status === 200) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
        }
        return response;
      }).catch(() => cached);
    })
  );
});
