// Datos de ejemplo. Las coordenadas del AMBA y la coherencia del par 30/09–12/10 salen de la
// prueba con un GUNW real; el resto de las series y los sitios de otros países son inventados
// para armar la interfaz. Se reemplaza entero cuando esté el backend.
import contornos from './seed/contornos.json'
import imagenes from './seed/imagenes.json'
import base from './seed/sitios.json'
import type { Imagen, Par, Sitio } from './types'

// imagenes.json tuvo dos formas: una lista de escenas por sitio, o { caja, escenas } cuando
// s2_fechas.py también guardó los recortes. Se aceptan las dos.
const IMAGENES = imagenes as unknown as Record<string, Imagen[] | { caja: Sitio['caja']; escenas: Imagen[] } | undefined>
const CONTORNOS = contornos as unknown as Record<string, Sitio['contorno']>
const escenas = (id: string) => {
  const i = IMAGENES[id]
  return Array.isArray(i) ? i : (i?.escenas ?? [])
}

/** Caja alrededor del sitio (oeste, sur, este, norte), de 3 a 10 km de lado. Misma cuenta que scripts/s2_fechas.py. */
function caja(s: { id: string; lat: number; lon: number; ha: number }): NonNullable<Sitio['caja']> {
  const guardada = IMAGENES[s.id]
  if (guardada && !Array.isArray(guardada) && guardada.caja) return guardada.caja
  const kx = 111320 * Math.cos((s.lat * Math.PI) / 180)
  const ky = 110540
  const anillo = CONTORNOS[s.id]?.coordinates[0]
  let ancho = Math.sqrt(s.ha * 10000)
  let centro = [s.lon, s.lat]
  if (anillo) {
    const lons = anillo.map((p) => p[0])
    const lats = anillo.map((p) => p[1])
    ancho = Math.max((Math.max(...lons) - Math.min(...lons)) * kx, (Math.max(...lats) - Math.min(...lats)) * ky)
    centro = [(Math.max(...lons) + Math.min(...lons)) / 2, (Math.max(...lats) + Math.min(...lats)) / 2]
  }
  const medio = Math.min(5000, Math.max(1500, ancho * 0.9))
  const r5 = (x: number) => Math.round(x * 1e5) / 1e5
  return [r5(centro[0] - medio / kx), r5(centro[1] - medio / ky), r5(centro[0] + medio / kx), r5(centro[1] + medio / ky)]
}

/** Segunda pasada de cada par de 12 días sobre el AMBA (órbita 10). */
const FECHAS = ['2026-07-07', '2026-07-19', '2026-07-31', '2026-08-12', '2026-08-25', '2026-09-06', '2026-09-18', '2026-09-30', '2026-10-12']

/** Ruido determinístico en [-1, 1]: la misma serie en cada carga. */
function ruido(semilla: string, i: number) {
  let h = 2166136261
  for (const c of semilla + i) h = Math.imul(h ^ c.charCodeAt(0), 16777619)
  return ((h >>> 0) / 4294967295) * 2 - 1
}

const r2 = (x: number) => Math.round(x * 100) / 100

function pares(id: string, sitio: number, anillo: number): Par[] {
  return FECHAS.map((fecha, i) => {
    const ultimo = i === FECHAS.length - 1
    return {
      fecha,
      sitio: r2(ultimo ? sitio : sitio + ruido(id, i) * 0.05),
      anillo: r2(ultimo ? anillo : anillo + ruido(id + 'a', i) * 0.03),
    }
  })
}

export const SITIOS: Sitio[] = base.map((s) => ({
  id: s.id,
  nombre: s.nombre,
  lugar: s.lugar,
  pais: s.pais,
  lat: s.lat,
  lon: s.lon,
  ha: s.ha,
  registro: s.registro as Sitio['registro'],
  cierre: s.cierre,
  radar: s.radar as Sitio['radar'],
  insomnio: s.insomnio,
  pares: pares(s.id, s.base, s.anillo),
  imagenes: escenas(s.id),
  caja: caja(s),
  contorno: CONTORNOS[s.id],
}))
