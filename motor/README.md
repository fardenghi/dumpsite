# motor/

Dumpsite's pipeline in Python: it reads NISAR, computes the insomnia index, builds the blobs, crosses them with the catalogs in `../data/catalogos/`, measures the optical data, trains the models and writes the verdicts for the web. Everything it writes goes to `../data/salidas/` (see `../data/README.md`). How each step works is in `../docs/`.

```bash
cd motor
python -m venv .venv && .venv/bin/pip install -r requirements.txt   # on Windows: .venv\Scripts\pip
python -m pytest tests -q                                           # about 2 minutes
```

Downloading NISAR needs a NASA Earthdata account (`EARTHDATA_TOKEN`). The `.h5` files and the crops aren't committed: they go to `datos/` or to a VM (`infra/README.md`).

## Scripts

| Script | Usage | What it does |
|---|---|---|
| `pipeline_insomnio.py` | `python pipeline_insomnio.py indice` | **El pipeline completo, para cualquier frame** (sin `--frame`, el AMBA). `buscar` lista los GUNW y GCOV que cruzan la caja con la API de ASF; `bajar` los baja con earthaccess; `procesar` recorta coherencia y backscatter a la grilla común del frame (necesita `h5py`). **`indice` calcula la versión final del índice** con los recortes ya hechos: tarda 14 s a 80 m y escribe `../salidas/` y, para el AMBA, los datos de `../../insomnes-web/`. `calibrar` barre los umbrales (sólo AMBA). `todo` corre desde cero, pensado para la VM (`../infra/README.md`). Resultados: `../idea/indice-final.md` |
| `insomnio.py` | se importa | El cálculo del índice, sin lectura ni escritura: máscara de agua, factor de separación, entorno, fracción por órbita, persistencia, manchas y ficha con veredicto por sitio. El anillo de un sitio excluye el agua y los polígonos de los catálogos (`excluir`). Los umbrales están en `Parametros` |
| `geo.py` | se importa | UTM ↔ lat/lon vectorizado para cualquier zona y hemisferio (el EPSG sale del producto), los frames (`geo.frame("DELHI")`, `geo.AMBA`), la grilla común, rasterizado de polígonos y remuestreo a Web Mercator para la web. Sin parámetros, todo es el AMBA en UTM 21S, como antes |
| `fuentes_fijas.py` | `python fuentes_fijas.py todo --frame DELHI` (o `agua`, `usos`, `catalogo`, `sitios`) | Arma las fuentes fijas de un frame y las cachea en `fijos/<FRAME>/`: máscara de agua de JRC Global Surface Water, usos conocidos de OSM desde Overture Maps, los polígonos de los catálogos de `../../data/` que caen en el frame y la fracción urbana y de cultivo de ESA WorldCover (`cobertura`). `indice` y `extraer_manchas.py` las arman solos si faltan. Las del AMBA están sueltas en `fijos/`, van al repo y son las de referencia (usos de Nominatim): con ellas `indice` no necesita red. Las de los otros frames no se suben. Necesita `tifffile` e `imagecodecs` para `agua` y `cobertura`, y `duckdb` para `usos` |
| `indice_png_web.py` | `python indice_png_web.py [--frame F ...]` | El índice de cada frame como imagen para la web, igual que el del AMBA. Lee `salidas/<FRAME>/indice_80m.npz` (lo escribe `pipeline_insomnio.py indice --frame F`), no recalcula nada, y escribe `insomnes-web/public/indice/insomnio-<frame>.png` y `insomnes-web/src/data/seed/indices.json` |
| `extraer_manchas.py` | `python extraer_manchas.py --frame LOS_ANGELES` y después `python extraer_manchas.py juntar` | **Etapa 4.** Con los recortes de un frame: arma las manchas y las escribe como polígonos (`manchas.geojson`), mide cada candidata contra su anillo (`tabla_radar.parquet`: movimiento, eco, HV/HH, forma y contexto) y mide el insomnio de cada polígono de los catálogos (`insomnio_catalogo.parquet`). Cada frame va a `../salidas/<FRAME>/` y `juntar` arma los tres archivos del contrato en `../salidas/`. Formato: `../idea/contratos-datos.md` |
| `sitios_registro.json` | se edita a mano | Los sitios con ficha: objeto de OSM o caja, registro, fecha de cierre y fuentes. `rol` dice cuáles se usaron para calibrar y cuáles son controles |
| `tests/test_insomnio.py` | `python -m pytest tests -q` | Caso sintético: ciudad quieta, basural despierto, agua, tosquera sin máscara, campo estacional, ruta y un predio demasiado chico |
| `resumen_etapa4.py` | `python resumen_etapa4.py` | Las tablas de `../idea/etapa4-manchas.md` en Markdown, a partir de `../salidas/<FRAME>/`: manchas por frame y despierto / quieto / no alcanza por estado, con los frames agregados por abiertos aparte de los de antes. No calcula nada nuevo |
| `optico_catalogo_frames.py` | `python optico_catalogo_frames.py preparar` y después `correr` | Óptico de Sentinel-2 de los basurales de 10 ha o más de los frames que no lo tienen de los prompts 7 ni 4. Usa `extraer_optico.py` sin modificarlo. `preparar` arma un trabajo chico (polígonos a medir y vecinos del catálogo) para poder correr la lectura en otra máquina. Escribe `../salidas/optico_catalogo_frames.parquet` |
| `modelo_estado.py` | `python modelo_estado.py` | **Modelo de abierto contra cerrado** con las etiquetas del registro: radar y óptico por predio, validado dejando un frame afuera, y qué aprende (coeficientes, importancia, control por área, prueba en el AMBA). Escribe `../salidas/modelo_estado.json` y `../salidas/predicciones_estado.parquet`. Resultado en `../idea/modelo-estado.md` |
| `tests/test_extraer_manchas.py` | `python -m pytest tests -q` | El trazado de píxeles a polígonos (área exacta, anillos simples, orientación de GeoJSON) y la etapa 4 de punta a punta con un frame sintético: un relleno despierto, un aeródromo quieto y un predio demasiado chico |
| `tests/test_frames.py` | `python -m pytest tests -q` | El pipeline fuera del AMBA, sin red: UTM en los dos hemisferios, grilla y máscaras en el norte, el anillo que excluye los catálogos, recortes entre zonas UTM y de frames de NISAR vecinos, y `procesar` + `indice` de punta a punta con productos sintéticos del hemisferio norte |
| `coherencia_gunw.py` | `python coherencia_gunw.py <GUNW.h5> [carpeta_salida]` | Lista las capas de coherencia del archivo, recorta alrededor de sitios fijos (Norte III, Luján, CABA, campo) y guarda una figura con el panorama del AMBA |
| `manchas.py` | `python manchas.py <GUNW.h5> [--frame X]` | Busca en un GUNW manchas de coherencia baja respecto de su entorno y las lista con superficie, coordenadas y elongación (compacta, alargada o lineal). Usa la zona UTM del producto; sin `--frame` ni `--caja` mira el AMBA |
| `predios.py` | `python predios.py <GUNW.h5> <carpeta_salida>` | Mide la coherencia adentro de predios conocidos (cajas de OSM) contra un anillo de 1,5 km, en las capas de 80 m y 20 m, y guarda una figura |
| `frames_elegir.py` | `python frames_elegir.py [--cache dir]` | Etapa 2. Con la API pública de ASF (GUNW `PR`, sin login) evalúa ciudades y las celdas con más basurales de estado conocido, y elige ~10 frames sin superponerse. Escribe `../../data/frames.json`, `../idea/frames-elegidos.md` y `../salidas/estado_conocido.json` (basurales de estado conocido por frame). Tarda ~1 min. Con `--agregar 20` no vuelve a elegir: deja los frames que ya están y suma 20 por cantidad de basurales abiertos (prompt 6) |
| `insomnio_catalogo.py` | `python insomnio_catalogo.py [--modo exacto\|aproximado]` | Etapa 4, segunda dirección del cruce: el insomnio sobre cada polígono del catálogo (basurales y negativos) del frame, esté o no en una mancha. `exacto` usa los recortes por par y `insomnio.ficha()` (reproduce `fichas_80m.json`); `aproximado`, sólo `indice_80m.npz`. Escribe `../salidas/insomnio_catalogo.parquet`. Por ahora sólo el AMBA |
| `veredicto.py` | `python veredicto.py [--carpeta ../datos/mock]` | Etapa 9: junta el cruce en las dos direcciones y da el veredicto por sitio (activo conocido, cerrado pero despierto, cerrado y quieto, quieto según el radar, posible nuevo, descartada, el radar no alcanza). Escribe `../salidas/veredictos.json` con la frase para el pitch |
| `evaluar_actividad.py` | `python evaluar_actividad.py [--fuentes epa_lmop curado_manual]` | Etapa 8: matriz de abierto contra cerrado por país sobre los basurales de estado conocido, con intervalos de Wilson. Escribe `../salidas/evaluacion_actividad.json` |
| `flujo.py` | `python flujo.py [--frame LOS_ANGELES AMBA] [--web]` | Etapa 9, el flujo completo: sobre cada `salidas/<FRAME>/insomnio_catalogo.parquet` corre el veredicto (cruce del prompt 4 o calculado en `datos/flujo/`) y la matriz de actividad con y sin OSM, con los casos para mirar a mano. Escribe `../salidas/veredictos.json`, `evaluacion_actividad.json`, `resumen_flujo.json`, `../idea/resultados-flujo.md` y, con `--web`, `insomnes-web/src/data/seed/veredictos.json` |
| `cruce_catalogo.py` | `python cruce_catalogo.py [--indice X.npz] [--min-ha 10]` | Cruza un índice ya calculado con los polígonos de basurales (por complejo) y de negativos de `../../data/`: insomnio mediano por polígono, por clase y AUC. No necesita los recortes: usa `../salidas/indice_80m.npz`. Resultados en `../idea/indice-final.md` |
| `manchas_vectorizar.py` | `python manchas_vectorizar.py [--indice X.npz --frame F --epsg N]` | Prompt 3. Las manchas de un índice ya calculado como polígonos (con `insomnio.manchas()`), todas, también las descartadas: escribe `../salidas/manchas.geojson` según el contrato. En el AMBA da 2.773 manchas, 219 candidatas. Cuando la etapa 4 escriba el suyo, ése lo reemplaza |
| `cruce_manchas.py` | `python cruce_manchas.py [--manchas X --catalogo Y]` | Prompt 3. Cruza las manchas candidatas con los polígonos de `../../data/` y escribe `cruce_manchas_catalogo.parquet` (todos los pares que se tocan, sin filtrar), más `inter_ha`. Criterio revisado en `../idea/criterio-cruce.md` |
| `catalogo_poligonos.py` | se importa | Carga los polígonos de basurales (con complejo y estado) y de negativos (AMBA o mundo) que caen en una caja, como shapely, y los pasa a UTM |
| `extraer_optico.py` | `python extraer_optico.py [--manchas X --salida Y --hilos 24]` | Etapa 5. Sentinel-2 L2A (Planetary Computer, sin cuenta) por mancha y por polígono del catálogo, adentro y contra el anillo: escribe `tabla_optico.parquet` y `tabla_optico_catalogo.parquet`. Lee sólo ventanas de los COG, en paralelo con hilos (3 min en el AMBA). Necesita red. Resultados en `../idea/optico-amba.md` |
| `tabla_radar_provisional.py` | `python tabla_radar_provisional.py` | Tabla de radar **provisional** del AMBA, sacada del índice resumido, para probar el modelo antes de la etapa 4. Escribe en `../datos/amba_provisional/` (no se sube) y deja vacías las columnas que necesitan la serie par a par |
| `armar_tabla.py` | `python armar_tabla.py [--datos X --salida Y]` | Etapa 6. Junta radar, óptico y cruce, etiqueta (`basural_activo` / `otro_movil`, un complejo una vez) y arma las particiones por frame (Argentina a `prueba_final`). Escribe `tabla_entrenamiento.parquet` y `particiones.json` |
| `entrenar.py` | `python entrenar.py [--datos X --predecir]` | Etapa 7. LightGBM binario en CPU, peso por clase, validación cruzada por frame: AUC, precisión y recall por frame con intervalos, errores por clase de negativo e importancia. Escribe `modelo.txt`, `metricas.json` y, con `--predecir`, `predicciones.parquet`. `--humo` permite un solo frame (no reportar) |
| `tests/test_modelo.py` | `python -m pytest tests -q` | Vectorizado, cruce, reglas de etiquetado, índices ópticos, máscaras del anillo y el flujo de punta a punta con el mock. No usan la red |

