import { useMemo, useState } from 'react'
import { Dot, Kpi, PageHead, Picker, Seg, num, pct, radar as radarTxt, veredicto } from '../components/ui'
import { useSitios } from '../data/api'
import type { Radar, Sitio, Veredicto } from '../data/types'
import { FRAME_AMBA, fueraDelAmba, nombreFrame, useVeredictos } from '../data/veredictos'
import { getLang, t } from '../i18n'

type Orden = 'insomnio' | 'ha' | 'nombre'
const TODOS = '*'

/** A row of the list: a curated AMBA site or a catalog polygon from another region. Only what the radar sees. */
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
}

const filaDeSitio = (s: Sitio): Fila => ({ id: s.id, frame: FRAME_AMBA, nombre: t(s.nombre), lugar: s.lugar, lat: s.lat, lon: s.lon, ha: s.ha, radar: s.radar, insomnio: s.insomnio })

const filaDeVeredicto = (v: Veredicto): Fila => ({
  id: v.id, frame: v.frame, nombre: v.nombre ?? t('Polígono sin nombre'), lugar: `${nombreFrame(v.frame)} · ${v.id}`,
  lat: v.lat as number, lon: v.lon as number, ha: v.area_ha, radar: v.radar ?? 'no_alcanza', insomnio: v.insomnio,
})

function aCsv(filas: Fila[]): string {
  const cols = ['id', 'region', 'name', 'place', 'lat', 'lon', 'hectares', 'radar', 'insomnia']
  const celda = (v: string | number | null | undefined) => {
    const x = v == null ? '' : String(v)
    return /[",\n]/.test(x) ? `"${x.replace(/"/g, '""')}"` : x
  }
  const lineas = filas.map((f) => [f.id, f.frame, f.nombre, f.lugar, f.lat, f.lon, f.ha, f.radar, f.insomnio].map(celda).join(','))
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

  const todas = useMemo(() => [...(sitios ?? []).map(filaDeSitio), ...fueraDelAmba(veredictos).map(filaDeVeredicto)], [sitios, veredictos, getLang()])
  const frames = useMemo(() => {
    const n = new Map<string, number>()
    for (const f of todas) n.set(f.frame, (n.get(f.frame) ?? 0) + 1)
    // the AMBA first and then by count
    return [...n].sort((a, b) => Number(b[0] === FRAME_AMBA) - Number(a[0] === FRAME_AMBA) || b[1] - a[1])
  }, [todas])
  const delFrame = useMemo(() => todas.filter((f) => frame === TODOS || f.frame === frame), [todas, frame])
  const filas = useMemo(() => {
    const cmp: Record<Orden, (a: Fila, b: Fila) => number> = {
      insomnio: (a, b) => (b.insomnio ?? -1) - (a.insomnio ?? -1),
      ha: (a, b) => (b.ha ?? -1) - (a.ha ?? -1),
      nombre: (a, b) => a.nombre.localeCompare(b.nombre, getLang()),
    }
    return delFrame.filter((f) => !radar || f.radar === radar).sort(cmp[orden])
  }, [delFrame, radar, orden])

  if (!sitios) return null

  const Col = ({ id, children, r }: { id: Orden; children: string; r?: boolean }) => (
    <button className={`${r ? 'r' : ''} ${orden === id ? 'on' : ''}`} onClick={() => setOrden(id)} aria-pressed={orden === id}>
      {children}
    </button>
  )
  const plural = (n: number) => `${num(n)} ${n === 1 ? t('sitio') : t('sitios')}`

  return (
    <>
      <PageHead title={t('Sitios')} sub={frames.length > 1 ? t('{0} sitios en {1} regiones de NISAR. Fuera del AMBA son polígonos del catálogo de basurales, sin verificar', num(todas.length), frames.length) : undefined} />

      <div className="kpis sm grid g4 section">
        <Kpi label={t('Sitios')} value={num(delFrame.length)} />
        {(['despierto', 'quieto', 'no_alcanza'] as const).map((r) => (
          <Kpi
            key={r}
            label={
              <>
                <Dot radar={r} />
                {radarTxt(r)}
              </>
            }
            value={num(delFrame.filter((f) => f.radar === r).length)}
          />
        ))}
      </div>

      <div className="filtros" data-filtros>
        {frames.length > 1 && (
          <Picker
            label={t('Región')}
            value={frame}
            onChange={setFrame}
            options={[...frames.map(([f, n]) => ({ value: f, label: nombreFrame(f), sub: plural(n) })), { value: TODOS, label: t('Todas las regiones'), sub: plural(todas.length) }]}
          />
        )}
        <Seg
          value={radar}
          onChange={setRadar}
          options={[
            { value: '', label: t('Todos') },
            { value: 'despierto', label: t('Despiertos') },
            { value: 'quieto', label: t('Quietos') },
            { value: 'no_alcanza', label: t('No alcanza') },
          ]}
        />
        <span className="grow" />
        <button className="btn sm" onClick={() => descargar('dumpsite-sites.csv', aCsv(filas))} disabled={!filas.length}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 4v11m0 0l-4-4m4 4l4-4M5 19h14" />
          </svg>
          CSV
          <span className="muted num">{filas.length}</span>
        </button>
      </div>

      {/* a grid that fits the panel width: there's never horizontal scroll */}
      <div className="lista">
        <div className="lista-head">
          <Col id="nombre">{t('Sitio')}</Col>
          <span className="ancho">{t('Radar')}</span>
          <Col id="ha" r>
            {t('Hectáreas')}
          </Col>
          <span className="r" title={t('Insomnio: en qué fracción de las pasadas del radar el sitio cambió más que su entorno')}>
            <Col id="insomnio" r>
              {t('Insomnio')}
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
                <span className="angosto"> · {veredicto(f.radar)}</span>
              </span>
            </div>
            <span className="ancho">
              <span className={`tag ${f.radar}`}>{veredicto(f.radar)}</span>
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
        {!filas.length && <div className="empty">{t('Ningún sitio con ese filtro')}</div>}
      </div>
    </>
  )
}
