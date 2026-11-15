# data/

Toda la data del proyecto: los catálogos que entran al motor y lo que el motor calcula. Los `.h5` de NISAR (2 GB cada uno), los recortes por par y las fuentes fijas de cada frame no se suben: el pipeline los rehace (ver `.gitignore`).

| Carpeta | Qué tiene | Quién lo escribe |
|---|---|---|
| `catalogos/` | Basurales del mundo, negativos (lo que el radar confunde con un basural), sus geometrías, los complejos y `frames.json` | `motor/curar_basurales.py`, `negativos_*.py`, `geometrias_*.py`, `complejos_agrupar.py`, `frames_elegir.py` |
| `salidas/` | Índice de insomnio, manchas candidatas, cruce con los catálogos, óptico, modelo y veredictos, para 30 frames | El pipeline de `motor/` (detalle abajo) |

Todos los archivos pesados van en git normal (sin LFS). El más grande es `catalogos/basurales/basurales_mundo.json`, con 57 MB.

## catalogos/frames.json
Los 30 frames de NISAR donde se corrió el pipeline: caja, EPSG de la grilla, órbitas y por qué se eligió cada uno (10 elegidos primero y 20 más por cantidad de basurales abiertos). Lo arma `motor/frames_elegir.py` (`--agregar` para los 20 nuevos) con la API pública de ASF.

## catalogos/basurales/
Catálogo de basurales y rellenos del mundo, armado el 14/11/2026 por `motor/curar_basurales.py`. El objetivo es encontrar sitios que **en teoría están cerrados pero en la práctica siguen activos**.

| Archivo | Qué tiene |
|---|---|
| `basurales_mundo.json` (57 MB) | 66.981 sitios: 1.225 abiertos, 3.579 cerrados, 31 contradictorios y 62.146 sin estado conocido. 64.492 tienen área |
| `basurales_cerrados.json` | Solo los cerrados o en disputa, ordenados por `puntaje_sospecha` |
| `casos_curados_argentina.json` | 7 casos de Buenos Aires curados a mano (Luján, Norte III, González Catán, Ensenada, San Pedro, Navarro, Nueve de Julio) con notas y documentos, más los inventarios argentinos relacionados |

### Estructura
Cada archivo tiene `meta` (fuentes con licencia y cita, criterios, advertencias y conteos) y `sitios`. Cada sitio trae:
- `id`, `nombre`, `pais`, `lat`, `lon`, `tipo`
- `estado`: `abierto`, `cerrado`, `contradictorio` o `desconocido`, más `estados_por_fuente` con el motivo que da cada fuente
- `fecha_apertura`, `fecha_cierre`
- `area_m2`, `area_ha` y `area_origen`, que dice de qué fuente sale el área
- `operador`, `residuos`, `emisiones_climate_trace`
- `plumas_metano_emit` y `ultima_pluma_emit`
- `senales_cerrado_pero_activo`, con el tipo, el detalle y el peso de cada señal, y `puntaje_sospecha`
- `fuentes`: cada registro original con su `fuente`, `id_fuente`, `url` y sus datos, más las plumas de EMIT con su granulo y fecha

### Fuentes (citar todas)
| Clave | Fuente | Licencia |
|---|---|---|
| `osm` / `overture` | OpenStreetMap, con los polígonos sacados de Overture Maps release 2026-10-21.0 (`base/land_use`, `class=landfill`) | ODbL 1.0, © colaboradores de OpenStreetMap |
| `climate_trace` | Climate TRACE, subsector solid-waste-disposal, API v6 | CC BY 4.0 |
| `epa_lmop` | U.S. EPA LMOP Landfill and Project Database (2024-09) | Dominio público |
| `nasa_emit` | NASA EMIT L2B CH4PLM v002, doi:10.5067/EMIT/EMITL2BCH4PLM.002 | Sin restricciones |
| `curado_manual` | Notas y documentos citados en cada caso | La de cada fuente |

### Advertencias
- OSM casi nunca dice si un basural está activo, por eso la mayoría queda en `desconocido`.
- El metano no prueba actividad: un relleno cerrado emite durante décadas.
- Las señales sirven para priorizar qué mirar con NISAR. No son acusaciones: hablar de "señal compatible con actividad".
- Los sitios que solo están en OSM no traen país.