## A frame other than the AMBA
A **frame** is a working area: a box, the EPSG of its grid and the NISAR orbits that cover it. It comes from `../data/catalogos/frames.json` (stage 2 in `../docs/model.md`) or from `--caja`.
```bash
python pipeline_insomnio.py todo --frame DELHI --remoto        # search, process by URL and index, without downloading the .h5 files
```
```bash
python pipeline_insomnio.py todo --frame todos --remoto        # all those in frames.json, in priority order
```
```bash
python pipeline_insomnio.py todo --frame PRUEBA --caja -118.75 33.85 -117.75 34.50 --orbitas 34 --remoto
```
- **Where it writes:** each frame that isn't the AMBA goes to `../data/salidas/<FRAME>/` (`frame.json`, `lista_productos.json`, `recortes_80m/`, `indice_80m.npz`, `resumen_80m.json`, the figure) and caches its fixed sources in `fijos/<FRAME>/`. The crops and the `.npz` aren't committed. The AMBA keeps writing to plain `../data/salidas/`.
- **`--caja`** goes in GeoJSON and `frames.json` order: `lon_west lat_south lon_east lat_north`. **Watch out:** `geo.CAJA` and `Frame.caja` use another order (`lat_north, lon_west, lat_south, lon_east`).
- **The UTM zone comes from the product:** `procesar` reads the `projection` dataset of each GUNW and GCOV. With `--caja` and no `--epsg`, the grid takes the first GUNW's. If an orbit comes in a different zone than the grid, it's reprojected by nearest neighbor.
- **Two NISAR frames of the same orbit:** if the box crosses two, `buscar` keeps both and `indice` joins them per pair.
- **Period and orbits:** `--desde`, `--hasta` and `--orbitas`. By default they're the frame's (AMBA: orbits 10 and 161, from 25/06 to 12/10/2026). Only `PR` products are used.
- **`frames_nisar`:** if `frames.json` says which NISAR frames cover the box (for example `034_A_019`), `buscar` uses only those.
- **Cross-polarized echo:** each GCOV gives two crops, the HH one (`gcov_*`) and the HV one (`gcovhv_*`), for the stage 4 HV/HH ratio.
- **Without or with downloading:** `--remoto` reads by URL only the frame's window. It uses about 0.8 GB of memory per process: with `--procesos 6` that's about 5 GB. Without `--remoto`, `todo --borrar` downloads, crops and deletes each `.h5`, frame by frame, so the disk doesn't fill up.
- **The ring:** each site's excludes water and all the frame's catalog polygons (`fijos/<FRAME>/catalogo.json`). `--sin-catalogos` leaves it as before, for comparison.
- **Sites with a record:** today `sitios_registro.json` only has AMBA sites. In another frame `indice` gives the layers and the blobs, and marks as `relleno_osm` those that overlap a catalog dump site. The insomnia of each catalog polygon is computed by `insomnio_catalogo.py` (stage 4).
- **Tested** with a Los Angeles box (northern hemisphere, EPSG 32611): see `../docs/insomnia-index.md`.

