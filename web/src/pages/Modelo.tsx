import { Kpi, PageHead } from '../components/ui'
import { FUENTES } from './Inicio'

// Lo que todavía no se midió va como null y se muestra con una raya: nunca un número inventado.
const ENTRENAMIENTO: { positivos: number | null; negativos: number | null; precision: number | null; recall: number | null; apartados: number | null } = {
  positivos: null,
  negativos: null,
  precision: null,
  recall: null,
  apartados: null,
}

const VARIABLES = [
  { nombre: 'Coherencia adentro del sitio, por par', fuente: 'NISAR GUNW' },
  { nombre: 'Coherencia en un anillo de 1,5 km, por par', fuente: 'NISAR GUNW' },
  { nombre: 'Eco HH y HV', fuente: 'NISAR GCOV' },
  { nombre: 'Superficie', fuente: 'geometría de la mancha' },
  { nombre: 'Elongación', fuente: 'geometría de la mancha' },
]

const LIMITES = [
  { que: 'Sitios de menos de 2 ha', porque: 'Quedan por debajo de la resolución de 80 m' },
  { que: 'Agua y superficies lisas', porque: 'Devuelven poco eco y parecen cambio. Se descartan con el eco y máscaras de OpenStreetMap' },
  { que: 'Canteras y obras', porque: 'Remueven suelo igual que un basural. Es lo que el clasificador tiene que separar' },
  { que: 'Cuatro meses de datos', porque: 'NISAR publica desde junio de 2026. Todavía no hay un año entero' },
]

const v = (n: number | null, f: (n: number) => string = String) => (n == null ? <span className="pending">–</span> : f(n))

export default function Modelo() {
  const e = ENTRENAMIENTO
  return (
    <>
      <PageHead title="Modelo" sub="Qué mira, con qué se entrenó y cuánto acierta" right={<span className="tag">En construcción</span>} />

      <div className="panel section">
        <div className="flow">
          <div>
            <span className="src">GUNW</span>
            <b>Insomnio</b>
            <p>Fracción de pares con coherencia baja</p>
          </div>
          <div>
            <span className="src">GCOV · OSM</span>
            <b>Filtros</b>
            <p>Fuera agua, rutas y superficies lisas</p>
          </div>
          <div>
            <span className="src">gradient boosting</span>
            <b>Clasificador</b>
            <p>Relleno, cantera u obra, por mancha</p>
          </div>
          <div>
            <span className="src">registro oficial</span>
            <b>Veredicto</b>
            <p>Despierto, quieto o el radar no alcanza</p>
          </div>
        </div>
      </div>

      <div className="split section" style={{ ['--cols' as string]: 'minmax(0, 1.3fr) minmax(0, 1fr)' }}>
        <div className="card">
          <div className="section-head">
            <h3>Variables</h3>
            <span className="note-r">una fila por mancha</span>
          </div>
          <table className="t">
            <tbody>
              {VARIABLES.map((x) => (
                <tr key={x.nombre}>
                  <td style={{ paddingLeft: 0, whiteSpace: 'normal' }}>{x.nombre}</td>
                  <td className="r muted mono" style={{ paddingRight: 0 }}>
                    {x.fuente}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="card col" style={{ gap: 24 }}>
          <h3>Entrenamiento</h3>
          <div className="kpis sm grid" style={{ gridTemplateColumns: '1fr 1fr' }}>
            <Kpi label="Rellenos" value={v(e.positivos)} />
            <Kpi label="Canteras, obras y otros" value={v(e.negativos)} />
          </div>
          <p className="small muted">Etiquetas de OpenStreetMap, de todo el mundo. Argentina queda afuera para validar</p>
        </div>
      </div>

      <div className="section">
        <div className="section-head">
          <h2>Validación</h2>
          <span className="note-r">sobre sitios que el modelo nunca vio</span>
        </div>
        <div className="kpis grid g3">
          <Kpi label="Precisión" value={v(e.precision, (n) => `${Math.round(n * 100)} %`)} />
          <Kpi label="Cobertura" value={v(e.recall, (n) => `${Math.round(n * 100)} %`)} />
          <Kpi label="Sitios apartados" value={v(e.apartados)} />
        </div>
      </div>

      <div className="panel section">
        <div className="section-head">
          <h3>Lo que no ve</h3>
        </div>
        <ul className="limits">
          {LIMITES.map((l) => (
            <li key={l.que}>
              <b style={{ fontWeight: 500 }}>{l.que}</b>
              <span>{l.porque}</span>
            </li>
          ))}
        </ul>
      </div>

      <div className="sources">
        {FUENTES.map((f) => (
          <a key={f.url} href={f.url} target="_blank" rel="noreferrer">
            {f.nombre}
          </a>
        ))}
      </div>
    </>
  )
}
