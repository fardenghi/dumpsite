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

// ---------- veredictos por frame y modelo de abierto contra cerrado
// Los escribe `motor/flujo.py --web` en seed/veredictos.json y seed/modelo.json.
// Todo lo del modelo es opcional: si no vino, la web no muestra nada del modelo.

/** Lo que dice el modelo de abierto contra cerrado de un polígono. No es el estado del registro ni una probabilidad calibrada. */
export interface LecturaModelo {
  /** puntaje de 0 a 1; null si no se pudo calcular */
  p_abierto: number | null
  lectura: 'compatible con abierto' | 'compatible con cerrado' | 'sin dato'
  /** de dónde sale el puntaje (por ejemplo, validación sin su frame o modelo final) */
  origen: string
}

/** Un polígono del catálogo de basurales (o una mancha) de un frame procesado: una fila de seed/veredictos.json. */
export interface Veredicto {
  tipo: string
  id: string
  /** clave del frame de `data/catalogos/frames.json`: `AMBA`, `LOS_ANGELES`, `USA_OH_LAKE`… */
  frame: string
  nombre: string | null
  area_ha: number | null
  /** estado según el registro: `abierto`, `cerrado`, `desconocido` o `contradictorio` */
  registro: string | null
  radar: Radar | null
  insomnio: number | null
  veredicto: string
  veredicto_texto: string
  motivo?: string | null
  lat: number | null
  lon: number | null
  modelo_estado?: LecturaModelo | null
}

export interface Veredictos {
  generado?: string
  frames?: string[]
  aviso?: string
  sitios: Veredicto[]
}

/** Métricas del modelo de abierto contra cerrado: la clave `estado` de seed/modelo.json. */
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