## Reproducing the index without the VM
The per-pair crops (35 `.npz` per layer) are in `gs://basurales-514714-salidas/salidas-v3.tgz` (1.1 GB, project `basurales-514714`). Extract `recortes_80m/` and `recortes_20m/` into `../data/salidas/` (`.gitignore` excludes them) and run `python pipeline_insomnio.py indice`. Neither the `.h5` files nor Earthdata credentials are needed.

Notes:
- **`procesar --remoto`** reads by URL only the needed window, without downloading the 2.2 GB: a site with its ring is a few MB per pair, and the 80 m coherence of a whole frame, a few tens of MB. It needs `buscar` first and Earthdata credentials. If it turns out too slow (opening HDF5 remotely makes many small reads), plan B is `bajar` + `procesar`.
- The GUNW structure is `science/LSAR/GUNW/grids/frequencyA/{unwrappedInterferogram (80 m), wrappedInterferogram (20 m)}/HH/coherenceMagnitude`, in the UTM zone of the NISAR frame: UTM 21S (EPSG 32721) for the AMBA, UTM 11N (EPSG 32611) for Los Angeles. The EPSG is in the `projection` dataset of the same group (its value and the `epsg_code` attribute).
- The lat/lon to UTM conversion is hand-written to avoid depending on pyproj (`geo.py`). It's checked with the Obelisco and, against pyproj, with 500 points in each of 8 zones of both hemispheres (maximum difference: 2 mm).
- **In cloud containers**, `--remoto` needs `env -u FSSPEC_GCS python pipeline_insomnio.py ...`: that environment variable breaks fsspec's HTTPS opening.
- The final index sites are in `sitios_registro.json`. `coherencia_gunw.py`, `manchas.py` and `predios.py` are the first-hour tests, with the coordinates as constants.

## License and AI use
Code: Apache 2.0. The final index (`insomnio.py`, `geo.py`, `fuentes_fijas.py`, `pipeline_insomnio.py`, `manchas.py` and the tests) was written with AI assistance (Claude); it has to be declared in the "Use of AI" field of the submission.
