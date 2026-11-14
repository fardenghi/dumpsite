import { useEffect, useRef, useState, type ReactNode } from 'react'
import type { Radar, Registro, Sitio } from '../data/types'

export const RADAR: Record<Radar, string> = { despierto: 'Despierto', quieto: 'Quieto', no_alcanza: 'No alcanza' }
export const REGISTRO: Record<Registro, string> = { activo: 'Activo', cerrado: 'Cerrado', sin_registro: 'Sin registro' }

const nombres = new Intl.DisplayNames('es', { type: 'region' })
export const pais = (iso: string) => nombres.of(iso) ?? iso

const nf = new Intl.NumberFormat('es-AR')
export const num = (n: number) => nf.format(n)
export const pct = (x: number) => `${Math.round(x * 100)} %`
export const coh = (x: number) => x.toFixed(2).replace('.', ',')

const MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']
/** "2026-10-12" -> "12 oct" (con año si se pide). Sin Date: no depende del huso horario. */
export function fecha(iso: string, conAnio = false) {
  const [a, m, d] = iso.split('-').map(Number)
  return `${d} ${MESES[m - 1]}${conAnio ? ` ${a}` : ''}`
}

/** El cruce entre lo que dice el registro y lo que ve el radar. */
export function veredicto(s: Sitio) {
  if (s.radar === 'no_alcanza') return 'El radar no alcanza'
  if (s.registro === 'cerrado') return s.radar === 'despierto' ? 'Cerrado pero despierto' : 'Cerrado y quieto'
  return RADAR[s.radar]
}

export function Dot({ radar }: { radar: Radar }) {
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

/** Si el sitio figura en un registro oficial, y cómo. */
export function RegistroTag({ s }: { s: Sitio }) {
  if (s.registro === 'sin_registro') return <span className="reg no">Sin registro</span>
  return (
    <span className="reg">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M5 12.5l4.5 4.5L19 7.5" />
      </svg>
      Registrado · {s.registro === 'activo' ? 'activo' : `cerrado${s.cierre ? ` ${fecha(s.cierre, true)}` : ''}`}
    </span>
  )
}

export interface Opcion<T extends string> {
  value: T
  label: string
  sub?: string
  radar?: Radar
}

/** Desplegable propio, en vez del selector del navegador. */
export function Picker<T extends string>({ value, onChange, options, placeholder, className = '', label }: { value: T | ''; onChange: (v: T) => void; options: Opcion<T>[]; placeholder?: string; className?: string; label: string }) {
  const [abierto, setAbierto] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const sel = options.find((o) => o.value === value)

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
        items[(i + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length]?.focus()
      }
    }
    document.addEventListener('pointerdown', afuera)
    document.addEventListener('keydown', tecla, true)
    ref.current?.querySelector<HTMLButtonElement>('[aria-selected=true]')?.focus()
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
          {options.map((o) => (
            <button
              key={o.value}
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
          ))}
        </div>
      )}
    </div>
  )
}
