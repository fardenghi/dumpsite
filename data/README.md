# data/

All the project's data: the catalogs that go into the engine and what the engine computes. The NISAR `.h5` files (2 GB each), the per-pair crops and each frame's fixed sources aren't committed: the pipeline rebuilds them (see `.gitignore`).

| Folder | What it has | Who writes it |
|---|---|---|
| `catalogos/` | World dump sites, negatives (what the radar confuses with a dump site), their geometries, the complexes and `frames.json` | `motor/curar_basurales.py`, `negativos_*.py`, `geometrias_*.py`, `complejos_agrupar.py`, `frames_elegir.py` |
| `salidas/` | Insomnia index, candidate blobs, cross with the catalogs, optical data, model and verdicts, for 37 frames | The `motor/` pipeline (details below) |

All heavy files are in plain git (no LFS). The largest is `catalogos/basurales/basurales_mundo.json`, at 57 MB.

## catalogos/frames.json
The 37 NISAR frames where the pipeline ran: box, grid EPSG, orbits and why each one was chosen (10 chosen first, 20 more by number of open dump sites and 7 in Argentina outside the AMBA, prediction only). Built by `motor/frames_elegir.py` (`--agregar` for the 20) and `motor/frames_argentina.py` (the 7 Argentine ones) with the public ASF API.

## catalogos/basurales/
Catalog of dump sites and landfills around the world, built on 14/11/2026 by `motor/curar_basurales.py`. The goal is to find sites that are **closed in theory but still active in practice**.

| File | What it has |
|---|---|
| `basurales_mundo.json` (57 MB) | 66,981 sites: 1,225 open, 3,579 closed, 31 contradictory and 62,146 with unknown status. 64,492 have an area |
| `basurales_cerrados.json` | Only the closed or disputed ones, sorted by `puntaje_sospecha` |
| `argentina_sitios.csv` | One row per Argentine site (393 from the catalog plus 4 found during the work), with category, province and sources. Built by `motor/conteo_argentina.py`; summary in [`../docs/argentina.md`](../docs/argentina.md) |
| `casos_curados_argentina.json` | 7 Buenos Aires cases curated by hand (Luján, Norte III, González Catán, Ensenada, San Pedro, Navarro, Nueve de Julio) with notes and documents, plus the related Argentine inventories |

### Structure
Each file has `meta` (sources with license and citation, criteria, warnings and counts) and `sitios`. Each site carries:
- `id`, `nombre`, `pais`, `lat`, `lon`, `tipo`
- `estado`: `abierto`, `cerrado`, `contradictorio` or `desconocido`, plus `estados_por_fuente` with the reason each source gives
- `fecha_apertura`, `fecha_cierre`
- `area_m2`, `area_ha` and `area_origen`, which says which source the area comes from
- `operador`, `residuos`, `emisiones_climate_trace`
- `plumas_metano_emit` and `ultima_pluma_emit`
- `senales_cerrado_pero_activo`, with the type, detail and weight of each signal, and `puntaje_sospecha`
- `fuentes`: each original record with its `fuente`, `id_fuente`, `url` and data, plus the EMIT plumes with their granule and date

### Sources (cite all of them)
| Key | Source | License |
|---|---|---|
| `osm` / `overture` | OpenStreetMap, with the polygons taken from Overture Maps release 2026-10-21.0 (`base/land_use`, `class=landfill`) | ODbL 1.0, © OpenStreetMap contributors |
| `climate_trace` | Climate TRACE, solid-waste-disposal subsector, API v6 | CC BY 4.0 |
| `epa_lmop` | U.S. EPA LMOP Landfill and Project Database (2024-09) | Public domain |
| `nasa_emit` | NASA EMIT L2B CH4PLM v002, doi:10.5067/EMIT/EMITL2BCH4PLM.002 | No restrictions |
| `curado_manual` | Notes and documents cited in each case | That of each source |

### Warnings
- OSM almost never says whether a dump site is active, so most end up as `desconocido`.
- Methane doesn't prove activity: a closed landfill emits for decades.
- The signals are for prioritizing what to look at with NISAR. They're not accusations: say "signal compatible with activity".
- Sites that are only in OSM don't carry a country.

### Regenerate
Download the sources to a folder (Overture with DuckDB, Climate TRACE through its API, the LMOP `.xlsx` and the EMIT metadata through CMR) and run:
```bash
cd motor
python curar_basurales.py <dir_descargas> ../data/catalogos/basurales
```

## catalogos/negativos/
Catalog of **confusers**: what the radar can confuse with a dump site. It's used to train the model with negative cases. It follows the list and rules in `docs/data.md` and is built by `negativos_extraer.py` and `negativos_curar.py` (in `motor/`).

| File | What it has |
|---|---|
| `negativos_mundo.json` (46 MB) | 64,986 polygons of 24 classes, in areas near dump sites with known status. The sample is balanced by class and by 1° cell |
| `negativos_amba.json` | 1,259 AMBA polygons, up to 150 per class |

