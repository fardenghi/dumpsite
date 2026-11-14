import { useState } from 'react'
import { Dot, PageHead, Picker, RADAR, fecha, num, pct } from '../components/ui'
import { useSitios } from '../data/api'
import candidatos from '../data/seed/candidatos.json'
import fichasJson from '../data/seed/fichas.json'
import indice from '../data/seed/indice.json'
import { Fuentes } from './Inicio'

// Todos los números de esta página salen del pipeline (seed/*.json) o de
// idea-basurales-nisar/idea/indice-final.md. Lo que no se midió no se muestra.
interface Ficha {
  motivo: string
  persistencia: number | null
  insomnio_orbita: Record<string, number> | null
  eco_db: number | null
  px: number
  pares: { fecha: string; orbita: number; sitio: number; anillo: number; despierto?: boolean }[]
}
const FICHAS = fichasJson as unknown as Record<string, Ficha>
const P = indice.parametros
const ECO_MIN = -13

// la grilla del AMBA, en hectáreas (indice-final.md)
const GRILLA = 718952
const AGUA = 97493
const CLASES = [
  { id: 'relleno_osm', nombre: 'Relleno según OpenStreetMap', color: 'var(--despierto)' },
  { id: 'uso_conocido', nombre: 'Uso conocido: aeródromos, golf, parques', color: 'var(--green)' },
  { id: 'sin_explicar', nombre: 'Sin explicar', color: 'var(--faint)' },
]
const DESCARTES = [
  { n: '2.375', que: 'de menos de 10 ha' },
  { n: '160', que: 'lisas: eco menor que −13 dB' },
  { n: '19', que: 'lineales: rutas y arroyos' },
  { n: '4.226 ha', que: 'despiertas sólo por temporada' },
]
const UMBRALES = [
  { nombre: 'Sitio / entorno', valor: 0.8, desde: 0.75, hasta: 0.825, min: 0.6, max: 1, nota: 'Más bajo, Norte III deja de ser persistente. Más alto, aparecen manchas en la costa del Roggero' },
  { nombre: 'Insomnio mínimo', valor: 0.7, desde: 0.5, hasta: 0.8, min: 0.3, max: 1, nota: 'Con 0,9 Norte III (0,86) queda afuera' },
  { nombre: 'Eco mínimo, dB', valor: -13, desde: -16.6, hasta: -11.6, min: -20, max: -8, nota: 'Entre lo liso conocido (el río, −16,6) y el relleno con menos eco (González Catán, −11,6)' },
]
const LIMITES = [
  { que: 'Pasto y monte', porque: 'Pierden coherencia igual que un relleno' },
  { que: 'Predios chicos', porque: 'Menos de 8 píxeles de 80 m' },
  { que: 'Un año entero', porque: 'Hay datos de junio a octubre de 2026' },
  { que: 'Validación independiente', porque: 'Sólo dos rellenos y cinco controles' },
]

const dec = (n: number, d = 2) => n.toFixed(d).replace('.', ',').replace('-', '−')

/** Cada par de pasadas: la raya es el 80 % de la coherencia del entorno y el punto, la del sitio. Punto debajo de la raya = par despierto. */
function Pares({ f }: { f: Ficha }) {
  const orbitas = [...new Set(f.pares.map((p) => p.orbita))].sort((a, b) => a - b)
  const alto = 84
  const paso = 26
  const y = (v: number) => 6 + (1 - v) * (alto - 12)
  return (
    <div className="orbitas">
      {orbitas.map((o) => {
        const pares = f.pares.filter((p) => p.orbita === o)
        const ancho = pares.length * paso
        return (
          <div key={o}>
            <div className="orbita-t">
              <b>Órbita {o}</b>
              <span>
                {pares.filter((p) => p.despierto).length} de {pares.length} despiertas
              </span>
            </div>
            <svg className="chart" width={ancho} height={alto} role="img" aria-label={`Comparaciones de la órbita ${o}`}>
              <line x1={0} x2={ancho} y1={y(0)} y2={y(0)} stroke="var(--line)" />
              <line x1={0} x2={ancho} y1={y(1)} y2={y(1)} stroke="var(--line)" />
              {pares.map((p, i) => {
                const x = i * paso + paso / 2
                const corte = y(P.razon * p.anillo)
                const color = p.despierto ? 'var(--despierto)' : 'var(--quieto)'
                return (
                  <g key={p.fecha}>
                    <title>{`${fecha(p.fecha, true)} · sitio ${dec(p.sitio)} · entorno ${dec(p.anillo)}`}</title>
                    <rect x={x - paso / 2} y={0} width={paso} height={alto} fill="transparent" />
                    <line x1={x} x2={x} y1={corte} y2={y(p.sitio)} stroke={color} strokeWidth={1.5} opacity={0.45} />
                    <line x1={x - 7} x2={x + 7} y1={corte} y2={corte} stroke="var(--ink-2)" strokeWidth={1.5} strokeLinecap="round" />
                    <circle cx={x} cy={y(p.sitio)} r={4.5} fill={p.despierto ? color : '#fff'} stroke={color} strokeWidth={1.5} />
                  </g>
                )
              })}
            </svg>
          </div>
        )
      })}
    </div>
  )
}