### Regenerar
Bajar las fuentes a un directorio (Overture con DuckDB, Climate TRACE por su API, el `.xlsx` de LMOP y los metadatos de EMIT por CMR) y correr:
```bash
cd motor
python curar_basurales.py <dir_descargas> ../data/catalogos/basurales
```

## catalogos/negativos/
Catálogo de **confusores**: lo que el radar puede confundir con un basural. Sirve para entrenar el modelo con casos negativos. Sigue la lista y las reglas de `docs/datos.md` y lo arman `negativos_extraer.py` y `negativos_curar.py` (en `motor/`).

| Archivo | Qué tiene |
|---|---|
| `negativos_mundo.json` (46 MB) | 64.986 polígonos de 24 clases, en zonas cercanas a basurales con estado conocido. La muestra se balancea por clase y por celda de 1° |
| `negativos_amba.json` | 1.259 polígonos del AMBA, hasta 150 por clase |

### Cómo se armó
- **Fuente:** Overture Maps release 2026-10-21.0, con las capas `land_use`, `land`, `water` e `infrastructure`. Son datos de OSM con licencia ODbL. De ahí salieron 4,26 millones de polígonos candidatos.
- **Tamaño:** entre 2 y 500 ha. Lo más grande va como máscara.
- **Zona:** celdas de 0,25° vecinas a un basural con estado conocido o curado. Es una aproximación a "los mismos frames de NISAR que los positivos".
- **Distancia:** a más de 500 m, de borde a borde, de cualquier sitio del catálogo de basurales.
- **Cupo:** por clase y por celda de 1°, A = 6, B = 3 y C = 2. El orden es reproducible porque usa el hash del id.

### Estructura de cada registro
- Identificación: `id`, `clase`, `grupo`, `prioridad` (A, B o C) y `rol` (`negativo` o `mascara`).
- Ubicación y tamaño: `nombre`, `pais` (inferido del basural más cercano), `lat`, `lon`, `area_ha` y `bbox`.
- Polígono: `poligono`, con el id de Overture y el de OSM.
- `frame_nisar`: queda vacío hasta que se bajen los frames.
- Origen: `fuente`, `id_fuente`, `url` (el objeto en OSM), `licencia` y `confianza` (alta, media o baja).
- Contexto: `basural_mas_cercano`, `etiquetas_osm` y `notas`.

En `meta` están los conteos por clase y las **clases pendientes**, las que no salen de OSM: rutas (son líneas y van como máscara), agua grande, quema y tala (FIRMS de la NASA), asentamientos (GHSL), cauces que se mueven (JRC) y zonas que el radar no ve bien por la geometría (máscara del GUNW más un DEM).

### Advertencias
- **Sesgo por país:** el 53 % es de EE. UU., porque ahí están la mayoría de los positivos con estado conocido (la EPA). Para entrenar hay que rebalancear por país o por frame.
- **Confianza baja:** los `feedlot` salen de `landuse=farmyard`, que no siempre es un corral de engorde. Igual con los acopios de granos. Hay que revisarlos antes de usarlos.
- OSM puede estar desactualizado: una obra que ya terminó puede seguir marcada como obra.
- Hay que validar separando por ciudad o por frame, no por sitio.

## Geometrías
Los polígonos van en archivos aparte. Cada feature se enlaza con su catálogo por `id`. Los arman `geometrias_extraer.py` y `geometrias_armar.py`.

| Archivo | Sitios | Con polígono | Formato |
|---|---|---|---|
| `catalogos/basurales/geometrias.geojson` (30 MB) | 66.981 | 57.068 | GeoJSON |
| `catalogos/negativos/geometrias_mundo.parquet` (34 MB) | 64.986 | 64.986 | GeoParquet (más de 50 MB en GeoJSON) |
| `catalogos/negativos/geometrias_amba.geojson` (1 MB) | 1.259 | 1.259 | GeoJSON |

