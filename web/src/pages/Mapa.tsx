import maplibregl, { type GeoJSONSource, type ImageSource, type RasterTileSource } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { FeatureCollection } from 'geojson'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Marca, go, useRoute } from '../App'
import { Coherencia } from '../components/Coherencia'
import { Dot, Kpi, Picker, RADAR, RegistroCatalogo, RegistroTag, SegunModelo, fecha, num, pct, veredicto } from '../components/ui'
import { useSitios } from '../data/api'
import { HAY_GOOGLE, creditoGoogle, sesionGoogle, tilesGoogle } from '../data/google'
import indice from '../data/seed/indice.json'
import type { Imagen, LecturaModelo, Sitio, Veredicto } from '../data/types'
import { fueraDelAmba, lecturaModelo, nombreFrame, useVeredictos, veredictoDeSitio } from '../data/veredictos'

// El fondo es Blue Marble (NASA GIBS); al abrir un sitio se suma la escena Sentinel-2 de 10 m
// de la fecha elegida, servida por Microsoft Planetary Computer. Las dos andan sin claves.
// Con VITE_GOOGLE_MAPS_KEY hay además una vista de alta resolución (Google, menos de 1 m, sin
// fecha): se pide sólo adentro de la caja del sitio abierto y desde ZOOM_GOOGLE, porque cada
// tile se cobra. Para comparar fechas se sigue usando Sentinel-2.
const FONDO = 'https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_ShadedRelief_Bathymetry/default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg'
const s2 = (i: Imagen) =>
  `https://planetarycomputer.microsoft.com/api/data/v1/item/tiles/WebMercatorQuad/{z}/{x}/{y}@2x?collection=sentinel-2-l2a&item=${i.item}&assets=visual&asset_bidx=visual%7C1%2C2%2C3&nodata=0&format=png`

const COLOR = ['match', ['get', 'radar'], 'despierto', '#ec5b3f', 'quieto', '#5bb3a8', '#dfe5e1'] as unknown as maplibregl.ExpressionSpecification
// la vista de partida es el AMBA entero: la grilla del índice de insomnio
const AMBA: [number, number, number, number] = [indice.oeste, indice.sur, indice.este, indice.norte]
const margenAmba = (ancho: number) => (ancho > 860 ? { top: 70, bottom: 90, left: 40, right: 40 } : { top: 70, bottom: 90, left: 12, right: 12 })
const ZOOM_GOOGLE = 13
// los basurales de los otros frames no tienen contorno ni imágenes cargadas: se va hasta ahí sin acercarse tanto
const ZOOM_OTRO = 9.5
type Vista = 'google' | 'sentinel'

/** Tiles Sentinel-2 que MapLibre pide al abrir un sitio (fuente de 512 px: el z del tile es el del mapa menos 1). */
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

/** Deja en el caché de public/sw.js la imagen más reciente de cada basural, de a poco y sin apurar al mapa. */
async function precargar(sitios: Sitio[]) {
  if (!('serviceWorker' in navigator)) return
  await navigator.serviceWorker.ready
  if (!navigator.serviceWorker.controller) return // primera visita: el caché empieza a llenarse en la próxima carga
  const cola = sitios.flatMap(tilesDelSitio)
  const tanda = async () => {
    for (let url = cola.shift(); url; url = cola.shift()) await fetch(url).catch(() => null)
  }
  await Promise.all([tanda(), tanda(), tanda()])
}

