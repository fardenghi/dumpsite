// Map data that doesn't go in the bundle: `scripts/datos_mapa.py` writes it to `public/datos/`
// from `../data/` and the pipeline outputs. If one is missing, the map works the same without that layer.
import type { FeatureCollection } from 'geojson'
import { useEffect, useState } from 'react'
import { getLang, t } from '../i18n'

/** The world dump-site catalog (`data/catalogos/basurales/basurales_mundo.json`), in columns. Row i is `BAS-` + (i + 1). */
export interface Catalogo {
  generado?: string
  /** citation of each source, by bit of `fuente` */
  fuentes: Record<string, string>
  /** country codes (ISO 3166-1 alpha-3, as they come from the source) */
  paises: string[]
  n: number
  lat: number[]
  lon: number[]
  /** one character per site: d unknown, a open, c closed, x contradictory */
  estado: string
  /** hectares; -1 if the source has no area */
  ha: number[]
  /** index into `paises`; -1 if the source has no country (the ones only in OpenStreetMap) */
  pais: number[]
  /** bits: 1 OpenStreetMap, 2 Climate TRACE, 4 EPA LMOP, 8 NASA EMIT, 16 curado a mano */
  fuente: number[]
  nombre: Record<string, string>
}

/** The box of a processed NISAR frame (`data/catalogos/frames.json`). */
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

/** A catalog site that doesn't fall in any processed frame: there's no radar data. */
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

/** The insomnia index of a frame as an image (`motor/indice_png_web.py`). */
export interface IndiceFrame {
  frame: string
  /** relative to the web root */
  url: string
  /** the four corners in the order of a MapLibre `image` source */
  coordinates: [[number, number], [number, number], [number, number], [number, number]]
}
// `seed/indices.json` may be missing: without it, outside the AMBA the index only shows as blobs
const indicesJson = import.meta.glob<IndiceFrame[]>('./seed/indices.json', { import: 'default', eager: true })
/** The frames, besides the AMBA, that have the full index as an image. */
export const INDICES: IndiceFrame[] = Object.values(indicesJson)[0] ?? []

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
/** The awake blobs of every frame: the insomnia index above the threshold, vectorized. */
export const useManchas = () => useDato<FeatureCollection>('manchas.geojson')

export const idCatalogo = (i: number) => `BAS-${String(i + 1).padStart(6, '0')}`
/** The catalog row of an id `BAS-000123`, or -1. */
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

// The catalogs have the country in alpha-3 and the browser can only name alpha-2
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
const regiones = { es: new Intl.DisplayNames('es', { type: 'region' }), en: new Intl.DisplayNames('en', { type: 'region' }) }
/** "USA" -> "Estados Unidos" or "United States", depending on the language. If the code isn't recognized, it's shown as it came. */
export function nombrePais(codigo: string | null | undefined): string {
  if (!codigo) return t('Sin país')
  const a2 = codigo.length === 2 ? codigo : A2[codigo]
  try {
    return (a2 && regiones[getLang()].of(a2)) || codigo
  } catch {
    return codigo
  }
}

/** "Painesville, Lake, OH (alrededor de …)" -> "Painesville, Lake, OH". */
export const ciudadFrame = (f: Frame | undefined) => f?.ciudad?.replace(/\s*\(.*$/, '') || null
