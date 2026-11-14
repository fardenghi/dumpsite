// Imagen satelital de Google (Map Tiles API, tiles 2D). Es opcional: sin VITE_GOOGLE_MAPS_KEY
// la web sigue andando con Sentinel-2. Cada tile se cobra, así que el mapa sólo la pide adentro
// de la caja del sitio abierto y con zoom alto (ver Mapa.tsx).
// Los términos de Google no permiten guardar ni precargar sus tiles: no pasan por el caché de
// public/sw.js; sólo los guarda el navegador según las cabeceras de la respuesta.
// Documentación: https://developers.google.com/maps/documentation/tile/satellite
const KEY = import.meta.env.VITE_GOOGLE_MAPS_KEY as string | undefined
const BASE = 'https://tile.googleapis.com'
const GUARDADA = 'insomnes.google.sesion'

export const HAY_GOOGLE = !!KEY

let sesion: Promise<string> | null = null

/** Token de sesión de la Map Tiles API. Dura unas dos semanas y se reutiliza entre visitas. */
export function sesionGoogle(): Promise<string> {
  sesion ??= (async () => {
    try {
      const g = JSON.parse(localStorage.getItem(GUARDADA) ?? 'null') as { token: string; vence: number } | null
      if (g && g.vence > Date.now() / 1000 + 3600) return g.token
    } catch {
      // sin localStorage se pide una sesión nueva
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

/** Texto de copyright que Google exige mostrar para la zona visible. */
export async function creditoGoogle(token: string, zoom: number, [o, s, e, n]: [number, number, number, number]): Promise<string> {
  const r = await fetch(`${BASE}/tile/v1/viewport?session=${token}&key=${KEY}&zoom=${Math.round(zoom)}&north=${n}&south=${s}&east=${e}&west=${o}`)
  if (!r.ok) return ''
  return ((await r.json()) as { copyright?: string }).copyright ?? ''
}
