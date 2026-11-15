// Google satellite imagery (Map Tiles API, 2D tiles). It's optional: without VITE_GOOGLE_MAPS_KEY
// the web keeps working with Sentinel-2. Each tile is billed, so the map only requests it inside
// the box of the open site and at high zoom (see Mapa.tsx).
// Google's terms don't allow storing or prefetching their tiles: they don't go through the
// public/sw.js cache; only the browser keeps them according to the response headers.
// Docs: https://developers.google.com/maps/documentation/tile/satellite
const KEY = import.meta.env.VITE_GOOGLE_MAPS_KEY as string | undefined
const BASE = 'https://tile.googleapis.com'
const GUARDADA = 'insomnes.google.sesion'

export const HAY_GOOGLE = !!KEY

let sesion: Promise<string> | null = null

/** Map Tiles API session token. It lasts about two weeks and is reused between visits. */
export function sesionGoogle(): Promise<string> {
  sesion ??= (async () => {
    try {
      const g = JSON.parse(localStorage.getItem(GUARDADA) ?? 'null') as { token: string; vence: number } | null
      if (g && g.vence > Date.now() / 1000 + 3600) return g.token
    } catch {
      // without localStorage a new session is requested
    }
    const r = await fetch(`${BASE}/v1/createSession?key=${KEY}`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ mapType: 'satellite', language: 'es-419', region: 'AR' }),
    })
    if (!r.ok) throw new Error(`Google createSession ${r.status}`)
    const j = (await r.json()) as { session: string; expiry: string }
    try {
      localStorage.setItem(GUARDADA, JSON.stringify({ token: j.session, vence: Number(j.expiry) }))
    } catch {
      // idem
    }
    return j.session
  })()
  sesion.catch(() => (sesion = null))
  return sesion
}

export const tilesGoogle = (token: string) => `${BASE}/v1/2dtiles/{z}/{x}/{y}?session=${token}&key=${KEY}`

/** Copyright text that Google requires to show for the visible area. */
export async function creditoGoogle(token: string, zoom: number, [o, s, e, n]: [number, number, number, number]): Promise<string> {
  const r = await fetch(`${BASE}/tile/v1/viewport?session=${token}&key=${KEY}&zoom=${Math.round(zoom)}&north=${n}&south=${s}&east=${e}&west=${o}`)
  if (!r.ok) return ''
  return ((await r.json()) as { copyright?: string }).copyright ?? ''
}
