import { Coherencia } from '../components/Coherencia'
import { Dot, Kpi, PageHead, fecha, num, pais, pct } from '../components/ui'
import { resumen, useSitios } from '../data/api'

export const FUENTES = [
  { nombre: 'NISAR · NASA/ISRO, vía ASF DAAC', url: 'https://search.asf.alaska.edu/' },
  { nombre: 'Blue Marble · NASA GIBS', url: 'https://www.earthdata.nasa.gov/engage/open-data-services-software/earthdata-developer-portal/gibs-api' },
  { nombre: 'Sentinel-2 · ESA Copernicus, vía Planetary Computer', url: 'https://planetarycomputer.microsoft.com/dataset/sentinel-2-l2a' },
  { nombre: 'Polígonos · OpenStreetMap, ODbL', url: 'https://www.openstreetmap.org/copyright' },
]

export default function Inicio() {
  const { sitios } = useSitios()
  if (!sitios) return null
  const r = resumen(sitios)
  const orden = [...sitios].sort((a, b) => b.insomnio - a.insomnio).slice(0, 8)
  const lujan = sitios.find((s) => s.id === 'lujan')
  const mancha = sitios.find((s) => s.id === 'lujan-oeste')

  return (
    <>
      <PageHead
        title="Los basurales que el radar nunca ve quietos"
        sub="NISAR pasa cada 12 días. Donde dos pasadas nunca se parecen, alguien está moviendo el suelo"
        right={
          <a className="btn primary" href="#/mapa">
            Abrir el mapa
          </a>
        }
      />

      <div className="kpis grid g4 section">
        <Kpi label="Sitios" value={num(r.sitios)} />
        <Kpi
          label={
            <>
              <Dot radar="despierto" />
              Despiertos
            </>
          }
          value={num(r.despiertos)}
          unit={`de ${r.sitios}`}
        />
        <Kpi label="Países" value={num(r.paises)} />
        <Kpi label="Superficie" value={num(r.hectareas)} unit="ha" />
      </div>

      <div className="split section" style={{ ['--cols' as string]: 'minmax(0, 1.5fr) minmax(0, 1fr)' }}>
        <div className="card">
          <div className="section-head">
            <h3>Insomnio</h3>
            <span className="note-r">
              pares con coherencia baja, {fecha(r.desde)} a {fecha(r.hasta, true)}
            </span>
          </div>
          <div className="rank">
            {orden.map((s) => (
              <a key={s.id} href={`#/mapa?sitio=${s.id}`}>
                <Dot radar={s.radar} />
                <b>
                  {s.nombre}
                  <span>
                    {s.lugar}, {pais(s.pais)}
                  </span>
                </b>
                <div className={`bar ${s.radar}`}>
                  <div style={{ width: pct(s.insomnio).replace(' ', '') }} />
                </div>
                <span className="pct">{pct(s.insomnio)}</span>
              </a>
            ))}
          </div>
        </div>

        {lujan && mancha && (
          <div className="panel col" style={{ gap: 16 }}>
            <div>
              <h3>Luján cerró el 1 de julio</h3>
              <p className="muted small" style={{ marginTop: 4 }}>
                El predio se durmió. A 700 m, una mancha sigue despierta
              </p>
            </div>
            <Coherencia
              fechas={lujan.pares.map((p) => p.fecha)}
              marca={{ fecha: lujan.cierre!, texto: 'cierre' }}
              series={[
                { nombre: 'Predio', color: 'var(--quieto)', valores: lujan.pares.map((p) => p.sitio) },
                { nombre: 'Mancha vecina', color: 'var(--despierto)', valores: mancha.pares.map((p) => p.sitio) },
              ]}
            />
            <a className="btn sm" href="#/mapa?sitio=lujan-oeste" style={{ alignSelf: 'flex-start', marginTop: 'auto' }}>
              Ver la mancha
            </a>
          </div>
        )}
      </div>

      <div className="panel section">
        <div className="steps grid g3">
          <div>
            <div>
              <b>Dos pasadas</b>
              <p>El radar compara cada pasada con la anterior y mide cuánto se parecen</p>
            </div>
          </div>
          <div>
            <div>
              <b>Lo que no se repite</b>
              <p>Un campo cambia por estación. Un basural activo cambia siempre</p>
            </div>
          </div>
          <div>
            <div>
              <b>Contra el registro</b>
              <p>Cada sitio se cruza con lo que dice el registro oficial</p>
            </div>
          </div>
        </div>
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
