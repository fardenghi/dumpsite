import { useEffect, useRef, useState } from 'react'
import { fecha } from './ui'

export interface Serie {
  nombre: string
  color: string
  valores: number[]
  /** thin reference line (the surroundings) instead of the main series */
  tenue?: boolean
}

/**
 * Pair-by-pair coherence, from 0 to 1. A low, flat series is a place that never slept.
 * `marca` draws a vertical line at a date (for example, the closure).
 */
export function Coherencia({ fechas, series, marca, alto: altoFijo = 150, llenar }: { fechas: string[]; series: Serie[]; marca?: { fecha: string; texto: string }; alto?: number; /** the chart grows to fill the height its container leaves */ llenar?: boolean }) {
  const ref = useRef<HTMLDivElement>(null)
  const [w, setW] = useState(0)
  const [h, setH] = useState(0)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const ro = new ResizeObserver(([e]) => {
      setW(Math.round(e.contentRect.width))
      setH(Math.round(e.contentRect.height))
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const alto = llenar ? Math.max(altoFijo, h) : altoFijo
  const m = { t: 8, r: 8, b: 20, l: 28 }
  const iw = Math.max(0, w - m.l - m.r)
  const ih = alto - m.t - m.b
  const x = (i: number) => m.l + (fechas.length > 1 ? (i / (fechas.length - 1)) * iw : iw / 2)
  const y = (v: number) => m.t + (1 - v) * ih
  const t = (iso: string) => Date.parse(iso)
  // position of any date between the first and the last pass
  const xFecha = (iso: string) => m.l + ((t(iso) - t(fechas[0])) / (t(fechas[fechas.length - 1]) - t(fechas[0]))) * iw
  const conMarca = marca && fechas.length > 1 && t(marca.fecha) >= t(fechas[0]) && t(marca.fecha) <= t(fechas[fechas.length - 1])
  const etiquetas = [0, Math.floor((fechas.length - 1) / 2), fechas.length - 1].filter((v, i, a) => a.indexOf(v) === i)

  return (
    <div className={llenar ? 'coh llenar' : 'coh'}>
      <div ref={ref} className="coh-area" style={{ minHeight: altoFijo }}>
      {w > 0 && (
        <svg className="chart" width={w} height={alto} role="img" aria-label="Coherencia entre pasadas consecutivas">
          {[0, 0.5, 1].map((v) => (
            <g key={v}>
              <line x1={m.l} x2={w - m.r} y1={y(v)} y2={y(v)} stroke="var(--line)" />
              <text x={m.l - 8} y={y(v) + 3.5} textAnchor="end">
                {v.toFixed(1).replace('.', ',')}
              </text>
            </g>
          ))}
          {etiquetas.map((i) => (
            <text key={i} x={x(i)} y={alto - 4} textAnchor={i === 0 ? 'start' : i === fechas.length - 1 ? 'end' : 'middle'}>
              {fecha(fechas[i])}
            </text>
          ))}
          {conMarca && (
            <g>
              <line x1={xFecha(marca.fecha)} x2={xFecha(marca.fecha)} y1={m.t} y2={m.t + ih} stroke="var(--text)" strokeDasharray="2 3" />
              <text x={xFecha(marca.fecha) + 6} y={m.t + 9} style={{ fill: 'var(--text)' }}>
                {marca.texto}
              </text>
            </g>
          )}
          {series.map((s) => (
            <g key={s.nombre}>
              <polyline
                points={s.valores.map((v, i) => `${x(i)},${y(v)}`).join(' ')}
                fill="none"
                stroke={s.color}
                strokeWidth={s.tenue ? 1.25 : 2}
                strokeDasharray={s.tenue ? '3 3' : undefined}
                strokeLinejoin="round"
                strokeLinecap="round"
              />
              {!s.tenue && s.valores.map((v, i) => <circle key={i} cx={x(i)} cy={y(v)} r={2.5} fill="#fff" stroke={s.color} strokeWidth={1.5} />)}
            </g>
          ))}
        </svg>
      )}
      </div>
      <div className="legend" style={{ marginTop: 8, minHeight: 20 }}>
        {series.map((s) => (
          <span key={s.nombre}>
            <i style={{ background: s.color }} />
            {s.nombre}
          </span>
        ))}
      </div>
    </div>
  )
}
