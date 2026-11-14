import { useMemo, useState } from 'react'
import { Dot, Kpi, PageHead, RADAR, REGISTRO, RegistroTag, Seg, fecha, num, pct, veredicto } from '../components/ui'
import { aCsv, useSitios } from '../data/api'
import type { Radar, Sitio } from '../data/types'

type Orden = 'insomnio' | 'ha' | 'nombre'

function descargar(nombre: string, texto: string) {
  const url = URL.createObjectURL(new Blob([texto], { type: 'text/csv;charset=utf-8' }))
  const a = Object.assign(document.createElement('a'), { href: url, download: nombre })
  a.click()
  URL.revokeObjectURL(url)
}

export default function Sitios() {
  const { sitios } = useSitios()
  const [radar, setRadar] = useState<Radar | ''>('')
  const [orden, setOrden] = useState<Orden>('insomnio')

  const filas = useMemo(() => {
    const cmp: Record<Orden, (a: Sitio, b: Sitio) => number> = {
      insomnio: (a, b) => b.insomnio - a.insomnio,
      ha: (a, b) => b.ha - a.ha,
      nombre: (a, b) => a.nombre.localeCompare(b.nombre, 'es'),
    }
    return (sitios ?? []).filter((s) => !radar || s.radar === radar).sort(cmp[orden])
  }, [sitios, radar, orden])

  if (!sitios) return null

  const Col = ({ id, children, r }: { id: Orden; children: string; r?: boolean }) => (
    <button className={`${r ? 'r' : ''} ${orden === id ? 'on' : ''}`} onClick={() => setOrden(id)} aria-pressed={orden === id}>
      {children}
    </button>
  )

  return (
    <>
      <PageHead title="Sitios" />

      <div className="kpis sm grid g4 section">
        <Kpi label="Sitios" value={sitios.length} />
        {(['despierto', 'quieto', 'no_alcanza'] as const).map((r) => (
          <Kpi
            key={r}
            label={
              <>
                <Dot radar={r} />
                {RADAR[r]}
              </>
            }
            value={sitios.filter((s) => s.radar === r).length}
          />
        ))}
      </div>

      <div className="row" style={{ marginBottom: 16, justifyContent: 'space-between' }} data-filtros>
        <Seg
          value={radar}
          onChange={setRadar}
          options={[
            { value: '', label: 'Todos' },
            { value: 'despierto', label: 'Despiertos' },
            { value: 'quieto', label: 'Quietos' },
            { value: 'no_alcanza', label: 'No alcanza' },
          ]}
        />
        <button className="btn sm" onClick={() => descargar('basurales-sitios.csv', aCsv(filas))} disabled={!filas.length}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 4v11m0 0l-4-4m4 4l4-4M5 19h14" />
          </svg>
          CSV
          <span className="muted num">{filas.length}</span>
        </button>
      </div>

      {/* una grilla que se acomoda al ancho del panel: nunca hay scroll horizontal */}
      <div className="lista">
        <div className="lista-head">
          <Col id="nombre">Sitio</Col>
          <span className="ancho">Registro oficial</span>
          <span className="ancho">Radar</span>
          <Col id="ha" r>
            Hectáreas
          </Col>
          <span className="r" title="Insomnio: en qué fracción de las pasadas del radar el sitio cambió más que su entorno">
            <Col id="insomnio" r>
              Insomnio
            </Col>
          </span>
        </div>
        {filas.map((s) => (
          <a key={s.id} className="fila" href={`#/mapa?sitio=${s.id}`}>
            <div className="quien">
              <b>
                <Dot radar={s.radar} />
                {s.nombre}
              </b>
              <span>
                {s.lugar}
                <span className="angosto">
                  {' '}
                  · {veredicto(s)}
                  {s.registro === 'activo' && ` · registro: ${REGISTRO.activo.toLowerCase()}`}
                  {s.cierre && ` · cierre: ${fecha(s.cierre, true)}`}
                </span>
              </span>
            </div>
            <span className="ancho">
              <RegistroTag s={s} />
            </span>
            <span className="ancho">
              <span className={`tag ${s.radar}`}>{veredicto(s)}</span>
            </span>
            <span className="num r">{num(s.ha)}</span>
            <div className="insomnio">
              <div className={`bar ${s.radar}`}>
                <div style={{ width: `${Math.round(s.insomnio * 100)}%` }} />
              </div>
              <span className="num r">{pct(s.insomnio)}</span>
            </div>
          </a>
        ))}
        {!filas.length && <div className="empty">Ningún sitio con ese filtro</div>}
      </div>
    </>
  )
}
