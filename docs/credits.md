# Credits, licenses and AI use

Every dataset, imagery service, library, font and AI tool that Dumpsite uses, with its license and how to cite it. The per-file detail (which script uses which source) is in [`data.md`](data.md) and [`../data/README.md`](../data/README.md).

**Dumpsite's own code and documentation are released under the [Apache License 2.0](../LICENSE).** Third-party material keeps its own license, listed below.

> Dumpsite is an independent project made for NASA Space Apps Challenge 2026. It is not endorsed by NASA, ISRO, ESA or any other agency or data provider named here. NASA and partner-agency names appear only to credit their data; the project does not use NASA logos or insignia.

## NASA data
| Data | What Dumpsite does with it | License / terms | Citation |
|---|---|---|---|
| **NISAR L2 GUNW** (geocoded unwrapped interferogram), `PR` products | The core input: the 80 m and 20 m coherence of each 12-day pair is what the insomnia index is built from. 37 frames, 1,087 pairs | NASA Earth science open data policy: no restrictions on use. Download needs a free NASA Earthdata account | NASA/JPL-Caltech and ISRO, NISAR L2 GUNW, retrieved from the Alaska Satellite Facility DAAC, https://search.asf.alaska.edu/ |
| **NISAR L2 GCOV** (geocoded covariance) | Radar echo (HH and HV) of each blob, for the open-versus-closed model | Same as above | NASA/JPL-Caltech and ISRO, NISAR L2 GCOV, ASF DAAC |
| **EMIT L2B CH4PLM v002** (methane plume complexes) | Methane plumes over catalog dump sites, as a signal to prioritize | NASA open data, no restrictions | EMIT L2B Estimated Methane Plume Complexes 60 m V002, NASA EOSDIS LP DAAC, doi:10.5067/EMIT/EMITL2BCH4PLM.002 |
| **Blue Marble** (shaded relief and bathymetry), via **GIBS** | World background of the web map | NASA open data, no restrictions | "We acknowledge the use of imagery provided by services from NASA's Global Imagery Browse Services (GIBS), part of NASA's Earth Science Data and Information System (ESDIS)." |
| **Earthdata Search / CMR** | Finding the EMIT granules | NASA service | https://cmr.earthdata.nasa.gov/ |

## Space agency partner data
| Data | Agency | What Dumpsite does with it | License / terms | Citation |
|---|---|---|---|---|
| NISAR (joint mission) | **ISRO** with NASA | See above | See above | See above |
| **Sentinel-2 L2A**, 10 m | **ESA** / European Commission (Copernicus) | Optical variables and labels, the image timeline on each site card | Copernicus Sentinel data legal notice: free, full and open | Contains modified Copernicus Sentinel data (2026), accessed via Microsoft Planetary Computer, https://planetarycomputer.microsoft.com/dataset/sentinel-2-l2a |
| **ESA WorldCover 10 m 2021 v200** | **ESA** | Land cover as context for each blob | CC BY 4.0 | Zanaga, D. et al. (2022). ESA WorldCover 10 m 2021 v200. doi:10.5281/zenodo.7254221 |

