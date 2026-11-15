import { useState } from 'react'
import { Dot, PageHead, Picker, dec, fecha, num, pct, radar } from '../components/ui'
import { useSitios } from '../data/api'
import type { ModeloEstado } from '../data/types'
import { MODELO_ESTADO } from '../data/veredictos'
import cal from '../data/seed/calibracion.json'
import candidatos from '../data/seed/candidatos.json'
import fichasJson from '../data/seed/fichas.json'
import indice from '../data/seed/indice.json'
import { Fuentes } from './Inicio'

// Todos los números de esta página salen del pipeline (seed/*.json). Los del embudo y los umbrales están en
// seed/calibracion.json, que escribe scripts/datos_mapa.py desde las salidas del índice. Lo que no se midió no se muestra.
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
const dec = (n: number, d = 2) => n.toFixed(d).replace('.', ',').replace('-', '−')
/** Un umbral o un borde de rango, sin ceros de más: 0,8 · 0,725 · −13. */
const corto = (n: number) => dec(n, 3).replace(/0+$/, '').replace(/,$/, '')

const ECO_MIN = cal.parametros.eco_min_db
// la grilla del frame, en hectáreas: la tierra más el agua de JRC
const AGUA = cal.superficie.agua_ha
const GRILLA = cal.superficie.tierra_ha + AGUA
const CLASES = [
  { id: 'relleno_osm', nombre: 'Relleno según OpenStreetMap', color: 'var(--despierto)' },
  { id: 'uso_conocido', nombre: 'Uso conocido: aeródromos, golf, parques', color: 'var(--green)' },
  { id: 'sin_explicar', nombre: 'Sin explicar', color: 'var(--faint)' },
]
const DESCARTES = [
  { n: num(cal.descartes.chicas), que: `de menos de ${corto(cal.parametros.min_ha)} ha` },
  { n: num(cal.descartes.lisas), que: `lisas: eco menor que ${corto(ECO_MIN)} dB` },
  { n: num(cal.descartes.lineales), que: 'lineales: rutas y arroyos' },
  { n: `${num(cal.superficie.estacional_ha)} ha`, que: 'despiertas sólo por temporada' },
]
const R = cal.rangos
// min y max son sólo el ancho de la escala dibujada; el valor y la franja válida salen de la calibración
const UMBRALES = [
  {
    nombre: 'Sitio / entorno', valor: cal.parametros.razon, desde: R.razon.desde, hasta: R.razon.hasta, min: 0.6, max: 1,
    nota: `Por debajo de ${corto(R.razon.desde)}, ${cal.testigo.nombre} deja de ser persistente.${R.razon.siguiente == null ? '' : ` Desde ${corto(R.razon.siguiente)}, aparecen manchas en la costa del Roggero`}`,
  },
  {
    nombre: 'Insomnio mínimo', valor: cal.parametros.min_insomnio, desde: R.min_insomnio.desde, hasta: R.min_insomnio.hasta, min: 0.3, max: 1,
    nota: R.min_insomnio.siguiente == null ? '' : `Con ${corto(R.min_insomnio.siguiente)}, ${cal.testigo.nombre} (${corto(cal.testigo.insomnio)}) queda afuera`,
  },
  {
    nombre: 'Eco mínimo, dB', valor: ECO_MIN, desde: R.eco_min_db.desde, hasta: R.eco_min_db.hasta, min: -20, max: -8,
    nota: `Entre lo liso conocido (${R.eco_min_db.liso}, ${corto(R.eco_min_db.desde)}) y el relleno con menos eco (${R.eco_min_db.relleno}, ${corto(R.eco_min_db.hasta)})`,
  },
]
const CALIBRADO_CON = `${cal.calibrado_con.rellenos} rellenos y ${cal.calibrado_con.controles} controles`
const LIMITES = [
  { que: 'Pasto y monte', porque: 'Pierden coherencia igual que un relleno' },
  { que: 'Predios chicos', porque: `Menos de ${cal.parametros.min_px_sitio} píxeles de 80 m` },
  { que: 'Un año entero', porque: `Hay datos del ${fecha(indice.desde)} al ${fecha(indice.hasta, true)}` },
  { que: 'Validación independiente', porque: `Sólo ${CALIBRADO_CON}` },
]


