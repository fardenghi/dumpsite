// Datos del mapa que no van en el bundle: los escribe `scripts/datos_mapa.py` en `public/datos/`
// a partir de `../data/` y de las salidas del pipeline. Si falta alguno, el mapa anda igual sin esa capa.
import type { FeatureCollection } from 'geojson'
import { useEffect, useState } from 'react'

/** El catálogo de basurales del mundo (`data/basurales/basurales_mundo.json`), en columnas. La fila i es `BAS-` + (i + 1). */
export interface Catalogo {
  generado?: string
  /** cita de cada fuente, por bit de `fuente` */
  fuentes: Record<string, string>
  /** códigos de país (ISO 3166-1 alfa-3, como vienen de la fuente) */
  paises: string[]
  n: number
  lat: number[]
  lon: number[]
  /** un carácter por sitio: d desconocido, a abierto, c cerrado, x contradictorio */
  estado: string
  /** hectáreas; -1 si la fuente no trae superficie */
  ha: number[]
  /** índice en `paises`; -1 si la fuente no trae país (los que sólo están en OpenStreetMap) */
  pais: number[]
  /** bits: 1 OpenStreetMap, 2 Climate TRACE, 4 EPA LMOP, 8 NASA EMIT, 16 curado a mano */
  fuente: number[]
  nombre: Record<string, string>
}

/** La caja de un frame de NISAR procesado (`data/frames.json`). */
export interface Frame {
  frame: string
  ciudad: string | null
  /** ISO 3166-1 alfa-3 */
  pais: string | null
  /** oeste, sur, este, norte */
  bbox: [number, number, number, number]
  pares: number | null
  desde: string | null
  hasta: string | null
}

/** Un sitio del catálogo que no cae en ningún frame procesado: no hay dato de radar. */
export interface SitioCatalogo {
  id: string
  nombre: string | null
  pais: string | null
  lat: number
  lon: number
  estado: 'desconocido' | 'abierto' | 'cerrado' | 'contradictorio'
  ha: number | null
  fuentes: string[]
}

const cache = new Map<string, Promise<unknown>>()
function pedir<T>(archivo: string): Promise<T | null> {
  if (!cache.has(archivo))
    cache.set(
      archivo,
      fetch(`${import.meta.env.BASE_URL}datos/${archivo}`).then((r) => (r.ok ? r.json() : null), () => null),
    )
  return cache.get(archivo) as Promise<T | null>
}

function useDato<T>(archivo: string): T | null {
  const [d, setD] = useState<T | null>(null)
  useEffect(() => {
    let vivo = true
    pedir<T>(archivo).then((x) => vivo && setD(x))
    return () => {
      vivo = false
    }
  }, [archivo])
  return d
}

export const useCatalogo = () => useDato<Catalogo>('catalogo.json')
export const useFrames = () => useDato<Frame[]>('frames.json')
/** Las manchas despiertas de todos los frames: el índice de insomnio por encima del umbral, vectorizado. */
export const useManchas = () => useDato<FeatureCollection>('manchas.geojson')

export const idCatalogo = (i: number) => `BAS-${String(i + 1).padStart(6, '0')}`
/** La fila del catálogo de un id `BAS-000123`, o -1. */
export function filaCatalogo(c: Catalogo | null, id: string | null): number {
  const m = id?.match(/^BAS-(\d{6})$/)
  const i = m ? Number(m[1]) - 1 : -1
  return c && i >= 0 && i < c.n ? i : -1
}

const ESTADOS = { d: 'desconocido', a: 'abierto', c: 'cerrado', x: 'contradictorio' } as const
const NOMBRE_FUENTE: [number, string][] = [
  [1, 'OpenStreetMap'],
  [2, 'Climate TRACE'],
  [4, 'EPA LMOP'],
  [8, 'NASA EMIT'],
  [16, 'curado a mano'],
]

export function sitioCatalogo(c: Catalogo, i: number): SitioCatalogo {
  return {
    id: idCatalogo(i),
    nombre: c.nombre[i] ?? null,
    pais: c.pais[i] >= 0 ? c.paises[c.pais[i]] : null,
    lat: c.lat[i],
    lon: c.lon[i],
    estado: ESTADOS[c.estado[i] as keyof typeof ESTADOS] ?? 'desconocido',
    ha: c.ha[i] >= 0 ? c.ha[i] : null,
    fuentes: NOMBRE_FUENTE.filter(([bit]) => c.fuente[i] & bit).map(([, n]) => n),
  }
}

