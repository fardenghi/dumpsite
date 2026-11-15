// Web language: English by default, Spanish on request (its own selector in the top bar).
// Texts are written in Spanish in the code and translated with t('…'): if a translation is missing,
// the Spanish is shown. {0}, {1}… are replaced by the values passed after it.
// The language can be forced with ?lang=es or #/mapa?lang=es (the video captures use it).
import { useSyncExternalStore } from 'react'

export type Lang = 'en' | 'es'
export const IDIOMAS: { value: Lang; label: string }[] = [
  { value: 'en', label: 'English' },
  { value: 'es', label: 'Español' },
]

const CLAVE = 'dumpsite-lang'

function inicial(): Lang {
  const dePedido = new URLSearchParams(location.search).get('lang') ?? new URLSearchParams(location.hash.split('?')[1] ?? '').get('lang')
  if (dePedido === 'es' || dePedido === 'en') return dePedido
  try {
    const guardado = localStorage.getItem(CLAVE)
    if (guardado === 'es' || guardado === 'en') return guardado
  } catch {
    /* no storage: the default stays */
  }
  return 'en'
}

let lang: Lang = inicial()
document.documentElement.lang = lang
const subs = new Set<() => void>()

export const getLang = () => lang

export function setLang(l: Lang) {
  if (l === lang) return
  lang = l
  document.documentElement.lang = l
  try {
    localStorage.setItem(CLAVE, l)
  } catch {
    /* no storage: it lasts until reload */
  }
  subs.forEach((f) => f())
}

/** Makes the component redraw when the language changes. App uses it, so everything redraws. */
export function useLang(): Lang {
  return useSyncExternalStore(
    (f) => {
      subs.add(f)
      return () => subs.delete(f)
    },
    getLang,
  )
}

export const locale = () => (lang === 'es' ? 'es-AR' : 'en-US')

export function t(es: string, ...vals: (string | number)[]): string {
  const base = lang === 'en' ? (EN[es] ?? es) : es
  return vals.length ? base.replace(/\{(\d+)\}/g, (_, i) => String(vals[Number(i)] ?? '')) : base
}

