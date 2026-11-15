import maplibregl, { type GeoJSONSource, type ImageSource, type RasterTileSource } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { FeatureCollection } from 'geojson'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Marca, go, useRoute } from '../App'
import { Coherencia } from '../components/Coherencia'
import { Dot, Kpi, Picker, dec, fecha, num, pct, radar as radarTxt, veredicto, type Opcion } from '../components/ui'
import { useSitios } from '../data/api'
import { HAY_GOOGLE, creditoGoogle, enLimite, marcarLimite, sesionGoogle, tilesGoogle, useLimiteGoogle } from '../data/google'
import indice from '../data/seed/indice.json'
import { INDICES, ciudadFrame, filaCatalogo, idCatalogo, nombrePais, sitioCatalogo, useCatalogo, useFrames, useManchas, type Frame, type SitioCatalogo } from '../data/mapa'
import { UMBRAL_BAJO, type Imagen, type Sitio, type Veredicto } from '../data/types'
import { FRAME_AMBA, UMBRAL_NUEVO, conRadar, nombreFrame, nuevosConUsoConocido, posiblesNuevos, useVeredictos } from '../data/veredictos'
import { IDIOMAS, getLang, setLang, t, type Lang } from '../i18n'

// The background is Blue Marble (NASA GIBS); opening a site adds the 10 m Sentinel-2 scene
// of the chosen date, served by Microsoft Planetary Computer. Both work without keys.
// With VITE_GOOGLE_MAPS_KEY there's also a high-resolution view (Google, under 1 m, no
// date): it's only requested inside the boxes of the dump sites (open or not) and from ZOOM_GOOGLE on,
// because every tile is billed. Sentinel-2 is still used to compare dates.
// EOX cloudless Sentinel-2 mosaic (10 m): the background when zoomed in, across the whole map and not only on the open site
const MOSAICO = 'https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2024_3857/default/g/{z}/{y}/{x}.jpg'
const FONDO = 'https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_ShadedRelief_Bathymetry/default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg'
const s2 = (i: Imagen) =>
  `https://planetarycomputer.microsoft.com/api/data/v1/item/tiles/WebMercatorQuad/{z}/{x}/{y}@2x?collection=sentinel-2-l2a&item=${i.item}&assets=visual&asset_bidx=visual%7C1%2C2%2C3&nodata=0&format=png`

const COLOR = ['match', ['get', 'radar'], 'despierto', '#ec5b3f', 'quieto', '#5bb3a8', '#dfe5e1'] as unknown as maplibregl.ExpressionSpecification
// what the system looks for: awake blobs that aren't in any catalog. It has to stand out from everything else
const COLOR_NUEVO = '#ffd21f'
// catalog dump sites that don't fall in any processed frame: there's no radar data
const COLOR_SIN_DATO = '#9db4e8'
// the insomnia index outside the AMBA: the blobs, with the same palette as the AMBA PNG (magma, from 0.3 to 1)
const MAGMA = ['interpolate', ['linear'], ['get', 'i'], 0.3, '#641a80', 0.55, '#b73779', 0.8, '#fc8961', 1, '#fcfdbf'] as unknown as maplibregl.ExpressionSpecification
const ES_NUEVO = ['all', ['>=', ['coalesce', ['get', 'p'], 0], UMBRAL_NUEVO], ['==', ['get', 'q'], 0]] as unknown as maplibregl.FilterSpecification
// the clickable layers, from most to least important: if several are under the cursor the first one wins
const TOCABLES = ['punto', 'aro', 'contorno-relleno', 'nuevos', 'otros', 'catalogo']
// the starting view is the whole AMBA: the insomnia index grid
const AMBA: [number, number, number, number] = [indice.oeste, indice.sur, indice.este, indice.norte]
const margenAmba = (ancho: number) => (ancho > 860 ? { top: 70, bottom: 90, left: 40, right: 40 } : { top: 70, bottom: 90, left: 12, right: 12 })
const ZOOM_GOOGLE = 13
// the dump sites of the other frames have no outline or images loaded: fly there without zooming in as much
const ZOOM_OTRO = 9.5
// radius of the box where Google tiles are requested around a catalog dump site, which has no box of its own
const RADIO_GOOGLE_KM = 1.5

/** West, south, east, north box of `km` around a point. */
function cajaAlrededor(lat: number, lon: number, km = RADIO_GOOGLE_KM): [number, number, number, number] {
  const dLat = km / 111.32
  const dLon = km / (111.32 * Math.cos((lat * Math.PI) / 180))
  return [lon - dLon, lat - dLat, lon + dLon, lat + dLat]
}

type Caja = [number, number, number, number]

// The boxes where Google tiles are requested. The `gtile://` protocol checks each tile: if it doesn't touch any
// box it returns a transparent one without calling Google, so many separate boxes don't need one source per site
// indexed on a grid of CELDA degrees: with the whole catalog there are tens of thousands and each tile only checks its cells
const CELDA = 0.1
let cajasGoogle = new Map<string, Caja[]>()
const celdas = ([o, s, e, n]: Caja) => {
  const claves: string[] = []
  for (let i = Math.floor(o / CELDA); i <= Math.floor(e / CELDA); i++) for (let j = Math.floor(s / CELDA); j <= Math.floor(n / CELDA); j++) claves.push(`${i},${j}`)
  return claves
}
function indexar(cajas: Caja[]) {
  const grilla = new Map<string, Caja[]>()
  for (const c of cajas) for (const k of celdas(c)) (grilla.get(k) ?? grilla.set(k, []).get(k)!).push(c)
  return grilla
}
let tokenGoogle = ''
let vacio: Promise<ArrayBuffer> | null = null
const tileVacio = () =>
  (vacio ??= new OffscreenCanvas(256, 256).convertToBlob({ type: 'image/png' }).then((b) => b.arrayBuffer()))

/** West, south, east, north box of a Web Mercator tile. */
function cajaDelTile(z: number, x: number, y: number): Caja {
  const n = 2 ** z
  const lat = (j: number) => (Math.atan(Math.sinh(Math.PI * (1 - (2 * j) / n))) * 180) / Math.PI
  return [(x / n) * 360 - 180, lat(y + 1), ((x + 1) / n) * 360 - 180, lat(y)]
}

const tocan = (a: Caja, b: Caja) => a[0] < b[2] && b[0] < a[2] && a[1] < b[3] && b[1] < a[3]
const tocaAlguna = (c: Caja) => celdas(c).some((k) => cajasGoogle.get(k)?.some((b) => tocan(b, c)))