- **Fuente:** Overture Maps 2026-10-21.0 (OSM, ODbL 1.0, © colaboradores de OpenStreetMap). Está en WGS84 (lon/lat), sin reproyectar.
- **Simplificación:** `ST_SimplifyPreserveTopology` con 0,0001° (unos 10 m), menos que un píxel de NISAR. El área cambia un 0,8 % en la mediana respecto del `area_ha` del catálogo, que se calculó con el polígono original.
- **Puntos:** los 9.913 basurales sin polígono van como punto con `geometria = "punto"`. Son los que vienen solo de la EPA o de Climate TRACE y los cerrados de OSM que Overture no trae. Entre los cerrados hay 1.925 con polígono y 1.654 con punto.
- **Lectura:** el GeoParquet se abre con GeoPandas (`geopandas.read_parquet`), DuckDB o QGIS. Los GeoJSON se abren con cualquier herramienta.
- **Revisión del 14/11:**
  - En 7.595 basurales el polígono es más de un 20 % más chico que el `area_ha` del catálogo. **Casi todos son sitios de menos de 5 ha** (la mayoría de menos de 1 ha), donde la simplificación a ~10 m pesa mucho. **En los sitios de 5 ha o más, que son los que se usan con el radar, no hay desajustes.**
  - De los 614 sitios formados por varios objetos OSM, sólo 33 (7 de 5 ha o más) quedaron con un contorno parcial, porque `geometrias_armar.py` se quedaba con el primer objeto. **El script ya une todos los objetos de cada sitio** (`ST_Union_Agg`), pero hay que volver a correrlo: los crudos (`geom_parts/`) no están en el repo.

## Complejos
`catalogos/basurales/complejos.json` (14 MB) agrupa en **complejos** los basurales del catálogo que están a menos de 1 km entre sí, por ejemplo las tres entradas de Norte III. Lo arma `motor/complejos_agrupar.py` a partir de `geometrias.geojson`, en unos 15 segundos.
- **Para qué:** que cada complejo cuente una sola vez y caiga entero en la misma partición de la validación. Al extraer variables, el anillo de control excluye todos los polígonos de los catálogos.
- **Estado del complejo:** `abierto` si alguna entrada está abierta y ninguna cerrada; `cerrado` al revés; `contradictorio` si hay de los dos; `desconocido` si ninguna tiene estado.
- **Contenido:** `complejo_por_sitio` (id del sitio → id del complejo) y `complejos` (sitios, estado, estados por sitio, área sumada, centro y nombres).
- **Conteos:** 59.538 complejos; 3.690 tienen varios sitios (11.133 sitios en total). Estados: 1.212 abiertos, 3.293 cerrados, 42 contradictorios y 54.991 desconocidos.
- **Limitación:** los polígonos de menos de 1 ha no unen a otros. Hay ciudades con cientos de micro basurales mapeados que, encadenados de a menos de 1 km, armaban "complejos" de 10 a 18 km. Igual puede quedar alguna cadena larga entre sitios más grandes: el mayor complejo tiene 75 sitios (escombreras mineras en Alemania).
- **Ojo con los nombres:** el sitio `BAS-061528`, "Ensenada", es Ensenada, Baja California (México), no la de Buenos Aires (`BAS-053303`).

## salidas/
Lo que calcula el motor. Cada archivo dice en `generado_por` qué script lo escribió. Se regenera corriendo ese script desde `motor/` (ver `motor/README.md`).

### Por frame: `salidas/<FRAME>/`
Una carpeta por cada uno de los 30 frames (el AMBA, Los Ángeles, CDMX, Delhi, Yakarta, Ponce y 24 condados de EE. UU.).

| Archivo | Qué tiene | Script |
|---|---|---|
| `frame.json`, `lista_productos.json` | La grilla del frame y los productos GUNW y GCOV de NISAR que la cruzan | `pipeline_insomnio.py buscar` |
| `manchas.geojson` | Manchas candidatas como polígonos, con su insomnio | `extraer_manchas.py --frame <FRAME>` |
| `tabla_radar.parquet` | Variables de radar de cada mancha contra su anillo | `extraer_manchas.py` |
| `insomnio_catalogo.parquet` | Insomnio de cada polígono de los catálogos que cae en el frame | `extraer_manchas.py` |
| `cruce_manchas_catalogo.parquet` | Qué manchas tocan qué polígonos de los catálogos | `modelo_por_frame.py` |
| `tabla_optico.parquet`, `tabla_optico_catalogo.parquet` | Variables de Sentinel-2 de las manchas y de los polígonos (sólo los 10 primeros frames) | `modelo_por_frame.py` (usa `extraer_optico.py`) |
| `modelo_por_frame.json` | Resumen del cruce y del óptico del frame | `modelo_por_frame.py` |

