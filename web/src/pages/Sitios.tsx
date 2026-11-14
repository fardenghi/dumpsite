import { useMemo, useState } from 'react'
import { go } from '../App'
import { Dot, PageHead, REGISTRO, Seg, fecha, num, pais, pct, veredicto } from '../components/ui'
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
  const [iso, setIso] = useState('')
  const [radar, setRadar] = useState<Radar | ''>('')
  const [orden, setOrden] = useState<Orden>('insomnio')

  const paises = useMemo(() => [...new Set((sitios ?? []).map((s) => s.pais))].sort((a, b) => pais(a).localeCompare(pais(b), 'es')), [sitios])
  const filas = useMemo(() => {
    const cmp: Record<Orden, (a: Sitio, b: Sitio) => number> = {
      insomnio: (a, b) => b.insomnio - a.insomnio,
      ha: (a, b) => b.ha - a.ha,
      nombre: (a, b) => a.nombre.localeCompare(b.nombre, 'es'),
    }
    return (sitios ?? []).filter((s) => (!iso || s.pais === iso) && (!radar || s.radar === radar)).sort(cmp[orden])
  }, [sitios, iso, radar, orden])

  if (!sitios) return null

  const Th = ({ id, children, r }: { id: Orden; children: string; r?: boolean }) => (
    <th className={r ? 'r' : ''} aria-sort={orden === id ? (id === 'nombre' ? 'ascending' : 'descending') : undefined}>
      <button onClick={() => setOrden(id)}>{children}</button>
    </th>
  )

  return (
    <>
      <PageHead
        title="Sitios"
        right={
          <button className="btn" onClick={() => descargar(`insomnes-sitios${iso ? '-' + iso.toLowerCase() : ''}.csv`, aCsv(filas))} disabled={!filas.length}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 4v11m0 0l-4-4m4 4l4-4M5 19h14" />
            </svg>
            Exportar CSV
            <span className="muted num">{filas.length}</span>
          </button>
        }
      />

      <div className="row" style={{ marginBottom: 20 }}>
        <select value={iso} onChange={(e) => setIso(e.target.value)} aria-label="País">
          <option value="">Todos los países</option>
          {paises.map((p) => (
            <option key={p} value={p}>
              {pais(p)}
            </option>
          ))}
        </select>
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
      </div>

      <div className="table-card">
        <table className="t">
          <thead>
            <tr>
              <Th id="nombre">Sitio</Th>
              <th>País</th>
              <th>Registro</th>
              <th>Radar</th>
              <Th id="ha" r>
                Hectáreas
              </Th>
              <Th id="insomnio" r>
                Insomnio
              </Th>
            </tr>
          </thead>
          <tbody>
            {filas.map((s) => (
              <tr key={s.id} className="click" onClick={() => go('mapa', `sitio=${s.id}`)}>
                <td>
                  <div className="name">
                    <Dot radar={s.radar} />
                    <a href={`#/mapa?sitio=${s.id}`} style={{ textDecoration: 'none' }} onClick={(e) => e.stopPropagation()}>
                      {s.nombre}
                    </a>
                  </div>
                </td>
                <td className="muted">
                  {s.lugar}, {pais(s.pais)}
                </td>
                <td>
                  {REGISTRO[s.registro]}
                  {s.cierre && <span className="muted small"> · {fecha(s.cierre, true)}</span>}
                </td>
                <td>{veredicto(s)}</td>
                <td className="r num">{num(s.ha)}</td>
                <td>
                  <div className="insomnio">
                    <div className={`bar ${s.radar}`}>
                      <div style={{ width: `${Math.round(s.insomnio * 100)}%` }} />
                    </div>
                    <span className="num r">{pct(s.insomnio)}</span>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!filas.length && <div className="empty">Ningún sitio con ese filtro</div>}
      </div>
    </>
  )
}