/** Zoom to see a whole site of `ha` hectares in high resolution (treats it as a circle). */
function zoomPorArea(ha: number | null | undefined): number {
  if (!ha || ha <= 0) return 15.5
  const radio = Math.sqrt((ha * 1e4) / Math.PI) // m
  // at zoom z, at the equator, 600 px cover 600 * 156543 / 2^z m; the goal is for the diameter to take ~300 px
  return Math.max(ZOOM_GOOGLE + 0.5, Math.min(17, Math.log2((300 * 156543) / (2 * radio * 1.15))))
}
type Vista = 'google' | 'sentinel'

/** Sentinel-2 tiles MapLibre requests when opening a site (512 px source: the tile z is the map's minus 1). */
function tilesDelSitio(s: Sitio): string[] {
  const ultima = s.imagenes[s.imagenes.length - 1]
  if (!ultima || !s.caja) return []
  const [o, sur, e, n] = s.caja
  const urls: string[] = []
  for (const z of [12, 13]) {
    const x = (lon: number) => Math.floor(((lon + 180) / 360) * 2 ** z)
    const y = (lat: number) => Math.floor(((1 - Math.asinh(Math.tan((lat * Math.PI) / 180)) / Math.PI) / 2) * 2 ** z)
    for (let i = x(o); i <= x(e); i++) for (let j = y(n); j <= y(sur); j++) urls.push(s2(ultima).replace('{z}', String(z)).replace('{x}', String(i)).replace('{y}', String(j)))
  }
  return urls
}

/** Leaves in the public/sw.js cache the latest image of each dump site, little by little and without slowing the map. */
async function precargar(sitios: Sitio[]) {
  if (!('serviceWorker' in navigator)) return
  await navigator.serviceWorker.ready
  if (!navigator.serviceWorker.controller) return // first visit: the cache starts filling on the next load
  const cola = sitios.flatMap(tilesDelSitio)
  const tanda = async () => {
    for (let url = cola.shift(); url; url = cola.shift()) await fetch(url).catch(() => null)
  }
  await Promise.all([tanda(), tanda(), tanda()])
}

function Ficha({ s, imagen, onImagen, vista, onVista }: { s: Sitio; imagen: Imagen | null; onImagen: (i: Imagen) => void; vista: Vista; onVista: (v: Vista) => void }) {
  return (
    <aside className="ficha" key={s.id}>
      <div className="row" style={{ alignItems: 'flex-start', flexWrap: 'nowrap' }}>
        <div className="grow">
          <h2>{t(s.nombre)}</h2>
          <div className="where">
            {s.lugar}
          </div>
        </div>
        <button className="btn icon" onClick={() => go('mapa')} aria-label={t('Cerrar')}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
            <path d="M5 5l14 14M19 5L5 19" />
          </svg>
        </button>
      </div>

      <div className="row" style={{ gap: 8 }}>
        <span className={`tag ${s.radar}`}>
          <Dot radar={s.radar} />
          {veredicto(s.radar)}
        </span>
      </div>

      <div className="kpis sm grid g2">
        <Kpi label={t('Insomnio')} value={pct(s.insomnio)} />
        <Kpi label={t('Superficie')} value={num(s.ha)} unit="ha" />
      </div>

      {s.umbral_bajo && <p className="motivo">{t('Despierto con el umbral bajo: insomnio mayor que {0}. El predio es chico, liso o de señal intermedia para la regla calibrada', pct(UMBRAL_BAJO))}</p>}

      <div className="crece">
        <h3>
          {t('Coherencia')} <span>{t('NISAR, {0} comparaciones', s.pares.length)}</span>
        </h3>
        <Coherencia
          llenar
          fechas={s.pares.map((p) => p.fecha)}
          series={[
            { nombre: t('Entorno'), color: 'var(--faint)', valores: s.pares.map((p) => p.anillo), tenue: true },
            { nombre: s.radar === 'no_alcanza' ? t('Sitio') : t('Sitio, {0}', radarTxt(s.radar).toLowerCase()), color: `var(--${s.radar.replace('_', '-')})`, valores: s.pares.map((p) => p.sitio) },
          ]}
        />
      </div>

      <div>
        <h3>
          {t('Imagen')} <span>{vista === 'google' ? t('Google, alta resolución, sin fecha') : t('Sentinel-2, 10 m')}</span>
        </h3>
        {(HAY_GOOGLE || s.imagenes.length > 0) && (
          <div className="dates">
            {HAY_GOOGLE && (
              <button aria-pressed={vista === 'google'} onClick={() => onVista('google')}>
                {t('Alta resolución')}
              </button>
            )}
            {s.imagenes.map((i) => (
              <button key={i.fecha} aria-pressed={vista === 'sentinel' && imagen?.fecha === i.fecha} onClick={() => onImagen(i)}>
                {fecha(i.fecha)}
              </button>
            ))}
          </div>
        )}
        {!s.imagenes.length && <p className="muted small">{t('Sin imagen Sentinel-2 despejada en el período')}</p>}
      </div>

      <div className="row" style={{ justifyContent: 'space-between' }}>
        <span className="coords">
          {s.lat.toFixed(4)}, {s.lon.toFixed(4)}
        </span>
        <a className="btn sm" href={`https://www.google.com/maps/@${s.lat},${s.lon},900m/data=!3m1!1e3`} target="_blank" rel="noreferrer">
          {t('Ver en Google Maps')}
        </a>
      </div>
    </aside>
  )
}

const Cerrar = () => (
  <button className="btn icon" onClick={() => go('mapa')} aria-label={t('Cerrar')}>
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
      <path d="M5 5l14 14M19 5L5 19" />
    </svg>
  </button>
)

const Pie = ({ lat, lon }: { lat: number; lon: number }) => (
  <div className="row" style={{ justifyContent: 'space-between' }}>
    <span className="coords">
      {lat.toFixed(4)}, {lon.toFixed(4)}
    </span>
    <a className="btn sm" href={`https://www.google.com/maps/@${lat},${lon},900m/data=!3m1!1e3`} target="_blank" rel="noreferrer">
      {t('Ver en Google Maps')}
    </a>
  </div>
)

