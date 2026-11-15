// Cache of the map images already opened: Blue Marble (NASA GIBS), Sentinel-2 (Planetary
// Computer) and the crops stored in /escenas/. Cache first and network second, so the
// dump-site areas, which are the ones people always browse, load instantly and offline.
// Google tiles are left out on purpose: their terms don't allow storing them.
const CACHE = 'insomnes-mapa-v1'
const MAX = 4000 // entries; when exceeded, the oldest are deleted

const guardable = (url) =>
  url.hostname === 'gibs.earthdata.nasa.gov' ||
  url.hostname === 'tiles.maps.eox.at' ||
  (url.hostname === 'planetarycomputer.microsoft.com' && url.pathname.includes('/tiles/')) ||
  (url.origin === self.location.origin && url.pathname.includes('/escenas/'))

self.addEventListener('install', () => self.skipWaiting())
self.addEventListener('activate', (e) =>
  e.waitUntil(
    caches
      .keys()
      .then((claves) => Promise.all(claves.filter((c) => c.startsWith('insomnes-mapa-') && c !== CACHE).map((c) => caches.delete(c))))
      .then(() => self.clients.claim()),
  ),
)

async function podar(cache) {
  const claves = await cache.keys()
  for (const c of claves.slice(0, Math.max(0, claves.length - MAX))) await cache.delete(c)
}

self.addEventListener('fetch', (e) => {
  if (e.request.method !== 'GET' || !guardable(new URL(e.request.url))) return
  e.respondWith(
    caches.open(CACHE).then(async (cache) => {
      const guardada = await cache.match(e.request.url)
      if (guardada) return guardada
      const r = await fetch(e.request)
      if (r.ok) {
        await cache.put(e.request.url, r.clone())
        if (Math.random() < 0.02) podar(cache)
      }
      return r
    }),
  )
})