### Todos los frames juntos
| Archivo | Qué tiene | Script |
|---|---|---|
| `manchas.geojson`, `tabla_radar.parquet`, `insomnio_catalogo.parquet` | Lo de cada frame, junto | `extraer_manchas.py juntar` |
| `cruce_manchas_catalogo.parquet`, `tabla_optico*.parquet` | Cruce y óptico de todos los frames | `modelo_por_frame.py` |
| `veredictos.json` | Un veredicto por polígono del catálogo y por mancha sin catálogo (lo que muestra la web) | `flujo.py` |
| `evaluacion_actividad.json` | Matriz de abierto contra cerrado por país, con intervalos de Wilson | `flujo.py` |
| `resumen_flujo.json` | Conteos del flujo por frame y en total | `flujo.py` |
| `estado_conocido.json` | Basurales con estado conocido (abierto o cerrado según el registro) por frame | `frames_elegir.py` |

### Índice de insomnio del AMBA
| Archivo | Qué tiene | Script |
|---|---|---|
| `indice_80m.npz`, `indice_80m.png`, `indice_20m.png` | El índice de insomnio del AMBA a 80 m (y la figura a 20 m) | `pipeline_insomnio.py indice` |
| `resumen_80m.json`, `resumen_20m.json`, `lista_productos.json` | Pares usados, parámetros y conteos | `pipeline_insomnio.py` |
| `fichas_80m.json`, `fichas_20m.json`, `calibracion_80m.json` | Ficha de cada sitio con registro y la calibración de los umbrales | `pipeline_insomnio.py indice` y `calibrar` |

### Modelo
| Archivo | Qué tiene | Script |
|---|---|---|
| `tabla_entrenamiento.parquet`, `particiones.json` | Tabla de manchas con etiqueta y particiones por frame | `armar_tabla.py` |
| `metricas.json`, `modelo.txt`, `predicciones.parquet` | Modelo LightGBM por mancha, sus métricas y predicciones (**sin validar**) | `entrenar.py` |
| `metricas_variantes.json` | Variantes del modelo con las etiquetas ópticas | `modelo_por_frame.py variantes` |
| `etiquetas_optico_ia.json` | Etiquetas de actividad de 89 predios asignadas por IA mirando Sentinel-2, a ciegas. No las revisó una persona | A mano, ver `docs/modelo.md` |
| `optico_estado_conocido.parquet`, `optico_estado_conocido/`, `optico_estado_conocido_resumen.json` | Óptico de los 1.008 basurales de estado conocido (en 3 partes) | `optico_estado_conocido.py` |
| `optico_catalogo_frames.parquet` | Óptico de los basurales de 10 ha o más de los frames nuevos | `optico_catalogo_frames.py` |
| `radar_frente.parquet`, `radar_frente_evaluacion.json` | Variables de radar del frente activo de cada basural y su evaluación | `radar_frente.py` |
| `modelo_estado.json`, `predicciones_estado.parquet` | Modelo de abierto contra cerrado con las etiquetas del registro | `modelo_estado.py` |
| `prueba_resolucion.json` | Prueba del modelo del frente a 20 m contra 80 m | `prueba_resolucion.py` |

### Fuentes de las salidas
- **NISAR** L2 GUNW y GCOV (NASA/ISRO), vía ASF DAAC.
- **Sentinel-2** L2A (Copernicus, ESA), vía Microsoft Planetary Computer.
- **JRC Global Surface Water** v1.4 (agua) y **ESA WorldCover** 2021 v200 (cobertura, CC BY 4.0).
- Los catálogos de `catalogos/`, con las fuentes y licencias de arriba.