## Other data
| Data | What Dumpsite does with it | License | Citation |
|---|---|---|---|
| **OpenStreetMap**, through **Overture Maps** release 2026-10-21.0 (`base` theme: `land_use`, `land`, `water`, `infrastructure`) | Dump-site polygons (`landuse=landfill`, `disused:landuse=landfill`), negatives (what the radar confuses with a dump site) and land-use masks | ODbL 1.0 | © OpenStreetMap contributors, https://www.openstreetmap.org/copyright; Overture Maps Foundation, https://docs.overturemaps.org/ |
| **Climate TRACE**, solid-waste-disposal subsector, API v6 | Emissions per dump site | CC BY 4.0 | Climate TRACE Emissions Inventory, https://climatetrace.org |
| **U.S. EPA LMOP** Landfill and Project Database (2024-09) | Open/closed status and closure year of US landfills: the main training label | Public domain (U.S. Government work) | U.S. EPA Landfill Methane Outreach Program, https://www.epa.gov/lmop |
| **JRC Global Surface Water** v1.4 | Water mask | Free of charge, without restriction of use (Copernicus programme) | Pekel, J.-F., Cottam, A., Gorelick, N., Belward, A. S. (2016). High-resolution mapping of global surface water and its long-term changes. *Nature* 540, 418–422 |
| **Natural Earth** 1:10m Admin 0 countries | Argentina's outline (`motor/fijos/argentina_ne10m.geojson`) | Public domain | Made with Natural Earth, https://www.naturalearthdata.com |
| **Sentinel-2 cloudless 2024** by EOX | Background mosaic of the web map when zoomed in (tiles loaded from EOX, not stored in the repo) and some figures | CC BY-NC-SA 4.0 | Sentinel-2 cloudless – https://s2maps.eu by EOX IT Services GmbH (contains modified Copernicus Sentinel data 2024) |
| **Google Map Tiles API** (2D satellite) | Optional, only if a key is configured. **The public site doesn't use it** | © Google and its providers, under the Google Maps Platform terms. Not redistributed | Shown on the map with Google's attribution |
| Curated Argentine cases (Luján, Norte III, González Catán, Ensenada, San Pedro, Navarro, Nueve de Julio) | Validation cases | That of each source | Each source (press articles and public documents) is cited with its URL in `data/catalogos/basurales/casos_curados_argentina.json` |

Microsoft Planetary Computer and the ASF API are only used as access services; the data terms are the ones above.

## Software
### Engine (Python, `motor/`)
| Library | License |
|---|---|
| NumPy, SciPy, pandas, scikit-learn, h5py, Shapely, rasterio, tifffile, imagecodecs | BSD-3-Clause |
| Matplotlib | Matplotlib License (PSF-based, BSD-compatible) |
| LightGBM, DuckDB, earthaccess, pytest, pyproj, openpyxl | MIT |
| Pillow | MIT-CMU (HPND) |
| PyArrow, functions-framework, google-cloud-compute | Apache-2.0 |

### Web (`web/`)
| Library | License |
|---|---|
| React, React DOM, Vite, @vitejs/plugin-react, @vercel/analytics | MIT |
| MapLibre GL JS | BSD-3-Clause |
| TypeScript | Apache-2.0 |
| Roboto Slab font (@fontsource/roboto-slab) | Apache-2.0 |
| DM Sans font (@fontsource/dm-sans) | SIL Open Font License 1.1 |

The web uses **Vercel Web Analytics**, which counts page views without cookies and without collecting personal data. The site doesn't ask users for any data.

### Video (`video/`)
| Library | License |
|---|---|
| React, React DOM, @remotion/fonts, python-dotenv | MIT / BSD-3-Clause |
| Remotion (`remotion`, `@remotion/cli`, `@remotion/google-fonts`) | Remotion License: free for individuals and small teams, **not OSI-approved**. Used only as a rendering tool; it isn't part of the solution's code |
| IBM Plex Sans, IBM Plex Mono and Barlow Condensed fonts (@fontsource) | SIL Open Font License 1.1 |
| TypeScript | Apache-2.0 |

The sources of the video's images, clips and voices are listed in [`../video/README.md`](../video/README.md).

## Use of AI
AI was used as a tool to speed up the work. The idea (using the coherence NISAR loses at a dump site as a sign of activity, the "insomnia index") and every decision about the method came from the team.

| Where | Tool | What it did | How it's marked |
|---|---|---|---|
| Code (`motor/`, `web/`, `video/`) and documentation | Claude (Anthropic), as a coding assistant | Helped write and review code and docs, which the team directed, ran and checked | This section, [`../motor/README.md`](../motor/README.md) and [`../web/README.md`](../web/README.md) |
| Data: `data/salidas/etiquetas_optico_ia.json` | Claude, a vision-language model | 89 optical activity labels, assigned blind on Sentinel-2 images in two independent passes. **No person reviewed them** | The file's `meta.generado_por` field and [`model.md`](model.md) |
| Video: opening clip and synthetic voice | Higgsfield (Seedance) and Azure AI Speech | Video only | On-screen notice in the video and [`../video/README.md`](../video/README.md) |

