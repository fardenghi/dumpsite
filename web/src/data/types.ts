/** Qué dice el registro oficial o la prensa sobre el sitio. */
export type Registro = 'activo' | 'cerrado' | 'sin_registro'
/** Qué ve el radar: coherencia baja en casi todos los pares, alta, o no se distingue del entorno. */
export type Radar = 'despierto' | 'quieto' | 'no_alcanza'

/** Un par de pasadas de NISAR separadas por 12 días. */
export interface Par {
  /** fecha de la segunda pasada, AAAA-MM-DD */
  fecha: string
  /** mediana de la coherencia adentro del sitio, 0 a 1 */
  sitio: number
  /** mediana en un anillo de 1,5 km alrededor */
  anillo: number
}

/** Una escena Sentinel-2 (10 m) con pocas nubes sobre el sitio. */
export interface Imagen {
  fecha: string
  /** id de la escena en la colección sentinel-2-l2a de Planetary Computer */
  item: string
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
  /** fecha de cierre según el registro, si está cerrado */
  cierre?: string
  radar: Radar
  /** fracción de pares con coherencia baja respecto del entorno, 0 a 1 */
  insomnio: number
  pares: Par[]
  imagenes: Imagen[]
  /** contorno del predio según OpenStreetMap, si existe */
  contorno?: { type: 'Polygon'; coordinates: number[][][] }
  /** caja de los recortes guardados: oeste, sur, este, norte */
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
