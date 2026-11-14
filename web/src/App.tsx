import { Suspense, lazy, useEffect, useState } from 'react'
import { Dot } from './components/ui'
import { DEMO, useSitios } from './data/api'
import Inicio from './pages/Inicio'
import Modelo from './pages/Modelo'
import Sitios from './pages/Sitios'

// MapLibre pesa: se baja recién cuando se abre el mapa
const Mapa = lazy(() => import('./pages/Mapa'))

const PAGES = [
  { id: 'inicio', label: 'Inicio', el: Inicio },
  { id: 'mapa', label: 'Mapa', el: Mapa },
  { id: 'sitios', label: 'Sitios', el: Sitios },
  { id: 'modelo', label: 'Modelo', el: Modelo },
]

function leer() {
  const [path, q] = location.hash.replace(/^#\/?/, '').split('?')
  return { page: path || 'inicio', query: new URLSearchParams(q || '') }
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

function Logo() {
  return (
    <a className="logo" href="#/inicio">
      <Dot radar="despierto" />
      Insomnes
    </a>
  )
}

function Vigilia() {
  const { sitios } = useSitios()
  const despiertos = sitios?.filter((s) => s.radar === 'despierto').length
  return (
    <div className="vigilia">
      <div className="v">{despiertos ?? '–'}</div>
      <div className="l">
        <Dot radar="despierto" />
        despiertos de {sitios?.length ?? '–'}
      </div>
    </div>
  )
}

export default function App() {
  const { page } = useRoute()
  const [menu, setMenu] = useState(false)
  const P = PAGES.find((p) => p.id === page) ?? PAGES[0]
  return (
    <div className="app">
      <header className="topbar">
        <Logo />
        <span className="grow" />
        <button className="menu-btn" onClick={() => setMenu(true)} aria-label="Abrir menú">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
            <path d="M4 7h16M4 12h16M4 17h16" />
          </svg>
        </button>
      </header>
      <div className={`drawer-bg ${menu ? 'open' : ''}`} onClick={() => setMenu(false)} />
      <aside className={`side ${menu ? 'open' : ''}`} onClick={(e) => (e.target as HTMLElement).closest('a') && setMenu(false)}>
        <Logo />
        <Vigilia />
        <nav className="nav">
          {PAGES.map((p) => (
            <a key={p.id} href={`#/${p.id}`} className={p.id === P.id ? 'on' : ''} aria-current={p.id === P.id ? 'page' : undefined}>
              {p.label}
            </a>
          ))}
        </nav>
        <div className="side-foot">
          {DEMO && (
            <span className="pill" title="Todavía no hay backend: los sitios y las series son de ejemplo.">
              datos de ejemplo
            </span>
          )}
          <span>NASA Space Apps 2026</span>
        </div>
      </aside>
      <main className={P.id === 'mapa' ? 'full' : ''}>
        <Suspense fallback={null}>
          {P.id === 'mapa' ? (
            <P.el />
          ) : (
            <div className="page" key={P.id}>
              <P.el />
            </div>
          )}
        </Suspense>
      </main>
    </div>
  )
}
