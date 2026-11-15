# web/

Dumpsite's web: the insomnia index map, each site's card and the model panel. It's a static site (React, Vite and MapLibre) that reads data precomputed by the engine, with no backend. The interface is in Spanish.

```bash
npm install
npm run dev      # http://localhost:5183
npm run build    # static site in dist/
```

## Sections
The map is the background of the whole site and is always visible. The sections are panels that float on top and open and close from the bottom bar (or with Esc).

| Route | What it shows |
|---|---|
| `#/mapa` | The AMBA with the insomnia index and the sites. Opening one shows: verdict, pair-by-pair coherence and Sentinel-2 images by date. The catalog dump sites of the other frames are shown as points; the legend has a button to zoom out until all of them are visible |
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
- OpenStreetMap, ODbL.
- Dump-site catalog for the other frames: OpenStreetMap polygons via Overture Maps (release 2026-10-21.0, ODbL) and registry status from U.S. EPA LMOP (2024-09, public domain). Details in `../data/README.md`.
- Google satellite imagery (Map Tiles API), only if the key is configured. It's copyrighted by Google and its providers: it has to be declared in the submission form.
- Roboto Slab (Apache 2.0) and DM Sans (OFL) fonts. Map with MapLibre GL JS (BSD-3).
- Code: Apache 2.0. Written with AI assistance (Claude).
