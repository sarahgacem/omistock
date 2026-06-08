/**
 * OMISTOCK — Service Worker
 * Stratégie Stale-While-Revalidate (SWR) pour l'app mobile terrain.
 */

const CACHE_NAME = 'omistock-cache-v2';

/** Fichiers locaux + CDN + polices Google (chemins relatifs au dossier /app/) */
const PRECACHE_URLS = [
  './app_mobile.html',
  './mobile_scan.html',
  './style.css',
  './erp-sidebar.js',
  './manifest.json',
  './icon-192.png',
  './icon-512.png',
  'https://cdn.tailwindcss.com',
  'https://unpkg.com/html5-qrcode',
  'https://unpkg.com/feather-icons',
  'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap',
  'https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap',
];

/**
 * @param {Request} request
 * @returns {boolean}
 */
function shouldUseCacheStrategy(request) {
  if (request.method !== 'GET') return false;
  const url = new URL(request.url);
  if (url.origin === self.location.origin && url.pathname.startsWith('/api')) {
    return false;
  }
  return true;
}

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(CACHE_NAME)
      .then((cache) =>
        Promise.allSettled(
          PRECACHE_URLS.map((url) =>
            cache.add(new Request(url, { cache: 'reload' }))
          )
        )
      )
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((key) => key !== CACHE_NAME)
            .map((key) => caches.delete(key))
        )
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  if (!shouldUseCacheStrategy(event.request)) return;

  event.respondWith(staleWhileRevalidate(event.request));
});

/**
 * SWR : réponse cache immédiate si disponible, mise à jour réseau en arrière-plan.
 * @param {Request} request
 * @returns {Promise<Response>}
 */
async function staleWhileRevalidate(request) {
  const cache = await caches.open(CACHE_NAME);
  const cachedResponse = await cache.match(request);

  const networkPromise = fetch(request)
    .then((networkResponse) => {
      if (networkResponse && networkResponse.status === 200) {
        cache.put(request, networkResponse.clone());
      }
      return networkResponse;
    })
    .catch(() => undefined);

  if (cachedResponse) {
    networkPromise.catch(() => {});
    return cachedResponse;
  }

  const networkResponse = await networkPromise;
  if (networkResponse) {
    return networkResponse;
  }

  return (
    (await cache.match('./app_mobile.html')) ||
    new Response('Hors ligne — ressource indisponible.', {
      status: 503,
      statusText: 'Service Unavailable',
      headers: { 'Content-Type': 'text/plain; charset=utf-8' },
    })
  );
}