### How it was built
- **Source:** Overture Maps release 2026-10-21.0, with the `land_use`, `land`, `water` and `infrastructure` layers. It's OSM data under the ODbL license. That gave 4.26 million candidate polygons.
- **Size:** between 2 and 500 ha. Anything larger goes as a mask.
- **Area:** 0.25° cells neighboring a dump site with known or curated status. It approximates "the same NISAR frames as the positives".
- **Distance:** more than 500 m, edge to edge, from any site in the dump-site catalog.
- **Quota:** per class and per 1° cell, A = 6, B = 3 and C = 2. The order is reproducible because it uses the hash of the id.

### Structure of each record
- Identification: `id`, `clase`, `grupo`, `prioridad` (A, B or C) and `rol` (`negativo` or `mascara`).
- Location and size: `nombre`, `pais` (inferred from the nearest dump site), `lat`, `lon`, `area_ha` and `bbox`.
- Polygon: `poligono`, with the Overture id and the OSM id.
- `frame_nisar`: empty until the frames are downloaded.
- Origin: `fuente`, `id_fuente`, `url` (the OSM object), `licencia` and `confianza` (high, medium or low).
- Context: `basural_mas_cercano`, `etiquetas_osm` and `notas`.

`meta` holds the counts per class and the **pending classes**, the ones that don't come from OSM: roads (they're lines and go as a mask), large water bodies, burning and logging (NASA FIRMS), settlements (GHSL), shifting riverbeds (JRC) and areas the radar can't see well because of the geometry (GUNW mask plus a DEM).

### Warnings
- **Country bias:** 53 % is in the US, because that's where most positives with known status are (the EPA). Training needs rebalancing by country or by frame.
- **Low confidence:** `feedlot` comes from `landuse=farmyard`, which isn't always a feedlot. Same with grain storage. They need review before use.
- OSM can be outdated: a finished construction site may still be tagged as construction.
- Validation has to be split by city or by frame, not by site.

## Geometries
The polygons go in separate files. Each feature links to its catalog by `id`. They're built by `geometrias_extraer.py` and `geometrias_armar.py`.

| File | Sites | With polygon | Format |
|---|---|---|---|
| `catalogos/basurales/geometrias.geojson` (30 MB) | 66,981 | 57,068 | GeoJSON |
| `catalogos/negativos/geometrias_mundo.parquet` (34 MB) | 64,986 | 64,986 | GeoParquet (over 50 MB as GeoJSON) |
| `catalogos/negativos/geometrias_amba.geojson` (1 MB) | 1,259 | 1,259 | GeoJSON |

- **Source:** Overture Maps 2026-10-21.0 (OSM, ODbL 1.0, © OpenStreetMap contributors). It's in WGS84 (lon/lat), not reprojected.
- **Simplification:** `ST_SimplifyPreserveTopology` with 0.0001° (about 10 m), less than a NISAR pixel. The area changes 0.8 % at the median relative to the catalog's `area_ha`, which was computed with the original polygon.
- **Points:** the 9,913 dump sites without a polygon go as points with `geometria = "punto"`. They're the ones that come only from the EPA or Climate TRACE, and the closed OSM ones that Overture doesn't carry. Among the closed ones, 1,925 have a polygon and 1,654 a point.
- **Reading:** the GeoParquet opens with GeoPandas (`geopandas.read_parquet`), DuckDB or QGIS. The GeoJSONs open with any tool.
- **Review of 14/11:**
  - In 7,595 dump sites the polygon is more than 20 % smaller than the catalog's `area_ha`. **Almost all of them are sites under 5 ha** (most under 1 ha), where the ~10 m simplification weighs a lot. **For sites of 5 ha or more, the ones used with the radar, there are no mismatches.**
  - Of the 614 sites made of several OSM objects, only 33 (7 of 5 ha or more) ended up with a partial outline, because `geometrias_armar.py` kept the first object. **The script now merges all the objects of each site** (`ST_Union_Agg`), but it has to be rerun: the raw files (`geom_parts/`) aren't in the repo.

## Complexes
`catalogos/basurales/complejos.json` (14 MB) groups into **complexes** the catalog dump sites that are less than 1 km apart, for example the three Norte III entries. It's built by `motor/complejos_agrupar.py` from `geometrias.geojson`, in about 15 seconds.
- **Why:** so each complex counts once and falls whole in the same validation partition. When extracting variables, the control ring excludes all the catalog polygons.
- **Complex status:** `abierto` if some entry is open and none closed; `cerrado` the other way around; `contradictorio` if there are both; `desconocido` if none has a status.
- **Content:** `complejo_por_sitio` (site id → complex id) and `complejos` (sites, status, statuses per site, summed area, center and names).
- **Counts:** 59,538 complexes; 3,690 have several sites (11,133 sites in total). Statuses: 1,212 open, 3,293 closed, 42 contradictory and 54,991 unknown.
- **Limitation:** polygons under 1 ha don't join others. Some cities have hundreds of mapped micro dumps that, chained at less than 1 km, built "complexes" of 10 to 18 km. A long chain between larger sites can still remain: the largest complex has 75 sites (mining spoil heaps in Germany).
- **Watch the names:** site `BAS-061528`, "Ensenada", is Ensenada, Baja California (Mexico), not the one in Buenos Aires (`BAS-053303`).

