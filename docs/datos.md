# Datos y fuentes

Qué datos usa Dumpsite, de dónde salen y con qué licencia. Qué archivo es cada cosa y qué script lo regenera está en `data/README.md`.

## NISAR
- **Productos:** L2 GUNW (interferograma con capa de coherencia a 80 m y otra envuelta a 20 m) y L2 GCOV (eco, a 10 o 20 m según el modo), de NASA/ISRO vía ASF DAAC (https://search.asf.alaska.edu/). Los productos son públicos y la descarga necesita una cuenta de NASA Earthdata.
- **Madurez:** la primera liberación pública de datos calibrados fue el 20/07/2026. ASF advierte que no hay que mezclar madureces (BETA, PROVISIONAL y VALIDATED). Usamos productos `PR`.
- **AMBA:** 15 GUNW y 19 GCOV de las órbitas 10 (descendente) y 161 (ascendente), del 25/06 al 12/10/2026. Cada GUNW pesa unos 2,2 GB, pero el pipeline lee por URL sólo la ventana que necesita.
- **30 frames:** 962 pares GUNW. Los `.h5` y los recortes no van al repo.

## Catálogo de basurales
Son **66.981 sitios del mundo** (1.225 abiertos, 3.579 cerrados, 31 contradictorios y 62.146 sin estado), unidos por sitio desde:

| Fuente | Qué aporta | Licencia |
|---|---|---|
| OpenStreetMap vía Overture Maps (release 2026-10-21.0) | Polígonos de `landuse=landfill` y los cerrados (`disused:landuse=landfill`) | ODbL 1.0, © colaboradores de OpenStreetMap |
| U.S. EPA LMOP (2024-09) | Estado, año de cierre y captura de biogás de los rellenos de EE. UU. | Dominio público |
| Climate TRACE (API v6) | Emisiones por sitio | CC BY 4.0 |
| NASA EMIT L2B CH4PLM v002 | Plumas de metano | Sin restricciones |
| Casos curados del equipo | 7 casos de Buenos Aires: Luján, Norte III, González Catán, Ensenada, San Pedro, Navarro y Nueve de Julio | La de cada fuente citada |

**OSM casi nunca dice si un basural está activo**, por eso la mayoría queda sin estado. El estado conocido sale casi todo de la EPA, y por eso los resultados están sesgados hacia EE. UU.

Otros datasets relevados que no entraron: detectores ópticos con etiquetas para ML, registros nacionales y regionales, y en el AMBA la base georreferenciada del CIM-FADU (UBA), que no confirmamos que tenga descarga pública.

## Negativos
**64.986 polígonos de 24 clases**, más 1.259 del AMBA. Son lo que el radar puede confundir con un basural porque también cambia seguido o devuelve poco eco:

- agua y superficies mojadas;
- canteras y movimiento de suelo;
- chatarrerías y playas de contenedores;
- agro y vegetación;
- aeródromos y otra infraestructura.

Salen de Overture Maps (OSM, ODbL). Miden entre 2 y 500 ha, están a más de 500 m de cualquier basural del catálogo y se muestrean cerca de basurales con estado conocido. Lo fijo y bien mapeado se saca con máscaras. Lo que el modelo tiene que aprender a separar, como las canteras, no se filtra: entra como negativo.

## Otras fuentes
- **Sentinel-2 L2A** (Copernicus, ESA), vía Microsoft Planetary Computer, sin cuenta: variables ópticas, etiquetas ópticas y el video.
- **JRC Global Surface Water** v1.4: máscara de agua.
- **ESA WorldCover** 2021 v200 (CC BY 4.0): cobertura de suelo como contexto.

## Casos de validación en Argentina
| Caso | Qué pasó | Para qué sirve |
|---|---|---|
| **Basural de Luján** | Dejó de recibir residuos el 1/07/2026, tras unos 52 años. La reconversión quedó frenada por disputas judiciales | Caso central: ¿cerrado y quieto o cerrado pero despierto? |
| **Norte III, CEAMSE** | Relleno activo que recibe la mayor parte de la basura del AMBA | Control positivo |
| San Pedro, Navarro, Nueve de Julio | Basural con orden judicial (octubre de 2026), cierre anunciado (febrero de 2026) y cierre en curso | Casos para seguir. Sus coordenadas son del centro del partido y falta ubicar cada predio |