const EN: Record<string, string> = {
  // brand and navigation
  'Basurales que el radar NISAR de la NASA nunca ve quietos.': 'Dump sites that NASA’s NISAR radar never sees at rest.',
  '{0} de {1} despiertos': '{0} of {1} awake',
  'Lo que nos queda': 'What’s next',
  'Llegamos al límite diario de imágenes de Google: el mapa sigue con Sentinel-2. La vista de Google vuelve hoy a las {0} (tu hora).':
    'We hit the daily limit of Google imagery: the map keeps using Sentinel-2. The Google view comes back today at {0} (your time).',
  'Llegamos al límite diario de imágenes de Google: el mapa sigue con Sentinel-2. La vista de Google vuelve mañana a las {0} (tu hora).':
    'We hit the daily limit of Google imagery: the map keeps using Sentinel-2. The Google view comes back tomorrow at {0} (your time).',
  'Correrlo en el resto del mundo. Por el tiempo del hackathon priorizamos algunas regiones: lo corrimos en {0} frames de NISAR.':
    'Running it on the rest of the world. Given the hackathon’s time, we prioritized a few regions: we ran it on {0} NISAR frames.',
  'Correrlo en el resto del mundo. Por el tiempo del hackathon priorizamos algunas regiones.':
    'Running it on the rest of the world. Given the hackathon’s time, we prioritized a few regions.',
  'Datos reales precalculados de NISAR (GUNW) en {0} frames procesados': 'Real, precomputed NISAR data (GUNW) across {0} processed frames',
  Resumen: 'Overview',
  Sitios: 'Sites',
  Modelo: 'Model',
  Mapa: 'Map',
  Secciones: 'Sections',
  'Cerrar panel': 'Close panel',
  Cerrar: 'Close',
  Idioma: 'Language',

  // radar states
  Despierto: 'Awake',
  Quieto: 'At rest',
  'No alcanza': 'Out of reach',
  'El radar no alcanza': 'Radar can’t tell',
  Despiertos: 'Awake',
  Quietos: 'At rest',
  Todos: 'All',

  // mapa
  'Ir a un sitio': 'Go to a site',
  'Ver todo': 'See all',
  'Índice de insomnio': 'Insomnia index',
  'Alejar el mapa hasta ver todos los frames procesados': 'Zoom out to see every processed frame',
  '{0} basurales en {1} regiones': '{0} dump sites in {1} regions',
  'Polígonos del catálogo, sin verificar': 'Catalog polygons, not verified',
  'Índice: NISAR GUNW (NASA/ISRO, vía ASF DAAC), agua de JRC Global Surface Water · Contornos: © OpenStreetMap':
    'Index: NISAR GUNW (NASA/ISRO, via ASF DAAC), water from JRC Global Surface Water · Outlines: © OpenStreetMap',
  ' · Otros frames: catálogo de basurales (OpenStreetMap vía Overture Maps, EPA LMOP)': ' · Other frames: dump-site catalog (OpenStreetMap via Overture Maps, EPA LMOP)',
  'Imágenes:': 'Imagery:',
  'ESA Copernicus, vía Planetary Computer': 'ESA Copernicus, via Planetary Computer',
  'Mosaico:': 'Mosaic:',
  'Sentinel-2 cloudless 2024 de EOX (CC BY-NC-SA 4.0)': 'Sentinel-2 cloudless 2024 by EOX (CC BY-NC-SA 4.0)',
  Insomnio: 'Insomnia',
  Superficie: 'Area',
  Coherencia: 'Coherence',
  'NISAR, {0} comparaciones': 'NISAR, {0} comparisons',
  Entorno: 'Surroundings',
  Sitio: 'Site',
  'Sitio, {0}': 'Site, {0}',
  Imagen: 'Image',
  'Google, alta resolución, sin fecha': 'Google, high resolution, undated',
  'Sentinel-2, 10 m': 'Sentinel-2, 10 m',
  'Alta resolución': 'High resolution',
  'Sin imagen Sentinel-2 despejada en el período': 'No cloud-free Sentinel-2 image in this period',
  'Ver en Google Maps': 'View on Google Maps',
  'Polígono sin nombre': 'Unnamed polygon',
  'Señal compatible con actividad, sin verificar en terreno': 'Signal consistent with activity, not verified on the ground',
  'Coherencia entre pasadas consecutivas': 'Coherence between consecutive passes',

  // lista
  'Sitios ': 'Sites ',
  '{0} sitios en {1} regiones de NISAR. Fuera del AMBA son polígonos del catálogo de basurales, sin verificar':
    '{0} sites in {1} NISAR regions. Outside Buenos Aires they are dump-site catalog polygons, not verified',
  sitio: 'site',
  sitios: 'sites',
  Región: 'Region',
  'Todas las regiones': 'All regions',
  Radar: 'Radar',
  Hectáreas: 'Hectares',
  'Insomnio: en qué fracción de las pasadas del radar el sitio cambió más que su entorno':
    'Insomnia: the share of radar passes in which the site changed more than its surroundings',
  'Ningún sitio con ese filtro': 'No site matches that filter',

  // resumen
  'Radar NISAR · {0} regiones': 'NISAR radar · {0} regions',
  'Los basurales que el radar nunca ve quietos': 'The dump sites the radar never sees at rest',
  'Donde dos pasadas del radar nunca se parecen, alguien está moviendo el suelo': 'Where two radar passes never look alike, someone is moving the ground',
  'Ver los sitios': 'See the sites',
  'Cómo se decide': 'How it decides',
  'Sitios analizados': 'Sites analyzed',
  '{0} ha en total': '{0} ha in total',
  'nunca quietos': 'never at rest',
  'Posibles basurales nuevos': 'Possible new dump sites',
  'sin verificar todavía': 'not verified yet',
  'Regiones de NISAR': 'NISAR regions',
  'procesadas con NISAR': 'processed with NISAR',
  'NISAR · NASA/ISRO, vía ASF DAAC': 'NISAR · NASA/ISRO, via ASF DAAC',
  'Agua · JRC Global Surface Water': 'Water · JRC Global Surface Water',
  'Sentinel-2 · ESA Copernicus, vía Planetary Computer': 'Sentinel-2 · ESA Copernicus, via Planetary Computer',
  'Polígonos · OpenStreetMap, ODbL': 'Polygons · OpenStreetMap, ODbL',
  'Catálogo de otras regiones · Overture Maps (OpenStreetMap, ODbL)': 'Catalog of other regions · Overture Maps (OpenStreetMap, ODbL)',
  'Rellenos en EE. UU. · EPA LMOP': 'US landfills · EPA LMOP',

  // modelo
  'Insomnio: en qué fracción de las pasadas del radar un lugar cambió más que su entorno':
    'Insomnia: the share of radar passes in which a place changed more than its surroundings',
  'La regla, pasada contra pasada': 'The rule, pass against pass',
  'Cada pasada del radar se compara con la anterior. Está despierta si el sitio (punto) queda debajo del {0} de su entorno (raya)':
    'Each radar pass is compared with the previous one. It counts as awake if the site (dot) falls below {0} of its surroundings (tick)',
  'Sitio de ejemplo': 'Example site',
  'Órbita {0}': 'Orbit {0}',
  '{0} de {1} despiertas': '{0} of {1} awake',
  'Comparaciones de la órbita {0}': 'Comparisons for orbit {0}',
  despierta: 'awake',
  quieta: 'at rest',
  '{0} del entorno': '{0} of surroundings',
  Persistencia: 'Persistence',
  Eco: 'Echo',
  'mínimo {0}': 'minimum {0}',
  'Del AMBA a {0} manchas': 'From Buenos Aires to {0} patches',
  'La misma regla en toda la grilla, píxel por píxel': 'The same rule across the whole grid, pixel by pixel',
  'Grilla del AMBA': 'Buenos Aires grid',
  'Tierra, sin el agua de JRC': 'Land, without JRC water',
  'Manchas candidatas': 'Candidate patches',
  '{0} ha · {1} % de la tierra': '{0} ha · {1} % of the land',
  'En el camino quedan': 'Dropped along the way',
  'lineales: rutas y arroyos': 'linear: roads and streams',
  'despiertas sólo por temporada': 'awake only seasonally',
  'Qué son las {0}': 'What the {0} are',
  'Relleno según OpenStreetMap': 'Landfill according to OpenStreetMap',
  'Uso conocido: aeródromos, golf, parques': 'Known use: airfields, golf, parks',
  'Sin explicar': 'Unexplained',
  'Las “sin explicar” no están verificadas: no son basurales confirmados': 'The “unexplained” ones are not verified: they are not confirmed dump sites',
  'Los umbrales': 'The thresholds',
  'Calibrados con dos rellenos y cinco controles. La franja es el rango válido': 'Calibrated on two landfills and five controls. The band is the valid range',
  'Sitio / entorno': 'Site / surroundings',
  'Insomnio mínimo': 'Minimum insomnia',
  'Eco mínimo, dB': 'Minimum echo, dB',
  'válido de {0} a {1}': 'valid from {0} to {1}',
  'Más bajo, Norte III deja de ser persistente. Más alto, aparecen manchas en la costa del Roggero':
    'Lower, Norte III stops being persistent. Higher, patches appear on the Roggero shore',
  '¿Basural u otra cosa? El clasificador por mancha': 'Dump site or something else? The per-patch classifier',
  'El radar dice si un lugar se mueve, no qué es. Para eso, un modelo LightGBM entrenado con un catálogo mundial de basurales':
    'The radar says whether a place moves, not what it is. For that, a LightGBM model trained on a worldwide dump-site catalog',
  'Catálogo mundial': 'Worldwide catalog',
  'basurales mapeados': 'mapped dump sites',
  'OpenStreetMap, Climate TRACE, EPA LMOP y plumas de metano de NASA EMIT': 'OpenStreetMap, Climate TRACE, EPA LMOP and NASA EMIT methane plumes',
  'Y lo que se les parece': 'And look-alikes',
  'canteras, aeródromos': 'quarries, airfields',
  '{0} variables por mancha': '{0} features per patch',
  'radar NISAR, Sentinel-2 (vegetación, suelo desnudo, agua, infrarrojo) y forma': 'NISAR radar, Sentinel-2 (vegetation, bare soil, water, infrared) and shape',
  'Cientos de árboles de decisión, cada uno corrige al anterior': 'Hundreds of decision trees, each one correcting the previous',
  'Basural u otra cosa': 'Dump site or something else',
  'Clasificado como basural por el modelo: no es una confirmación': 'Classified as a dump site by the model: not a confirmation',
  'Sólo dos rellenos y cinco controles': 'Only two landfills and five controls',
  'todas las pasadas': 'all passes',

  // full catalog, possible new sites and index in every region
  'Posible basural nuevo': 'Possible new dump site',
  'No figura en ningún catálogo': 'Not in any catalog',
  'Según el modelo · basural u otra cosa': 'According to the model · dump site or something else',
  'Puntaje de basural {0}, de 0 a 1': 'Dump-site score {0}, from 0 to 1',
  'Puntaje de basural, de 0 a 1. No es una probabilidad': 'Dump-site score, from 0 to 1. Not a probability',
  'Mancha que el radar NISAR nunca ve quieta y que no está en ninguno de los catálogos de basurales. Señal compatible con actividad, sin verificar en terreno':
    'A patch the NISAR radar never sees at rest and that is in none of the dump-site catalogs. Signal consistent with activity, not verified on the ground',
  'Basural sin nombre': 'Unnamed dump site',
  'Sin procesar todavía': 'Not processed yet',
  'Despierto con el umbral bajo: insomnio mayor que {0}. El predio es chico, liso o de señal intermedia para la regla calibrada':
    'Awake at the lowered threshold: insomnia above {0}. The site is small, smooth or mid-signal for the calibrated rule',
  'Está en el catálogo de basurales, pero todavía no procesamos pasadas de NISAR sobre este lugar: no hay índice de insomnio':
    'It is in the dump-site catalog, but we have not processed NISAR passes over this place yet: there is no insomnia index',
  'Fuente del catálogo: {0}': 'Catalog source: {0}',
  'curado a mano': 'hand-curated',
  'Sin país': 'No country',
  'Manchas despiertas que no están en ningún catálogo y que el modelo lee como basural. Sin verificar': 'Awake patches that are in no catalog and that the model reads as a dump site. Not verified',
  'Otras {0} quedan afuera porque OpenStreetMap ya las explica con otro uso': 'Another {0} are left out because OpenStreetMap already explains them with another use',
  'Basurales del catálogo donde todavía no procesamos pasadas de NISAR': 'Catalog dump sites where we have not processed NISAR passes yet',
  'En el AMBA, el índice completo ({0} comparaciones de NISAR, del {1} al {2}). En las otras regiones, las manchas donde el índice supera el umbral':
    'In Greater Buenos Aires, the full index ({0} NISAR comparisons, {1} to {2}). In the other regions, the patches where the index exceeds the threshold',
  'Recuadro: cada región procesada con NISAR. Acercate a un recuadro para ver el índice': 'Box: each region processed with NISAR. Zoom into a box to see the index',
  'Índice de insomnio relativo, de 0 a 1; transparente por debajo de {3} y en el agua. En el AMBA, {0} comparaciones de NISAR, del {1} al {2}. Donde no hay imagen del índice se pintan las manchas despiertas':
    'Relative insomnia index, from 0 to 1; transparent below {3} and over water. In Greater Buenos Aires, {0} NISAR comparisons, {1} to {2}. Where there is no index image, the awake patches are painted',
  ' · Catálogo de basurales: © OpenStreetMap vía Overture Maps, Climate TRACE (CC BY 4.0), U.S. EPA LMOP, NASA EMIT': ' · Dump-site catalog: © OpenStreetMap via Overture Maps, Climate TRACE (CC BY 4.0), U.S. EPA LMOP, NASA EMIT',
  'Buscar por nombre, ciudad o país': 'Search by name, city or country',
  'Buscar': 'Search',
  'Ningún sitio con ese texto': 'No site matches that text',
  'Catálogo de basurales · Overture Maps (OpenStreetMap, ODbL)': 'Dump-site catalog · Overture Maps (OpenStreetMap, ODbL)',
  'Catálogo de basurales · Climate TRACE, CC BY 4.0': 'Dump-site catalog · Climate TRACE, CC BY 4.0',
  'Plumas de metano · NASA EMIT L2B CH4PLM': 'Methane plumes · NASA EMIT L2B CH4PLM',

  // Model panel: the numbers come from seed/calibracion.json
  'de menos de {0} ha': 'under {0} ha',
  'lisas: eco menor que {0} dB': 'smooth: echo below {0} dB',
  'Calibrados con {0} rellenos y {1} controles. La franja es el rango válido': 'Calibrated on {0} landfills and {1} controls. The band is the valid range',
  'Por debajo de {0}, {1} deja de ser persistente': 'Below {0}, {1} stops being persistent',
  'Desde {0}, aparecen manchas en la costa del Roggero': 'From {0} up, patches appear on the Roggero shore',
  'Con {0}, {1} ({2}) queda afuera': 'At {0}, {1} ({2}) is left out',
  'Entre lo liso conocido ({0}, {1}) y el relleno con menos eco ({2}, {3})': 'Between known smooth ground ({0}, {1}) and the landfill with the least echo ({2}, {3})',

  // names of the curated sites
  'Norte III, disposición final': 'Norte III, final disposal',
  'Relleno del CEAMSE al noreste de Norte III': 'CEAMSE landfill northeast of Norte III',
  'Relleno al norte de Norte III': 'Landfill north of Norte III',
  'Relleno junto a Norte III (oeste)': 'Landfill next to Norte III (west)',
  'Basural de Ministro Rivadavia': 'Ministro Rivadavia dump site',
  'Basural Cuartel V': 'Cuartel V dump site',
  'Mancha al oeste de Luján': 'Patch west of Luján',
  'Relleno sin nombre (OSM)': 'Unnamed landfill (OSM)',
  'Basural de Luján': 'Luján dump site',
}
