/** What the official registry or the press says about the site. */
export type Registro = 'activo' | 'cerrado' | 'sin_registro'
/** What the radar sees: low coherence in almost every pair, high, or indistinguishable from its surroundings. */
export type Radar = 'despierto' | 'quieto' | 'no_alcanza'

/** A pair of NISAR passes 12 days apart. */
export interface Par {
  /** date of the second pass, YYYY-MM-DD */
  fecha: string
  /** median coherence inside the site, 0 to 1 */
  sitio: number
  /** median in a 1.5 km ring around it */
  anillo: number
}

/** A Sentinel-2 scene (10 m) with few clouds over the site. */
export interface Imagen {
  fecha: string
  /** scene id in the Planetary Computer sentinel-2-l2a collection */
  item: string
}

/** Low threshold, decided by the team on 15/11: a site the pipeline leaves as "no alcanza" (small site, smooth
 * surface or intermediate signal) is shown as awake if its measured insomnia is above the "quieto" ceiling (the index's
 * `max_quieto`, 0.2). It doesn't touch the pipeline data: it's applied on load and leaves the `umbral_bajo` flag.
 * Sites without measured insomnia, or with 0.2 or less, stay as "no alcanza". */
export const UMBRAL_BAJO = 0.2

/** Applies the low threshold to a site or to a verdict row. */
export function conUmbralBajo<T extends { radar: Radar | null; insomnio: number | null; umbral_bajo?: boolean }>(x: T): T {
  return x.radar === 'no_alcanza' && typeof x.insomnio === 'number' && x.insomnio > UMBRAL_BAJO ? { ...x, radar: 'despierto', umbral_bajo: true } : x
}

export interface Sitio {
  id: string
  nombre: string
  lugar: string
  /** ISO 3166-1 alfa-2 */
  pais: string
  lat: number
  lon: number
  ha: number
  registro: Registro
  /** closure date according to the registry, if it's closed */
  cierre?: string
  radar: Radar
  /** fraction of pairs with low coherence relative to the surroundings, 0 to 1 */
  insomnio: number
  /** true if the pipeline left it as "no alcanza" and it's shown awake because of the low threshold */
  umbral_bajo?: boolean
  pares: Par[]
  imagenes: Imagen[]
  /** site outline according to OpenStreetMap, if it exists */
  contorno?: { type: 'Polygon'; coordinates: number[][][] }
  /** box of the stored crops: west, south, east, north */
  caja?: [number, number, number, number]
}

export interface Resumen {
  sitios: number
  despiertos: number
  paises: number
  hectareas: number
  pares: number
  desde: string
  hasta: string
}

// ---------- verdicts per frame and open-versus-closed model
// Written by `motor/flujo.py --web` in seed/veredictos.json and seed/modelo.json.
// Everything about the model is optional: if it didn't come, the web shows nothing about the model.

/** What the open-versus-closed model says about a polygon. It's neither the registry status nor a calibrated probability. */
export interface LecturaModelo {
  /** score from 0 to 1; null if it couldn't be computed */
  p_abierto: number | null
  lectura: 'compatible con abierto' | 'compatible con cerrado' | 'sin dato'
  /** where the score comes from (for example, validation without its frame or final model) */
  origen: string
}

/** A dump-site catalog polygon (or a blob) of a processed frame: one row of seed/veredictos.json. */
export interface Veredicto {
  tipo: string
  id: string
  /** frame key in `data/catalogos/frames.json`: `AMBA`, `LOS_ANGELES`, `USA_OH_LAKE`… */
  frame: string
  nombre: string | null
  area_ha: number | null
  /** status according to the registry: `abierto`, `cerrado`, `desconocido` or `contradictorio` */
  registro: string | null
  radar: Radar | null
  insomnio: number | null
  veredicto: string
  veredicto_texto: string
  motivo?: string | null
  lat: number | null
  lon: number | null
  /** blobs only: score of the "dump site versus something else that moves" model, from 0 to 1 */
  p_basural?: number | null
  /** blobs only: what OpenStreetMap has mapped there (airfield, reserve…), if anything */
  que?: string | null
  persistencia?: number | null
  modelo_estado?: LecturaModelo | null
  /** true if the flow left it as "no alcanza" and it's shown awake because of the low threshold */
  umbral_bajo?: boolean
}

export interface Veredictos {
  generado?: string
  frames?: string[]
  aviso?: string
  sitios: Veredicto[]
}

/** Metrics of the open-versus-closed model: the `estado` key of seed/modelo.json. */
export interface ModeloEstado {
  auc: number
  ic95: [number, number]
  n: number
  abiertos: number
  cerrados: number
  frames: number
  variables: string[]
  validacion: string
  limites: string[]
  prueba_amba: { nombre: string; estado_registro: string; p_abierto: number | null }[]
}
