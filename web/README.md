# web/

Dumpsite's web: the insomnia index map, each site's card and the model panel. It's a static site (React, Vite and MapLibre) that reads data precomputed by the engine, with no backend. The interface is in English by default and in Spanish on request (selector in the top bar, or `?lang=es`); the texts live in `src/i18n.ts`.

```bash
npm install
npm run dev      # http://localhost:5183
npm run build    # static site in dist/
```

## Sections
The map is the background of the whole site and is always visible. The sections are panels that float on top and open and close from the bottom bar (or with Esc).

| Route | What it shows |
|---|---|
| `#/mapa` | Starts on the AMBA. It shows **the whole dump-site catalog** (66,981) and the processed NISAR frames; see "Map layers". Opening a curated AMBA site shows: verdict, pair-by-pair coherence and Sentinel-2 images by date. "Ir a un sitio" (go to a site) lists everything with radar data, grouped by country and with a search box. With `VITE_GOOGLE_MAPS_KEY`, from zoom 13 the Google image appears on its own inside the box of each dump site (the crop box on curated sites, 1.5 km around the point elsewhere), without opening it; outside the boxes nothing is requested from Google |
| `#/inicio` | "Resumen" (summary) panel: number of sites, insomnia ranking and the Luján case |
| `#/sitios` | Panel with the list, filterable by frame and by radar status, exportable to CSV. It starts on the AMBA |
| `#/modelo` | Panel with the pair-by-pair rule (with an example site), the funnel from the grid to the candidate blobs, the calibrated thresholds, **the open-versus-closed model with its metrics** (if `modelo.json` carries them) and the proposed per-blob classifier, which has no metrics yet |

## Data
**They're real and precomputed.** They're written by the insomnia index pipeline and aren't edited by hand:

```bash
python ../motor/pipeline_insomnio.py indice
```

| File | What it has |
|---|---|
| `src/data/seed/sitios.json` | 12 AMBA sites with the exact shape of `Sitio[]` (`src/data/types.ts`): insomnia relative to the 1.5 km ring, radar verdict, 15 NISAR pairs (both orbits, sorted by date), registry with its source and OpenStreetMap outline |
| `src/data/seed/fichas.json` | Per site, what doesn't fit in `Sitio`: reason for the verdict, persistence, insomnia per orbit, orbit of each pair, echo, OSM objects and registry sources. Used by the Model panel |
| `src/data/seed/candidatos.json` | The 219 candidate blobs with center, area and class (`relleno_osm`, `uso_conocido`, `sin_explicar`). The Model panel shows the count per class; they're not on the map yet. The "unexplained" ones aren't verified: say "signal compatible with activity" |
| `public/indice/insomnio-amba.png` + `src/data/seed/indice.json` | The AMBA index as a PNG (north up, regular in Web Mercator) and its bounds: `oeste`, `sur`, `este`, `norte` and `coordinates`, the four corners in the order a MapLibre `image` source expects. `Mapa.tsx` loads it that way and the "Índice de insomnio" button toggles it |

### Map layers
What doesn't fit in the bundle goes to `public/datos/` and the web requests it on load. It's written, with no dependencies and without touching the sources, by:

```bash
python3 scripts/datos_mapa.py
```

| File | Comes from | What it draws |
|---|---|---|
| `public/datos/catalogo.json` (2.7 MB) | `../data/catalogos/basurales/basurales_mundo.json` | The 66,981 catalog dump sites, in columns. The ones that don't fall in a processed frame are small light-blue points, **"Sin dato de radar"** (no radar data): the card shows name, country, area and source, and says there's no index (without the status of any registry, like the rest of the web) |
| `public/datos/manchas.geojson` (6.3 MB) | `../data/salidas/manchas.geojson` + `seed/veredictos.json` | The 20,589 awake blobs of the frames, simplified to an 80 m pixel. With "Índice de insomnio" on they're painted by insomnia with the AMBA PNG palette |
| `public/datos/frames.json` | `../data/catalogos/frames.json` | The box of each frame (filled from afar, fading when zooming in; with the index on), its city and its country |

The same script writes `src/data/seed/calibracion.json` from `../data/salidas/resumen_80m.json` and `calibracion_80m.json`: grid areas, funnel discards, chosen thresholds and their valid range. **The Model panel no longer has numbers written in the code**: it reads them from there.

