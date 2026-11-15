import { Suspense, lazy, useEffect, useState } from 'react'
import { Dot } from './components/ui'
import { DEMO, useSitios } from './data/api'
import Inicio from './pages/Inicio'
import Modelo from './pages/Modelo'
import Sitios from './pages/Sitios'

// MapLibre is heavy: it's loaded separately, but the map is the background of the whole site and stays mounted
const Mapa = lazy(() => import('./pages/Mapa'))

// Panels float over the map; "mapa" means having none open
const PANELES = [
  { id: 'inicio', label: 'Resumen', el: Inicio },
  { id: 'sitios', label: 'Sitios', el: Sitios },
  { id: 'modelo', label: 'Modelo', el: Modelo },
]

function leer() {
  const [path, q] = location.hash.replace(/^#\/?/, '').split('?')
  return { page: path || 'mapa', query: new URLSearchParams(q || '') }
}

export function useRoute() {
  const [r, setR] = useState(leer)
  useEffect(() => {
    const f = () => setR(leer())
    window.addEventListener('hashchange', f)
    return () => window.removeEventListener('hashchange', f)
  }, [])
  return r
}

export function go(page: string, query = '') {
  location.hash = `/${page}${query ? '?' + query : ''}`
}

export function Marca() {
  const { sitios } = useSitios()
  const despiertos = sitios?.filter((s) => s.radar === 'despierto').length
  return (
    <a
      className="marca"
      href="#/mapa"
      title={DEMO ? 'Datos reales precalculados: 15 comparaciones de pasadas de NISAR (GUNW, 80 m) sobre el AMBA, del 25/06 al 12/10/2026' : undefined}
    >
      <Dot radar="despierto" />
      <b>Basurales</b>
      {sitios && (
        <span>
          {despiertos} de {sitios.length} despiertos
        </span>
      )}
    </a>
  )
}

export default function App() {
  const { page } = useRoute()
  const P = PANELES.find((p) => p.id === page)
  // the last panel stays mounted while it closes, so it leaves with a transition
  const [ultimo, setUltimo] = useState(P)
  useEffect(() => {
    if (P) setUltimo(P)
  }, [P])
  const V = P ?? ultimo

  useEffect(() => {
    const f = (e: KeyboardEvent) => e.key === 'Escape' && P && go('mapa')
    window.addEventListener('keydown', f)
    return () => window.removeEventListener('keydown', f)
  }, [P])

  return (
    <div className={`app ${P ? 'con-panel' : ''}`}>
      <Suspense fallback={<div className="map" />}>
        <Mapa />
      </Suspense>

      <section className={`flota ${P ? 'abierta' : ''}`} aria-label={V?.label} aria-hidden={!P} inert={!P}>
        <a className="btn icon cerrar" href="#/mapa" aria-label="Cerrar panel">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
            <path d="M5 5l14 14M19 5L5 19" />
          </svg>
        </a>
        {V && (
          <div className="flota-in" key={V.id}>
            <V.el />
          </div>
        )}
      </section>

      <nav className="dock" aria-label="Secciones">
        <a href="#/mapa" className={!P ? 'on' : ''} aria-current={!P ? 'page' : undefined}>
          Mapa
        </a>
        {PANELES.map((p) => (
          // tapping the open section closes it: the panel toggles
          <a key={p.id} href={p.id === P?.id ? '#/mapa' : `#/${p.id}`} className={p.id === P?.id ? 'on' : ''} aria-current={p.id === P?.id ? 'page' : undefined}>
            {p.label}
          </a>
        ))}
      </nav>
    </div>
  )
}
