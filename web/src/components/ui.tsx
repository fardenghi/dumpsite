import { useEffect, useRef, useState, type ReactNode } from 'react'
import { getLang, locale, t } from '../i18n'
import type { Radar } from '../data/types'

const RADAR_ES: Record<Radar, string> = { despierto: 'Despierto', quieto: 'Quieto', no_alcanza: 'No alcanza' }
/** Estado del radar en el idioma elegido. */
export const radar = (r: Radar) => t(RADAR_ES[r])

export const num = (n: number) => new Intl.NumberFormat(locale()).format(n)
export const pct = (x: number) => `${Math.round(x * 100)} %`
/** Decimal con coma en castellano y punto en inglés. */
export const dec = (n: number, d = 2) => {
  const s = n.toFixed(d).replace('-', '−')
  return getLang() === 'es' ? s.replace('.', ',') : s
}
export const coh = (x: number) => dec(x)

const MESES: Record<string, string[]> = {
  es: ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'],
  en: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'],
}
/** "2026-10-12" -> "12 oct" o "Oct 12" (con año si se pide). Sin Date: no depende del huso horario. */
export function fecha(iso: string, conAnio = false) {
  const [a, m, d] = iso.split('-').map(Number)
  if (getLang() === 'en') return `${MESES.en[m - 1]} ${d}${conAnio ? `, ${a}` : ''}`
  return `${d} ${MESES.es[m - 1]}${conAnio ? ` ${a}` : ''}`
}

/** Lo que ve el radar, nada más: la web no muestra el estado de ningún registro. */
export const veredicto = (r: Radar) => (r === 'no_alcanza' ? t('El radar no alcanza') : radar(r))

/** Radar de un sitio, o `nuevo` (mancha que no está en ningún catálogo) o `sin_dato` (catálogo sin NISAR procesado). */
export type Marca = Radar | 'nuevo' | 'sin_dato'

export function Dot({ radar }: { radar: Marca }) {
  return <span className={`dot ${radar}`} />
}

export function PageHead({ title, sub, right }: { title: string; sub?: string; right?: ReactNode }) {
  return (
    <header className="page-head">
      <div>
        <h1>{title}</h1>
        {sub && <p className="sub">{sub}</p>}
      </div>
      <span className="grow" />
      {right}
    </header>
  )
}

export function Kpi({ label, value, unit }: { label: ReactNode; value: ReactNode; unit?: string }) {
  return (
    <div className="kpi">
      <div className="l">{label}</div>
      <div className="v">
        {value}
        {unit && <small>{unit}</small>}
      </div>
    </div>
  )
}

export function Seg<T extends string>({ value, onChange, options }: { value: T; onChange: (v: T) => void; options: { value: T; label: string }[] }) {
  return (
    <div className="seg" role="group">
      {options.map((o) => (
        <button key={o.value} className={o.value === value ? 'on' : ''} aria-pressed={o.value === value} onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  )
}

export interface Opcion<T extends string> {
  value: T
  label: string
  sub?: string
  radar?: Marca
  /** título bajo el que se agrupa en la lista (por ejemplo, el país). Las opciones tienen que venir ordenadas por grupo */
  grupo?: string
}

/** Desplegable propio, en vez del selector del navegador. */
const llano = (t: string) => t.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase()
/** Con más opciones que estas, la lista trae un buscador. */
const BUSCAR_DESDE = 20

export function Picker<T extends string>({ value, onChange, options, placeholder, className = '', label }: { value: T | ''; onChange: (v: T) => void; options: Opcion<T>[]; placeholder?: string; className?: string; label: string }) {
  const [abierto, setAbierto] = useState(false)
  const [texto, setTexto] = useState('')
  const ref = useRef<HTMLDivElement>(null)
  const sel = options.find((o) => o.value === value)
  const conBuscador = options.length > BUSCAR_DESDE
  const visibles = useMemo(() => {
    const q = llano(texto.trim())
    return q ? options.filter((o) => llano(`${o.label} ${o.sub ?? ''} ${o.grupo ?? ''}`).includes(q)) : options
  }, [options, texto])
  const porGrupo = useMemo(() => {
    const n = new Map<string, number>()
    for (const o of visibles) if (o.grupo) n.set(o.grupo, (n.get(o.grupo) ?? 0) + 1)
    return n
  }, [visibles])

  useEffect(() => {
    if (!abierto) return
    const afuera = (e: PointerEvent) => !ref.current?.contains(e.target as Node) && setAbierto(false)
    const tecla = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        setAbierto(false)
        ref.current?.querySelector('button')?.focus()
      }
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault()
        const items = [...(ref.current?.querySelectorAll<HTMLButtonElement>('[role=option]') ?? [])]
        const i = items.indexOf(document.activeElement as HTMLButtonElement)
        // desde el buscador, la flecha baja al primero
        items[i < 0 ? (e.key === 'ArrowDown' ? 0 : items.length - 1) : (i + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length]?.focus()
      }
    }
    document.addEventListener('pointerdown', afuera)
    document.addEventListener('keydown', tecla, true)
    const elegido = ref.current?.querySelector<HTMLButtonElement>('[aria-selected=true]')
    elegido?.scrollIntoView({ block: 'nearest' })
    ;(ref.current?.querySelector<HTMLInputElement>('input') ?? elegido)?.focus()
    return () => {
      document.removeEventListener('pointerdown', afuera)
      document.removeEventListener('keydown', tecla, true)
    }
  }, [abierto])

  return (
    <div className={`picker ${abierto ? 'abierto' : ''} ${className}`} ref={ref}>
      <button className="picker-btn" onClick={() => setAbierto((a) => !a)} aria-haspopup="listbox" aria-expanded={abierto} aria-label={label}>
        {sel?.radar && <Dot radar={sel.radar} />}
        <span>{sel?.label ?? placeholder}</span>
        <svg width="10" height="6" viewBox="0 0 10 6" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
          <path d="M1 1l4 4 4-4" />
        </svg>
      </button>
      {abierto && (
        <div className="picker-lista" role="listbox" aria-label={label}>
          {conBuscador && <input type="search" value={texto} onChange={(e) => setTexto(e.target.value)} placeholder="Buscar por nombre, ciudad o país" aria-label="Buscar" />}
          {visibles.map((o, i) => (
            <Fragment key={o.value}>
              {o.grupo && o.grupo !== visibles[i - 1]?.grupo && (
                <div className="picker-grupo" role="presentation">
                  {o.grupo}
                  <span className="num">{num(porGrupo.get(o.grupo) ?? 0)}</span>
                </div>
              )}
              <button
                role="option"
                aria-selected={o.value === value}
                onClick={() => {
                  onChange(o.value)
                  setAbierto(false)
                }}
              >
                {o.radar && <Dot radar={o.radar} />}
                <span>
                  <b>{o.label}</b>
                  {o.sub && <small>{o.sub}</small>}
                </span>
              </button>
            </Fragment>
          ))}
          {!visibles.length && <div className="picker-vacio">Ningún sitio con ese texto</div>}
        </div>
      )}
    </div>
  )
}