/** Una barra con el umbral marcado. */
function Medidor({ nombre, valor, texto, umbral, textoUmbral, min = 0, max = 1, pasa }: { nombre: string; valor: number | null; texto: string; umbral: number; textoUmbral: string; min?: number; max?: number; pasa: boolean }) {
  const pos = (v: number) => `${Math.max(0, Math.min(1, (v - min) / (max - min))) * 100}%`
  return (
    <div className="medidor">
      <div className="medidor-t">
        <span>{nombre}</span>
        <b className="num">{texto}</b>
      </div>
      <div className="medidor-b">
        {valor != null && <div className={pasa ? 'pasa' : ''} style={{ width: pos(valor) }} />}
        <i style={{ left: pos(umbral) }} />
      </div>
      <div className="medidor-u" style={{ paddingLeft: `min(${pos(umbral)}, calc(100% - 9ch))` }}>
        mínimo {textoUmbral}
      </div>
    </div>
  )
}

export default function Modelo() {
  const { sitios } = useSitios()
  const [id, setId] = useState('norte-iii')
  if (!sitios) return null
  const conFicha = sitios.filter((s) => FICHAS[s.id]).sort((a, b) => b.insomnio - a.insomnio)
  const s = conFicha.find((x) => x.id === id) ?? conFicha[0]
  const f = FICHAS[s.id]

  const tierra = GRILLA - AGUA
  const haCand = candidatos.reduce((a, c) => a + c.ha, 0)
  const clases = CLASES.map((c) => ({ ...c, n: candidatos.filter((x) => x.clase === c.id).length }))

  return (
    <div className="pasos">
      <PageHead title="Modelo" sub="Insomnio: en qué fracción de las pasadas del radar un lugar cambió más que su entorno" />

      <section className="section">
        <div className="paso-t">
          <i>1</i>
          <div>
            <h3>La regla, pasada contra pasada</h3>
            <p>
              Cada pasada del radar se compara con la anterior. Está despierta si el sitio (punto) queda debajo del {pct(P.razon)} de su entorno (raya)
            </p>
          </div>
        </div>
        <div className="card">
          <Picker label="Sitio de ejemplo" value={s.id} onChange={setId} options={conFicha.map((x) => ({ value: x.id, label: x.nombre, sub: x.lugar, radar: x.radar }))} />
          <Pares f={f} />
          <div className="legend">
            <span>
              <span className="dot" style={{ background: 'var(--despierto)' }} />
              despierta
            </span>
            <span>
              <span className="dot" style={{ background: '#fff', boxShadow: 'inset 0 0 0 1.5px var(--quieto)' }} />
              quieta
            </span>
            <span>
              <i style={{ background: 'var(--ink-2)' }} />
              {pct(P.razon)} del entorno
            </span>
          </div>
          <div className="medidores">
            <Medidor nombre="Insomnio" valor={s.insomnio} texto={pct(s.insomnio)} umbral={P.min_insomnio} textoUmbral={pct(P.min_insomnio)} pasa={s.insomnio >= P.min_insomnio} />
            <Medidor
              nombre="Persistencia"
              valor={f.persistencia}
              texto={f.persistencia == null ? '–' : pct(f.persistencia)}
              umbral={P.min_persistencia}
              textoUmbral={pct(P.min_persistencia)}
              pasa={(f.persistencia ?? 0) >= P.min_persistencia}
            />
            <Medidor nombre="Eco" valor={f.eco_db} texto={f.eco_db == null ? '–' : `${dec(f.eco_db, 1)} dB`} umbral={ECO_MIN} textoUmbral={`${dec(ECO_MIN, 0)} dB`} min={-20} max={0} pasa={(f.eco_db ?? -99) >= ECO_MIN} />
          </div>
          <div className={`veredicto ${s.radar}`}>
            <Dot radar={s.radar} />
            <div>
              <b>{RADAR[s.radar]}</b>
              <span>{f.motivo.replace('todos los pares', 'todas las pasadas')}</span>
            </div>
          </div>
        </div>
      </section>

      <section className="section">
        <div className="paso-t">
          <i>2</i>
          <div>
            <h3>Del AMBA a {candidatos.length} manchas</h3>
            <p>La misma regla en toda la grilla, píxel por píxel</p>
          </div>
        </div>
        <div className="embudo">
          <div>
            <span>Grilla del AMBA</span>
            <div className="embudo-b" style={{ width: '100%' }} />
            <b className="num">{num(GRILLA)} ha</b>
          </div>
          <div>
            <span>Tierra, sin el agua de JRC</span>
            <div className="embudo-b" style={{ width: `${(tierra / GRILLA) * 100}%` }} />
            <b className="num">{num(tierra)} ha</b>
          </div>
          <div>
            <span>Manchas candidatas</span>
            <div className="embudo-b fin" style={{ width: `${(haCand / GRILLA) * 100}%` }} />
            <b className="num">
              {num(Math.round(haCand))} ha · {dec((haCand / tierra) * 100, 1)} % de la tierra
            </b>
          </div>
        </div>
        <div className="descartes">
          <span>En el camino quedan</span>
          {DESCARTES.map((d) => (
            <span className="tag" key={d.que}>
              <b className="num">{d.n}</b> {d.que}
            </span>
          ))}
        </div>
        <div className="card" style={{ marginTop: 16 }}>
          <div className="section-head" style={{ marginBottom: 12 }}>
            <h4>Qué son las {candidatos.length}</h4>
          </div>
          <div className="apilada" role="img" aria-label={clases.map((c) => `${c.n} ${c.nombre}`).join(', ')}>
            {clases.map((c) => (
              <div key={c.id} style={{ flexGrow: c.n, background: c.color }} />
            ))}
          </div>
          <div className="clases">
            {clases.map((c) => (
              <div key={c.id}>
                <b className="num">{c.n}</b>
                <span>
                  <i style={{ background: c.color }} />
                  {c.nombre}
                </span>
              </div>
            ))}
          </div>
          <p className="note" style={{ marginTop: 16 }}>Las “sin explicar” no están verificadas: no son basurales confirmados</p>
        </div>
      </section>

      <section className="section">
        <div className="paso-t">
          <i>3</i>
          <div>
            <h3>Los umbrales</h3>
            <p>Calibrados con dos rellenos y cinco controles. La franja es el rango válido</p>
          </div>
        </div>
        <div className="umbrales">
          {UMBRALES.map((u) => {
            const pos = (v: number) => `${((v - u.min) / (u.max - u.min)) * 100}%`
            return (
              <div key={u.nombre} title={u.nota}>
                <div className="medidor-t">
                  <span>{u.nombre}</span>
                  <b className="num">{dec(u.valor, Number.isInteger(u.valor) ? 0 : 2)}</b>
                </div>
                <div className="rango">
                  <div style={{ left: pos(u.desde), right: `calc(100% - ${pos(u.hasta)})` }} />
                  <i style={{ left: pos(u.valor) }} />
                </div>
                <div className="rango-e num">
                  <span>{dec(u.min, 1)}</span>
                  <span>
                    válido de {dec(u.desde, 3).replace(/0+$/, '').replace(/,$/, '')} a {dec(u.hasta, 3).replace(/0+$/, '').replace(/,$/, '')}
                  </span>
                  <span>{dec(u.max, 1)}</span>
                </div>
              </div>
            )
          })}
        </div>
      </section>

      <section className="section">
        <div className="paso-t">
          <i>4</i>
          <div>
            <h3>
              Lo que sigue: decir qué es cada mancha <span className="tag">Propuesta, sin probar</span>
            </h3>
            <p>El radar dice si un lugar se mueve, no qué es. Todavía no hay métricas</p>
          </div>
        </div>
        <div className="futuro">
          <div className="entradas">
            <div>
              <span className="src">NISAR · se mueve o no</span>
              <b>Índice de insomnio</b>
            </div>
            <div>
              <span className="src">Sentinel-2 · qué es</span>
              <b>ResNet-50 con SSL4EO-S12</b>
              <p>Basural, cantera, obra o suelo desnudo</p>
            </div>
          </div>
          <div className="une" aria-hidden="true" />
          <div className="salida">
            <span className="src">por mancha</span>
            <b>Gradient boosting</b>
            <p>Junta las dos miradas</p>
          </div>
        </div>
      </section>

      <section className="panel section">
        <h3 style={{ marginBottom: 12 }}>Lo que no ve</h3>
        <ul className="limits">
          {LIMITES.map((l) => (
            <li key={l.que}>
              <b>{l.que}</b>
              <span>{l.porque}</span>
            </li>
          ))}
        </ul>
      </section>

      <Fuentes />
    </div>
  )
}
