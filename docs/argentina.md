# Argentina outside the AMBA

Two pieces of work from 15/11/2026: what the dump-site catalog has in Argentina, and the classifier run on 7 Argentine zones outside the AMBA.

**Wording:** "signal compatible with activity" and "classified as a dump site by the model". Nothing here is verified in optical imagery or on the ground.

## What the catalog has in Argentina
Made with `motor/conteo_argentina.py`. There's one row per site in `data/catalogos/basurales/argentina_sitios.csv`.

- **393 georeferenced sites** in the world catalog (`data/catalogos/basurales/basurales_mundo.json`), which make **365 complexes** (sites less than 1 km apart count as one). Another 4 came up during the work and aren't in the catalog: Villa Domínico (closed CEAMSE landfill) and three curated cases without coordinates (San Pedro, Navarro and Nueve de Julio).
- **Mapped area: 4,347 ha.** 149 sites have 5 ha or more, the useful size for NISAR at 80 m, and 94 have 10 ha or more.
- **There's almost no status:** 1 open (Norte III), 1 closed (Luján) and 391 without a status. OSM doesn't tell active from closed, and Argentina has no open official registry.
- **What has no coordinates is much bigger:** the Ministry of Environment estimates about **5,000 open-air dump sites** (not from a formal survey). With what is mapped we'd see under 8 %, and that compares two figures that don't measure the same thing.

### By category
The catalog's `tipo` field doesn't help: Climate TRACE labels almost everything as a sanitary landfill. The category is assigned from the **site name in OSM or Climate TRACE** (`CATEGORIAS` in the script), so it's approximate.

| Category | Sites | < 1 ha | 1-5 ha | 5-20 ha | 20-100 ha | ≥ 100 ha | Total ha |
|---|---:|---:|---:|---:|---:|---:|---:|
| No name in OSM (plain `landuse=landfill`) | 263 | 91 | 100 | 58 | 13 | 1 | 1,477 |
| Open-air dump or municipal dump | 61 | 13 | 18 | 22 | 8 | 0 | 717 |
| Sanitary landfill or final disposal complex | 37 | 1 | 2 | 12 | 16 | 6 | 1,725 |
| Not municipal waste (mining, nuclear, cars, industrial, mislabeled wetland) | 9 | 1 | 4 | 1 | 2 | 1 | 267 |
| Micro-dump or informal dump | 8 | 7 | 1 | 0 | 0 | 0 | 4 |
| Treatment or recycling plant | 8 | 0 | 3 | 3 | 2 | 0 | 108 |
| Former dump, closed or old according to its name | 7 | 0 | 3 | 4 | 0 | 0 | 49 |
| **Total** | **393** | **113** | **131** | **100** | **41** | **8** | **4,347** |

- **Not municipal waste (9):** mining waste piles in San Juan, encapsulated uranium tailings in Mendoza, radioactive waste in Córdoba, a car cemetery and a wetland reserve, among others. **They have to be removed or flagged before using them as positives.**
- **Former dumps (7):** Plottier, Godoy Cruz, Merlo (San Luis) and four more. They're the natural candidates for "closed but awake" outside the AMBA, but their status only comes from a name someone put in OSM.
- **Micro-dumps (8):** almost all are points under 0.1 ha in Córdoba. They're no use for radar.