No AI-generated image, video or audio uses, contains or modifies NASA logos, flags or mission insignia.

## References (for the submission form)
Paste-ready list for the "Space Agency Partner Data and Other References" field.

```text
SPACE AGENCY PARTNER DATA
1. NISAR L2 GUNW and L2 GCOV (NASA/JPL-Caltech and ISRO), via the Alaska Satellite Facility DAAC – https://search.asf.alaska.edu/ – NASA open data policy.
2. Copernicus Sentinel-2 L2A (ESA / European Commission), via Microsoft Planetary Computer – https://planetarycomputer.microsoft.com/dataset/sentinel-2-l2a – Copernicus free, full and open data policy. Contains modified Copernicus Sentinel data (2026).
3. ESA WorldCover 10 m 2021 v200 – Zanaga, D. et al. (2022), doi:10.5281/zenodo.7254221 – CC BY 4.0.

OTHER DATA
4. OpenStreetMap, via Overture Maps release 2026-10-21.0 – © OpenStreetMap contributors – ODbL 1.0 – https://www.openstreetmap.org/copyright, https://docs.overturemaps.org/
5. Climate TRACE emissions inventory, solid-waste-disposal subsector, API v6 – https://climatetrace.org – CC BY 4.0.
6. U.S. EPA Landfill Methane Outreach Program (LMOP) Landfill and Project Database, September 2024 – https://www.epa.gov/lmop – public domain.
7. JRC Global Surface Water v1.4 – Pekel, J.-F. et al. (2016), Nature 540, 418–422 – free, without restriction of use.
8. Natural Earth 1:10m Admin 0 countries – https://www.naturalearthdata.com – public domain.
9. Sentinel-2 cloudless 2024 by EOX IT Services GmbH – https://s2maps.eu – CC BY-NC-SA 4.0 (web map background, loaded from EOX).
10. Curated Argentine dump-site cases: press articles and public documents, each cited with its URL in data/catalogos/basurales/casos_curados_argentina.json.

SOFTWARE
11. Python: NumPy, SciPy, pandas, scikit-learn, h5py, Shapely, rasterio, tifffile, imagecodecs (BSD-3-Clause); Matplotlib (Matplotlib License); LightGBM, DuckDB, earthaccess, pytest, pyproj, openpyxl (MIT); Pillow (MIT-CMU); PyArrow, functions-framework, google-cloud-compute (Apache-2.0).
12. Web: React, Vite, Vercel Web Analytics (MIT); MapLibre GL JS (BSD-3-Clause); TypeScript (Apache-2.0); Roboto Slab (Apache-2.0) and DM Sans (OFL 1.1) fonts.
13. Video: Remotion (Remotion License); IBM Plex and Barlow Condensed fonts (OFL 1.1).

AI TOOLS
14. Claude (Anthropic): coding assistant, and 89 blind optical activity labels (data/salidas/etiquetas_optico_ia.json, not human-reviewed).
15. Higgsfield (Seedance) and Azure AI Speech: AI clip and synthetic voice in the video, marked on screen.

Full detail and licenses: https://github.com/fardenghi/dumpsite/blob/main/docs/credits.md
```

## NASA Data (for the submission form)
Draft for the "NASA Data" field:

> Dumpsite is built on **NISAR** (NASA–ISRO), the L-band SAR launched in 2025, using its first public calibrated products (released 20 July 2026), downloaded from the **ASF DAAC** with `earthaccess`. From each **L2 GUNW** we read the coherence layer (80 m, and 20 m from the wrapped interferogram) for every 12-day pair: 1,087 pairs over 37 frames, including Buenos Aires and 7 more Argentine regions. An active dump site is reworked every day, so it loses coherence in every pair; the share of pairs where a place "didn't sleep" is our **insomnia index**. **L2 GCOV** gives the HH and HV radar echo used by the open-versus-closed model (AUC 0.91 on frames it didn't see). We also use **EMIT L2B CH4PLM** methane plumes to prioritize sites, and **Blue Marble** via **GIBS** as the web map's background.
