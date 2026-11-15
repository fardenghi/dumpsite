// Verdicts for all processed frames and metrics of the open-versus-closed model.
// Both files are written by `motor/flujo.py --web` and may be missing:
// that's why they're looked up with `import.meta.glob` (a direct `import` of a missing file breaks the build).
import { useEffect, useState } from 'react'
import { conUmbralBajo, type LecturaModelo, type ModeloEstado, type Sitio, type Veredicto, type Veredictos } from './types'

const cargaVeredictos = import.meta.glob<Veredictos>('./seed/veredictos.json', { import: 'default' })
const modeloJson = import.meta.glob<{ estado?: ModeloEstado | null }>('./seed/modelo.json', { import: 'default', eager: true })

/** Metrics of the open-versus-closed model, or null if `modelo.json` isn't there or doesn't carry `estado`. */
export const MODELO_ESTADO: ModeloEstado | null = Object.values(modeloJson)[0]?.estado ?? null

/** The frame of the 12 curated sites in `seed/sitios.json`: the map and the list start there. */
export const FRAME_AMBA = 'AMBA'

let cache: Promise<Veredictos | null> | null = null

export function getVeredictos(): Promise<Veredictos | null> {
  const carga = Object.values(cargaVeredictos)[0]
  cache ??= carga ? carga().then((v) => (Array.isArray(v?.sitios) ? { ...v, sitios: v.sitios.map((x) => (x.tipo === 'catalogo' ? conUmbralBajo(x) : x)) } : null), () => null) : Promise.resolve(null)
  return cache
}

/** null while loading or if there's no file: callers have to work without verdicts too. */
export function useVeredictos() {
  const [v, setV] = useState<Veredictos | null>(null)
  useEffect(() => {
    let vivo = true
    getVeredictos().then((x) => vivo && setV(x))
    return () => {
      vivo = false
    }
  }, [])
  return v
}

/** The catalog polygons that can be placed on the map. */
export function delCatalogo(v: Veredictos | null): Veredicto[] {
  return (v?.sitios ?? []).filter((x) => x.tipo === 'catalogo' && typeof x.lat === 'number' && typeof x.lon === 'number')
}

/** Those from the other frames: the AMBA ones are already among the curated sites. */
export function fueraDelAmba(v: Veredictos | null): Veredicto[] {
  return delCatalogo(v).filter((x) => x.frame !== FRAME_AMBA)
}

/** Las manchas despiertas que no están en ningún catálogo y que el modelo lee como basural: lo que el sistema busca.
 * Quedan afuera las que OpenStreetMap ya explica con otro uso (un aeródromo, una reserva, una cantera). */
export function posiblesNuevos(v: Veredictos | null): Veredicto[] {
  return (v?.sitios ?? []).filter((x) => x.tipo === 'mancha' && x.veredicto === 'posible_nuevo' && !x.que && typeof x.lat === 'number' && typeof x.lon === 'number')
}

/** Las manchas que el flujo marca como posible basural nuevo pero OpenStreetMap explica con otro uso. */
export function nuevosConUsoConocido(v: Veredictos | null): number {
  return (v?.sitios ?? []).filter((x) => x.tipo === 'mancha' && x.veredicto === 'posible_nuevo' && !!x.que).length
}

/** Los polígonos del catálogo con dato de radar que el mapa dibuja como punto: los de los otros frames y los del AMBA
 * que no son uno de los sitios curados (esos ya están, con su contorno). */
export function conRadar(v: Veredictos | null, curados: Sitio[]): Veredicto[] {
  return delCatalogo(v).filter((x) => x.frame !== FRAME_AMBA || !curados.some((s) => km(s, x as { lat: number; lon: number }) <= 0.5))
}

/** `USA_OH_LAKE` -> "Lake, OH, USA"; `LOS_ANGELES` -> "Los Angeles". Sale de la clave: no hay otra fuente en el seed. */
export function nombreFrame(frame: string): string {
  const palabras = (t: string[]) => t.map((p) => p.charAt(0) + p.slice(1).toLowerCase()).join(' ')
  const partes = frame.split('_')
  if (partes.length >= 3 && partes[0].length === 3 && partes[1].length === 2) return `${palabras(partes.slice(2))}, ${partes[1]}, ${partes[0]}`
  if (partes.length >= 2 && partes[0].length === 3 && partes[0] !== 'LOS') return `${palabras(partes.slice(1))}, ${partes[0]}`
  return frame === FRAME_AMBA ? 'AMBA' : frame.length <= 4 ? frame : palabras(partes)
}

const km = (a: { lat: number; lon: number }, b: { lat: number; lon: number }) =>
  Math.hypot((a.lat - b.lat) * 111.32, (a.lon - b.lon) * 111.32 * Math.cos((a.lat * Math.PI) / 180))

// The curated AMBA sites don't carry the catalog id. We look for the catalog polygon in the same frame
// that is in the same place and has the same size: within MAX_KM and with a similar area. If there isn't a
// clear one (for example, the blob west of Luján, which isn't a site), the site stays without a model reading.
const MAX_KM = 0.4
const MAX_COCIENTE_HA = 1.25

/** The catalog polygon that matches a curated site, if there's a clear one. */
export function veredictoDeSitio(s: Sitio, v: Veredictos | null): Veredicto | null {
  let mejor: Veredicto | null = null
  let dMejor = MAX_KM
  for (const x of delCatalogo(v)) {
    if (x.frame !== FRAME_AMBA || !x.area_ha || !s.ha) continue
    const cociente = Math.max(x.area_ha, s.ha) / Math.min(x.area_ha, s.ha)
    const d = km(s, x as { lat: number; lon: number })
    if (cociente <= MAX_COCIENTE_HA && d <= dMejor) {
      mejor = x
      dMejor = d
    }
  }
  return mejor
}

/** The model reading, only if it really came (an empty `modelo_estado` or one without `lectura` doesn't count). */
export function lecturaModelo(x: Veredicto | null | undefined): LecturaModelo | null {
  const m = x?.modelo_estado
  return m && typeof m.lectura === 'string' ? m : null
}