/** Card of an awake blob that isn't in any catalog and that the model reads as a dump site. */
function FichaNuevo({ v, lugar }: { v: Veredicto; lugar: string }) {
  const p = typeof v.p_basural === 'number' ? v.p_basural : null
  return (
    <aside className="ficha" key={v.id}>
      <div className="row" style={{ alignItems: 'flex-start', flexWrap: 'nowrap' }}>
        <div className="grow">
          <h2>{t('Posible basural nuevo')}</h2>
          <div className="where">
            {lugar} · {v.id}
          </div>
        </div>
        <Cerrar />
      </div>

      <div className="row" style={{ gap: 8 }}>
        <span className="tag nuevo">
          <Dot radar="nuevo" />
          {t('No figura en ningún catálogo')}
        </span>
      </div>

      {p != null && (
        <div className="segun-modelo">
          <span className="src">{t('Según el modelo · basural u otra cosa')}</span>
          <div className="puntaje" role="img" aria-label={t('Puntaje de basural {0}, de 0 a 1', dec(p))}>
            <div className="bar">
              <div style={{ width: `${Math.round(Math.max(0, Math.min(1, p)) * 100)}%` }} />
            </div>
            <span className="num">{dec(p)}</span>
          </div>
          <small>{t('Puntaje de basural, de 0 a 1. No es una probabilidad')}</small>
        </div>
      )}

      <div className="kpis sm grid g2">
        <Kpi label={t('Insomnio')} value={v.insomnio == null ? '–' : pct(v.insomnio)} />
        <Kpi label={t('Superficie')} value={v.area_ha == null ? '–' : num(Math.round(v.area_ha))} unit="ha" />
      </div>

      <p className="note">{t('Mancha que el radar NISAR nunca ve quieta y que no está en ninguno de los catálogos de basurales. Señal compatible con actividad, sin verificar en terreno')}</p>

      <span className="grow" />
      <Pie lat={v.lat as number} lon={v.lon as number} />
    </aside>
  )
}

/** Card of a catalog dump site that doesn't fall in any processed NISAR frame. The web doesn't show the status of any registry. */
function FichaSinDato({ s }: { s: SitioCatalogo }) {
  return (
    <aside className="ficha" key={s.id}>
      <div className="row" style={{ alignItems: 'flex-start', flexWrap: 'nowrap' }}>
        <div className="grow">
          <h2>{s.nombre ?? t('Basural sin nombre')}</h2>
          <div className="where">
            {s.pais ? `${nombrePais(s.pais)} · ` : ''}
            {s.id}
          </div>
        </div>
        <Cerrar />
      </div>

      <div className="row" style={{ gap: 8 }}>
        <span className="tag sin_dato">
          <Dot radar="sin_dato" />
          {t('Sin procesar todavía')}
        </span>
      </div>

      <div className="kpis sm grid g2">
        <Kpi label={t('Insomnio')} value="–" />
        <Kpi label={t('Superficie')} value={s.ha == null ? '–' : s.ha < 10 ? dec(s.ha, 1) : num(Math.round(s.ha))} unit={s.ha == null ? undefined : 'ha'} />
      </div>

      <p className="note">
        {t('Está en el catálogo de basurales, pero todavía no procesamos pasadas de NISAR sobre este lugar: no hay índice de insomnio')}
        {s.fuentes.length > 0 && `. ${t('Fuente del catálogo: {0}', s.fuentes.map((f) => t(f)).join(', '))}`}
      </p>

      <span className="grow" />
      <Pie lat={s.lat} lon={s.lon} />
    </aside>
  )
}

/** Card of a catalog polygon with radar data: what `veredictos.json` has, without series or images. */
function FichaCatalogo({ v, lugar }: { v: Veredicto; lugar: string }) {
  const radar = v.radar ?? 'no_alcanza'
  return (
    <aside className="ficha" key={v.id}>
      <div className="row" style={{ alignItems: 'flex-start', flexWrap: 'nowrap' }}>
        <div className="grow">
          <h2>{v.nombre ?? t('Polígono sin nombre')}</h2>
          <div className="where">
            {lugar} · {v.id}
          </div>
        </div>
        <button className="btn icon" onClick={() => go('mapa')} aria-label={t('Cerrar')}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
            <path d="M5 5l14 14M19 5L5 19" />
          </svg>
        </button>
      </div>

      <div className="row" style={{ gap: 8 }}>
        <span className={`tag ${radar}`}>
          <Dot radar={radar} />
          {veredicto(radar)}
        </span>
      </div>

      <div className="kpis sm grid g2">
        <Kpi label={t('Insomnio')} value={v.insomnio == null ? '–' : pct(v.insomnio)} />
        <Kpi label={t('Superficie')} value={v.area_ha == null ? '–' : num(Math.round(v.area_ha))} unit="ha" />
      </div>

      {v.umbral_bajo && <p className="motivo">{t('Despierto con el umbral bajo: insomnio mayor que {0}. El predio es chico, liso o de señal intermedia para la regla calibrada', pct(UMBRAL_BAJO))}</p>}
      <p className="note">{t('Señal compatible con actividad, sin verificar en terreno')}</p>

      <span className="grow" />
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <span className="coords">
          {(v.lat as number).toFixed(4)}, {(v.lon as number).toFixed(4)}
        </span>
        <a className="btn sm" href={`https://www.google.com/maps/@${v.lat},${v.lon},900m/data=!3m1!1e3`} target="_blank" rel="noreferrer">
          {t('Ver en Google Maps')}
        </a>
      </div>
    </aside>
  )
}

/** Our own language selector (not the browser's): English or Español, no flags. */
function Idioma() {
  return <Picker className="float idioma" label={t('Idioma')} value={getLang()} onChange={(l: Lang) => setLang(l)} options={IDIOMAS} />
}

