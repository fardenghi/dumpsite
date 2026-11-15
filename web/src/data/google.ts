import { useSyncExternalStore } from 'react'
// Google satellite imagery (Map Tiles API, 2D tiles). It's optional: without VITE_GOOGLE_MAPS_KEY
// the web keeps working with Sentinel-2. Each tile is billed, so the map only requests it inside
// the box of the open site and at high zoom (see Mapa.tsx).
// Google's terms don't allow storing or prefetching their tiles: they don't go through the
// public/sw.js cache; only the browser keeps them according to the response headers.
// Docs: https://developers.google.com/maps/documentation/tile/satellite
const KEY = import.meta.env.VITE_GOOGLE_MAPS_KEY as string | undefined
const BASE = 'https://tile.googleapis.com'
const GUARDADA = 'insomnes.google.sesion'
const LIMITE = 'dumpsite.google.limite'

// Daily quota of the Map Tiles API. When it runs out Google answers 429 until the quota resets, at midnight
// Pacific time. We remember the reset time so the web stops asking (and shows a notice) until then.
let reinicio = 0
try {
  reinicio = Number(localStorage.getItem(LIMITE)) || 0
} catch {
  // without localStorage it's only remembered for this visit
}
const oyentes = new Set<() => void>()

/** Next midnight in Pacific time (when Google resets daily quotas), as a Date in the viewer's clock. */
export function proximoReinicio(ahora = new Date()): Date {
  const partes = Object.fromEntries(
    new Intl.DateTimeFormat('en-US', { timeZone: 'America/Los_Angeles', year: 'numeric', month: 'numeric', day: 'numeric', hour: 'numeric', minute: 'numeric', second: 'numeric', hourCycle: 'h23' })
      .formatToParts(ahora)
      .map((p) => [p.type, Number(p.value)]),
  )
  const pared = Date.UTC(partes.year, partes.month - 1, partes.day, partes.hour, partes.minute, partes.second)
  const desfase = Math.round((pared - ahora.getTime()) / 60000) * 60000
  return new Date(Date.UTC(partes.year, partes.month - 1, partes.day + 1) - desfase)
}

/** Called when Google answers 429: the daily quota is used up. */
export function marcarLimite() {
  if (enLimite()) return
  reinicio = proximoReinicio().getTime()
  try {
    localStorage.setItem(LIMITE, String(reinicio))
  } catch {
    // idem
  }
  oyentes.forEach((f) => f())
}

/** true while the daily quota is used up. */
export const enLimite = () => Date.now() < reinicio

/** The reset time while the quota is used up, or null. Re-renders when the limit is hit. */
export function useLimiteGoogle(): Date | null {
  const valor = useSyncExternalStore(
    (f) => {
      oyentes.add(f)
      return () => oyentes.delete(f)
    },
    () => (enLimite() ? reinicio : 0),
  )
  return valor ? new Date(valor) : null
}

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
    if (r.status === 429) marcarLimite()
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
