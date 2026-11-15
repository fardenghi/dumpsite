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
  /** mediana en un anillo de 1,5 km alrededor */
  anillo: number
}

/** A Sentinel-2 scene (10 m) with few clouds over the site. */
export interface Imagen {
  fecha: string
  /** scene id in the Planetary Computer sentinel-2-l2a collection */
  item: string
}

/** Umbral bajo, decidido por el equipo el 15/11: un sitio que el pipeline deja en "no alcanza" (predio chico, superficie
 * lisa o señal intermedia) se muestra como despierto si su insomnio medido supera el techo de "quieto" (`max_quieto` del
 * índice, 0,2). No toca los datos del pipeline: se aplica al cargarlos y deja la marca `umbral_bajo`.
 * Los que no tienen insomnio medido, o lo tienen en 0,2 o menos, siguen en "no alcanza". */
export const UMBRAL_BAJO = 0.2

/** Aplica el umbral bajo a un sitio o a una fila de veredictos. */
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
  /** true si el pipeline lo dejó en "no alcanza" y se muestra despierto por el umbral bajo */
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
  /** sólo en las manchas: puntaje del modelo de "basural contra otra cosa que se mueve", de 0 a 1 */
  p_basural?: number | null
  /** sólo en las manchas: lo que OpenStreetMap tiene mapeado ahí (aeródromo, reserva…), si hay algo */
  que?: string | null
  persistencia?: number | null
  modelo_estado?: LecturaModelo | null
  /** true si el flujo lo dejó en "no alcanza" y se muestra despierto por el umbral bajo */
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
