# Model data contracts (14/11/2026)

The format of the model's intermediate files, so the stages in `modelo.md` can be written in parallel without waiting for each other. Each stage writes its files and reads the others' **in this format and no other**.

- **In code:** `motor/contratos.py` has the same columns as constants and the `validar()` function. If this document and the code disagree, the code wins (and there's a test that warns).
- **Test data:** `python motor/contratos_mock.py` generates all the files in `motor/datos/mock/`, with made-up values.
- **None of this was computed with real data.** The mock values aren't results: they're not quoted and they don't go to the web.

## How to use it
```python
import contratos                                        # from motor/

contratos.validar(df, "tabla_radar")                    # fails with ErrorContrato and says everything that's wrong
contratos.guardar(df, "tabla_radar", "../data/salidas") # validates, orders the columns and writes the parquet
df = contratos.leer("datos/mock", "tabla_radar")        # reads and validates (also manchas, frames and particiones)
contratos.COLUMNAS_MODELO                               # the model's 29 variables, in order
```
```bash
python motor/contratos_mock.py                         # generates motor/datos/mock/
python motor/contratos.py motor/datos/mock             # validates everything in a folder
python motor/contratos.py data/salidas/tabla_radar.parquet
```
It needs `pandas` and `pyarrow` (they're in `motor/requirements.txt`).

## Common rules
- **Paths:** relative to `data/`, the data folder at the repo root. `salidas/` holds what the engine writes and `catalogos/` the catalogs.
- **Columns can be added. The contract's can't be removed or renamed.** The ones marked *optional* may be missing; if present, they're validated.
- **Tables:** parquet, written with `contratos.guardar()` (pandas and pyarrow), without an index. Texts are text, numbers `float64` and integers `int64` (or `Int64` if there may be empty values).
- **Empty values:** a column may only come empty (null or NaN) if the table says "yes" under *Empty?*. Empty means "couldn't be measured", never zero.
- **Coordinates:** degrees, WGS84, in GeoJSON order: **(lon, lat)**. Boxes go as `[lon_oeste, lat_sur, lon_este, lat_norte]` (west, south, east, north). **Watch out:** `geo.CAJA` uses another order (`lat_norte, lon_oeste, lat_sur, lon_este`).
- **Dates:** text `YYYY-MM-DD`.
- **`frame`:** the key in `frames.json`, uppercase, with letters, digits and underscores (`AMBA`, `DELHI`, `LOS_ANGELES`). A frame is a working area; it can join more than one NISAR orbit, like the AMBA (orbits 10 and 161).
- **`id_mancha`:** `MAN-<frame>-<n>`, with `n` as four digits from 1, in the order of `insomnio.manchas()` (largest area first). Example: `MAN-AMBA-0001`. Built by `contratos.id_mancha(frame, n)`. The number also counts the discarded blobs.
- **`id_catalogo`:** the polygon's `id` in the catalogs, as is: `BAS-…` for `data/catalogos/basurales/` and `NEG-…` for `data/catalogos/negativos/`. They're **not** the ids in `fichas_80m.json` (`norte-iii`) or in `casos_curados_argentina.json` (`AR-LUJAN`).
- **Ring:** 1.5 km around the blob or polygon, without water and without the other catalog polygons (`insomnio.anillo`, stage 1).
- **Minimum size:** 10 ha. Anything smaller comes out as `no_alcanza`.
- **Heavy files aren't committed:** a parquet of more than a few MB goes to `datos/`.
- **Wording:** "signal compatible with activity" and "quiet according to the radar". Never "illegal dump".

## Summary
| File | Written by | Read by | One row per |
|---|---|---|---|
| `salidas/manchas.geojson` | stage 4 (in the AMBA, prompt 3) | stages 5, 6 and 9, and the web | a blob of a frame, including the discarded ones |
| `salidas/tabla_radar.parquet` | stage 4 | stage 6 | a candidate (not discarded) blob of a frame |
| `salidas/insomnio_catalogo.parquet` | stage 4 (the logic, prompt 2) | stages 8 and 9 | a catalog polygon (dump site or negative) in a frame, whether or not it's in a blob |
| `salidas/tabla_optico.parquet` | stage 5 | stage 6 | a candidate blob of a frame |
| `salidas/tabla_optico_catalogo.parquet` | stage 5 | stages 8 and 9 (site card) | a catalog polygon in a frame |
| `salidas/cruce_manchas_catalogo.parquet` | stage 6 (`cruce_manchas.py`) | stages 6 and 9 | a pair of blob and catalog polygon that touch (intersection > 0), not filtered by the 30 % |
| `catalogos/frames.json` | stage 2 | stages 1, 4, 6, 7, 8 and 9 | a frame (a working area covered by one or more NISAR orbits) |
| `salidas/particiones.json` | stage 6 (`armar_tabla.py`) | stage 7 and the CNN | it's not a table: which frames go in each partition |
| `salidas/tabla_entrenamiento.parquet` | stage 6 (`armar_tabla.py`) | stage 7 and the CNN | a labeled blob of a frame |
| `salidas/predicciones.parquet` | stage 7 (or the mock, while there's no model) | stage 9 (`veredicto.py`) | a candidate blob of a frame |

The mock also writes `catalogo_mock.geojson`, which isn't a contract: it's the made-up catalog polygons the mock blobs are crossed against.

---

## 1. `salidas/manchas.geojson`
- **Written by:** stage 4, frame by frame. For the AMBA it's built by prompt 3, from `salidas/indice_80m.npz` with `insomnio.manchas()`.
- **Read by:** stage 5 (optical), stage 6 (cross with the catalog), stage 9 and the web.
- **One row per blob and frame** because the blob is the model's unit: it trains and predicts on blobs, not on catalog polygons.
- **Format:** a GeoJSON `FeatureCollection`. Each feature is a `Polygon` or `MultiPolygon` in degrees (lon, lat). The properties are the columns below.
- **All the blobs are there, including the discarded ones** (`descartada` gives the reason). The candidates are the ones with `descartada` null.
- **Blobs only.** Catalog polygons don't go here: their optical data goes in `tabla_optico_catalogo.parquet`.

| Column | Type | Unit | Empty? | What it is |
|---|---|---|---|---|
| `id_mancha` | text | — | no | Blob identifier: `MAN-<frame>-<n>` |
| `frame` | text | — | no | Frame key, the one in `frames.json` (for example `AMBA`) |
| `ha` | number | ha | no | Blob area |
| `forma` | text | — | no | Shape according to `insomnio.manchas()`. Values: `compacta`, `alargada`, `lineal` |
| `descartada` | text | — | yes | Reason for discarding, or null if it's a candidate. Values: `chica`, `lineal`, `lisa` |
| `etiqueta` | integer | — | no | Blob number in the index's `manchas` layer |
| `insomnio` | number | fraction 0-1 | yes | Mean per-pixel insomnia over the blob |
| `persistencia` | number | fraction 0-1 | yes | Mean per-pixel persistence |
| `eco_db` | number | dB | yes | Mean echo of the blob |
| `elongacion` | number | ratio ≥ 1 | no | Major axis / minor axis |
| `nucleo` | number | fraction 0-1 | no | Part of the blob that survives a 1-pixel erosion |
| `lat` | number | degrees | no | *Optional.* Latitude of the center |
| `lon` | number | degrees | no | *Optional.* Longitude of the center |

**Key** (not repeated): `id_mancha`.

`insomnio`, `persistencia`, `eco_db`, `elongacion`, `nucleo`, `forma`, `descartada` and `etiqueta` are the summaries `insomnio.manchas()` returns, unchanged. The allowed values of `descartada`: `chica` (under 10 ha), `lineal` (road or stream) and `lisa` (mean echo below −13 dB).

## 2. `salidas/tabla_radar.parquet`
- **Written by:** stage 4 (`extraer_manchas.py`, on the VM).
- **Read by:** stage 6 (`armar_tabla.py`).
- **One row per candidate blob and frame.** Discarded ones aren't included. Everything is measured **blob against ring**.
- They're the Movement, Roughness, Shape and Context columns of section 4 of the plan.

| Column | Type | Unit | Empty? | What it is |
|---|---|---|---|---|
| `id_mancha` | text | — | no | Blob identifier: `MAN-<frame>-<n>` |
| `frame` | text | — | no | Frame key, the one in `frames.json` (for example `AMBA`) |
| `insomnio` | number | fraction 0-1 | no | Fraction of pairs with coherence < 0.80 × the ring's, averaging orbits |
| `persistencia` | number | fraction 0-1 | no | Minimum of the awake fraction across the three segments of the series |
| `contraste_mediana` | number | ratio | yes | Blob coherence / ring coherence: median across pairs |
| `contraste_desvio` | number | ratio | yes | Standard deviation of that ratio across pairs |
| `coherencia_media` | number | coherence 0-1 | yes | Mean absolute coherence, normalized to 12 days |
| `tendencia` | number | coherence per day | yes | Slope of the normalized coherence over time |
| `n_pares` | integer | pairs | no | Valid GUNW pairs over the blob |
| `n_orbitas` | integer | orbits | no | Orbits with enough pairs |
| `eco_db` | number | dB | yes | Mean echo (HH backscatter, gamma0) of the blob |
| `eco_contraste` | number | dB | yes | Blob echo minus ring echo |
| `eco_variacion` | number | dB | yes | Standard deviation of the mean echo across dates |
| `hv_hh` | number | dB | yes | Polarization ratio: HV echo minus HH echo |
| `area_ha` | number | ha | no | Blob area (same as `ha` in `manchas.geojson`) |
| `elongacion` | number | ratio ≥ 1 | no | Major axis / minor axis (the one from `insomnio.manchas()`) |
| `compacidad` | number | 0-1 | yes | 4π × area / perimeter²: 1 is a circle |
| `agua_anillo` | number | fraction 0-1 | yes | Part of the 1.5 km ring that is water (JRC) |
| `urbano_anillo` | number | fraction 0-1 | yes | Part of the ring that is urban (ESA WorldCover, class 50) |
| `cultivo_anillo` | number | fraction 0-1 | yes | Part of the ring that is cropland (ESA WorldCover, class 40) |

**Key** (not repeated): `id_mancha`.

## 3. `salidas/insomnio_catalogo.parquet`
- **Written by:** stage 4. The logic is `insomnio_catalogo.py` (prompt 2).
- **Read by:** stage 8 (activity evaluation) and stage 9 (verdict).
- **One row per catalog polygon and frame, whether or not it's in a blob.** It's the second direction of the cross: without it you can't say "closed and quiet" about a dump site that formed no blob, like Luján.
- Dump sites and negatives whose polygon falls in the frame are included. Those under 10 ha are included too, with `radar` = `no_alcanza`.
- `radar` uses the thresholds of `insomnio.Parametros`: `despierto` (insomnia ≥ 0.70 and persistence ≥ 0.50), `quieto` (insomnia ≤ 0.20 with coherent surroundings) and `no_alcanza` (everything else).
- Reference in the AMBA (`salidas/fichas_80m.json`): Norte III 0.86 awake, González Catán 1.00 awake and Luján 0.00 quiet.

| Column | Type | Unit | Empty? | What it is |
|---|---|---|---|---|
| `id_catalogo` | text | — | no | Polygon `id` in `data/catalogos/basurales/` (`BAS-…`) or `data/catalogos/negativos/` (`NEG-…`) |
| `catalogo` | text | — | no | Which catalog the polygon comes from. Values: `basurales`, `negativos` |
| `complejo` | text | — | yes | `CPX-…` from `complejos.json` for dump sites; null for negatives |
| `frame` | text | — | no | Frame key, the one in `frames.json` (for example `AMBA`) |
| `insomnio` | number | fraction 0-1 | yes | Insomnia of the polygon against its ring, like `insomnio.ficha()` |
| `persistencia` | number | fraction 0-1 | yes | Minimum of the awake fraction across the three segments |
| `eco_db` | number | dB | yes | Median echo over the polygon |
| `n_pares` | integer | pairs | no | Valid GUNW pairs over the polygon |
| `radar` | text | — | no | What the radar says, with the thresholds of `insomnio.Parametros`. Values: `despierto`, `quieto`, `no_alcanza` |
| `motivo` | text | — | yes | *Optional.* Why that `radar` came out |
| `area_ha` | number | ha | yes | *Optional.* Polygon area according to the catalog |
| `estado` | text | — | yes | *Optional.* Registry status (dump sites only). Values: `abierto`, `cerrado`, `contradictorio`, `desconocido` |
| `clase` | text | — | yes | *Optional.* Negative class (`aeropuerto`, `cantera`…); null for dump sites |

**Key** (not repeated): `id_catalogo`, `frame`.

## 4. `salidas/tabla_optico.parquet`
- **Written by:** stage 5 (`extraer_optico.py`).
- **Read by:** stage 6.
- **One row per candidate blob and frame.** It's joined with `tabla_radar` by `id_mancha`.
- **Source:** Sentinel-2 L2A (Copernicus), 6 to 8 low-cloud scenes in the NISAR period, with clouds masked using the SCL layer. Reflectances go from 0 to 1, with the product offset already applied.
- **Indices:** NDVI = (B08 − B04) / (B08 + B04); NDWI = (B03 − B08) / (B03 + B08); BSI = ((B11 + B04) − (B08 + B02)) / ((B11 + B04) + (B08 + B02)).
- "Mean" is the mean across dates of the mean value inside. "Contrast" is that value minus the ring's. If there was no useful scene, `n_escenas` is 0 and the rest is empty.

| Column | Type | Unit | Empty? | What it is |
|---|---|---|---|---|
| `id_mancha` | text | — | no | Blob identifier: `MAN-<frame>-<n>` |
| `frame` | text | — | no | Frame key, the one in `frames.json` (for example `AMBA`) |
| `ndvi_media` | number | index −1 to 1 | yes | NDVI inside, mean across dates |
| `ndvi_variacion` | number | index | yes | Standard deviation of the inside NDVI across dates |
| `bsi_media` | number | index −1 to 1 | yes | Bare soil (BSI) inside, mean across dates |
| `ndwi_media` | number | index −1 to 1 | yes | NDWI (water) inside, mean across dates |
| `swir_b11` | number | reflectance 0-1 | yes | Band B11 (1.6 µm) inside, mean across dates |
| `swir_b12` | number | reflectance 0-1 | yes | Band B12 (2.2 µm) inside, mean across dates |
| `ndvi_contraste` | number | index | yes | `ndvi_media` minus the ring NDVI |
| `bsi_contraste` | number | index | yes | `bsi_media` minus the ring BSI |
| `ndwi_contraste` | number | index | yes | `ndwi_media` minus the ring NDWI |
| `swir_b11_contraste` | number | reflectance | yes | `swir_b11` minus the ring B11 |
| `swir_b12_contraste` | number | reflectance | yes | `swir_b12` minus the ring B12 |
| `n_escenas` | integer | scenes | no | Sentinel-2 scenes used |
| `fechas` | text | YYYY-MM-DD | yes | Dates of those scenes, comma-separated and in order |

**Key** (not repeated): `id_mancha`.

## 5. `salidas/tabla_optico_catalogo.parquet`
- **Written by:** stage 5, with the same script.
- **Read by:** stages 8 and 9, for each site's card.
- **One row per catalog polygon and frame.** Same optical columns, but the key is `id_catalogo` instead of `id_mancha`.
- It exists so catalog polygons don't get mixed with blobs in `tabla_optico.parquet`. **It doesn't go into training.**

| Column | Type | Unit | Empty? | What it is |
|---|---|---|---|---|
| `id_catalogo` | text | — | no | Polygon `id` in `data/catalogos/basurales/` (`BAS-…`) or `data/catalogos/negativos/` (`NEG-…`) |
| `catalogo` | text | — | no | Which catalog the polygon comes from. Values: `basurales`, `negativos` |
| `frame` | text | — | no | Frame key, the one in `frames.json` (for example `AMBA`) |
| `ndvi_media` | number | index −1 to 1 | yes | NDVI inside, mean across dates |
| `ndvi_variacion` | number | index | yes | Standard deviation of the inside NDVI across dates |
| `bsi_media` | number | index −1 to 1 | yes | Bare soil (BSI) inside, mean across dates |
| `ndwi_media` | number | index −1 to 1 | yes | NDWI (water) inside, mean across dates |
| `swir_b11` | number | reflectance 0-1 | yes | Band B11 (1.6 µm) inside, mean across dates |
| `swir_b12` | number | reflectance 0-1 | yes | Band B12 (2.2 µm) inside, mean across dates |
| `ndvi_contraste` | number | index | yes | `ndvi_media` minus the ring NDVI |
| `bsi_contraste` | number | index | yes | `bsi_media` minus the ring BSI |
| `ndwi_contraste` | number | index | yes | `ndwi_media` minus the ring NDWI |
| `swir_b11_contraste` | number | reflectance | yes | `swir_b11` minus the ring B11 |
| `swir_b12_contraste` | number | reflectance | yes | `swir_b12` minus the ring B12 |
| `n_escenas` | integer | scenes | no | Sentinel-2 scenes used |
| `fechas` | text | YYYY-MM-DD | yes | Dates of those scenes, comma-separated and in order |

**Key** (not repeated): `id_catalogo`, `frame`.

## 6. `salidas/cruce_manchas_catalogo.parquet`
- **Written by:** stage 6 (`cruce_manchas.py`).
- **Read by:** stage 6 (`armar_tabla.py`, to label) and stage 9 (to know whether a blob was already known).
- **One row per pair of blob and polygon that touch** (intersection greater than zero). A blob can have several rows and so can a polygon.
- **It isn't filtered by the 30 %:** the file carries all the crosses and the reader applies the criterion (`contratos.CRITERIO_CRUCE`, 0.30 on `frac_area_menor`; it's an assumption tuned by looking at the AMBA).
- Areas are measured in meters (the frame's UTM), not in degrees.

| Column | Type | Unit | Empty? | What it is |
|---|---|---|---|---|
| `id_mancha` | text | — | no | Blob identifier: `MAN-<frame>-<n>` |
| `id_catalogo` | text | — | no | Polygon `id` in `data/catalogos/basurales/` (`BAS-…`) or `data/catalogos/negativos/` (`NEG-…`) |
| `catalogo` | text | — | no | Which catalog the polygon comes from. Values: `basurales`, `negativos` |
| `frame` | text | — | no | Frame key, the one in `frames.json` (for example `AMBA`) |
| `frac_mancha` | number | fraction 0-1 | no | Intersection / blob area |
| `frac_poligono` | number | fraction 0-1 | no | Intersection / polygon area |
| `frac_area_menor` | number | fraction 0-1 | no | Intersection / the smaller of the two areas (the maximum of the other two) |
| `complejo` | text | — | yes | *Optional.* `CPX-…` of the dump site; null for negatives |
| `clase_negativo` | text | — | yes | *Optional.* Negative class; null for dump sites |

**Key** (not repeated): `id_mancha`, `id_catalogo`.

## 7. `catalogos/frames.json`
- **Written by:** stage 2 (`frames_elegir.py`).
- **Read by:** stages 1 and 4 (each frame's box and EPSG), 6 and 7 (city, country and what's kept for the final test), 8 and 9.
- **One entry per frame.** It goes in `data/catalogos/`, next to the catalogs.
- **Format:** `{"meta": {…}, "frames": [ {…}, … ]}`, like the catalogs. `meta` holds the date, the script, the source (ASF API) and the selection criterion.

```json
{
  "meta": {"generado_por": "motor/frames_elegir.py", "fuente": "ASF, productos GUNW PR"},
  "frames": [
    {
      "frame": "AMBA", "orbita": [10, 161], "ciudad": "Buenos Aires", "pais": "ARG",
      "hemisferio": "S", "epsg": 32721, "bbox": [-59.35, -34.90, -58.25, -34.25],
      "n_gunw": 15, "fecha_inicio": "2026-06-25", "fecha_fin": "2026-10-12",
      "n_basurales_10ha": {"abierto": 1, "cerrado": 1, "desconocido": 2},
      "n_negativos": {"aeropuerto": 12, "cantera": 30},
      "reservado_prueba": true
    }
  ]
}
```
The counts in the example are illustrative.

| Column | Type | Unit | Empty? | What it is |
|---|---|---|---|---|
| `frame` | text | — | no | Frame key, the one in `frames.json` (for example `AMBA`) |
| `orbita` | list of integers | — | no | NISAR orbits (tracks) used. The AMBA uses two: `[10, 161]` |
| `ciudad` | text | — | no | Reference city |
| `pais` | text | ISO 3166-1 alpha-3 | no | Country, as in the catalogs (`ARG`, `USA`, `IND`) |
| `hemisferio` | text | — | no | Hemisphere of the UTM zone. Values: `N`, `S` |
| `epsg` | integer | — | no | EPSG of the product's UTM grid (326xx north, 327xx south) |
| `bbox` | list of 4 numbers | degrees | no | `[lon_oeste, lat_sur, lon_este, lat_norte]`, as in GeoJSON. WATCH OUT: `geo.CAJA` uses another order |
| `n_gunw` | integer | pairs | no | Available `PR` GUNW pairs |
| `fecha_inicio` | text | YYYY-MM-DD | no | First date of the series |
| `fecha_fin` | text | YYYY-MM-DD | no | Last date of the series |
| `n_basurales_10ha` | object {key: integer} | complexes | no | Dump sites of 10 ha or more by status, counting each complex once. Keys: `abierto`, `cerrado`, `desconocido` |
| `n_negativos` | object {key: integer} | polygons | no | Negatives by class (`aeropuerto`, `cantera`…) |
| `reservado_prueba` | boolean | — | no | true if it stays out of training (Argentina) |
| `frames_nisar` | list of texts | — | yes | *Optional.* Track, direction and frame of each product, as in the name: `010_D_106` |

**Key** (not repeated): `frame`.

## 8. `salidas/tabla_entrenamiento.parquet`
- **Written by:** stage 6 (`armar_tabla.py`).
- **Read by:** stage 7 (`entrenar.py`) and the optional CNN.
- **One row per labeled blob and frame.** It's the table in section 4 of the plan: identification, the 29 variables (`contratos.COLUMNAS_MODELO`) and the label.
- **Which blobs get in** (stage 6): those that cross, with the 30 % criterion, polygons of **a single** catalog. With a dump site of any status → `basural_activo`; with a negative → `otro_movil`. Those that cross both, or neither, don't get in.
- **A complex counts once:** if several blobs fall on the same complex, one row per `complejo` and frame is kept.
- **EMIT variables don't go in** (it would be data leakage).
- The Argentine frames are in the table, but in `prueba_final` (see `particiones.json`).

| Column | Type | Unit | Empty? | What it is |
|---|---|---|---|---|
| `id_mancha` | text | — | no | Blob identifier: `MAN-<frame>-<n>` |
| `id_catalogo` | text | — | no | The polygon it crosses (the one with the largest `frac_area_menor`) |
| `complejo` | text | — | no | `CPX-…` of the dump site; for negatives, its own `id_catalogo`. Used for grouping |
| `frame` | text | — | no | Frame key, the one in `frames.json` (for example `AMBA`) |
| `ciudad` | text | — | no | The one in `frames.json` |
| `pais` | text | ISO 3166-1 alpha-3 | no | The one in `frames.json` |
| `clase_negativo` | text | — | yes | Negative class (`aeropuerto`…); null if it's a dump site |
| `insomnio` | number | fraction 0-1 | no | Fraction of pairs with coherence < 0.80 × the ring's, averaging orbits |
| `persistencia` | number | fraction 0-1 | no | Minimum of the awake fraction across the three segments of the series |
| `contraste_mediana` | number | ratio | yes | Blob coherence / ring coherence: median across pairs |
| `contraste_desvio` | number | ratio | yes | Standard deviation of that ratio across pairs |
| `coherencia_media` | number | coherence 0-1 | yes | Mean absolute coherence, normalized to 12 days |
| `tendencia` | number | coherence per day | yes | Slope of the normalized coherence over time |
| `n_pares` | integer | pairs | no | Valid GUNW pairs over the blob |
| `n_orbitas` | integer | orbits | no | Orbits with enough pairs |
| `eco_db` | number | dB | yes | Mean echo (HH backscatter, gamma0) of the blob |
| `eco_contraste` | number | dB | yes | Blob echo minus ring echo |
| `eco_variacion` | number | dB | yes | Standard deviation of the mean echo across dates |
| `hv_hh` | number | dB | yes | Polarization ratio: HV echo minus HH echo |
| `ndvi_media` | number | index −1 to 1 | yes | NDVI inside, mean across dates |
| `ndvi_variacion` | number | index | yes | Standard deviation of the inside NDVI across dates |
| `bsi_media` | number | index −1 to 1 | yes | Bare soil (BSI) inside, mean across dates |
| `ndwi_media` | number | index −1 to 1 | yes | NDWI (water) inside, mean across dates |
| `swir_b11` | number | reflectance 0-1 | yes | Band B11 (1.6 µm) inside, mean across dates |
| `swir_b12` | number | reflectance 0-1 | yes | Band B12 (2.2 µm) inside, mean across dates |
| `ndvi_contraste` | number | index | yes | `ndvi_media` minus the ring NDVI |
| `bsi_contraste` | number | index | yes | `bsi_media` minus the ring BSI |
| `ndwi_contraste` | number | index | yes | `ndwi_media` minus the ring NDWI |
| `swir_b11_contraste` | number | reflectance | yes | `swir_b11` minus the ring B11 |
| `swir_b12_contraste` | number | reflectance | yes | `swir_b12` minus the ring B12 |
| `area_ha` | number | ha | no | Blob area (same as `ha` in `manchas.geojson`) |
| `elongacion` | number | ratio ≥ 1 | no | Major axis / minor axis (the one from `insomnio.manchas()`) |
| `compacidad` | number | 0-1 | yes | 4π × area / perimeter²: 1 is a circle |
| `agua_anillo` | number | fraction 0-1 | yes | Part of the 1.5 km ring that is water (JRC) |
| `urbano_anillo` | number | fraction 0-1 | yes | Part of the ring that is urban (ESA WorldCover, class 50) |
| `cultivo_anillo` | number | fraction 0-1 | yes | Part of the ring that is cropland (ESA WorldCover, class 40) |
| `cnn_p_basural` | number | probability 0-1 | yes | *Optional.* What the ResNet-50 says, out of partition |
| `clase` | text | — | no | The label. Values: `basural_activo`, `otro_movil` |

**Key** (not repeated): `id_mancha`.

## 9. `salidas/particiones.json`
- **Written by:** stage 6, together with the table.
- **Read by:** stage 7 and the CNN, which has to use the same partitions.
- **Partitions go by frame:** all the blobs of a frame fall in the same one, so a complex is never split. The Argentine frames (`reservado_prueba` in `frames.json`) go to `prueba_final` and are used neither for training nor for choosing anything.

```json
{
  "meta": {"umbral_insomnio": 0.70, "criterio_cruce": 0.30},
  "particiones": {"0": ["DELHI", "LAGOS"], "1": ["CDMX"], "2": ["NAIROBI", "YAKARTA"]},
  "prueba_final": ["AMBA"]
}
```

| Key | Type | What it is |
|---|---|---|
| `meta.umbral_insomnio` | number | The minimum insomnia used to build the training blobs (0.70, or less if it was lowered only for training) |
| `meta.criterio_cruce` | number | The fraction of the smaller area used for labeling (0.30) |
| `particiones` | object | Partition number (as text) → list of frames. At least two partitions, none empty |
| `prueba_final` | list | Frames left out of training. It can be empty |

Each frame in the table appears exactly once. `contratos.particion_por_frame(d)` returns `{frame: partition}`. Anything needed (seed, counts per class) can be added to `meta`.

## 10. `salidas/predicciones.parquet`
- **Written by:** stage 7, once there's a model. Meanwhile, the mock.
- **Read by:** stage 9 (`veredicto.py`).
- **One row per candidate blob and frame.** For the training frames, the probability comes from the partition in which the blob wasn't used for training.

| Column | Type | Unit | Empty? | What it is |
|---|---|---|---|---|
| `id_mancha` | text | — | no | Blob identifier: `MAN-<frame>-<n>` |
| `frame` | text | — | no | Frame key, the one in `frames.json` (for example `AMBA`) |
| `p_basural` | number | probability 0-1 | no | Probability of `basural_activo` according to the model |

**Key** (not repeated): `id_mancha`.

---

## What the mock carries
`python motor/contratos_mock.py` writes to `motor/datos/mock/` (not committed) all the files above, with the same names and in a single folder. They're consistent with each other: the ids cross from one file to another.

- **Frames:** `AMBA` (Argentina, goes to `prueba_final`) and three more so there are partitions: `DELHI`, `CDMX` and `NAIROBI`. The orbits, dates and counts of those three are made up.
- **Per frame, 10 candidate blobs:** 2 over a dump site, 4 over a negative (airport, quarry, containers and wetland), 1 touching a dump site and a negative, 1 grazing a negative with less than 30 %, and 2 touching nothing. Plus 3 discarded ones (small, linear and smooth), which are only in the geojson.
- **Catalog polygons without a blob:** a closed quiet dump site, an open quiet one, one under 10 ha, a quiet crop field and a small construction site. Outside the AMBA there's also a closed dump site with a blob on top, to test "closed but awake".
- **The only real things:** the ids and radar values of Norte III (`BAS-053304`), González Catán (`BAS-000001`) and Luján (`BAS-000007`) in `insomnio_catalogo.parquet`, copied from `salidas/fichas_80m.json`, and the id of the El Palomar airport (`NEG-AMBA-000931`). Their geometries in the mock are made-up rectangles.
- **More rows:** `--manchas-por-frame 60` (to test training with more than 27 rows) and `--semilla`.

## Decisions made here
The ones that weren't in the plan and had to be fixed. If any is a problem, it's discussed with the team and changed in `contratos.py` and here at the same time.

1. **`frames.json` goes with the catalogs** (`data/catalogos/frames.json`), and `orbita` is a list because the AMBA uses two orbits.
2. **`reservado_prueba`** on each frame, so the partitions come from a single place.
3. **Optical contrast columns** (`ndvi_contraste`, `bsi_contraste`, `ndwi_contraste`, `swir_b11_contraste`, `swir_b12_contraste`): the plan asks for the indices "inside and against the ring" but only names the inside ones.
4. **`tabla_optico_catalogo.parquet`**, for the optical data of the catalog polygons, separate from the blobs'.
5. **`predicciones.parquet`**, with `p_basural`, so the verdict can be written before there's a model.
6. **`clase_negativo`** in the training table, to report which negative class the model gets wrong; and `complejo` never empty (for negatives it's their own id), to group without special cases.
7. **`fechas` is a text** with the dates comma-separated, not a list: it reads the same from any tool.
8. **Units the plan didn't state:** `tendencia` in coherence per day; `hv_hh` and `eco_contraste` in dB (differences); `compacidad` = 4π × area / perimeter²; `urbano_anillo` and `cultivo_anillo` with ESA WorldCover classes 50 and 40.

## Sources
- NISAR GUNW and GCOV (NASA/ISRO, via ASF DAAC): movement and roughness.
- Sentinel-2 L2A (Copernicus, ESA): optical.
- JRC Global Surface Water and ESA WorldCover: context.
- OpenStreetMap via Overture Maps (ODbL), Climate TRACE (CC BY 4.0), EPA LMOP (public domain) and NASA EMIT: the catalogs in `data/catalogos/` (details in `data/README.md`).
