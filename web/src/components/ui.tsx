import { Fragment, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { getLang, locale, t } from '../i18n'
import type { Radar } from '../data/types'

const RADAR_ES: Record<Radar, string> = { despierto: 'Despierto', quieto: 'Quieto', no_alcanza: 'No alcanza' }
/** Radar status in the chosen language. */
export const radar = (r: Radar) => t(RADAR_ES[r])

export const num = (n: number) => new Intl.NumberFormat(locale()).format(n)
export const pct = (x: number) => `${Math.round(x * 100)} %`
/** Decimal with a comma in Spanish and a point in English. */
export const dec = (n: number, d = 2) => {
  const s = n.toFixed(d).replace('-', '−')
  return getLang() === 'es' ? s.replace('.', ',') : s
}
export const coh = (x: number) => dec(x)

const MESES: Record<string, string[]> = {
  es: ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'],
  en: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'],
}
/** "2026-10-12" -> "12 oct" or "Oct 12" (with the year if asked). No Date: it doesn't depend on the time zone. */
export function fecha(iso: string, conAnio = false) {
  const [a, m, d] = iso.split('-').map(Number)
  if (getLang() === 'en') return `${MESES.en[m - 1]} ${d}${conAnio ? `, ${a}` : ''}`
  return `${d} ${MESES.es[m - 1]}${conAnio ? ` ${a}` : ''}`
}

/** What the radar sees, nothing else: the web doesn't show the status of any registry. */
export const veredicto = (r: Radar) => (r === 'no_alcanza' ? t('El radar no alcanza') : radar(r))

/** A site's radar, or `nuevo` (a blob that isn't in any catalog) or `sin_dato` (catalog without processed NISAR). */
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
  /** heading the option is grouped under in the list (for example, the country). Options have to come sorted by group */
  grupo?: string
}

const llano = (x: string) => x.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase()
/** With more options than this, the list has a search box. */
const BUSCAR_DESDE = 20

/** Custom dropdown, instead of the browser's select. */
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
        // from the search box, the down arrow goes to the first one
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
          {conBuscador && <input type="search" value={texto} onChange={(e) => setTexto(e.target.value)} placeholder={t('Buscar por nombre, ciudad o país')} aria-label={t('Buscar')} />}
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
          {!visibles.length && <div className="picker-vacio">{t('Ningún sitio con ese texto')}</div>}
        </div>
      )}
    </div>
  )
}