export default function Mapa() {
  const { sitios } = useSitios()
  const veredictos = useVeredictos()
  const catalogo = useCatalogo()
  const frames = useFrames()
  const manchas = useManchas()
  // the catalog dump sites with radar data that aren't a curated site: they go as points
  const otros = useMemo(() => conRadar(veredictos, sitios ?? []), [veredictos, sitios])
  // the awake blobs that aren't in any catalog: what the system looks for
  const nuevos = useMemo(() => posiblesNuevos(veredictos), [veredictos])
  const porFrame = useMemo(() => new Map((frames ?? []).map((f) => [f.frame, f] as [string, Frame])), [frames])
  const lugarDe = (frame: string) => ciudadFrame(porFrame.get(frame)) ?? nombreFrame(frame)
  const { page, query } = useRoute()
  // with a panel open there's no card: the map stays where it was
  const enMapa = page === 'mapa'
  const id = enMapa ? query.get('sitio') : null
  const sel = sitios?.find((s) => s.id === id) ?? null
  const selOtro = (!sel && id && (otros.find((v) => v.id === id) ?? nuevos.find((v) => v.id === id))) || null
  // a catalog dump site without radar data
  const selCat = useMemo(() => {
    const i = sel || selOtro || !catalogo ? -1 : filaCatalogo(catalogo, id)
    return i >= 0 ? sitioCatalogo(catalogo!, i) : null
  }, [sel, selOtro, catalogo, id])
  // the chosen point when it isn't a curated site (those have an outline)
  const punto = selOtro ? { lat: selOtro.lat as number, lon: selOtro.lon as number, color: selOtro.tipo === 'mancha' ? COLOR_NUEVO : '#ffffff' } : selCat ? { lat: selCat.lat, lon: selCat.lon, color: '#ffffff' } : null
  const caja = useRef<HTMLDivElement>(null)
  const mapa = useRef<maplibregl.Map | null>(null)
  const [listo, setListo] = useState(false)
  const [imagen, setImagen] = useState<Imagen | null>(null)
  const [vista, setVista] = useState<Vista>(HAY_GOOGLE ? 'google' : 'sentinel')
  const [credito, setCredito] = useState('')
  const limite = useLimiteGoogle()

  useEffect(() => {
    if (sitios) precargar(sitios)
  }, [sitios])
  const [verIndice, setVerIndice] = useState(false)

  // the map is created only once
  useEffect(() => {
    const m = new maplibregl.Map({
      container: caja.current!,
      style: {
        version: 8,
        sources: {
          fondo: { type: 'raster', tiles: [FONDO], tileSize: 256, maxzoom: 8 },
          mosaico: { type: 'raster', tiles: [MOSAICO], tileSize: 256, minzoom: 7, maxzoom: 15 },
        },
        layers: [
          { id: 'fondo', type: 'raster', source: 'fondo' },
          { id: 'mosaico', type: 'raster', source: 'mosaico', minzoom: 7, paint: { 'raster-opacity': ['interpolate', ['linear'], ['zoom'], 7, 0, 8, 1] } },
        ],
      },
      bounds: AMBA,
      fitBoundsOptions: { padding: margenAmba(caja.current!.clientWidth) },
      maxZoom: HAY_GOOGLE ? 19 : 15,
      attributionControl: false,
      dragRotate: false,
      pitchWithRotate: false,
    })
    m.touchZoomRotate.disableRotation()
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right')
    m.on('load', () => setListo(true))
    mapa.current = m
    // with ?captura the map is exposed to the script that builds the video images (video/compartido/scripts/capturas_mapa.mjs)
    if (new URLSearchParams(location.search).has('captura')) (window as unknown as { mapa?: maplibregl.Map }).mapa = m
    return () => {
      mapa.current = null
      m.remove()
    }
  }, [])

  // points from afar; up close, the site outline (or a ring if OpenStreetMap doesn't have it)
  useEffect(() => {
    const m = mapa.current
    if (!m || !listo || !sitios) return
    const puntos: FeatureCollection = {
      type: 'FeatureCollection',
      features: sitios.map((s) => ({ type: 'Feature', geometry: { type: 'Point', coordinates: [s.lon, s.lat] }, properties: { id: s.id, radar: s.radar, contorno: !!s.contorno } })),
    }
    const contornos: FeatureCollection = {
      type: 'FeatureCollection',
      features: sitios.filter((s) => s.contorno).map((s) => ({ type: 'Feature', geometry: s.contorno!, properties: { id: s.id, radar: s.radar } })),
    }
    const src = m.getSource('sitios') as GeoJSONSource | undefined
    if (src) {
      src.setData(puntos)
      ;(m.getSource('contornos') as GeoJSONSource).setData(contornos)
      return
    }
    const deCerca = (desde: number, hasta: number): maplibregl.ExpressionSpecification => ['interpolate', ['linear'], ['zoom'], 9, desde, 10.5, hasta]
    m.addSource('sitios', { type: 'geojson', data: puntos })
    m.addSource('contornos', { type: 'geojson', data: contornos })
    // AMBA insomnia index: a precomputed PNG (pipeline_insomnio.py indice) with its four corners
    m.addSource('indice', { type: 'image', url: `${import.meta.env.BASE_URL}${indice.url}`, coordinates: indice.coordinates as [[number, number], [number, number], [number, number], [number, number]] })
    m.addLayer({ id: 'indice', type: 'raster', source: 'indice', minzoom: 7, paint: { 'raster-opacity': 0.8, 'raster-resampling': 'nearest', 'raster-fade-duration': 0 } })
    m.addLayer({ id: 'contorno-relleno', type: 'fill', source: 'contornos', minzoom: 9, paint: { 'fill-color': COLOR, 'fill-opacity': deCerca(0, 0.08) } })
    m.addLayer({ id: 'contorno-linea', type: 'line', source: 'contornos', minzoom: 9, layout: { 'line-join': 'round' }, paint: { 'line-color': COLOR, 'line-width': 2, 'line-opacity': deCerca(0, 1) } })
    m.addLayer({
      id: 'aro',
      type: 'circle',
      source: 'sitios',
      minzoom: 9,
      filter: ['!', ['get', 'contorno']],
      paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 9, 10, 12, 30, 14, 70, 15, 120], 'circle-opacity': 0, 'circle-stroke-color': COLOR, 'circle-stroke-width': 2, 'circle-stroke-opacity': deCerca(0, 1) },
    })
    m.addLayer({
      id: 'halo',
      type: 'circle',
      source: 'sitios',
      paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 1, 9, 8, 14], 'circle-color': COLOR, 'circle-opacity': deCerca(0.28, 0) },
    })
    m.addLayer({
      id: 'punto',
      type: 'circle',
      source: 'sitios',
      paint: {
        'circle-radius': ['interpolate', ['linear'], ['zoom'], 1, 4, 8, 6],
        'circle-color': COLOR,
        'circle-opacity': deCerca(1, 0),
        'circle-stroke-color': '#ffffff',
        'circle-stroke-width': 1.5,
        'circle-stroke-opacity': deCerca(1, 0),
      },
    })
  }, [listo, sitios])

  // a single handler for everything clickable: with several layers under the cursor the most important one wins
  useEffect(() => {
    const m = mapa.current
    if (!m || !listo) return
    const debajo = (e: maplibregl.MapMouseEvent) => {
      const capas = TOCABLES.filter((c) => m.getLayer(c))
      const fs = capas.length ? m.queryRenderedFeatures([[e.point.x - 3, e.point.y - 3], [e.point.x + 3, e.point.y + 3]], { layers: capas }) : []
      return fs.sort((a, b) => TOCABLES.indexOf(a.layer.id) - TOCABLES.indexOf(b.layer.id))[0]
    }
    const click = (e: maplibregl.MapMouseEvent) => {
      const f = debajo(e)
      if (f) go('mapa', `sitio=${f.properties.id}`)
    }
    const mover = (e: maplibregl.MapMouseEvent) => (m.getCanvas().style.cursor = debajo(e) ? 'pointer' : '')
    m.on('click', click)
    m.on('mousemove', mover)
    return () => {
      m.off('click', click)
      m.off('mousemove', mover)
    }
  }, [listo])

  // every catalog dump site without radar data: small points of another color, below everything
  useEffect(() => {
    const m = mapa.current
    if (!m || !listo || !catalogo || !sitios || !veredictos) return
    // the ones already drawn with what the radar sees (or that are a curated site) aren't repeated
    const yaEstan = new Set(veredictos.sitios.filter((v) => v.tipo === 'catalogo').map((v) => v.id))
    const features: FeatureCollection['features'] = []
    for (let i = 0; i < catalogo.n; i++) {
      const idc = idCatalogo(i)
      if (!yaEstan.has(idc)) features.push({ type: 'Feature', geometry: { type: 'Point', coordinates: [catalogo.lon[i], catalogo.lat[i]] }, properties: { id: idc } })
    }
    const datos: FeatureCollection = { type: 'FeatureCollection', features }
    const src = m.getSource('catalogo') as GeoJSONSource | undefined
    if (src) {
      src.setData(datos)
      return
    }
    m.addSource('catalogo', { type: 'geojson', data: datos })
    m.addLayer(
      {
        id: 'catalogo',
        type: 'circle',
        source: 'catalogo',
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 1, 1.4, 5, 2.4, 8, 3.6, 12, 6],
          'circle-color': COLOR_SIN_DATO,
          'circle-opacity': ['interpolate', ['linear'], ['zoom'], 1, 0.7, 8, 0.95],
          'circle-stroke-color': '#16233f',
          'circle-stroke-width': ['interpolate', ['linear'], ['zoom'], 4, 0, 7, 1],
        },
      },
      ['otros', 'nuevo-relleno', 'nuevos-halo', 'halo', 'aro', 'contorno-relleno'].find((c) => m.getLayer(c)),
    )
  }, [listo, catalogo, sitios, veredictos])

  // the insomnia index of every frame: each frame's box and its awake blobs, painted by insomnia.
  // The AMBA also has the full index as an image, so its blobs aren't painted on top
  useEffect(() => {
    const m = mapa.current
    if (!m || !listo || !sitios || !frames || m.getSource('frames')) return
    const cajas: FeatureCollection = {
      type: 'FeatureCollection',
      features: frames.map((f) => {
        const [o, s, e, n] = f.bbox
        return { type: 'Feature', geometry: { type: 'Polygon', coordinates: [[[o, s], [e, s], [e, n], [o, n], [o, s]]] }, properties: { frame: f.frame } }
      }),
    }
    m.addSource('frames', { type: 'geojson', data: cajas })
    // from afar a region is a few pixels and its blobs can't be seen: the box is filled and above the points, and it fades
    // when zooming in, once the blobs can be seen. It isn't clickable: clicks still reach the points below
    m.addLayer({ id: 'frames-relleno', type: 'fill', source: 'frames', paint: { 'fill-color': '#fc8961', 'fill-opacity': ['interpolate', ['linear'], ['zoom'], 2, 0.85, 5, 0.6, 6.5, 0.15, 8, 0] } })
    m.addLayer({ id: 'frames', type: 'line', source: 'frames', paint: { 'line-color': '#fcfdbf', 'line-width': ['interpolate', ['linear'], ['zoom'], 1, 1.5, 6, 2], 'line-opacity': 0.95 } })
  }, [listo, sitios, frames])

  // the full index of the other frames, if it was exported (motor/indice_png_web.py): one image per frame, like the AMBA one
  useEffect(() => {
    const m = mapa.current
    if (!m || !listo || !sitios) return
    for (const x of INDICES) {
      const idc = `indice-${x.frame}`
      if (m.getSource(idc)) continue
      m.addSource(idc, { type: 'image', url: `${import.meta.env.BASE_URL}${x.url}`, coordinates: x.coordinates })
      m.addLayer({ id: idc, type: 'raster', source: idc, minzoom: 5, layout: { visibility: 'none' }, paint: { 'raster-opacity': 0.8, 'raster-resampling': 'nearest', 'raster-fade-duration': 0 } }, 'indice')
    }
  }, [listo, sitios])

  useEffect(() => {
    const m = mapa.current
    if (!m || !listo || !sitios || !manchas || m.getSource('manchas')) return
    // the frames that have the full index as an image (the AMBA and the ones in seed/indices.json) don't paint their blobs,
    // but they do paint the outline of the possible new ones
    const conImagen = [FRAME_AMBA, ...INDICES.map((x) => x.frame)].map((f) => `MAN-${f}-`)
    const fueraDelAmba = ['all', ...conImagen.map((pre) => ['!=', ['slice', ['get', 'id'], 0, pre.length], pre])] as unknown as maplibregl.FilterSpecification
    const debajoDe = m.getLayer('contorno-relleno') ? 'contorno-relleno' : undefined
    m.addSource('manchas', { type: 'geojson', data: manchas })
    m.addLayer({ id: 'manchas', type: 'fill', source: 'manchas', filter: fueraDelAmba, paint: { 'fill-color': MAGMA, 'fill-opacity': 0.8, 'fill-antialias': false } }, debajoDe)
    // from afar a blob is smaller than a screen pixel: without this line the index wouldn't show until zooming in
    m.addLayer({ id: 'manchas-borde', type: 'line', source: 'manchas', maxzoom: 9, filter: fueraDelAmba, paint: { 'line-color': MAGMA, 'line-width': 1.2, 'line-opacity': 0.9 } }, debajoDe)
    // the outline of the possible new dump sites always stays, with the index on or off
    m.addLayer({ id: 'nuevo-contorno', type: 'line', source: 'manchas', minzoom: 8, filter: ES_NUEVO, layout: { 'line-join': 'round' }, paint: { 'line-color': COLOR_NUEVO, 'line-width': 2.5 } }, ['nuevos-halo', 'halo'].find((c) => m.getLayer(c)))
    m.addLayer({ id: 'nuevo-relleno', type: 'fill', source: 'manchas', minzoom: 8, filter: ES_NUEVO, paint: { 'fill-color': COLOR_NUEVO, 'fill-opacity': 0.12 } }, 'nuevo-contorno')
  }, [listo, sitios, manchas])

  // the possible new dump sites: above the whole catalog, with another color and a halo
  useEffect(() => {
    const m = mapa.current
    if (!m || !listo || !sitios || !nuevos.length) return
    const datos: FeatureCollection = {
      type: 'FeatureCollection',
      features: nuevos.map((v) => ({ type: 'Feature', geometry: { type: 'Point', coordinates: [v.lon as number, v.lat as number] }, properties: { id: v.id } })),
    }
    const src = m.getSource('nuevos') as GeoJSONSource | undefined
    if (src) {
      src.setData(datos)
      return
    }
    const debajoDe = ['halo', 'aro', 'contorno-relleno'].find((c) => m.getLayer(c))
    const deLejos: maplibregl.ExpressionSpecification = ['interpolate', ['linear'], ['zoom'], 9.5, 1, 11.5, 0]
    m.addSource('nuevos', { type: 'geojson', data: datos })
    m.addLayer({ id: 'nuevos-halo', type: 'circle', source: 'nuevos', paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 1, 9, 8, 15], 'circle-color': COLOR_NUEVO, 'circle-opacity': ['interpolate', ['linear'], ['zoom'], 9.5, 0.3, 11.5, 0] } }, debajoDe)
    m.addLayer(
      {
        id: 'nuevos',
        type: 'circle',
        source: 'nuevos',
        paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 1, 4.5, 8, 6.5], 'circle-color': COLOR_NUEVO, 'circle-opacity': deLejos, 'circle-stroke-color': '#3a2c00', 'circle-stroke-width': 1.5, 'circle-stroke-opacity': deLejos },
      },
      debajoDe,
    )
  }, [listo, sitios, nuevos])

  useEffect(() => {
    const m = mapa.current
    if (!m || !listo) return
    for (const capa of ['indice', ...INDICES.map((x) => `indice-${x.frame}`), 'frames', 'frames-relleno', 'manchas', 'manchas-borde']) if (m.getLayer(capa)) m.setLayoutProperty(capa, 'visibility', verIndice ? 'visible' : 'none')
  }, [listo, sitios, frames, manchas, verIndice])

  // the dump sites of the other frames: one point per catalog polygon, under the AMBA sites
  useEffect(() => {
    const m = mapa.current
    if (!m || !listo || !otros.length) return
    const puntos: FeatureCollection = {
      type: 'FeatureCollection',
      features: otros.map((v) => ({ type: 'Feature', geometry: { type: 'Point', coordinates: [v.lon as number, v.lat as number] }, properties: { id: v.id, radar: v.radar ?? 'no_alcanza' } })),
    }
    const src = m.getSource('otros') as GeoJSONSource | undefined
    if (src) {
      src.setData(puntos)
      return
    }
    const debajoDe = ['nuevo-relleno', 'nuevos-halo', 'halo', 'aro', 'contorno-relleno'].find((c) => m.getLayer(c))
    m.addSource('otros', { type: 'geojson', data: puntos })
    m.addLayer(
      {
        id: 'otros',
        type: 'circle',
        source: 'otros',
        paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 1, 4, 6, 5, 10, 7], 'circle-color': COLOR, 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 1, 'circle-opacity': 0.95 },
      },
      debajoDe,
    )
  }, [listo, otros])

  // the chosen point, with a ring
  const puntoSel = punto ? `${punto.lon},${punto.lat},${punto.color}` : ''
  useEffect(() => {
    const m = mapa.current
    if (!m || !listo) return
    const datos: FeatureCollection = { type: 'FeatureCollection', features: punto ? [{ type: 'Feature', geometry: { type: 'Point', coordinates: [punto.lon, punto.lat] }, properties: { color: punto.color } }] : [] }
    const src = m.getSource('elegido') as GeoJSONSource | undefined
    if (src) {
      src.setData(datos)
      return
    }
    m.addSource('elegido', { type: 'geojson', data: datos })
    m.addLayer({ id: 'elegido', type: 'circle', source: 'elegido', paint: { 'circle-radius': 16, 'circle-opacity': 0, 'circle-stroke-color': ['get', 'color'], 'circle-stroke-width': 2.5 } })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [listo, puntoSel])

  /** The overview: the world with every processed region (the AMBA and the catalog points). Without the catalog, the AMBA. */
  const general = (): [number, number, number, number] => {
    if (!otros.length) return AMBA
    const lons = [AMBA[0], AMBA[2], ...(frames ?? []).flatMap((f) => [f.bbox[0], f.bbox[2]]), ...otros.map((v) => v.lon as number)]
    const lats = [AMBA[1], AMBA[3], ...(frames ?? []).flatMap((f) => [f.bbox[1], f.bbox[3]]), ...otros.map((v) => v.lat as number)]
    return [Math.min(...lons), Math.max(-80, Math.min(...lats)), Math.max(...lons), Math.min(80, Math.max(...lats))]
  }
  /** Zoom out until every region is visible. */
  const verOtros = () => {
    go('mapa')
    const m = mapa.current
    if (!m) return
    m.fitBounds(general(), { padding: margenAmba(m.getContainer().clientWidth), duration: 1800 })
  }

  // on entry, the world map with every dump site; if a site is opened directly, it goes there
  const arranco = useRef(false)
  useEffect(() => {
    const m = mapa.current
    if (!m || !listo || !otros.length || arranco.current) return
    arranco.current = true
    if (!id) m.fitBounds(general(), { padding: margenAmba(m.getContainer().clientWidth), duration: 0 })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [listo, otros])

  // when choosing a site: fly there and show its latest image
  useEffect(() => {
    const m = mapa.current
    if (!m || !listo) return
    // when the card closes the map stays where it is; "Ver todo" zooms out
    if (!sel && !punto) return
    const ancho = m.getContainer().clientWidth
    const margen = ancho > 860 ? { right: 440, top: 80, bottom: 100, left: 60 } : { bottom: 400, top: 80, left: 24, right: 24 }
    if (!sel) {
      // a catalog point or a new blob: there's no saved crop, it flies to the point
      // (new blobs have an outline from zoom 8: it goes a bit closer to show it).
      // With Google it zooms in until the whole site is visible in high resolution
      if (HAY_GOOGLE) {
        setVista('google')
        m.flyTo({ center: [punto!.lon, punto!.lat], zoom: zoomPorArea(selOtro ? selOtro.area_ha : selCat?.ha), padding: margen, duration: 2600, essential: true })
      } else {
        const zoom = selOtro?.tipo === 'mancha' ? 11 : ZOOM_OTRO
        m.flyTo({ center: [punto!.lon, punto!.lat], zoom: Math.max(zoom, Math.min(m.getZoom(), 12)), padding: margen, duration: 2200, essential: true })
      }
      return
    }
    setImagen(sel.imagenes[sel.imagenes.length - 1] ?? null)
    if (HAY_GOOGLE) setVista('google')
    const anillo = sel.contorno?.coordinates[0]
    if (HAY_GOOGLE && anillo) {
      // with high resolution the site is framed, not the several-km box
      const lons = anillo.map((p) => p[0])
      const lats = anillo.map((p) => p[1])
      m.fitBounds([Math.min(...lons), Math.min(...lats), Math.max(...lons), Math.max(...lats)], { padding: margen, maxZoom: 17, duration: 2200, essential: true })
    } else if (HAY_GOOGLE) {
      m.flyTo({ center: [sel.lon, sel.lat], zoom: 15.5, padding: margen, duration: 2200, essential: true })
    } else if (sel.caja) {
      const [o, s, e, n] = sel.caja
      m.fitBounds([o, s, e, n], { padding: margen, maxZoom: 14.5, duration: 1800, essential: true })
    } else {
      m.flyTo({ center: [sel.lon, sel.lat], zoom: 13.6, padding: margen, duration: 1800, essential: true })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [listo, sel, puntoSel])

  // the image of the chosen date: the site's stored crop (works offline) and,
  // underneath, the whole scene in tiles to see the surroundings when online
  useEffect(() => {
    const m = mapa.current
    if (!m || !listo || !imagen || !sel) return
    const antesDe = (...capas: string[]) => capas.find((c) => m.getLayer(c))
    const tiles = m.getSource('escena') as RasterTileSource | undefined
    if (tiles) tiles.setTiles([s2(imagen)])
    else {
      m.addSource('escena', { type: 'raster', tiles: [s2(imagen)], tileSize: 512, minzoom: 8, maxzoom: 14 })
      m.addLayer({ id: 'escena', type: 'raster', source: 'escena', minzoom: 8, paint: { 'raster-fade-duration': 200 } }, antesDe('recorte', 'google', 'indice', 'contorno-relleno'))
    }
    if (!sel.caja) return
    const [o, s, e, n] = sel.caja
    const recorte = { url: `${import.meta.env.BASE_URL}escenas/${sel.id}/${imagen.fecha}.jpg`, coordinates: [[o, n], [e, n], [e, s], [o, s]] as [[number, number], [number, number], [number, number], [number, number]] }
    const guardado = m.getSource('recorte') as ImageSource | undefined
    if (guardado) guardado.updateImage(recorte)
    else {
      m.addSource('recorte', { type: 'image', ...recorte })
      m.addLayer({ id: 'recorte', type: 'raster', source: 'recorte', paint: { 'raster-fade-duration': 0 } }, antesDe('google', 'indice', 'contorno-relleno'))
    }
  }, [listo, imagen, sel])

  // the site's Sentinel-2 image is only shown with that site open: in the overview it would look like a patch
  useEffect(() => {
    const m = mapa.current
    if (!m || !listo) return
    for (const capa of ['escena', 'recorte']) if (m.getLayer(capa)) m.setLayoutProperty(capa, 'visibility', sel ? 'visible' : 'none')
  }, [listo, imagen, sel])

  // Google high resolution: at high zoom, inside the box of any dump site, without having to open it.
  // Curated sites have their own box; the rest of the catalog and the blobs use one of RADIO_GOOGLE_KM around the point
  const idSel = sel?.id ?? selOtro?.id ?? selCat?.id
  useEffect(() => {
    const cajas: Caja[] = (sitios ?? []).map((s) => s.caja ?? cajaAlrededor(s.lat, s.lon))
    // the whole catalog (with radar data or not) and the new blobs
    if (catalogo) for (let i = 0; i < catalogo.n; i++) cajas.push(cajaAlrededor(catalogo.lat[i], catalogo.lon[i]))
    for (const v of [...otros, ...nuevos]) if (v.lat != null && v.lon != null) cajas.push(cajaAlrededor(v.lat, v.lon))
    cajasGoogle = indexar(cajas)
    // tiles that came back empty are requested again with the new boxes
    const fuente = mapa.current?.getSource('google') as RasterTileSource | undefined
    fuente?.setTiles(['gtile://{z}/{x}/{y}'])
  }, [sitios, catalogo, otros, nuevos])

  useEffect(() => {
    const m = mapa.current
    if (!HAY_GOOGLE || !m || !listo) return
    let vivo = true
    maplibregl.addProtocol('gtile', async ({ url }, abort) => {
      const [z, x, y] = url.slice('gtile://'.length).split('/').map(Number)
      if (!tokenGoogle || enLimite() || !tocaAlguna(cajaDelTile(z, x, y))) return { data: await tileVacio() }
      const r = await fetch(tilesGoogle(tokenGoogle).replace('{z}', String(z)).replace('{x}', String(x)).replace('{y}', String(y)), { signal: abort.signal })
      // daily quota used up: stop asking until it resets; the notice at the bottom says until when
      if (r.status === 429) {
        marcarLimite()
        return { data: await tileVacio() }
      }
      if (!r.ok) throw new Error(`Google tile ${r.status}`)
      return { data: await r.arrayBuffer() }
    })
    const acreditar = () => {
      const b = m.getBounds()
      const vista: Caja = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()]
      if (!tokenGoogle || m.getZoom() < ZOOM_GOOGLE || !tocaAlguna(vista)) return setCredito('')
      creditoGoogle(tokenGoogle, m.getZoom(), vista).then((c) => vivo && setCredito(c), () => null)
    }
    sesionGoogle().then(
      (t) => {
        if (!vivo || mapa.current !== m) return
        tokenGoogle = t
        m.addSource('google', { type: 'raster', tiles: ['gtile://{z}/{x}/{y}'], tileSize: 256, minzoom: ZOOM_GOOGLE, maxzoom: 20 })
        m.addLayer({ id: 'google', type: 'raster', source: 'google', minzoom: ZOOM_GOOGLE, paint: { 'raster-fade-duration': 200 } }, m.getLayer('indice') ? 'indice' : m.getLayer('contorno-relleno') ? 'contorno-relleno' : undefined)
        m.on('moveend', acreditar)
        acreditar()
      },
      (e: Error) => {
        console.warn(e.message)
        if (vivo) setVista('sentinel')
      },
    )
    return () => {
      vivo = false
      setCredito('')
      maplibregl.removeProtocol('gtile')
      if (mapa.current !== m) return
      m.off('moveend', acreditar)
      if (m.getLayer('google')) m.removeLayer('google')
      if (m.getSource('google')) m.removeSource('google')
    }
  }, [listo])

  // when the card closes the Google view comes back, which on the general map is the only high-resolution one
  useEffect(() => {
    if (HAY_GOOGLE && !idSel) setVista('google')
  }, [idSel])

  // the chosen view: Google covers Sentinel-2 or hides; with Google the outline fill doesn't tint the image
  useEffect(() => {
    const m = mapa.current
    if (!m || !listo) return
    const aplicar = () => {
      if (m.getLayer('google')) m.setLayoutProperty('google', 'visibility', vista === 'google' ? 'visible' : 'none')
      if (m.getLayer('contorno-relleno')) m.setPaintProperty('contorno-relleno', 'fill-opacity', ['interpolate', ['linear'], ['zoom'], 9, 0, 10.5, 0.08, ZOOM_GOOGLE + 1, vista === 'google' && HAY_GOOGLE ? 0 : 0.08])
    }
    aplicar()
    m.on('styledata', aplicar)
    return () => {
      m.off('styledata', aplicar)
    }
  }, [listo, vista, idSel])

  // "Ir a un sitio": only the awake sites (red on the map), grouped by country. Argentina first and, within each
  // country, the named ones and at the end the unnamed polygons
  const idioma = getLang()
  const opciones = useMemo(() => {
    type Op = Opcion<string> & { orden: number }
    const paisDe = (frame: string) => nombrePais(porFrame.get(frame)?.pais ?? (frame === FRAME_AMBA ? 'ARG' : frame.split('_')[0]))
    const ops: Op[] = [
      ...(sitios ?? []).filter((s) => s.radar === 'despierto').map((s) => ({ value: s.id, label: t(s.nombre), sub: s.lugar, radar: s.radar, grupo: nombrePais(s.pais), orden: 1 })),
      ...otros.filter((v) => v.radar === 'despierto').map((v) => ({ value: v.id, label: v.nombre ?? `${t('Polígono sin nombre')} · ${v.id}`, sub: lugarDe(v.frame), radar: 'despierto' as const, grupo: paisDe(v.frame), orden: v.nombre ? 1 : 2 })),
    ]
    const argentina = nombrePais('ARG')
    return ops.sort((a, b) => Number(b.grupo === argentina) - Number(a.grupo === argentina) || a.grupo!.localeCompare(b.grupo!, idioma) || a.orden - b.orden || a.label.localeCompare(b.label, idioma))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sitios, otros, porFrame, idioma])
  const cuenta = useMemo(() => {
    const n = { despierto: 0, quieto: 0, no_alcanza: 0 }
    for (const s of sitios ?? []) n[s.radar]++
    for (const v of otros) n[v.radar ?? 'no_alcanza']++
    return n
  }, [sitios, otros])
  const sinDato = catalogo ? catalogo.n - (veredictos?.sitios.filter((v) => v.tipo === 'catalogo').length ?? 0) : 0
  const conUso = nuevosConUsoConocido(veredictos)

  return (
    <>
      <div className="map" ref={caja} />
      {HAY_GOOGLE && limite && (
        <div className="aviso-limite" role="status">
          {t(
            limite.toDateString() === new Date().toDateString()
              ? 'Llegamos al límite diario de imágenes de Google: el mapa sigue con Sentinel-2. La vista de Google vuelve hoy a las {0} (tu hora).'
              : 'Llegamos al límite diario de imágenes de Google: el mapa sigue con Sentinel-2. La vista de Google vuelve mañana a las {0} (tu hora).',
            limite.toLocaleTimeString(idioma === 'es' ? 'es-AR' : 'en-US', { hour: '2-digit', minute: '2-digit' }),
          )}
        </div>
      )}
      <div className={`map-top ${sel || punto ? 'con-ficha' : ''}`}>
        <Marca despiertos={cuenta.despierto} total={cuenta.despierto + cuenta.quieto + cuenta.no_alcanza} frames={veredictos?.frames?.length ?? 0} />
        <Picker
          className="float"
          label={t('Ir a un sitio')}
          placeholder={t('Ir a un sitio')}
          value={id ?? ''}
          onChange={(v) => go('mapa', `sitio=${v}`)}
          options={opciones}
        />
        {(sel || punto) && (
          <button className="btn float" onClick={verOtros}>
            {t('Ver todo')}
          </button>
        )}
        <Idioma />
      </div>
      <div className="map-legend">
        <div className="estados">
          {nuevos.length > 0 && (
            <span
              className="destacado"
              title={`${t('Manchas despiertas que no están en ningún catálogo y que el modelo lee como basural. Sin verificar')}${conUso ? `. ${t('Otras {0} quedan afuera porque OpenStreetMap ya las explica con otro uso', conUso)}` : ''}`}
            >
              <span className="dot nuevo" />
              {t('Posible basural nuevo')}
              <b className="num">{num(nuevos.length)}</b>
            </span>
          )}
          {(['despierto', 'quieto', 'no_alcanza'] as const).map((r) => (
            <span key={r}>
              <span className={`dot ${r}`} />
              {radarTxt(r)}
              <b className="num">{num(cuenta[r])}</b>
            </span>
          ))}
          {catalogo && (
            <span title={t('Basurales del catálogo donde todavía no procesamos pasadas de NISAR')}>
              <span className="dot sin_dato" />
              {t('Sin procesar todavía')}
              <b className="num">{num(sinDato)}</b>
            </span>
          )}
        </div>
        <button
          className="capa"
          role="switch"
          aria-checked={verIndice}
          onClick={() => setVerIndice((v) => !v)}
          title={t('Índice de insomnio relativo, de 0 a 1; transparente por debajo de {3} y en el agua. En el AMBA, {0} comparaciones de NISAR, del {1} al {2}. Donde no hay imagen del índice se pintan las manchas despiertas', indice.pares, fecha(indice.desde, true), fecha(indice.hasta, true), dec(indice.transparente_bajo, 1))}
        >
          <span>{t('Índice de insomnio')}</span>
          <i />
        </button>
        {verIndice && (
          <div className="escala">
            <div />
            <span>{getLang() === 'es' ? '0,3' : '0.3'}</span>
            <span>1</span>
            {frames && frames.length > 1 && <small>{t('Recuadro: cada región procesada con NISAR. Acercate a un recuadro para ver el índice')}</small>}
          </div>
        )}
        {otros.length > 0 && (
          <button className="otros-frames" onClick={verOtros} title={t('Alejar el mapa hasta ver todos los frames procesados')}>
            <b>{t('{0} basurales en {1} regiones', num(otros.length + (sitios?.length ?? 0)), new Set([FRAME_AMBA, ...otros.map((v) => v.frame)]).size)}</b>
            <span>{t('Polígonos del catálogo, sin verificar')}</span>
          </button>
        )}
      </div>
      <div className="map-credit">
        {vista === 'google' && credito && (
          <>
            <b className="google">Google</b> {credito} ·{' '}
          </>
        )}
        {t('Índice: NISAR GUNW (NASA/ISRO, vía ASF DAAC), agua de JRC Global Surface Water · Contornos: © OpenStreetMap')}
        {catalogo && t(' · Catálogo de basurales: © OpenStreetMap vía Overture Maps, Climate TRACE (CC BY 4.0), U.S. EPA LMOP, NASA EMIT')} · {t('Imágenes:')}{' '}
        <a href="https://www.earthdata.nasa.gov/engage/open-data-services-software/earthdata-developer-portal/gibs-api" target="_blank" rel="noreferrer">
          NASA GIBS
        </a>{' '}
        · Sentinel-2:{' '}
        <a href="https://planetarycomputer.microsoft.com/dataset/sentinel-2-l2a" target="_blank" rel="noreferrer">
          {t('ESA Copernicus, vía Planetary Computer')}
        </a>{' '}
        · {t('Mosaico:')}{' '}
        <a href="https://s2maps.eu" target="_blank" rel="noreferrer">
          {t('Sentinel-2 cloudless 2024 de EOX (CC BY-NC-SA 4.0)')}
        </a>
      </div>
      {selOtro && (selOtro.tipo === 'mancha' ? <FichaNuevo v={selOtro} lugar={lugarDe(selOtro.frame)} /> : <FichaCatalogo v={selOtro} lugar={lugarDe(selOtro.frame)} />)}
      {selCat && <FichaSinDato s={selCat} />}
      {sel && (
        <Ficha
          s={sel}
          imagen={imagen}
          vista={vista}
          onVista={setVista}
          onImagen={(i) => {
            setImagen(i)
            setVista('sentinel')
          }}
        />
      )}
    </>
  )
}
