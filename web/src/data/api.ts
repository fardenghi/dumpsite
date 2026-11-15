// Single gateway to the data. Today it reads the seed; with VITE_API_URL set it calls the backend.
// Expected backend contract:
//   GET /sitios  -> Sitio[]   (ver types.ts)
// The summary is computed here: a few thousand rows at most.
import { useEffect, useState } from 'react'
import { conUmbralBajo, type Resumen, type Sitio } from './types'

const API = import.meta.env.VITE_API_URL as string | undefined

/** true while there's no backend: the UI says so. */
export const DEMO = !API

let cache: Promise<Sitio[]> | null = null

export function getSitios(): Promise<Sitio[]> {
  cache ??= (
    API
      ? fetch(`${API}/sitios`).then((r) => {
          if (!r.ok) throw new Error(`GET /sitios ${r.status}`)
          return r.json() as Promise<Sitio[]>
        })
      : import('./seed').then((m) => m.SITIOS)
  ).then((sitios) => sitios.map(conUmbralBajo))
  return cache
}

export function resumen(sitios: Sitio[]): Resumen {
  const fechas = sitios.flatMap((s) => s.pares.map((p) => p.fecha)).sort()
  return {
    sitios: sitios.length,
    despiertos: sitios.filter((s) => s.radar === 'despierto').length,
    paises: new Set(sitios.map((s) => s.pais)).size,
    hectareas: sitios.reduce((a, s) => a + s.ha, 0),
    pares: Math.max(0, ...sitios.map((s) => s.pares.length)),
    desde: fechas[0] ?? '',
    hasta: fechas[fechas.length - 1] ?? '',
  }
}

export function useSitios() {
  const [sitios, setSitios] = useState<Sitio[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    let vivo = true
    getSitios().then(
      (s) => vivo && setSitios(s),
      (e: Error) => vivo && setError(e.message),
    )
    return () => {
      vivo = false
    }
  }, [])
  return { sitios, error }
}

export function aCsv(sitios: Sitio[]): string {
  const cols = ['id', 'nombre', 'lugar', 'pais', 'lat', 'lon', 'hectareas', 'registro', 'cierre', 'radar', 'insomnio']
  const celda = (v: string | number | undefined) => {
    const t = v == null ? '' : String(v)
    return /[",\n]/.test(t) ? `"${t.replace(/"/g, '""')}"` : t
  }
  const filas = sitios.map((s) => [s.id, s.nombre, s.lugar, s.pais, s.lat, s.lon, s.ha, s.registro, s.cierre, s.radar, s.insomnio].map(celda).join(','))
  return [cols.join(','), ...filas].join('\n') + '\n'
}
