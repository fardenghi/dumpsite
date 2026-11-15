// Veredictos de todos los frames procesados y métricas del modelo de abierto contra cerrado.
// Los dos archivos los escribe `idea-basurales-nisar/herramientas/flujo.py --web` y pueden faltar:
// por eso se buscan con `import.meta.glob` (un `import` directo de un archivo que no está rompe el build).
import { useEffect, useState } from 'react'
import type { LecturaModelo, ModeloEstado, Sitio, Veredicto, Veredictos } from './types'

const cargaVeredictos = import.meta.glob<Veredictos>('./seed/veredictos.json', { import: 'default' })
const modeloJson = import.meta.glob<{ estado?: ModeloEstado | null }>('./seed/modelo.json', { import: 'default', eager: true })

/** Métricas del modelo de abierto contra cerrado, o null si `modelo.json` no está o no trae `estado`. */
export const MODELO_ESTADO: ModeloEstado | null = Object.values(modeloJson)[0]?.estado ?? null

/** El frame de los 12 sitios curados de `seed/sitios.json`: el mapa y la lista arrancan ahí. */
export const FRAME_AMBA = 'AMBA'

let cache: Promise<Veredictos | null> | null = null

export function getVeredictos(): Promise<Veredictos | null> {
  const carga = Object.values(cargaVeredictos)[0]
  cache ??= carga ? carga().then((v) => (Array.isArray(v?.sitios) ? v : null), () => null) : Promise.resolve(null)
  return cache
}

/** null mientras carga o si no hay archivo: quien lo usa tiene que andar igual sin veredictos. */
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

/** Los polígonos del catálogo que se pueden ubicar en el mapa. */
export function delCatalogo(v: Veredictos | null): Veredicto[] {
  return (v?.sitios ?? []).filter((x) => x.tipo === 'catalogo' && typeof x.lat === 'number' && typeof x.lon === 'number')
}

/** Los de los otros frames: los del AMBA ya están en los sitios curados. */
export function fueraDelAmba(v: Veredictos | null): Veredicto[] {
  return delCatalogo(v).filter((x) => x.frame !== FRAME_AMBA)
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

// Los sitios curados del AMBA no traen el id del catálogo. Se busca el polígono del catálogo del mismo frame
// que está en el mismo lugar y mide lo mismo: a menos de MAX_KM y con una superficie parecida. Si no hay uno
// claro (por ejemplo, la mancha al oeste de Luján, que no es un predio), el sitio queda sin lectura del modelo.
const MAX_KM = 0.4
const MAX_COCIENTE_HA = 1.25

/** El polígono del catálogo que corresponde a un sitio curado, si hay uno claro. */
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

/** La lectura del modelo, sólo si de verdad vino (un `modelo_estado` vacío o sin `lectura` no cuenta). */
export function lecturaModelo(x: Veredicto | null | undefined): LecturaModelo | null {
  const m = x?.modelo_estado
  return m && typeof m.lectura === 'string' ? m : null
}
