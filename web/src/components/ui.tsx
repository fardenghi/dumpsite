import type { ReactNode } from 'react'
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
