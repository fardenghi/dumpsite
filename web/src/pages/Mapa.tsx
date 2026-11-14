import maplibregl, { type GeoJSONSource, type ImageSource, type RasterTileSource } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { FeatureCollection } from 'geojson'
import { useEffect, useRef, useState } from 'react'
import { go, useRoute } from '../App'
import { Coherencia } from '../components/Coherencia'
import { Dot, Kpi, RADAR, REGISTRO, fecha, num, pais, pct, veredicto } from '../components/ui'
import { useSitios } from '../data/api'
import type { Imagen, Sitio } from '../data/types'

// Sin claves. El fondo es Blue Marble (NASA GIBS); al abrir un sitio se suma la escena
// Sentinel-2 de 10 m de la fecha elegida, servida por Microsoft Planetary Computer.
const FONDO = 'https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_ShadedRelief_Bathymetry/default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg'
const s2 = (i: Imagen) =>
  `https://planetarycomputer.microsoft.com/api/data/v1/item/tiles/WebMercatorQuad/{z}/{x}/{y}@2x?collection=sentinel-2-l2a&item=${i.item}&assets=visual&asset_bidx=visual%7C1%2C2%2C3&nodata=0&format=png`

const COLOR = ['match', ['get', 'radar'], 'despierto', '#ec5b3f', 'quieto', '#5bb3a8', '#d8d2cc'] as unknown as maplibregl.ExpressionSpecification
const MUNDO = { center: [-20, 8] as [number, number], zoom: 1.5 }

function Ficha({ s, imagen, onImagen }: { s: Sitio; imagen: Imagen | null; onImagen: (i: Imagen) => void }) {
  return (
    <aside className="ficha" key={s.id}>
      <div className="row" style={{ alignItems: 'flex-start', flexWrap: 'nowrap' }}>
        <div className="grow">
          <h2>{s.nombre}</h2>
          <div className="where">
            {s.lugar}, {pais(s.pais)}
          </div>
        </div>
        <button className="btn icon" onClick={() => go('mapa')} aria-label="Cerrar">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
            <path d="M5 5l14 14M19 5L5 19" />
          </svg>
        </button>
      </div>

      <div className="row" style={{ gap: 8 }}>
        <span className={`tag ${s.radar}`}>
          <Dot radar={s.radar} />
          {veredicto(s)}
        </span>
        {s.registro !== 'cerrado' && <span className="tag">Registro: {REGISTRO[s.registro].toLowerCase()}</span>}
        {s.cierre && <span className="tag">Cierre: {fecha(s.cierre, true)}</span>}
      </div>

      <div className="kpis sm grid g3">
        <Kpi label="Insomnio" value={pct(s.insomnio)} />
        <Kpi label="Superficie" value={num(s.ha)} unit="ha" />
        <Kpi label="Pares" value={s.pares.length} />
      </div>

      <div>
        <h3>
          Coherencia <span>NISAR, cada 12 días</span>
        </h3>
        <Coherencia
          fechas={s.pares.map((p) => p.fecha)}
          marca={s.cierre ? { fecha: s.cierre, texto: 'cierre' } : undefined}
          series={[
            { nombre: 'Entorno', color: 'var(--faint)', valores: s.pares.map((p) => p.anillo), tenue: true },
            { nombre: RADAR[s.radar] === 'No alcanza' ? 'Sitio' : `Sitio, ${RADAR[s.radar].toLowerCase()}`, color: `var(--${s.radar.replace('_', '-')})`, valores: s.pares.map((p) => p.sitio) },
          ]}
        />
      </div>

      <div>
        <h3>
          Imagen <span>Sentinel-2, 10 m</span>
        </h3>
        {s.imagenes.length ? (
          <div className="dates">
            {s.imagenes.map((i) => (
              <button key={i.fecha} aria-pressed={imagen?.fecha === i.fecha} onClick={() => onImagen(i)}>
                {fecha(i.fecha)}
              </button>
            ))}
          </div>
        ) : (
          <p className="muted small">Sin imagen despejada en el período</p>
        )}
      </div>

      <div className="row" style={{ justifyContent: 'space-between' }}>
        <span className="coords">
          {s.lat.toFixed(4)}, {s.lon.toFixed(4)}
        </span>
        <a className="btn sm" href={`https://www.google.com/maps/@${s.lat},${s.lon},900m/data=!3m1!1e3`} target="_blank" rel="noreferrer">
          Ver en Google Maps
        </a>
      </div>
    </aside>
  )
}

