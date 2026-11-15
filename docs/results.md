# Results

**Wording:** "signal compatible with activity" and "quiet according to the radar". None of this is an accusation.

## The 37 frames
The pipeline ran over **37 NISAR frames, with 1,087 GUNW pairs** on the 80 m layer:

- **10 frames chosen first** by number of known-status dump sites and negatives: AMBA, Los Angeles, Mexico City, Delhi, Jakarta, Ponce (Puerto Rico) and four US counties.
- **20 US frames added** by number of open dump sites.
- **7 Argentine frames outside the AMBA**, added later for prediction only (125 pairs, 151 candidate blobs): [`argentina.md`](argentina.md).

| Frames | Pairs | Blobs | Candidates | On a catalog dump site | Known land use (OSM) | Unexplained | Candidate ha |
|---|---|---|---|---|---|---|---|
| The first 10 | 333 | 22,874 | 2,578 | 41 | 639 | 1,898 | 84,382 |
| The 20 added | 629 | 46,703 | 1,945 | 56 | 492 | 1,397 | 48,370 |

A blob is a **candidate** if it has an insomnia of 0.70 or more, a persistence of 0.50 or more, isn't water or linear, has an echo of −13 dB or more and measures 10 ha or more. The thresholds were calibrated **only in the AMBA** and weren't touched per frame. The per-frame detail is in `data/salidas/<FRAME>/` and `motor/resumen_etapa4.py` summarizes it.

## Verdict per site
`motor/flujo.py` joins the cross in both directions (blobs over catalog and catalog over blobs) and gives a verdict per catalog polygon and per blob without a catalog. It's in `data/salidas/veredictos.json` and it's what the web shows.

**Across the 37 frames, the radar and the model find 274 active dump sites: 102 were already in the catalogs and 172 are new (possible new dump sites, not verified). Of the known ones, 20 are listed as closed but are still awake.** The web highlights the blobs with a dump-site score of 0.4 or more, a threshold the team lowered from 0.5 for the map: 223 blobs, of which it shows 183 and leaves out 40 that OpenStreetMap already explains with another use.

**AMBA controls:**
- **González Catán:** not listed, awake, insomnia 1.0. Verdict: active, already known.
- **Norte III:** open, awake, insomnia 1.0. Verdict: active, already known.
- The per-blob classifier also ran on the AMBA, as the final test: it doubts on the two active landfills (`p_basural` 0.08 for González Catán and 0.00 for Norte III), and recognizes 1 of the 7 blobs that sit on known landfills.
- **Luján dump site:** closed, quiet, insomnia 0.0. Verdict: **closed and quiet**.

## Activity matrix
Does the insomnia agree with the registry? Over the known-status dump sites the radar could measure, with 95 % Wilson intervals:

| Country | Open and awake | Closed and quiet | Closed and awake | Agreement |
|---|---|---|---|---|
| ARG | 1/1 | 1/1 | 0/1 | 2/2 |
| PRI | 0/5 (0 % to 43 %) | 2/2 | 0/2 | 2/7 (29 %) |
| USA | 16/40 (40 %, 26 % to 55 %) | 10/26 (38 %) | 16/26 (62 %) | 26/66 (39 %) |

**Honest reading:** in the US, 40 % of the open sites and 62 % of the closed ones come out awake. **The insomnia alone doesn't separate open from closed.** Many closed landfills keep moving because of biogas, settlement, construction work or vegetation. That's the reason for the active-front model (`model.md`).

Bias: of the 193 known-status sites the radar measured, 179 are in the US (they come from the EPA). The matrix is valid for those countries, not "for the world".

## Rule versus model
Over the same 198 dump sites of 10 ha or more with a status (26 frames, without the AMBA):

| | Decides | Agrees with the registry |
|---|---|---|
| Insomnia rule | 73 of 198 (37 %) | 28 of 73 (38 %) |
| **Front model** (0.5 threshold) | 198 of 198 | **170 of 198 (86 %)** |

Applied to the 148 dump sites of 10 ha or more **without a status** in the first 30 frames, the model flags 56 with `p_abierto` above 0.5. They're in `data/salidas/predicciones_estado.parquet`. **They're not verified.**

## Cases to check by hand
- **Closed but awake: 16**, all in the US. For example: Operating Industries (Los Angeles, closed in 1984), Palos Verdes (1980), Norris Farms (Maryland, 1986) and Tri-Cities (California, 2012). In almost all of them an obvious explanation **can't be ruled out**: many have biogas capture according to LMOP (wells and pipes move the ground) or a recycling plant on the site. Before naming one, it has to be checked in optical imagery.
- **Open but quiet: 29.** The most common explanation is that the tipping front (1 to 3 ha) is too small to move the median of a large site, or that the EPA registry (2024) is outdated.

## Norte III
The radar model said "closed" for the Norte III polygon carrying the "open" status. The label was on the wrong polygon: `BAS-053304` is a vegetated sector, and both the radar and the optical data place the change in another polygon of the same complex, `BAS-016796`. Measured as a complex, the model gives 0.99.

## Optical
- **AMBA, with means over the polygon:** the optical data **doesn't separate** a sanitary landfill from a grass airfield. The large AMBA landfills are almost all covered with vegetation, and the active front is a small part of the site.
- **1,008 known-status dump sites** (`motor/optico_estado_conocido.py`): the "less green than its surroundings" rule (site NDVI minus ring NDVI, below −0.15) flags **313 of 578 open (54 %) and 71 of 369 closed (19 %)**, with an AUC of 0.77. The threshold was fixed beforehand and not tuned.

## What shouldn't be said
- That the radar "detects the closure" in general. Specific cases, like Luján, can be shown with their context.
- That the unexplained blobs are dump sites. None is verified.
- That `p_abierto` or `p_basural` are calibrated probabilities.
