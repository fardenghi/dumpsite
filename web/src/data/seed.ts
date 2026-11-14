// Datos de ejemplo. Las coordenadas del AMBA y la coherencia del par 30/09–12/10 salen de la
// prueba con un GUNW real; el resto de las series y los sitios de otros países son inventados
// para armar la interfaz. Se reemplaza entero cuando esté el backend.
import contornos from './seed/contornos.json'
import imagenes from './seed/imagenes.json'
import base from './seed/sitios.json'
import type { Imagen, Par, Sitio } from './types'

const IMAGENES = imagenes as unknown as Record<string, { caja: Sitio['caja']; escenas: Imagen[] } | undefined>

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
  imagenes: IMAGENES[s.id]?.escenas ?? [],
  caja: IMAGENES[s.id]?.caja,
  contorno: (contornos as unknown as Record<string, Sitio['contorno']>)[s.id],
}))