export default function Mapa() {
  const { sitios } = useSitios()
  const { query } = useRoute()
  const id = query.get('sitio')
  const sel = sitios?.find((s) => s.id === id) ?? null
  const caja = useRef<HTMLDivElement>(null)
  const mapa = useRef<maplibregl.Map | null>(null)
  const [listo, setListo] = useState(false)
  const [imagen, setImagen] = useState<Imagen | null>(null)

  // el mapa se crea una sola vez
  useEffect(() => {
    const m = new maplibregl.Map({
      container: caja.current!,
      style: {
        version: 8,
        sources: { fondo: { type: 'raster', tiles: [FONDO], tileSize: 256, maxzoom: 8 } },
        layers: [{ id: 'fondo', type: 'raster', source: 'fondo' }],
      },
      ...MUNDO,
      maxZoom: 15,
      attributionControl: false,
      dragRotate: false,
      pitchWithRotate: false,
    })
    m.touchZoomRotate.disableRotation()
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right')
    m.on('load', () => setListo(true))
    mapa.current = m
    return () => {
      mapa.current = null
      m.remove()
    }
  }, [])

  // puntos de lejos; de cerca, el contorno del predio (o un aro si OpenStreetMap no lo tiene)
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
    for (const capa of ['punto', 'aro', 'contorno-relleno']) {
      m.on('click', capa, (e) => go('mapa', `sitio=${e.features![0].properties.id}`))
      m.on('mouseenter', capa, () => (m.getCanvas().style.cursor = 'pointer'))
      m.on('mouseleave', capa, () => (m.getCanvas().style.cursor = ''))
    }
  }, [listo, sitios])

  // al elegir un sitio: volar hasta ahí y mostrar su imagen más reciente
  useEffect(() => {
    const m = mapa.current
    if (!m || !listo) return
    if (!sel) {
      // sin sitio elegido se vuelve a la vista del mundo; la última imagen queda cargada
      if (m.getZoom() > MUNDO.zoom + 0.5) m.flyTo({ ...MUNDO, padding: 0, duration: 1400 })
      return
    }
    setImagen(sel.imagenes[sel.imagenes.length - 1] ?? null)
    const ancho = m.getContainer().clientWidth
    const margen = ancho > 860 ? { right: 440, top: 60, bottom: 60, left: 60 } : { bottom: 340, top: 80, left: 24, right: 24 }
    if (sel.caja) {
      const [o, s, e, n] = sel.caja
      m.fitBounds([o, s, e, n], { padding: margen, maxZoom: 14.5, duration: 1800, essential: true })
    } else {
      m.flyTo({ center: [sel.lon, sel.lat], zoom: 13.6, padding: margen, duration: 1800, essential: true })
    }
  }, [listo, sel])

  // la imagen de la fecha elegida: el recorte guardado del sitio (anda sin conexión) y,
  // debajo, la escena entera en tiles para ver los alrededores cuando hay red
  useEffect(() => {
    const m = mapa.current
    if (!m || !listo || !imagen || !sel) return
    const antesDe = (...capas: string[]) => capas.find((c) => m.getLayer(c))
    const tiles = m.getSource('escena') as RasterTileSource | undefined
    if (tiles) tiles.setTiles([s2(imagen)])
    else {
      m.addSource('escena', { type: 'raster', tiles: [s2(imagen)], tileSize: 512, minzoom: 8, maxzoom: 14 })
      m.addLayer({ id: 'escena', type: 'raster', source: 'escena', minzoom: 8, paint: { 'raster-fade-duration': 200 } }, antesDe('recorte', 'contorno-relleno'))
    }
    if (!sel.caja) return
    const [o, s, e, n] = sel.caja
    const recorte = { url: `${import.meta.env.BASE_URL}escenas/${sel.id}/${imagen.fecha}.jpg`, coordinates: [[o, n], [e, n], [e, s], [o, s]] as [[number, number], [number, number], [number, number], [number, number]] }
    const guardado = m.getSource('recorte') as ImageSource | undefined
    if (guardado) guardado.updateImage(recorte)
    else {
      m.addSource('recorte', { type: 'image', ...recorte })
      m.addLayer({ id: 'recorte', type: 'raster', source: 'recorte', paint: { 'raster-fade-duration': 0 } }, antesDe('contorno-relleno'))
    }
  }, [listo, imagen, sel])

  return (
    <>
      <div className="map" ref={caja} />
      <div className="map-top">
        <select value={id ?? ''} onChange={(e) => go('mapa', e.target.value ? `sitio=${e.target.value}` : '')} aria-label="Ir a un sitio" style={{ boxShadow: 'var(--shadow)', borderColor: 'transparent' }}>
          <option value="">Ir a un sitio</option>
          {[...(sitios ?? [])]
            .sort((a, b) => a.nombre.localeCompare(b.nombre, 'es'))
            .map((s) => (
              <option key={s.id} value={s.id}>
                {s.nombre} · {pais(s.pais)}
              </option>
            ))}
        </select>
        {sel && (
          <button
            className="btn"
            style={{ borderColor: 'transparent', boxShadow: 'var(--shadow)' }}
            onClick={() => go('mapa')}
          >
            Ver todo
          </button>
        )}
      </div>
      <div className="map-legend">
        {(['despierto', 'quieto', 'no_alcanza'] as const).map((r) => (
          <span key={r}>
            <span className={`dot ${r}`} style={{ animation: 'none' }} />
            {RADAR[r]}
          </span>
        ))}
      </div>
      <div className="map-credit">
        Imágenes:{' '}
        <a href="https://www.earthdata.nasa.gov/engage/open-data-services-software/earthdata-developer-portal/gibs-api" target="_blank" rel="noreferrer">
          NASA GIBS
        </a>{' '}
        · Sentinel-2:{' '}
        <a href="https://planetarycomputer.microsoft.com/dataset/sentinel-2-l2a" target="_blank" rel="noreferrer">
          ESA Copernicus, vía Planetary Computer
        </a>
      </div>
      {sel && <Ficha s={sel} imagen={imagen} onImagen={setImagen} />}
    </>
  )
}
