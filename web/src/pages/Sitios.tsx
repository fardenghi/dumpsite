import { useMemo, useState } from 'react'
import { Dot, Kpi, PageHead, Picker, RADAR, REGISTRO, RegistroCatalogo, RegistroTag, SegunModelo, Seg, fecha, num, pct, veredicto } from '../components/ui'
import { useSitios } from '../data/api'
import type { LecturaModelo, Radar, Sitio, Veredicto } from '../data/types'
import { FRAME_AMBA, fueraDelAmba, lecturaModelo, nombreFrame, useVeredictos, veredictoDeSitio } from '../data/veredictos'

type Orden = 'insomnio' | 'ha' | 'nombre'
const TODOS = '*'

/** A row of the list: a curated AMBA site or a catalog polygon from another frame. */
interface Fila {
  id: string
  frame: string
  nombre: string
  lugar: string
  lat: number
  lon: number
  ha: number | null
  radar: Radar
  insomnio: number | null
  veredicto: string
  /** registry status in words, for the CSV and the narrow view */
  registro: string
  cierre?: string
  modelo: LecturaModelo | null
  /** the curated site, if the row is from the AMBA: it has its own registry tag */
  sitio?: Sitio
  /** the catalog registry status, as it comes, if the row is from another frame */
  registroCatalogo?: string | null
}

function filaDeSitio(s: Sitio, modelo: LecturaModelo | null): Fila {
  return {
    id: s.id, frame: FRAME_AMBA, nombre: s.nombre, lugar: s.lugar, lat: s.lat, lon: s.lon, ha: s.ha, radar: s.radar, insomnio: s.insomnio,
    veredicto: veredicto(s), registro: s.registro === 'sin_registro' ? 'sin registro' : REGISTRO[s.registro].toLowerCase(), cierre: s.cierre, modelo, sitio: s,
  }
}

function filaDeVeredicto(v: Veredicto): Fila {
  return {
    id: v.id, frame: v.frame, nombre: v.nombre ?? 'Polígono sin nombre', lugar: `${nombreFrame(v.frame)} · ${v.id}`, lat: v.lat as number, lon: v.lon as number,
    ha: v.area_ha, radar: v.radar ?? 'no_alcanza', insomnio: v.insomnio, veredicto: v.veredicto_texto,
    registro: v.registro === 'abierto' || v.registro === 'cerrado' ? v.registro : v.registro === 'contradictorio' ? 'contradictorio' : 'sin estado',
    modelo: lecturaModelo(v), registroCatalogo: v.registro,
  }
}