- **Colors:** coral, teal and white are the radar verdict (awake, quiet, not enough). **Yellow is "possible new dump site"**: an awake blob that isn't in any catalog and that the model reads as a dump site (`veredicto = posible_nuevo` in `veredictos.json`). It goes above everything, with a halo, and with its outline from zoom 8. Light blue is the catalog without radar data.
- **183 blobs are highlighted: the ones with a dump-site score of 0.4 or more** (`UMBRAL_NUEVO` in `src/data/veredictos.ts`; the flow cuts at 0.5 and gives 172, the team lowered it on 15/11). Another 40 with that score fall on something OpenStreetMap already explains (airfields, reserves, quarries, golf courses: for example Los Angeles airport) and aren't painted yellow. The rule is in `posiblesNuevos` (`src/data/veredictos.ts`). None is verified.
- **The full index, pixel by pixel, is there for all 37 regions:** the AMBA (`public/indice/insomnio-amba.png`, from the pipeline) and the other 36 (`public/indice/insomnio-<frame>.png` and `src/data/seed/indices.json`; the 7 Argentine frames outside the AMBA were added later, with their own run: [`../docs/argentina.md`](../docs/argentina.md)). **How the first 29 were made (15/11):** for 27 frames `gs://basurales-514714-salidas/p6/<FRAME>.tgz` was downloaded and `recortes_80m/` extracted into `../data/salidas/<FRAME>/`; `USA_TX_HARRIS` and `USA_CA_SAN_JOAQUIN` aren't in the bucket and were read remotely from a container (`pipeline_insomnio.py procesar --frame <FRAME> --remoto --procesos 4`, 8 and 11 minutes, with `EARTHDATA_TOKEN`; in a cloud container the `FSSPEC_GCS` variable has to be removed from the environment, with `env -u FSSPEC_GCS`, because it breaks reading over HTTPS). Then, per frame, `python pipeline_insomnio.py indice --frame <FRAME> --web ''` (about 60 s; it writes `indice_80m.npz`, which isn't committed, and `resumen_80m.json` and `fichas_80m.json`, which are) and finally `python indice_png_web.py`. The web loads the images from `indices.json` and doesn't paint those frames' blobs.
- Since the run on the afternoon of 15/11 the AMBA also has a classifier prediction: 7 of the 183 are there.

### Low threshold (team decision, 15/11)
Sites the pipeline leaves as "no alcanza" (small site, smooth surface or intermediate signal) **are shown as awake if their measured insomnia is above 0.2**, the index's "quiet" ceiling. It's a web rule, not a pipeline one: `conUmbralBajo` in `src/data/types.ts` is applied when loading `sitios.json` and `veredictos.json`, which aren't touched, and leaves the `umbral_bajo` flag. The card and the Model panel say so ("Despierto con el umbral bajo").
- With this, 306 sites become awake: 4 in the AMBA (Villa Domínico, Ministro Rivadavia, Cuartel V and the blob west of Luján) and 302 from the catalog. Altogether the web shows 379 of 700 sites awake.
- 222 stay as "no alcanza": 87 without measured insomnia (smaller than a pixel or outside the grid) and 135 with insomnia of 0.2 or less.
- **Careful in the pitch:** the calibrated rule is still insomnia of 0.7 or more (Model panel). The low-threshold ones didn't go through that calibration: they're "signal compatible with activity", not a validated verdict.

### Verdicts for all frames and open-versus-closed model
Written by `python ../motor/flujo.py --web`. **Both files are optional**: the web looks for them with `import.meta.glob` (`src/data/veredictos.ts`) and, if they're missing or don't carry the new keys, it stays as before.

| File | What the web uses |
|---|---|
| `src/data/seed/veredictos.json` | `sitios[]`: one dump-site catalog polygon per row, with `frame`, `registro`, `radar`, `insomnio`, `veredicto_texto`, `lat` and `lon`. The AMBA ones aren't listed separately: the AMBA is still the 12 curated sites in `sitios.json`. The ones from the other frames are the new rows of the list and the new points on the map |
| `sitios[].modelo_estado` (optional) | `{p_abierto, lectura, origen}`: what the open-versus-closed model says about that polygon. It's shown on the card and in the list, **labeled "según el modelo" (according to the model)** and separate from the registry status and the radar verdict. `p_abierto` is shown as an "open score, from 0 to 1", not as a probability |
| `src/data/seed/modelo.json`, `estado` key (optional) | `{auc, ic95, n, abiertos, cerrados, frames, variables, validacion, limites, prueba_amba}`: the Model panel shows it as it comes, with the limits and the AMBA test. Without `estado`, the panel doesn't show the model |