function Ficha({ s, modelo, imagen, onImagen, vista, onVista }: { s: Sitio; modelo: LecturaModelo | null; imagen: Imagen | null; onImagen: (i: Imagen) => void; vista: Vista; onVista: (v: Vista) => void }) {
  return (
    <aside className="ficha" key={s.id}>
      <div className="row" style={{ alignItems: 'flex-start', flexWrap: 'nowrap' }}>
        <div className="grow">
          <h2>{s.nombre}</h2>
          <div className="where">
            {s.lugar}
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
        <RegistroTag s={s} />
      </div>

      {modelo && <SegunModelo m={modelo} />}

      <div className="kpis sm grid g2">
        <Kpi label="Insomnio" value={pct(s.insomnio)} />
        <Kpi label="Superficie" value={num(s.ha)} unit="ha" />
      </div>

      <div className="crece">
        <h3>
          Coherencia <span>NISAR, cada 12 días</span>
        </h3>
        <Coherencia
          llenar
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
          Imagen <span>{vista === 'google' ? 'Google, alta resolución, sin fecha' : 'Sentinel-2, 10 m'}</span>
        </h3>
        {(HAY_GOOGLE || s.imagenes.length > 0) && (
          <div className="dates">
            {HAY_GOOGLE && (
              <button aria-pressed={vista === 'google'} onClick={() => onVista('google')}>
                Alta resolución
              </button>
            )}
            {s.imagenes.map((i) => (
              <button key={i.fecha} aria-pressed={vista === 'sentinel' && imagen?.fecha === i.fecha} onClick={() => onImagen(i)}>
                {fecha(i.fecha)}
              </button>
            ))}
          </div>
        )}
        {!s.imagenes.length && <p className="muted small">Sin imagen Sentinel-2 despejada en el período</p>}
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

/** Ficha de un polígono del catálogo de otro frame: lo que trae `veredictos.json`, sin serie ni imágenes. */
function FichaCatalogo({ v, aviso }: { v: Veredicto; aviso?: string }) {
  const radar = v.radar ?? 'no_alcanza'
  const modelo = lecturaModelo(v)
  return (
    <aside className="ficha" key={v.id}>
      <div className="row" style={{ alignItems: 'flex-start', flexWrap: 'nowrap' }}>
        <div className="grow">
          <h2>{v.nombre ?? 'Polígono sin nombre'}</h2>
          <div className="where">
            {nombreFrame(v.frame)} · {v.id}
          </div>
        </div>
        <button className="btn icon" onClick={() => go('mapa')} aria-label="Cerrar">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
            <path d="M5 5l14 14M19 5L5 19" />
          </svg>
        </button>
      </div>

      <div className="row" style={{ gap: 8 }}>
        <span className={`tag ${radar}`}>
          <Dot radar={radar} />
          {v.veredicto_texto}
        </span>
        <RegistroCatalogo registro={v.registro} />
      </div>

      {modelo && <SegunModelo m={modelo} />}

      <div className="kpis sm grid g2">
        <Kpi label="Insomnio" value={v.insomnio == null ? '–' : pct(v.insomnio)} />
        <Kpi label="Superficie" value={v.area_ha == null ? '–' : num(Math.round(v.area_ha))} unit="ha" />
      </div>

      {v.motivo && <p className="motivo">Radar: {v.motivo}</p>}
      <p className="note">Polígono del catálogo de basurales, en un frame de NISAR fuera del AMBA. {aviso ?? 'Señal compatible con actividad, no prueba.'} No está verificado</p>

      <span className="grow" />
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <span className="coords">
          {(v.lat as number).toFixed(4)}, {(v.lon as number).toFixed(4)}
        </span>
        <a className="btn sm" href={`https://www.google.com/maps/@${v.lat},${v.lon},900m/data=!3m1!1e3`} target="_blank" rel="noreferrer">
          Ver en Google Maps
        </a>
      </div>
    </aside>
  )
}

export default function Mapa() {
  const { sitios } = useSitios()
  const veredictos = useVeredictos()
  // los basurales del catálogo de los otros frames: van como puntos, sin tocar la vista del AMBA
  const otros = useMemo(() => fueraDelAmba(veredictos), [veredictos])
  const { page, query } = useRoute()
  // con un panel abierto no hay ficha: el mapa queda donde estaba
  const enMapa = page === 'mapa'
  const id = enMapa ? query.get('sitio') : null
  const sel = sitios?.find((s) => s.id === id) ?? null
  const selOtro = (!sel && id && otros.find((v) => v.id === id)) || null
  const modeloSel = useMemo(() => (sel ? lecturaModelo(veredictoDeSitio(sel, veredictos)) : null), [sel, veredictos])
  const caja = useRef<HTMLDivElement>(null)
  const mapa = useRef<maplibregl.Map | null>(null)
  const [listo, setListo] = useState(false)
  const [imagen, setImagen] = useState<Imagen | null>(null)
  const [vista, setVista] = useState<Vista>(HAY_GOOGLE ? 'google' : 'sentinel')
  const [credito, setCredito] = useState('')
  const habiaSitio = useRef(false)

  useEffect(() => {
    if (sitios) precargar(sitios)
  }, [sitios])
  const [verIndice, setVerIndice] = useState(false)

  // el mapa se crea una sola vez
  useEffect(() => {
    const m = new maplibregl.Map({
      container: caja.current!,
      style: {
        version: 8,
        sources: { fondo: { type: 'raster', tiles: [FONDO], tileSize: 256, maxzoom: 8 } },
        layers: [{ id: 'fondo', type: 'raster', source: 'fondo' }],
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
    // índice de insomnio del AMBA: un PNG precalculado (pipeline_insomnio.py indice) con sus cuatro esquinas
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
    for (const capa of ['punto', 'aro', 'contorno-relleno']) {
      m.on('click', capa, (e) => go('mapa', `sitio=${e.features![0].properties.id}`))
      m.on('mouseenter', capa, () => (m.getCanvas().style.cursor = 'pointer'))
      m.on('mouseleave', capa, () => (m.getCanvas().style.cursor = ''))
    }
  }, [listo, sitios])

  useEffect(() => {
    const m = mapa.current
    if (m && listo && m.getLayer('indice')) m.setLayoutProperty('indice', 'visibility', verIndice ? 'visible' : 'none')
  }, [listo, sitios, verIndice])

  // los basurales de los otros frames: un punto por polígono del catálogo, debajo de los sitios del AMBA
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
    const debajoDe = ['halo', 'aro', 'contorno-relleno'].find((c) => m.getLayer(c))
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
    // el elegido, con un aro
    m.addLayer(
      {
        id: 'otros-sel',
        type: 'circle',
        source: 'otros',
        filter: ['==', ['get', 'id'], ''],
        paint: { 'circle-radius': 16, 'circle-opacity': 0, 'circle-stroke-color': COLOR, 'circle-stroke-width': 2.5 },
      },
      debajoDe,
    )
    m.on('click', 'otros', (e) => go('mapa', `sitio=${e.features![0].properties.id}`))
    m.on('mouseenter', 'otros', () => (m.getCanvas().style.cursor = 'pointer'))
    m.on('mouseleave', 'otros', () => (m.getCanvas().style.cursor = ''))
  }, [listo, otros])

  const idOtro = selOtro?.id ?? ''
  useEffect(() => {
    const m = mapa.current
    if (m && listo && m.getLayer('otros-sel')) m.setFilter('otros-sel', ['==', ['get', 'id'], idOtro])
  }, [listo, otros, idOtro])

  /** Alejar hasta ver todos los frames: el AMBA y los puntos del catálogo. */
  const verOtros = () => {
    const m = mapa.current
    if (!m || !otros.length) return
    const lons = [AMBA[0], AMBA[2], ...otros.map((v) => v.lon as number)]
    const lats = [AMBA[1], AMBA[3], ...otros.map((v) => v.lat as number)]
    go('mapa')
    m.fitBounds([Math.min(...lons), Math.max(-80, Math.min(...lats)), Math.max(...lons), Math.min(80, Math.max(...lats))], { padding: margenAmba(m.getContainer().clientWidth), duration: 1800 })
  }

  // al elegir un sitio: volar hasta ahí y mostrar su imagen más reciente
  useEffect(() => {
    const m = mapa.current
    if (!m || !listo) return
    if (!sel && !selOtro) {
      // al cerrar la ficha se vuelve a la vista del AMBA; la última imagen queda cargada
      if (habiaSitio.current && enMapa) m.fitBounds(AMBA, { padding: margenAmba(m.getContainer().clientWidth), duration: 1400 })
      habiaSitio.current = false
      return
    }
    habiaSitio.current = true
    const ancho = m.getContainer().clientWidth
    const margen = ancho > 860 ? { right: 440, top: 80, bottom: 100, left: 60 } : { bottom: 400, top: 80, left: 24, right: 24 }
    if (!sel) {
      // un basural de otro frame: no hay contorno ni recorte, se vuela hasta el punto
      m.flyTo({ center: [selOtro!.lon as number, selOtro!.lat as number], zoom: Math.max(ZOOM_OTRO, Math.min(m.getZoom(), 12)), padding: margen, duration: 2200, essential: true })
      return
    }
    setImagen(sel.imagenes[sel.imagenes.length - 1] ?? null)
    if (HAY_GOOGLE) setVista('google')
    const anillo = sel.contorno?.coordinates[0]
    if (HAY_GOOGLE && anillo) {
      // con alta resolución se encuadra el predio, no la caja de varios km
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
  }, [listo, sel, selOtro])

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
      m.addLayer({ id: 'escena', type: 'raster', source: 'escena', minzoom: 8, paint: { 'raster-fade-duration': 200 } }, antesDe('recorte', 'indice', 'contorno-relleno'))
    }
    if (!sel.caja) return
    const [o, s, e, n] = sel.caja
    const recorte = { url: `${import.meta.env.BASE_URL}escenas/${sel.id}/${imagen.fecha}.jpg`, coordinates: [[o, n], [e, n], [e, s], [o, s]] as [[number, number], [number, number], [number, number], [number, number]] }
    const guardado = m.getSource('recorte') as ImageSource | undefined
    if (guardado) guardado.updateImage(recorte)
    else {
      m.addSource('recorte', { type: 'image', ...recorte })
      m.addLayer({ id: 'recorte', type: 'raster', source: 'recorte', paint: { 'raster-fade-duration': 0 } }, antesDe('indice', 'contorno-relleno'))
    }
  }, [listo, imagen, sel])

  // la imagen Sentinel-2 del sitio sólo se ve con ese sitio abierto: en la vista general quedaría como un parche
  useEffect(() => {
    const m = mapa.current
    if (!m || !listo) return
    for (const capa of ['escena', 'recorte']) if (m.getLayer(capa)) m.setLayoutProperty(capa, 'visibility', sel ? 'visible' : 'none')
  }, [listo, imagen, sel])

  // alta resolución de Google: sólo adentro de la caja del sitio abierto y con zoom alto
  const idSel = sel?.id
  useEffect(() => {
    const m = mapa.current
    if (!HAY_GOOGLE || !m || !listo || !sel?.caja) return
    const limites = sel.caja
    let vivo = true
    let token = ''
    const acreditar = () => {
      if (!token || m.getZoom() < ZOOM_GOOGLE) return setCredito('')
      const b = m.getBounds()
      creditoGoogle(token, m.getZoom(), [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()]).then((c) => vivo && setCredito(c), () => null)
    }
    sesionGoogle().then(
      (t) => {
        if (!vivo || mapa.current !== m) return
        token = t
        m.addSource('google', { type: 'raster', tiles: [tilesGoogle(t)], tileSize: 256, bounds: limites, minzoom: ZOOM_GOOGLE, maxzoom: 20 })
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
      if (mapa.current !== m) return
      m.off('moveend', acreditar)
      if (m.getLayer('google')) m.removeLayer('google')
      if (m.getSource('google')) m.removeSource('google')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [listo, idSel])

  // la vista elegida: Google tapa a Sentinel-2 o se esconde; con Google el relleno del contorno no tiñe la imagen
  useEffect(() => {
    const m = mapa.current
    if (!m || !listo) return
    const aplicar = () => {
      if (m.getLayer('google')) m.setLayoutProperty('google', 'visibility', vista === 'google' ? 'visible' : 'none')
      if (m.getLayer('contorno-relleno')) m.setPaintProperty('contorno-relleno', 'fill-opacity', ['interpolate', ['linear'], ['zoom'], 9, 0, 10.5, 0.08, ZOOM_GOOGLE + 1, vista === 'google' && idSel ? 0 : 0.08])
    }
    aplicar()
    m.on('styledata', aplicar)
    return () => {
      m.off('styledata', aplicar)
    }
  }, [listo, vista, idSel])

  return (
    <>
      <div className="map" ref={caja} />
      <div className={`map-top ${sel || selOtro ? 'con-ficha' : ''}`}>
        <Marca />
        <Picker
          className="float"
          label="Ir a un sitio"
          placeholder="Ir a un sitio"
          value={id ?? ''}
          onChange={(v) => go('mapa', `sitio=${v}`)}
          options={[...(sitios ?? [])].sort((a, b) => a.nombre.localeCompare(b.nombre, 'es')).map((s) => ({ value: s.id, label: s.nombre, sub: s.lugar, radar: s.radar }))}
        />
        {(sel || selOtro) && (
          <button className="btn float" onClick={() => go('mapa')}>
            Ver todo
          </button>
        )}
      </div>
      <div className="map-legend">
        <div className="estados">
          {(['despierto', 'quieto', 'no_alcanza'] as const).map((r) => (
            <span key={r}>
              <span className={`dot ${r}`} />
              {RADAR[r]}
            </span>
          ))}
        </div>
        <button
          className="capa"
          role="switch"
          aria-checked={verIndice}
          onClick={() => setVerIndice((v) => !v)}
          title={`${indice.que}. ${indice.pares} comparaciones de NISAR, del ${fecha(indice.desde, true)} al ${fecha(indice.hasta, true)}`}
        >
          <span>Índice de insomnio</span>
          <i />
        </button>
        {verIndice && (
          <div className="escala">
            <div />
            <span>0,3</span>
            <span>1</span>
          </div>
        )}
        {otros.length > 0 && (
          <button className="otros-frames" onClick={verOtros} title="Alejar el mapa hasta ver todos los frames procesados">
            <b>
              {num(otros.length)} basurales en otros {new Set(otros.map((v) => v.frame)).size} frames
            </b>
            <span>Polígonos del catálogo, sin verificar</span>
          </button>
        )}
      </div>
      <div className="map-credit">
        {vista === 'google' && credito && (
          <>
            <b className="google">Google</b> {credito} ·{' '}
          </>
        )}
        Índice: NISAR GUNW (NASA/ISRO, vía ASF DAAC), agua de JRC Global Surface Water · Contornos: © OpenStreetMap
        {otros.length > 0 && ' · Otros frames: catálogo de basurales (OpenStreetMap vía Overture Maps, EPA LMOP)'} · Imágenes:{' '}
        <a href="https://www.earthdata.nasa.gov/engage/open-data-services-software/earthdata-developer-portal/gibs-api" target="_blank" rel="noreferrer">
          NASA GIBS
        </a>{' '}
        · Sentinel-2:{' '}
        <a href="https://planetarycomputer.microsoft.com/dataset/sentinel-2-l2a" target="_blank" rel="noreferrer">
          ESA Copernicus, vía Planetary Computer
        </a>
      </div>
      {selOtro && <FichaCatalogo v={selOtro} aviso={veredictos?.aviso} />}
      {sel && (
        <Ficha
          s={sel}
          modelo={modeloSel}
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