### By province and source
- **Most sites:** Santa Fe 95, Buenos Aires 90, Córdoba 73, Misiones 21, Entre Ríos 19. Formosa and CABA have none. The AMBA frame box has 18.
- What drives the count is **how much each province's OSM community mapped**, not how many dump sites it has: Santa Fe has 84 unnamed polygons, more than Buenos Aires.
- **Sources:** OpenStreetMap via Overture (388 sites, polygon and area, no status), Climate TRACE (69, of which 5 only exist there: Bower, Los Vázquez, Río Cuarto, San Javier II and San Martín de los Andes), NASA EMIT (8 methane plumes, all in Norte III and Cuartel V) and the team's curated cases.
- **Highest emitters according to Climate TRACE** (t CO₂e, 100 years): Norte III module C 2.42 M, Bower 0.78 M, Piedras Blancas 0.46 M, Brandsen 0.46 M, González Catán 0.43 M.
- **Sources found but not processed** (no open coordinates): the ACUMAR 2017 dump-site baseline for the Matanza-Riachuelo basin (CSV on datos.gob.ar, the next one to add for the AMBA), the Buenos Aires province 2023 report, Devesa and Vazquez Brust 2021 ([arXiv 2110.08599](https://arxiv.org/abs/2110.08599)) and the CIM-FADU-UBA database (on request).

## The classifier in 7 zones outside the AMBA
**In one line:** the current model, without retraining, leaves 5 blobs with `p_basural` ≥ 0.5 in 7 new frames. One is on a catalog site (Mar del Plata) and 4 have no catalog. It's a list to check by hand, not a set of findings.

- **Code:** `motor/frames_argentina.py` picks the zones and adds them to `data/catalogos/frames.json`; `motor/predecir_frames.py` predicts with `data/salidas/modelo.txt` without retraining. The rest is the usual pipeline (`pipeline_insomnio.py`, `extraer_manchas.py`, `modelo_por_frame.py --sin-juntar`, `flujo.py --web`, `web/scripts/datos_mapa.py` and `indice_png_web.py`).
- **Outputs:** `data/salidas/ARG_*/`, `data/salidas/veredictos.json` and the web seed.
- **What didn't change:** the model, its metrics, the AMBA predictions (checked by hash) and the thresholds.

### How the zones were chosen
- **Argentine sites:** the catalog sites whose point falls inside the Natural Earth 1:10m outline, minus the 18 in the AMBA box.
- **Count:** per 1° cell, of the sites of 10 ha or more. The first 3 cells were clear and the next 4 tied with 3 sites each, so all of them went in.
- **Box and radar:** the sites' polygons plus 5 km, with up to 2 NISAR tracks covering 75 % of the box. At least 15 GUNW pairs were needed, and all 7 zones passed.
- **No site in these zones has a known status**, so these frames can't measure open versus closed, only predict.

| Frame | Sites ≥ 10 ha / total | GUNW pairs | Period | Candidate blobs | On a catalog site | `p_basural` ≥ 0.5 | Possible new |
|---|---|---|---|---|---|---|---|
| `ARG_ROSARIO` | 8 / 50 | 17 | 20/06 to 19/10/2026 | 34 | 0 | 0 (max 0.27) | 0 |
| `ARG_CORDOBA` | 5 / 32 | 22 | 11/11/2025 to 21/10/2026 | 36 | 0 | 1 | 1 |
| `ARG_SAN_NICOLAS` (and Pergamino) | 4 / 44 | 17 | 20/06 to 19/10/2026 | 12 | 0 | 1 | 1 |
| `ARG_MAR_DEL_PLATA` | 3 / 4 | 17 | 19/06 to 17/10/2026 | 6 | 1 | 2 | 1 |
| `ARG_SANTA_FE` (and Paraná) | 3 / 7 | 18 | 4/11/2025 to 19/10/2026 | 40 | 1 | 0 (max 0.49) | 0 |
| `ARG_CASILDA` (and Venado Tuerto) | 3 / 8 | 17 | 20/06 to 19/10/2026 | 17 | 0 | 0 (max 0.48) | 0 |
| `ARG_JUNIN` (and Chacabuco) | 3 / 3 | 17 | 20/06 to 18/10/2026 | 6 | 0 | 1 | 1 |
| **Total** | | **125** | | **151** | **2** | **5** | **4** |

The 7 frames were read at 80 m in the VM, with remote reads per window, in 4 minutes.

### The 5 blobs the model classifies as a dump site
All have insomnia 1.0 (low coherence against the ring in almost every pair). **Nobody has looked at them in optical imagery yet.**

| Blob | `p_basural` | Area | Echo (dB) | Catalog | Coordinates |
|---|---|---|---|---|---|
| `MAN-ARG_JUNIN-0014` | 0.70 | 16.0 ha | −12.8 | none | [−34.68413, −60.01335](https://www.google.com/maps?q=-34.68413,-60.01335&t=k) |
| `MAN-ARG_CORDOBA-0190` | 0.65 | 10.2 ha | −12.9 | none | [−31.32235, −64.12684](https://www.google.com/maps?q=-31.32235,-64.12684&t=k) |
| `MAN-ARG_MAR_DEL_PLATA-0005` | 0.64 | 14.7 ha | −11.7 | none (about 1.4 km from the "Viejo basural municipal", `BAS-050022`) | [−38.04747, −57.62094](https://www.google.com/maps?q=-38.04747,-57.62094&t=k) |
| `MAN-ARG_MAR_DEL_PLATA-0004` | 0.61 | 15.4 ha | −9.9 | on the "Predio basural" (`BAS-053315`, 92 ha) and the "Centro de Disposición final" (`BAS-043883`, 40 ha) | [−38.06945, −57.64991](https://www.google.com/maps?q=-38.06945,-57.64991&t=k) |
| `MAN-ARG_SAN_NICOLAS-0106` | 0.53 | 13.4 ha | −11.0 | none | [−33.77292, −60.14060](https://www.google.com/maps?q=-33.77292,-60.14060&t=k) |

### What the radar says about the known landfills
- **The model recognizes 1 of the 2 blobs on known landfills** (in the AMBA it was 1 of 7): the Mar del Plata disposal site comes out at 0.61, and a blob on two small unnamed OSM polygons near Paraná (`MAN-ARG_SANTA_FE-0021`) at 0.15. Two cases give no rate.
- **The large landfills hardly produce blobs.** Of the 28 catalog polygons of 10 ha or more with a radar reading in these frames, 22 are quiet, 4 give an intermediate signal, 1 is awake (`BAS-016694`, 15 ha, unnamed, near Venado Tuerto, insomnia 0.82) and 1 is a smooth surface. Quiet named landfills include Pérez, Piedras Blancas, Ricardone, Capitán Bermúdez, the Mar del Plata site and the Pergamino plant.
- That **doesn't** mean they're inactive: in the US frames a 1 to 3 ha tipping front doesn't move the median of a site of tens of hectares at 80 m, and many open sites come out quiet ([`results.md`](results.md), [`model.md`](model.md)). Here there's no known status to compare with.

## Limits
- **The per-blob model is weak:** precision 0.29, recall 0.23 and AUC 0.79 out of partition ([`model.md`](model.md)). In a manual review of the 10 strongest blobs of other frames, most were container yards. Most of these 5 blobs are probably not dump sites.
- **Out of distribution:** the model was trained on 9 frames in the US, Mexico, India, Indonesia and Puerto Rico. Argentina was held out on purpose.
- **Short series:** 17 to 22 pairs, and in 5 frames barely 4 months (June to October 2026). A construction site or a harvest in those months can look "insomniac".
- **The Argentine catalog is almost all OSM:** it has no status and is missing sites. "No catalog" means it isn't in the catalog, not that it's a new site.

## Next steps
1. Check the 5 blobs and the Paraná one in Sentinel-2 or high-resolution imagery.
2. If one turns out to be a dump site, look for it in municipal or provincial registries.
3. Add the ACUMAR baseline to the AMBA catalog.

## Sources
- NISAR L2 GUNW and GCOV (NASA/ISRO), provisional PR version, via ASF DAAC: 125 GUNW and 141 GCOV pairs in the 7 frames.
- Copernicus Sentinel-2 L2A (ESA), via Microsoft Planetary Computer.
- JRC Global Surface Water v1.4 (Pekel et al., 2016, *Nature* 540:418-422) and ESA WorldCover 2021 v200 (CC BY 4.0).
- Dump-site catalog: OpenStreetMap via Overture Maps release 2026-10-21.0 (ODbL 1.0) and Climate TRACE (CC BY 4.0); details in [`data.md`](data.md).
- OSM land uses via Overpass (ODbL 1.0).
- Natural Earth 1:10m Admin 0 and Admin 1 v5.1.2 (public domain), for the Argentine outline and the provinces.