/** Each pair of passes: the dash is 80 % of the surroundings' coherence and the dot, the site's. Dot below the dash = awake pair. */
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
              <b>{t('Órbita {0}', o)}</b>
              <span>{t('{0} de {1} despiertas', pares.filter((p) => p.despierto).length, pares.length)}</span>
            </div>
            <svg className="chart" width={ancho} height={alto} role="img" aria-label={t('Comparaciones de la órbita {0}', o)}>
              <line x1={0} x2={ancho} y1={y(0)} y2={y(0)} stroke="var(--line)" />
              <line x1={0} x2={ancho} y1={y(1)} y2={y(1)} stroke="var(--line)" />
              {pares.map((p, i) => {
                const x = i * paso + paso / 2
                const corte = y(P.razon * p.anillo)
                const color = p.despierto ? 'var(--despierto)' : 'var(--quieto)'
                return (
                  <g key={p.fecha}>
                    <title>{`${fecha(p.fecha, true)} · ${t('Sitio')} ${dec(p.sitio)} · ${t('Entorno')} ${dec(p.anillo)}`}</title>
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

/** A bar with the threshold marked. */
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
        {t('mínimo {0}', textoUmbral)}
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
      <PageHead title={t('Modelo')} sub={t('Insomnio: en qué fracción de las pasadas del radar un lugar cambió más que su entorno')} />

      <section className="section">
        <div className="paso-t">
          <i>1</i>
          <div>
            <h3>{t('La regla, pasada contra pasada')}</h3>
            <p>{t('Cada pasada del radar se compara con la anterior. Está despierta si el sitio (punto) queda debajo del {0} de su entorno (raya)', pct(P.razon))}</p>
          </div>
        </div>
        <div className="card">
          <Picker label={t('Sitio de ejemplo')} value={s.id} onChange={setId} options={conFicha.map((x) => ({ value: x.id, label: t(x.nombre), sub: x.lugar, radar: x.radar }))} />
          <Pares f={f} />
          <div className="legend">
            <span>
              <span className="dot" style={{ background: 'var(--despierto)' }} />
              {t('despierta')}
            </span>
            <span>
              <span className="dot" style={{ background: '#fff', boxShadow: 'inset 0 0 0 1.5px var(--quieto)' }} />
              {t('quieta')}
            </span>
            <span>
              <i style={{ background: 'var(--ink-2)' }} />
              {t('{0} del entorno', pct(P.razon))}
            </span>
          </div>
          <div className="medidores">
            <Medidor nombre={t('Insomnio')} valor={s.insomnio} texto={pct(s.insomnio)} umbral={P.min_insomnio} textoUmbral={pct(P.min_insomnio)} pasa={s.insomnio >= P.min_insomnio} />
            <Medidor
              nombre={t('Persistencia')}
              valor={f.persistencia}
              texto={f.persistencia == null ? '–' : pct(f.persistencia)}
              umbral={P.min_persistencia}
              textoUmbral={pct(P.min_persistencia)}
              pasa={(f.persistencia ?? 0) >= P.min_persistencia}
            />
            <Medidor nombre={t('Eco')} valor={f.eco_db} texto={f.eco_db == null ? '–' : `${dec(f.eco_db, 1)} dB`} umbral={ECO_MIN} textoUmbral={`${dec(ECO_MIN, 0)} dB`} min={-20} max={0} pasa={(f.eco_db ?? -99) >= ECO_MIN} />
          </div>
          <div className={`veredicto ${s.radar}`}>
            <Dot radar={s.radar} />
            <div>
              <b>{radar(s.radar)}</b>
              {getLang() === 'es' && <span>{f.motivo.replace('todos los pares', 'todas las pasadas')}</span>}
            </div>
          </div>
        </div>
      </section>

      <section className="section">
        <div className="paso-t">
          <i>2</i>
          <div>
            <h3>{t('Del AMBA a {0} manchas', candidatos.length)}</h3>
            <p>{t('La misma regla en toda la grilla, píxel por píxel')}</p>
          </div>
        </div>
        <div className="embudo">
          <div>
            <span>Grilla del {cal.frame === 'AMBA' ? 'AMBA' : 'frame'}</span>
            <div className="embudo-b" style={{ width: '100%' }} />
            <b className="num">{num(GRILLA)} ha</b>
          </div>
          <div>
            <span>{t('Tierra, sin el agua de JRC')}</span>
            <div className="embudo-b" style={{ width: `${(tierra / GRILLA) * 100}%` }} />
            <b className="num">{num(tierra)} ha</b>
          </div>
          <div>
            <span>{t('Manchas candidatas')}</span>
            <div className="embudo-b fin" style={{ width: `${(haCand / GRILLA) * 100}%` }} />
            <b className="num">
              {t('{0} ha · {1} % de la tierra', num(Math.round(haCand)), dec((haCand / tierra) * 100, 1))}
            </b>
          </div>
        </div>
        <div className="descartes">
          <span>{t('En el camino quedan')}</span>
          {DESCARTES.map((d) => (
            <span className="tag" key={d.que}>
              <b className="num">{getLang() === 'es' ? d.n : d.n.replace('.', ',')}</b> {t(d.que)}
            </span>
          ))}
        </div>
        <div className="card" style={{ marginTop: 16 }}>
          <div className="section-head" style={{ marginBottom: 12 }}>
            <h4>{t('Qué son las {0}', candidatos.length)}</h4>
          </div>
          <div className="apilada" role="img" aria-label={clases.map((c) => `${c.n} ${t(c.nombre)}`).join(', ')}>
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
                  {t(c.nombre)}
                </span>
              </div>
            ))}
          </div>
          <p className="note" style={{ marginTop: 16 }}>{t('Las “sin explicar” no están verificadas: no son basurales confirmados')}</p>
        </div>
      </section>

      <section className="section">
        <div className="paso-t">
          <i>3</i>
          <div>
            <h3>Los umbrales</h3>
            <p>Calibrados con {CALIBRADO_CON}. La franja es el rango válido</p>
          </div>
        </div>
        <div className="umbrales">
          {UMBRALES.map((u) => {
            const pos = (v: number) => `${((v - u.min) / (u.max - u.min)) * 100}%`
            return (
              <div key={u.nombre} title={t(u.nota)}>
                <div className="medidor-t">
                  <span>{u.nombre}</span>
                  <b className="num">{corto(u.valor)}</b>
                </div>
                <div className="rango">
                  <div style={{ left: pos(u.desde), right: `calc(100% - ${pos(u.hasta)})` }} />
                  <i style={{ left: pos(u.valor) }} />
                </div>
                <div className="rango-e num">
                  <span>{dec(u.min, 1)}</span>
                  <span>
                    válido de {corto(u.desde)} a {corto(u.hasta)}
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
            <h3>{t('¿Basural u otra cosa? El clasificador por mancha')}</h3>
            <p>{t('El radar dice si un lugar se mueve, no qué es. Para eso, un modelo LightGBM entrenado con un catálogo mundial de basurales')}</p>
          </div>
        </div>
        <div className="futuro">
          <div className="entradas">
            <div>
              <span className="src">{t('Catálogo mundial')}</span>
              <b>
                {num(CATALOGO)} {t('basurales mapeados')}
              </b>
              <p>{t('OpenStreetMap, Climate TRACE, EPA LMOP y plumas de metano de NASA EMIT')}</p>
            </div>
            <div>
              <span className="src">{t('Y lo que se les parece')}</span>
              <b>{t('canteras, aeródromos')}</b>
              <p>{t('29 variables por mancha')}: {t('radar NISAR, Sentinel-2 (vegetación, suelo desnudo, agua, infrarrojo) y forma')}</p>
            </div>
          </div>
          <div className="une" aria-hidden="true" />
          <div className="salida">
            <span className="src">LightGBM</span>
            <b>{t('Basural u otra cosa')}</b>
            <p>{t('Cientos de árboles de decisión, cada uno corrige al anterior')}</p>
          </div>
        </div>
        <p className="note" style={{ marginTop: 16 }}>{t('Clasificado como basural por el modelo: no es una confirmación')}</p>
      </section>

      <section className="panel section">
        <h3 style={{ marginBottom: 12 }}>{t('Lo que no ve')}</h3>
        <ul className="limits">
          {LIMITES.map((l) => (
            <li key={l.que}>
              <b>{t(l.que)}</b>
              <span>{t(l.porque)}</span>
            </li>
          ))}
        </ul>
      </section>

      <Fuentes />
    </div>
  )
}