## salidas/
What the engine computes. Each file says in `generado_por` which script wrote it. It's regenerated by running that script from `motor/` (see `motor/README.md`).

### Per frame: `salidas/<FRAME>/`
One folder for each of the 37 frames (the AMBA, Los Angeles, Mexico City, Delhi, Jakarta, Ponce, 24 US counties and 7 Argentine zones outside the AMBA). `salidas/poc_sitios/` holds the site-level proof of concept of `motor/poc_sitios.py`.

| File | What it has | Script |
|---|---|---|
| `frame.json`, `lista_productos.json` | The frame's grid and the NISAR GUNW and GCOV products that cross it | `pipeline_insomnio.py buscar` |
| `manchas.geojson` | Candidate blobs as polygons, with their insomnia | `extraer_manchas.py --frame <FRAME>` |
| `tabla_radar.parquet` | Radar variables of each blob against its ring | `extraer_manchas.py` |
| `insomnio_catalogo.parquet` | Insomnia of each catalog polygon that falls in the frame | `extraer_manchas.py` |
| `cruce_manchas_catalogo.parquet` | Which blobs touch which catalog polygons | `modelo_por_frame.py` |
| `tabla_optico.parquet`, `tabla_optico_catalogo.parquet` | Sentinel-2 variables of the blobs and the polygons (only the first 10 frames) | `modelo_por_frame.py` (uses `extraer_optico.py`) |
| `modelo_por_frame.json` | Summary of the frame's cross and optical step | `modelo_por_frame.py` |

### All frames together
| File | What it has | Script |
|---|---|---|
| `manchas.geojson`, `tabla_radar.parquet`, `insomnio_catalogo.parquet` | Each frame's data, joined | `extraer_manchas.py juntar` |
| `cruce_manchas_catalogo.parquet`, `tabla_optico*.parquet` | Cross and optical data for all frames | `modelo_por_frame.py` |
| `veredictos.json` | One verdict per catalog polygon and per blob without a catalog (what the web shows) | `flujo.py` |
| `evaluacion_actividad.json` | Open-versus-closed matrix by country, with Wilson intervals | `flujo.py` |
| `resumen_flujo.json` | Flow counts per frame and in total | `flujo.py` |
| `estado_conocido.json` | Dump sites with known status (open or closed according to the registry) per frame | `frames_elegir.py` |

### AMBA insomnia index
| File | What it has | Script |
|---|---|---|
| `indice_80m.npz`, `indice_80m.png`, `indice_20m.png` | The AMBA insomnia index at 80 m (and the 20 m figure) | `pipeline_insomnio.py indice` |
| `resumen_80m.json`, `resumen_20m.json`, `lista_productos.json` | Pairs used, parameters and counts | `pipeline_insomnio.py` |
| `fichas_80m.json`, `fichas_20m.json`, `calibracion_80m.json` | Record of each site with a registry entry and the threshold calibration | `pipeline_insomnio.py indice` and `calibrar` |

### Model
| File | What it has | Script |
|---|---|---|
| `tabla_entrenamiento.parquet`, `particiones.json` | Table of labeled blobs and partitions by frame | `armar_tabla.py` |
| `metricas.json`, `modelo.txt`, `predicciones.parquet` | Per-blob LightGBM model, its metrics and predictions (**not validated**) | `entrenar.py` |
| `metricas_variantes.json` | Model variants with the optical labels | `modelo_por_frame.py variantes` |
| `etiquetas_optico_ia.json` | Activity labels for 89 sites assigned by AI looking at Sentinel-2, blind. No person reviewed them | By hand, see `docs/model.md` |
| `optico_estado_conocido.parquet`, `optico_estado_conocido/`, `optico_estado_conocido_resumen.json` | Optical data for the 1,008 known-status dump sites (in 3 parts) | `optico_estado_conocido.py` |
| `optico_catalogo_frames.parquet` | Optical data for the dump sites of 10 ha or more in the new frames | `optico_catalogo_frames.py` |
| `radar_frente.parquet`, `radar_frente_evaluacion.json` | Active-front radar variables of each dump site and their evaluation | `radar_frente.py` |
| `modelo_estado.json`, `predicciones_estado.parquet` | Open-versus-closed model with the registry labels | `modelo_estado.py` |
| `prueba_resolucion.json` | Test of the front model at 20 m versus 80 m | `prueba_resolucion.py` |

### Sources of the outputs
- **NISAR** L2 GUNW and GCOV (NASA/ISRO), via ASF DAAC.
- **Sentinel-2** L2A (Copernicus, ESA), via Microsoft Planetary Computer.
- **JRC Global Surface Water** v1.4 (water) and **ESA WorldCover** 2021 v200 (land cover, CC BY 4.0).
- The catalogs in `catalogos/`, with the sources and licenses above.
