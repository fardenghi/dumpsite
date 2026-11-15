# Data and sources

What data Dumpsite uses, where it comes from and under which license. Which file is which and what script regenerates it is in `data/README.md`.

## NISAR
- **Products:** L2 GUNW (interferogram with an 80 m coherence layer and a wrapped one at 20 m) and L2 GCOV (echo, at 10 or 20 m depending on the mode), from NASA/ISRO via ASF DAAC (https://search.asf.alaska.edu/). The products are public and downloading needs a NASA Earthdata account.
- **Maturity:** the first public release of calibrated data was on 20/07/2026. ASF warns against mixing maturities (BETA, PROVISIONAL and VALIDATED). We use `PR` products.
- **AMBA:** 15 GUNWs and 19 GCOVs from orbits 10 (descending) and 161 (ascending), from 25/06 to 12/10/2026. Each GUNW weighs about 2.2 GB, but the pipeline reads by URL only the window it needs.
- **30 frames:** 962 GUNW pairs. The `.h5` files and the crops aren't committed.

## Dump-site catalog
**66,981 sites around the world** (1,225 open, 3,579 closed, 31 contradictory and 62,146 without a status), joined per site from:

| Source | What it adds | License |
|---|---|---|
| OpenStreetMap via Overture Maps (release 2026-10-21.0) | `landuse=landfill` polygons and the closed ones (`disused:landuse=landfill`) | ODbL 1.0, © OpenStreetMap contributors |
| U.S. EPA LMOP (2024-09) | Status, closure year and biogas capture of US landfills | Public domain |
| Climate TRACE (API v6) | Emissions per site | CC BY 4.0 |
| NASA EMIT L2B CH4PLM v002 | Methane plumes | No restrictions |
| Team's curated cases | 7 Buenos Aires cases: Luján, Norte III, González Catán, Ensenada, San Pedro, Navarro and Nueve de Julio | That of each cited source |

**OSM almost never says whether a dump site is active**, so most remain without a status. The known status comes almost entirely from the EPA, which is why the results are biased toward the US.

Other datasets we surveyed that didn't make it in: optical detectors with ML labels, national and regional registries, and, in the AMBA, the CIM-FADU (UBA) georeferenced database, which we couldn't confirm has a public download.

## Negatives
**64,986 polygons of 24 classes**, plus 1,259 in the AMBA. They're what the radar can confuse with a dump site because they also change often or return little echo:

- water and wet surfaces;
- quarries and earthworks;
- scrapyards and container yards;
- farming and vegetation;
- airfields and other infrastructure.

They come from Overture Maps (OSM, ODbL). They measure between 2 and 500 ha, are more than 500 m from any catalog dump site and are sampled near dump sites with a known status. What's fixed and well mapped is removed with masks. What the model has to learn to separate, like quarries, isn't filtered: it goes in as a negative.

## Other sources
- **Sentinel-2 L2A** (Copernicus, ESA), via Microsoft Planetary Computer, no account needed: optical variables, optical labels and the video.
- **JRC Global Surface Water** v1.4: water mask.
- **ESA WorldCover** 2021 v200 (CC BY 4.0): land cover as context.

## Validation cases in Argentina
| Case | What happened | What it's for |
|---|---|---|
| **Luján dump site** | Stopped receiving waste on 1/07/2026, after about 52 years. The conversion stalled because of legal disputes | Central case: closed and quiet, or closed but awake? |
| **Norte III, CEAMSE** | Active landfill that takes most of the AMBA's waste | Positive control |
| San Pedro, Navarro, Nueve de Julio | Dump site under a court order (October 2026), announced closure (February 2026) and ongoing closure | Cases to follow. Their coordinates are the district centers; each site still has to be located |
