import { Analytics } from '@vercel/analytics/react'
import { Suspense, lazy, useEffect, useState } from 'react'
import { Dot, num } from './components/ui'
import { t, useLang } from './i18n'
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

/** Brand and the awake count. It counts the same sites as the map legend: the curated AMBA ones plus every
 * catalog polygon with NISAR data from the other frames. Mapa passes the numbers, so both always agree. */
export function Marca({ despiertos, total, frames }: { despiertos: number; total: number; frames: number }) {
  return (
    <a className="marca" href="#/mapa" title={frames ? t('Datos reales precalculados de NISAR (GUNW) en {0} frames procesados', frames) : undefined}>
      <Dot radar="despierto" />
      <b>Dumpsite</b>
      {total > 0 && <span>{t('{0} de {1} despiertos', num(despiertos), num(total))}</span>}
    </a>
  )
}

export default function App() {
  // switching language redraws the whole web from here
  useLang()
  const { page, query } = useRoute()
  // Vercel Web Analytics (no cookies, no IPs stored). The web routes by hash, which Vercel doesn't see on its own:
  // each section, and each site opened on the map, is reported as its own path
  const sitio = query.get('sitio')
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
      <Analytics route={sitio ? `/${page}/[sitio]` : `/${page}`} path={sitio ? `/${page}/${sitio}` : `/${page}`} />
      <Suspense fallback={<div className="map" />}>
        <Mapa />
      </Suspense>

      <section className={`flota ${P ? 'abierta' : ''}`} aria-label={V ? t(V.label) : undefined} aria-hidden={!P} inert={!P}>
        <a className="btn icon cerrar" href="#/mapa" aria-label={t('Cerrar panel')}>
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

      <nav className="dock" aria-label={t('Secciones')}>
        <a href="#/mapa" className={!P ? 'on' : ''} aria-current={!P ? 'page' : undefined}>
          {t('Mapa')}
        </a>
        {PANELES.map((p) => (
          // tapping the open section closes it: the panel toggles
          <a key={p.id} href={p.id === P?.id ? '#/mapa' : `#/${p.id}`} className={p.id === P?.id ? 'on' : ''} aria-current={p.id === P?.id ? 'page' : undefined}>
            {t(p.label)}
          </a>
        ))}
      </nav>
    </div>
  )
}