// Los catálogos traen el país en alfa-3 y el navegador sólo sabe nombrar alfa-2
const A2: Record<string, string> = {
  AGO: 'AO', ALB: 'AL', AND: 'AD', ARE: 'AE', ARG: 'AR', ARM: 'AM', AUS: 'AU', AUT: 'AT', BEL: 'BE', BEN: 'BJ', BFA: 'BF', BGD: 'BD', BGR: 'BG', BIH: 'BA',
  BLR: 'BY', BLZ: 'BZ', BOL: 'BO', BRA: 'BR', BRN: 'BN', BWA: 'BW', CAN: 'CA', CHE: 'CH', CHL: 'CL', CHN: 'CN', CMR: 'CM', COD: 'CD', COL: 'CO', CRI: 'CR',
  CUB: 'CU', CYP: 'CY', CZE: 'CZ', DEU: 'DE', DNK: 'DK', DOM: 'DO', DZA: 'DZ', ECU: 'EC', EGY: 'EG', ERI: 'ER', ESP: 'ES', EST: 'EE', ETH: 'ET', FIN: 'FI',
  FJI: 'FJ', FRA: 'FR', GAB: 'GA', GBR: 'GB', GEO: 'GE', GHA: 'GH', GIN: 'GN', GLP: 'GP', GMB: 'GM', GRC: 'GR', GTM: 'GT', GUF: 'GF', GUM: 'GU', GUY: 'GY',
  HKG: 'HK', HND: 'HN', HRV: 'HR', HTI: 'HT', HUN: 'HU', IDN: 'ID', IND: 'IN', IRL: 'IE', IRN: 'IR', IRQ: 'IQ', ISL: 'IS', ISR: 'IL', ITA: 'IT', JOR: 'JO',
  JPN: 'JP', KAZ: 'KZ', KEN: 'KE', KGZ: 'KG', KHM: 'KH', KOR: 'KR', KWT: 'KW', LAO: 'LA', LBN: 'LB', LBY: 'LY', LKA: 'LK', LSO: 'LS', LTU: 'LT', LUX: 'LU',
  LVA: 'LV', MAR: 'MA', MDA: 'MD', MDG: 'MG', MEX: 'MX', MKD: 'MK', MLI: 'ML', MMR: 'MM', MNE: 'ME', MNG: 'MN', MOZ: 'MZ', MUS: 'MU', MYS: 'MY', NAM: 'NA',
  NCL: 'NC', NER: 'NE', NGA: 'NG', NIC: 'NI', NLD: 'NL', NOR: 'NO', NPL: 'NP', NZL: 'NZ', PAK: 'PK', PAN: 'PA', PER: 'PE', PHL: 'PH', PNG: 'PG', POL: 'PL',
  PRI: 'PR', PRT: 'PT', PRY: 'PY', PSE: 'PS', QAT: 'QA', REU: 'RE', ROU: 'RO', RUS: 'RU', SAU: 'SA', SEN: 'SN', SGP: 'SG', SJM: 'SJ', SLE: 'SL', SLV: 'SV',
  SRB: 'RS', SSD: 'SS', SUR: 'SR', SVK: 'SK', SVN: 'SI', SWE: 'SE', TCD: 'TD', TGO: 'TG', THA: 'TH', TJK: 'TJ', TLS: 'TL', TON: 'TO', TTO: 'TT', TUN: 'TN',
  TUR: 'TR', TWN: 'TW', TZA: 'TZ', UGA: 'UG', UKR: 'UA', URY: 'UY', USA: 'US', UZB: 'UZ', VEN: 'VE', VIR: 'VI', VNM: 'VN', VUT: 'VU', XKX: 'XK', YEM: 'YE',
  ZAF: 'ZA', ZMB: 'ZM', ZWE: 'ZW',
}
const regiones = new Intl.DisplayNames('es', { type: 'region' })
/** "USA" -> "Estados Unidos". Si no se reconoce el código, se muestra como vino. */
export function nombrePais(codigo: string | null | undefined): string {
  if (!codigo) return 'Sin país'
  const a2 = codigo.length === 2 ? codigo : A2[codigo]
  try {
    return (a2 && regiones.of(a2)) || codigo
  } catch {
    return codigo
  }
}

/** "Painesville, Lake, OH (alrededor de …)" -> "Painesville, Lake, OH". */
export const ciudadFrame = (f: Frame | undefined) => f?.ciudad?.replace(/\s*\(.*$/, '') || null
