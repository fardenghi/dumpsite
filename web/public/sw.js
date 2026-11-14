// Caché de las imágenes abiertas del mapa: Blue Marble (NASA GIBS), Sentinel-2 (Planetary
// Computer) y los recortes guardados en /escenas/. Primero el caché y después la red, así las
// zonas de los basurales, que son las que se recorren siempre, cargan al instante y sin conexión.
// Los tiles de Google quedan afuera a propósito: sus términos no permiten guardarlos.
const CACHE = 'insomnes-mapa-v1'
const MAX = 4000 // entradas; al pasarse se borran las más viejas

const guardable = (url) =>
  url.hostname === 'gibs.earthdata.nasa.gov' ||
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
