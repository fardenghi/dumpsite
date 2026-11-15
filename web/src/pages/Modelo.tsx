import { useState } from 'react'
import { Dot, PageHead, Picker, dec, fecha, num, pct, radar } from '../components/ui'
import { useSitios } from '../data/api'
import { UMBRAL_BAJO } from '../data/types'
import { N_VARIABLES, useVeredictos } from '../data/veredictos'
import { getLang, t } from '../i18n'
import cal from '../data/seed/calibracion.json'
import candidatos from '../data/seed/candidatos.json'
import fichasJson from '../data/seed/fichas.json'
import indice from '../data/seed/indice.json'
import { Fuentes } from './Inicio'

// Every number on this page comes from the pipeline (seed/*.json). The funnel and threshold ones are in
// seed/calibracion.json, written by scripts/datos_mapa.py from the index outputs. What wasn't measured isn't shown.
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
const ECO_MIN = cal.parametros.eco_min_db
// the frame grid, in hectares: land plus JRC water
const AGUA = cal.superficie.agua_ha
const GRILLA = cal.superficie.tierra_ha + AGUA
const CLASES = [
  { id: 'relleno_osm', nombre: 'Relleno según OpenStreetMap', color: 'var(--despierto)' },
  { id: 'uso_conocido', nombre: 'Uso conocido: aeródromos, golf, parques', color: 'var(--green)' },
  { id: 'sin_explicar', nombre: 'Sin explicar', color: 'var(--faint)' },
]
/** A threshold or a range edge, without extra zeros: 0,8 · 0,725 · −13. */
const corto = (n: number) => dec(n, 3).replace(/0+$/, '').replace(/[,.]$/, '')
const R = cal.rangos
const CON = cal.calibrado_con

// Built at render time, not at module load: texts and decimals depend on the chosen language
const descartes = () => [
  { n: num(cal.descartes.chicas), que: t('de menos de {0} ha', corto(cal.parametros.min_ha)) },
  { n: num(cal.descartes.lisas), que: t('lisas: eco menor que {0} dB', corto(ECO_MIN)) },
  { n: num(cal.descartes.lineales), que: t('lineales: rutas y arroyos') },
  { n: `${num(cal.superficie.estacional_ha)} ha`, que: t('despiertas sólo por temporada') },
]
// min and max are only the width of the drawn scale; the value and the valid band come from the calibration
const umbrales = () => [
  {
    nombre: t('Sitio / entorno'), valor: cal.parametros.razon, desde: R.razon.desde, hasta: R.razon.hasta, min: 0.6, max: 1,
    nota: t('Por debajo de {0}, {1} deja de ser persistente', corto(R.razon.desde), cal.testigo.nombre) + (R.razon.siguiente == null ? '' : `. ${t('Desde {0}, aparecen manchas en la costa del Roggero', corto(R.razon.siguiente))}`),
  },
  {
    nombre: t('Insomnio mínimo'), valor: cal.parametros.min_insomnio, desde: R.min_insomnio.desde, hasta: R.min_insomnio.hasta, min: 0.3, max: 1,
    nota: R.min_insomnio.siguiente == null ? '' : t('Con {0}, {1} ({2}) queda afuera', corto(R.min_insomnio.siguiente), cal.testigo.nombre, corto(cal.testigo.insomnio)),
  },
  {
    nombre: t('Eco mínimo, dB'), valor: ECO_MIN, desde: R.eco_min_db.desde, hasta: R.eco_min_db.hasta, min: -20, max: -8,
    nota: t('Entre lo liso conocido ({0}, {1}) y el relleno con menos eco ({2}, {3})', R.eco_min_db.liso, corto(R.eco_min_db.desde), R.eco_min_db.relleno, corto(R.eco_min_db.hasta)),
  },
]

// world dump-site catalog the classifier is trained with (data/catalogos/basurales/basurales_mundo.json)
const CATALOGO = cal.catalogo_sitios

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
  const frames = useVeredictos()?.frames?.length ?? 0
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
              {/* with the low threshold the pipeline's reason ("señal intermedia"…) no longer explains the verdict: the rule used is stated */}
              {s.umbral_bajo ? (
                <span>{t('Despierto con el umbral bajo: insomnio mayor que {0}. El predio es chico, liso o de señal intermedia para la regla calibrada', pct(UMBRAL_BAJO))}</span>
              ) : (
                getLang() === 'es' && <span>{f.motivo.replace('todos los pares', 'todas las pasadas')}</span>
              )}
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
            <span>{t('Grilla del AMBA')}</span>
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
          {descartes().map((d) => (
            <span className="tag" key={d.que}>
              <b className="num">{d.n}</b> {d.que}
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
            <h3>{t('Los umbrales')}</h3>
            <p>{t('Calibrados con {0} rellenos y {1} controles. La franja es el rango válido', CON.rellenos, CON.controles)}</p>
          </div>
        </div>
        <div className="umbrales">
          {umbrales().map((u) => {
            const pos = (v: number) => `${((v - u.min) / (u.max - u.min)) * 100}%`
            return (
              <div key={u.nombre} title={u.nota}>
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
                  <span>{t('válido de {0} a {1}', corto(u.desde), corto(u.hasta))}</span>
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
              <p>
                {N_VARIABLES ? `${t('{0} variables por mancha', N_VARIABLES)}: ` : ''}
                {t('radar NISAR, Sentinel-2 (vegetación, suelo desnudo, agua, infrarrojo) y forma')}
              </p>
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
        <h3 style={{ marginBottom: 8 }}>{t('Lo que nos queda')}</h3>
        <p>
          {frames
            ? t('Correrlo en el resto del mundo. Por el tiempo del hackathon priorizamos algunas regiones: lo corrimos en {0} frames de NISAR.', frames)
            : t('Correrlo en el resto del mundo. Por el tiempo del hackathon priorizamos algunas regiones.')}
        </p>
      </section>

      <Fuentes />
    </div>
  )
}