- **No model number is hard-coded**: everything comes from those two JSON files. The types are in `src/data/types.ts` (`Veredicto`, `LecturaModelo`, `ModeloEstado`).
- **How the model reading is assigned to a curated AMBA site:** `sitios.json` doesn't carry the catalog id, so it looks for the catalog polygon of the `AMBA` frame that is within 0.4 km and has the same size (area ratio up to 1.25). If there's no clear one, the site has no reading (for example, the blob west of Luján, which isn't a site). See `veredictoDeSitio` in `src/data/veredictos.ts`.
- **Each frame's name comes from its key** (`USA_OH_LAKE` → "Lake, OH, USA"): the seed doesn't carry the city.
- **Outside the AMBA there's no outline, coherence series or images by date**: the card shows the verdict, the registry, the insomnia, the area, the reason and the model reading, and the map zooms in less (the Blue Marble background goes up to zoom 8).
- **Wording:** "compatible with open according to the model" and "signal compatible with activity". The status is only shown when the registry gives it; polygons without a status say "En el catálogo, sin estado" (in the catalog, no status).

The sites from other countries that the seed had were removed: they have no processed NISAR. `scripts/contornos.py` is no longer used (the outlines are written by the pipeline). How each number is computed: `../docs/insomnia-index.md`.

The whole web reads the data through `src/data/api.ts`. To connect a backend, set `VITE_API_URL` (see `.env.example`) and have it answer `GET /sitios` with the shape of `Sitio` in `src/data/types.ts`.

## Satellite imagery
No keys or accounts needed:
- **Blue Marble** (NASA GIBS) as the world background.
- **Sentinel-2 L2A, 10 m** (ESA Copernicus) by date, when opening a site. The tiles are served by [Microsoft Planetary Computer](https://planetarycomputer.microsoft.com/dataset/sentinel-2-l2a).
- Each card has a link to Google Maps to see the site in more detail.

**Optional, with a key: Google high resolution** (Map Tiles API, 2D satellite). With `VITE_GOOGLE_MAPS_KEY` in `.env.local` (see `.env.example`), opening a dump site frames the site and shows the Google image, under 1 m. It's for visual impact: you can see it's a dump site.
- **Each tile is billed**, so they're requested only inside the box of the open site and from zoom 13. The rest of the map never calls Google.
- **It has no date.** To compare moments Sentinel-2 is still used: picking a date on the card switches back to that view.
- Without a key, or if the session fails, the web works as before.
- The key is visible in the browser: restrict it by HTTP referrer and to the Map Tiles API. It doesn't go in the repo.
- Google requires showing its name and the copyright for the area; the map does it at the bottom right. Tested on 14/11 with a real key.

## Site outlines
The outlines come from the index pipeline (OpenStreetMap `landuse=landfill` polygons, downloaded by `fuentes_fijas.py`): 11 of the 12 sites have a real outline. The blob west of Luján, which isn't a registered site, keeps a ring. `scripts/contornos.py` is for new sites outside the AMBA, but it no longer writes this seed's outlines.

## Map cache
`public/sw.js` stores the Blue Marble and Sentinel-2 tiles the first time they're requested and then serves them offline. Also, when the web loads it preloads the most recent Sentinel-2 image of each dump site, which is what people always browse. Google tiles are left out: their terms don't allow storing or preloading them, only the browser's normal cache.

`python3 scripts/s2_fechas.py` queries the STAC catalog and saves in `src/data/seed/imagenes.json` up to 8 scenes with less than 10 % clouds per site. It has no dependencies.

## Sources and licenses
- NISAR L2 GUNW and GCOV (NASA/ISRO), via ASF DAAC.
- JRC Global Surface Water v1.4 (Pekel et al., 2016, Nature 540), for the water mask.
- Blue Marble (NASA), via GIBS.
- Sentinel-2 (ESA Copernicus), via Microsoft Planetary Computer.
- Sentinel-2 cloudless 2024 mosaic by EOX IT Services (s2maps.eu, CC BY-NC-SA 4.0), as the zoomed-in background.
- OpenStreetMap, ODbL.
- Dump-site catalog: OpenStreetMap polygons via Overture Maps (release 2026-10-21.0, ODbL), Climate TRACE (solid-waste-disposal, API v6, CC BY 4.0), registry status from U.S. EPA LMOP (2024-09, public domain) and NASA EMIT L2B CH4PLM v002 plumes. Details in `../data/README.md`.
- Google satellite imagery (Map Tiles API), only if the key is configured. It's copyrighted by Google and its providers: it has to be declared in the submission form.
- Roboto Slab (Apache 2.0) and DM Sans (OFL) fonts. Map with MapLibre GL JS (BSD-3).
- Code: Apache 2.0 (see `../LICENSE`). Written with AI assistance (Claude). Full list of sources and licenses: `../docs/credits.md`.
