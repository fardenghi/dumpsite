import { dec, num } from '../components/ui'
import { useSitios } from '../data/api'
import { UMBRAL_BAJO } from '../data/types'
import { conteo, posiblesNuevos, useVeredictos } from '../data/veredictos'
import { t } from '../i18n'

export const FUENTES = [
  { nombre: 'NISAR · NASA/ISRO, vía ASF DAAC', url: 'https://search.asf.alaska.edu/' },
  { nombre: 'Agua · JRC Global Surface Water', url: 'https://global-surface-water.appspot.com/' },
  { nombre: 'Blue Marble · NASA GIBS', url: 'https://www.earthdata.nasa.gov/engage/open-data-services-software/earthdata-developer-portal/gibs-api' },
  { nombre: 'Sentinel-2 · ESA Copernicus, vía Planetary Computer', url: 'https://planetarycomputer.microsoft.com/dataset/sentinel-2-l2a' },
  { nombre: 'Polígonos · OpenStreetMap, ODbL', url: 'https://www.openstreetmap.org/copyright' },
  { nombre: 'Catálogo de basurales · Overture Maps (OpenStreetMap, ODbL)', url: 'https://docs.overturemaps.org/' },
  { nombre: 'Catálogo de basurales · Climate TRACE, CC BY 4.0', url: 'https://climatetrace.org/data' },
  { nombre: 'Rellenos en EE. UU. · EPA LMOP', url: 'https://www.epa.gov/lmop' },
  { nombre: 'Plumas de metano · NASA EMIT L2B CH4PLM', url: 'https://doi.org/10.5067/EMIT/EMITL2BCH4PLM.002' },
]

export function Fuentes() {
  return (
    <div className="sources">
      {FUENTES.map((f) => (
        <a key={f.url} href={f.url} target="_blank" rel="noreferrer">
          {t(f.nombre)}
        </a>
      ))}
    </div>
  )
}

export default function Inicio() {
  const { sitios } = useSitios()
  const veredictos = useVeredictos()
  if (!sitios) return null
  // the same count as the header, the map legend and Sites: all regions
  const n = conteo(sitios, veredictos)
  const regiones = veredictos?.frames?.length ?? 1
  const nuevos = posiblesNuevos(veredictos).length

  return (
    <div className="resumen">
      <div className="portada">
        <div className="portada-txt">
          <p className="portada-meta">{t('Radar NISAR · {0} regiones', num(regiones))}</p>
          <h1>{t('Los basurales que el radar nunca ve quietos')}</h1>
          <p className="portada-sub">{t('Donde dos pasadas del radar nunca se parecen, alguien está moviendo el suelo')}</p>
          <div className="row">
            <a className="btn primary" href="#/sitios">
              {t('Ver los sitios')}
            </a>
            <a className="btn" href="#/modelo">
              {t('Cómo se decide')}
            </a>
          </div>
        </div>

        <div className="cifras">
          <div>
            <span>{t('Sitios analizados')}</span>
            <b className="num">{num(n.total)}</b>
            <small>{t('{0} ha en total', num(Math.round(n.ha)))}</small>
          </div>
          <div className="despierto">
            <span>{t('Despiertos')}</span>
            <b className="num">{num(n.despierto)}</b>
            <small>{t('insomnio mayor que {0}', dec(UMBRAL_BAJO, 1))}</small>
          </div>
          <div>
            <span>{t('Regiones de NISAR')}</span>
            <b className="num">{num(regiones)}</b>
            <small>{t('procesadas con NISAR')}</small>
          </div>
          <div>
            <span>{t('Posibles basurales nuevos')}</span>
            <b className="num">{num(nuevos)}</b>
            <small>{t('sin verificar todavía')}</small>
          </div>
        </div>
      </div>

      <Fuentes />
    </div>
  )
}
