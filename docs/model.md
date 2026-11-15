# Model

There are two models and they answer different questions:

| Model | Question | Result | Status |
|---|---|---|---|
| **Open versus closed** (`motor/modelo_estado.py`) | With what NISAR measures over a site, does the registry list it as open or closed? | AUC **0.91** (0.87 to 0.95) on frames it didn't see | Main |
| Dump site versus something else that moves (`motor/entrenar.py`) | Is an awake blob a dump site, or an airfield, a quarry, a port? | AUC 0.79 (0.72 to 0.87) | Weak: useful for ranking, not as a verdict |

## The flow
1. **Pipeline per frame** (`pipeline_insomnio.py`): the per-pixel insomnia on any NISAR frame.
2. **Frames** (`frames_elegir.py`): 10 chosen by number of known-status dump sites and 20 more by number of open ones. They're in `data/catalogos/frames.json`.
3. **Blobs and radar** (`extraer_manchas.py`): blobs, radar variables against the ring and insomnia of each catalog polygon.
4. **Optical** (`extraer_optico.py`): Sentinel-2 L2A per blob and per polygon, against the ring.
5. **Cross** (`cruce_manchas.py`): which blobs touch which polygons.
6. **Table and training** (`armar_tabla.py`, `entrenar.py`, `modelo_por_frame.py`).
7. **Activity** (`evaluar_actividad.py`): the radar against the registry, with labels independent of the insomnia.
8. **Verdict and web** (`veredicto.py`, `flujo.py`).

The intermediate files follow `data-contracts.md`. Argentina stays **out of training**: the AMBA is kept as the final test.

## Cross between blobs and catalog
A blob is assigned to a polygon if the intersection covers **at least 30 % of the smaller area** and measures **at least 5.12 ha** (8 pixels of 80 m). The minimum area prevents a tiny polygon inside a large blob from labeling the whole blob. If a blob touches a dump site and a negative at the same time, it's left out.

## Open-versus-closed model
- **Labels:** the registry status (EPA LMOP, curated cases). **They don't come from the insomnia.**
- **Samples:** 198 dump sites of 10 ha or more with a status, from 26 frames (121 open and 77 closed). Almost all are in the US and 12 in Puerto Rico.
- **Validation:** one frame is left out at a time. 95 % intervals by resampling.
- **No model uses the area:** in the registry the open ones are larger, and area alone already gives AUC 0.79.

### Active-front variables (`motor/radar_frente.py`)
Instead of the site median, we look at **the part that changes most**. There are 10 variables, all against the 1.5 km ring:

- **Echo:** per-pixel temporal deviation of the echo (HH and HV), the 3×3 patch where it changes most and the net change between the start and the end of the series.
- **Coherence:** the worst 3×3 patch, the worst patch over the site median, the largest area that stays below the ring and how far the worst patch moves.

### Result
| Variables | AUC (95 % CI) |
|---|---|
| **Front** (10, NISAR only) | **0.908 (0.867 to 0.946)** |
| Front + optical (18) | 0.927 (0.889 to 0.958) |
| Optical (8, Sentinel-2) | 0.869 (0.807 to 0.920) |
| Whole-site radar (7) | 0.778 (0.708 to 0.839) |

The selection criterion was fixed before looking at the AMBA: the simplest one within 0.02 of the best. **Front wins, using only NISAR.**

By size: AUC of 0.76 for small sites (10 to 42 ha), 0.90 for medium ones and 0.97 for large ones.

### What it learns
1. There's **a small area that loses coherence much more than the rest** of the site (open).
2. **The echo changes over time** (open).
3. A site that is **even and without coherence over its whole surface** is, in this data, a closed landfill. That's compatible with vegetation over the final cover.

The variable that weighs most is mixed with size: in a large site it's easier for some patch to end up very low. The echo variation is the cleanest.

### Test in the AMBA (not used for training)
| Site | Registry | `p_abierto` |
|---|---|---|
| Luján dump site | Closed (1/07/2026) | **0.16** |
| Norte III, the complex as a single unit | Open | **0.99** |
| Norte III, polygon `BAS-053304` | Carries the complex's "open" | 0.07 |
| Norte III, west sector (`BAS-016796`) | No status of its own | 0.96 |
| González Catán | No status | 0.87 |

**Norte III:** the "open" status got attached to the polygon closest to an approximate coordinate, `BAS-053304`, which is a vegetated sector. The radar and the optical data place the change in the west sector. Measured as a complex it gets 0.99. The individual polygon still comes out closed and we don't hide it.

### What can be said
- **Yes:** "with NISAR variables that look at the active front, a model trained on the EPA registry ranks open and closed sites with AUC 0.91 on frames it didn't see".
- **Carefully:** Luján 0.16 and Norte III 0.99 are two cases, not a statistic.
- **No:** that it works on small sites or outside the US, or that `p_abierto` is a calibrated probability.

## Dump site versus something else that moves
LightGBM over one row per awake blob (about 30 radar, optical, shape and context variables): `basural_activo` versus `otro_movil` (airfields, containers, quarries, wetlands). What's quiet doesn't go through the model.

- 39 dump sites and 553 blobs of something else, in 9 frames. Leaving one frame out, the AUC is **0.79**.
- With a 0.5 threshold it finds 9 of 39 dump sites (recall 0.23) and gets 9 of the 31 it flags right (precision 0.29).
- **It's useful for ranking** which unexplained blob to look at first. **It's not useful as a verdict.**

## Optical labels assigned by AI
For 89 dump sites in 9 frames, a vision-language model answered "is there visible activity inside the site?" looking at Sentinel-2 on three dates. It did so in two independent, blind passes, without the name, registry or radar. **No person reviewed them.** They were used for the activity index and for the variants of the per-blob model (`data/salidas/etiquetas_optico_ia.json`).

## Resolution test: 20 m versus 80 m
`motor/prueba_resolucion.py` tested measuring the front with the echo and the coherence at 20 m. **No variant improves the 80 m model beyond the margin of error.** The only one that adds something is the 20 m coherence (+0.016 AUC, with an interval from −0.022 to +0.061). It's not worth redoing the 30 frames.

## What exists out there
We looked for models or products that classify landfills as active or closed from satellite. **We found none using radar at scale**, neither with NISAR nor with Sentinel-1. The closest are optical detectors that tell *where* there's a dump site, emission inventories that take the status from official registries, and activity methods with Sentinel-1 coherence in mining.

## Untested proposal: optical CNN
A ResNet-50 pretrained on SSL4EO-S12 (the 13 Sentinel-2 bands, including SWIR) that looks at each blob's crop and goes in as one more variable of the per-blob model. It was proposed and never trained.
