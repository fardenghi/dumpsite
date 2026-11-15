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
| `pipeline_insomnio.py` | `python pipeline_insomnio.py indice` | **The full pipeline, for any frame** (without `--frame`, the AMBA). `buscar` lists the GUNWs and GCOVs that cross the box using the ASF API; `bajar` downloads them with earthaccess; `procesar` crops coherence and backscatter to the frame's common grid (needs `h5py`). **`indice` computes the final version of the index** with the crops already made: it takes 14 s at 80 m and writes `../data/salidas/` and, for the AMBA, the data in `../web/`. `calibrar` sweeps the thresholds (AMBA only). `todo` runs from scratch, meant for the VM (`infra/README.md`). Results: `../docs/insomnia-index.md` |
| `insomnio.py` | imported | The index computation, without reading or writing: water mask, separation factor, surroundings, fraction per orbit, persistence, blobs and per-site record with a verdict. A site's ring excludes water and the catalog polygons (`excluir`). The thresholds are in `Parametros` |
| `geo.py` | imported | Vectorized UTM ↔ lat/lon for any zone and hemisphere (the EPSG comes from the product), the frames (`geo.frame("DELHI")`, `geo.AMBA`), the common grid, polygon rasterization and resampling to Web Mercator for the web. Without parameters, everything is the AMBA in UTM 21S, as before |
| `fuentes_fijas.py` | `python fuentes_fijas.py todo --frame DELHI` (or `agua`, `usos`, `catalogo`, `sitios`) | Builds a frame's fixed sources and caches them in `fijos/<FRAME>/`: JRC Global Surface Water mask, known OSM land uses from Overture Maps, the polygons of the catalogs in `../data/catalogos/` that fall in the frame and the urban and cropland fraction from ESA WorldCover (`cobertura`). `indice` and `extraer_manchas.py` build them on their own if they're missing. The AMBA ones are loose in `fijos/`, are committed and are the reference ones (land uses from Nominatim): with them `indice` needs no network. The other frames' aren't committed. Needs `tifffile` and `imagecodecs` for `agua` and `cobertura`, and `duckdb` for `usos` |
| `extraer_manchas.py` | `python extraer_manchas.py --frame LOS_ANGELES` and then `python extraer_manchas.py juntar` | **Stage 4.** With a frame's crops: builds the blobs and writes them as polygons (`manchas.geojson`), measures each candidate against its ring (`tabla_radar.parquet`: movement, echo, HV/HH, shape and context) and measures the insomnia of each catalog polygon (`insomnio_catalogo.parquet`). Each frame goes to `../data/salidas/<FRAME>/` and `juntar` builds the three contract files in `../data/salidas/`. Format: `../docs/data-contracts.md` |
| `sitios_registro.json` | edited by hand | The sites with a record: OSM object or box, registry, closure date and sources. `rol` says which were used for calibration and which are controls |
| `tests/test_insomnio.py` | `python -m pytest tests -q` | Synthetic case: quiet city, awake dump site, water, unmasked gravel pit, seasonal field, road and a site that's too small |
| `resumen_etapa4.py` | `python resumen_etapa4.py` | The tables of `../docs/results.md` in Markdown, from `../data/salidas/<FRAME>/`: blobs per frame and awake / quiet / can't tell by status, with the frames added by open sites separate from the earlier ones. It computes nothing new |
| `optico_catalogo_frames.py` | `python optico_catalogo_frames.py preparar` and then `correr` | Sentinel-2 optical data for the dump sites of 10 ha or more in the frames that don't have it from prompts 7 or 4. Uses `extraer_optico.py` unmodified. `preparar` builds a small job (polygons to measure and catalog neighbors) so the reading can run on another machine. Writes `../data/salidas/optico_catalogo_frames.parquet` |
| `modelo_estado.py` | `python modelo_estado.py` | **Open-versus-closed model** with the registry labels: radar and optical data per site, validated leaving one frame out, and what it learns (coefficients, importance, area control, AMBA test). Writes `../data/salidas/modelo_estado.json` and `../data/salidas/predicciones_estado.parquet`. Result in `../docs/model.md` |
| `tests/test_extraer_manchas.py` | `python -m pytest tests -q` | The tracing from pixels to polygons (exact area, simple rings, GeoJSON orientation) and stage 4 end to end with a synthetic frame: an awake landfill, a quiet airfield and a site that's too small |
| `tests/test_frames.py` | `python -m pytest tests -q` | The pipeline outside the AMBA, offline: UTM in both hemispheres, grid and masks in the north, the ring that excludes the catalogs, crops across UTM zones and from neighboring NISAR frames, and `procesar` + `indice` end to end with synthetic northern hemisphere products |
| `coherencia_gunw.py` | `python coherencia_gunw.py <GUNW.h5> [output_folder]` | Lists the file's coherence layers, crops around fixed sites (Norte III, Luján, CABA, countryside) and saves a figure with the AMBA overview |
| `manchas.py` | `python manchas.py <GUNW.h5> [--frame X]` | Finds in a GUNW blobs of low coherence relative to their surroundings and lists them with area, coordinates and elongation (compact, elongated or linear). Uses the product's UTM zone; without `--frame` or `--caja` it looks at the AMBA |
| `predios.py` | `python predios.py <GUNW.h5> <output_folder>` | Measures the coherence inside known sites (OSM boxes) against a 1.5 km ring, on the 80 m and 20 m layers, and saves a figure |
| `frames_elegir.py` | `python frames_elegir.py [--cache dir]` | Stage 2. With the public ASF API (`PR` GUNW, no login) it evaluates cities and the cells with the most known-status dump sites, and picks ~10 non-overlapping frames. Writes `../data/catalogos/frames.json`, `datos/frames-elegidos.md` and `../data/salidas/estado_conocido.json` (known-status dump sites per frame). Takes ~1 min. With `--agregar 20` it doesn't choose again: it keeps the existing frames and adds 20 by number of open dump sites (prompt 6) |
| `insomnio_catalogo.py` | `python insomnio_catalogo.py [--modo exacto\|aproximado]` | Stage 4, second direction of the cross: the insomnia over each catalog polygon (dump sites and negatives) of the frame, whether or not it's in a blob. `exacto` uses the per-pair crops and `insomnio.ficha()` (reproduces `fichas_80m.json`); `aproximado`, only `indice_80m.npz`. Writes `../data/salidas/insomnio_catalogo.parquet`. AMBA only for now |
| `veredicto.py` | `python veredicto.py [--carpeta datos/mock]` | Stage 9: joins the cross in both directions and gives the verdict per site (known active, closed but awake, closed and quiet, quiet according to the radar, possible new, discarded, the radar can't tell). Writes `../data/salidas/veredictos.json` with the pitch sentence |
| `evaluar_actividad.py` | `python evaluar_actividad.py [--fuentes epa_lmop curado_manual]` | Stage 8: open-versus-closed matrix by country over the known-status dump sites, with Wilson intervals. Writes `../data/salidas/evaluacion_actividad.json` |
| `flujo.py` | `python flujo.py [--frame LOS_ANGELES AMBA] [--web]` | Stage 9, the full flow: over each `salidas/<FRAME>/insomnio_catalogo.parquet` it runs the verdict (cross from prompt 4 or computed in `datos/flujo/`) and the activity matrix with and without OSM, with the cases to check by hand. Writes `../data/salidas/veredictos.json`, `evaluacion_actividad.json`, `resumen_flujo.json`, `datos/resultados-flujo.md` and, with `--web`, `web/src/data/seed/veredictos.json` |
| `cruce_catalogo.py` | `python cruce_catalogo.py [--indice X.npz] [--min-ha 10]` | Crosses an already computed index with the dump-site (per complex) and negative polygons in `../data/catalogos/`: median insomnia per polygon, per class and AUC. It doesn't need the crops: it uses `../data/salidas/indice_80m.npz`. Results in `../docs/insomnia-index.md` |
| `manchas_vectorizar.py` | `python manchas_vectorizar.py [--indice X.npz --frame F --epsg N]` | Prompt 3. The blobs of an already computed index as polygons (with `insomnio.manchas()`), all of them, including the discarded ones: writes `../data/salidas/manchas.geojson` following the contract. In the AMBA it gives 2,773 blobs, 219 candidates. Once stage 4 writes its own, that one replaces it |
| `cruce_manchas.py` | `python cruce_manchas.py [--manchas X --catalogo Y]` | Prompt 3. Crosses the candidate blobs with the polygons in `../data/catalogos/` and writes `cruce_manchas_catalogo.parquet` (all the pairs that touch, unfiltered), plus `inter_ha`. Criterion reviewed in `../docs/model.md` |
| `catalogo_poligonos.py` | imported | Loads the dump-site polygons (with complex and status) and the negative ones (AMBA or world) that fall in a box, as shapely, and converts them to UTM |
| `extraer_optico.py` | `python extraer_optico.py [--manchas X --salida Y --hilos 24]` | Stage 5. Sentinel-2 L2A (Planetary Computer, no account) per blob and per catalog polygon, inside and against the ring: writes `tabla_optico.parquet` and `tabla_optico_catalogo.parquet`. It reads only COG windows, in parallel with threads (3 min in the AMBA). Needs the network. Results in `../docs/results.md` |
| `tabla_radar_provisional.py` | `python tabla_radar_provisional.py` | **Provisional** AMBA radar table, taken from the summarized index, to test the model before stage 4. Writes to `datos/amba_provisional/` (not committed) and leaves empty the columns that need the pair-by-pair series |
| `armar_tabla.py` | `python armar_tabla.py [--datos X --salida Y]` | Stage 6. Joins radar, optical data and cross, labels (`basural_activo` / `otro_movil`, a complex once) and builds the partitions by frame (Argentina to `prueba_final`). Writes `tabla_entrenamiento.parquet` and `particiones.json` |
| `entrenar.py` | `python entrenar.py [--datos X --predecir]` | Stage 7. Binary LightGBM on CPU, class weights, cross-validation by frame: AUC, precision and recall per frame with intervals, errors per negative class and importance. Writes `modelo.txt`, `metricas.json` and, with `--predecir`, `predicciones.parquet`. `--humo` allows a single frame (don't report) |
| `tests/test_modelo.py` | `python -m pytest tests -q` | Vectorizing, cross, labeling rules, optical indices, ring masks and the flow end to end with the mock. They don't use the network |

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