function aCsv(filas: Fila[]): string {
  const cols = ['id', 'frame', 'nombre', 'lugar', 'lat', 'lon', 'hectareas', 'registro', 'cierre', 'radar', 'insomnio', 'veredicto', 'modelo_lectura', 'modelo_puntaje_abierto']
  const celda = (v: string | number | null | undefined) => {
    const t = v == null ? '' : String(v)
    return /[",\n]/.test(t) ? `"${t.replace(/"/g, '""')}"` : t
  }
  const lineas = filas.map((f) => [f.id, f.frame, f.nombre, f.lugar, f.lat, f.lon, f.ha, f.registro, f.cierre, f.radar, f.insomnio, f.veredicto, f.modelo?.lectura, f.modelo?.p_abierto].map(celda).join(','))
  return [cols.join(','), ...lineas].join('\n') + '\n'
}

function descargar(nombre: string, texto: string) {
  const url = URL.createObjectURL(new Blob([texto], { type: 'text/csv;charset=utf-8' }))
  const a = Object.assign(document.createElement('a'), { href: url, download: nombre })
  a.click()
  URL.revokeObjectURL(url)
}

export default function Sitios() {
  const { sitios } = useSitios()
  const veredictos = useVeredictos()
  const [frame, setFrame] = useState(FRAME_AMBA)
  const [radar, setRadar] = useState<Radar | ''>('')
  const [orden, setOrden] = useState<Orden>('insomnio')

  // el AMBA son los sitios curados, con su lectura del modelo si el catálogo tiene ese mismo predio; el resto, el catálogo
  const todas = useMemo(
    () => [...(sitios ?? []).map((s) => filaDeSitio(s, lecturaModelo(veredictoDeSitio(s, veredictos)))), ...fueraDelAmba(veredictos).map(filaDeVeredicto)],
    [sitios, veredictos],
  )
  const frames = useMemo(() => {
    const n = new Map<string, number>()
    for (const f of todas) n.set(f.frame, (n.get(f.frame) ?? 0) + 1)
    // primero el AMBA y después por cantidad
    return [...n].sort((a, b) => Number(b[0] === FRAME_AMBA) - Number(a[0] === FRAME_AMBA) || b[1] - a[1])
  }, [todas])
  const delFrame = useMemo(() => todas.filter((f) => frame === TODOS || f.frame === frame), [todas, frame])
  const filas = useMemo(() => {
    const cmp: Record<Orden, (a: Fila, b: Fila) => number> = {
      insomnio: (a, b) => (b.insomnio ?? -1) - (a.insomnio ?? -1),
      ha: (a, b) => (b.ha ?? -1) - (a.ha ?? -1),
      nombre: (a, b) => a.nombre.localeCompare(b.nombre, 'es'),
    }
    return delFrame.filter((f) => !radar || f.radar === radar).sort(cmp[orden])
  }, [delFrame, radar, orden])

  if (!sitios) return null

  const Col = ({ id, children, r }: { id: Orden; children: string; r?: boolean }) => (
    <button className={`${r ? 'r' : ''} ${orden === id ? 'on' : ''}`} onClick={() => setOrden(id)} aria-pressed={orden === id}>
      {children}
    </button>
  )
  const plural = (n: number) => `${num(n)} ${n === 1 ? 'sitio' : 'sitios'}`

  return (
    <>
      <PageHead title="Sitios" sub={frames.length > 1 ? `${num(todas.length)} en ${frames.length} frames de NISAR. Fuera del AMBA son los polígonos del catálogo de basurales, sin verificar` : undefined} />

      <div className="kpis sm grid g4 section">
        <Kpi label="Sitios" value={num(delFrame.length)} />
        {(['despierto', 'quieto', 'no_alcanza'] as const).map((r) => (
          <Kpi
            key={r}
            label={
              <>
                <Dot radar={r} />
                {RADAR[r]}
              </>
            }
            value={num(delFrame.filter((f) => f.radar === r).length)}
          />
        ))}
      </div>

      <div className="filtros" data-filtros>
        {frames.length > 1 && (
          <Picker
            label="Frame"
            value={frame}
            onChange={setFrame}
            options={[...frames.map(([f, n]) => ({ value: f, label: nombreFrame(f), sub: plural(n) })), { value: TODOS, label: 'Todos los frames', sub: plural(todas.length) }]}
          />
        )}
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
        <span className="grow" />
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
        {filas.map((f) => (
          <a key={f.id} className="fila" href={`#/mapa?sitio=${f.id}`}>
            <div className="quien">
              <b>
                <Dot radar={f.radar} />
                {f.nombre}
              </b>
              <span>
                {f.lugar}
                <span className="angosto">
                  {' '}
                  · {f.veredicto}
                  {f.registro !== 'sin registro' && f.registro !== 'sin estado' && f.registro !== 'cerrado' && ` · registro: ${f.registro}`}
                  {f.registro === 'cerrado' && !f.cierre && ' · registro: cerrado'}
                  {f.cierre && ` · cierre: ${fecha(f.cierre, true)}`}
                  {f.modelo && ` · según el modelo: ${f.modelo.lectura}`}
                </span>
              </span>
            </div>
            <span className="ancho">{f.sitio ? <RegistroTag s={f.sitio} /> : <RegistroCatalogo registro={f.registroCatalogo ?? null} />}</span>
            <span className="ancho">
              <span className={`tag ${f.radar}`}>{f.veredicto}</span>
              {f.modelo && <SegunModelo m={f.modelo} corto />}
            </span>
            <span className="num r">{f.ha == null ? '–' : num(Math.round(f.ha))}</span>
            <div className="insomnio">
              <div className={`bar ${f.radar}`}>
                <div style={{ width: `${Math.round((f.insomnio ?? 0) * 100)}%` }} />
              </div>
              <span className="num r">{f.insomnio == null ? '–' : pct(f.insomnio)}</span>
            </div>
          </a>
        ))}
        {!filas.length && <div className="empty">Ningún sitio con ese filtro</div>}
      </div>
    </>
  )
}
