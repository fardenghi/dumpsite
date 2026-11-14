import { Dot, PageHead, fecha, num } from '../components/ui'
import { resumen, useSitios } from '../data/api'
import candidatos from '../data/seed/candidatos.json'

export const FUENTES = [
  { nombre: 'NISAR · NASA/ISRO, vía ASF DAAC', url: 'https://search.asf.alaska.edu/' },
  { nombre: 'Agua · JRC Global Surface Water', url: 'https://global-surface-water.appspot.com/' },
  { nombre: 'Blue Marble · NASA GIBS', url: 'https://www.earthdata.nasa.gov/engage/open-data-services-software/earthdata-developer-portal/gibs-api' },
  { nombre: 'Sentinel-2 · ESA Copernicus, vía Planetary Computer', url: 'https://planetarycomputer.microsoft.com/dataset/sentinel-2-l2a' },
  { nombre: 'Polígonos · OpenStreetMap, ODbL', url: 'https://www.openstreetmap.org/copyright' },
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
      <PageHead title="Los basurales que el radar nunca ve quietos" />

      <div className="heroes">
        <div>
          <b className="num">{num(r.sitios)}</b>
          <span>sitios analizados</span>
        </div>
        <div className="despierto">
          <b className="num">{num(r.despiertos)}</b>
          <span>
            <Dot radar="despierto" />
            despiertos
          </span>
        </div>
        <div>
          <b className="num">{num(sinRegistro)}</b>
          <span>despiertos sin registro oficial</span>
        </div>
        <div>
          <b className="num">{num(sinExplicar)}</b>
          <span>manchas sin explicar, sin verificar</span>
        </div>
      </div>

      <div className="datos">
        <span>
          <b className="num">{num(r.hectareas)}</b> ha en sitios
        </span>
        <span>
          {fecha(r.desde)} a {fecha(r.hasta, true)}
        </span>
      </div>

      <div className="row" style={{ marginBottom: 'auto' }}>
        <a className="btn primary" href="#/sitios">
          Ver los sitios
        </a>
        <a className="btn" href="#/modelo">
          Cómo se decide
        </a>
      </div>

      <Fuentes />
    </div>
  )
}
