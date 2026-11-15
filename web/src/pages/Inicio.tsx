import { fecha, num } from '../components/ui'
import { resumen, useSitios } from '../data/api'
import candidatos from '../data/seed/candidatos.json'

export const FUENTES = [
  { nombre: 'NISAR · NASA/ISRO, vía ASF DAAC', url: 'https://search.asf.alaska.edu/' },
  { nombre: 'Agua · JRC Global Surface Water', url: 'https://global-surface-water.appspot.com/' },
  { nombre: 'Blue Marble · NASA GIBS', url: 'https://www.earthdata.nasa.gov/engage/open-data-services-software/earthdata-developer-portal/gibs-api' },
  { nombre: 'Sentinel-2 · ESA Copernicus, vía Planetary Computer', url: 'https://planetarycomputer.microsoft.com/dataset/sentinel-2-l2a' },
  { nombre: 'Polígonos · OpenStreetMap, ODbL', url: 'https://www.openstreetmap.org/copyright' },
  { nombre: 'Catálogo de otros frames · Overture Maps (OpenStreetMap, ODbL)', url: 'https://docs.overturemaps.org/' },
  { nombre: 'Estado del registro en EE. UU. · EPA LMOP', url: 'https://www.epa.gov/lmop' },
]

export function Fuentes() {
  return (
    <div className="sources">
      {FUENTES.map((f) => (
        <a key={f.url} href={f.url} target="_blank" rel="noreferrer">
          {f.nombre}
        </a>
      ))}
    </div>
  )
}

export default function Inicio() {
  const { sitios } = useSitios()
  if (!sitios) return null
  const r = resumen(sitios)
  const sinRegistro = sitios.filter((s) => s.radar === 'despierto' && s.registro === 'sin_registro').length
  const sinExplicar = candidatos.filter((c) => c.clase === 'sin_explicar').length

  return (
    <div className="resumen">
      <div className="portada">
        <div className="portada-txt">
          <p className="portada-meta">
            Radar NISAR · AMBA · {fecha(r.desde)} a {fecha(r.hasta, true)}
          </p>
          <h1>Los basurales que el radar nunca ve quietos</h1>
          <p className="portada-sub">Donde dos pasadas del radar nunca se parecen, alguien está moviendo el suelo</p>
          <div className="row">
            <a className="btn primary" href="#/sitios">
              Ver los sitios
            </a>
            <a className="btn" href="#/modelo">
              Cómo se decide
            </a>
          </div>
        </div>

        <div className="cifras">
          <div>
            <span>Sitios analizados</span>
            <b className="num">{num(r.sitios)}</b>
            <small>{num(r.hectareas)} ha en total</small>
          </div>
          <div className="despierto">
            <span>Despiertos</span>
            <b className="num">{num(r.despiertos)}</b>
            <small>nunca quietos</small>
          </div>
          <div>
            <span>Despiertos sin registro</span>
            <b className="num">{num(sinRegistro)}</b>
            <small>fuera de los registros</small>
          </div>
          <div>
            <span>Manchas sin explicar</span>
            <b className="num">{num(sinExplicar)}</b>
            <small>sin verificar todavía</small>
          </div>
        </div>
      </div>

      <Fuentes />
    </div>
  )
}
