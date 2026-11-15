# Insomnia index

The index answers **"does it move?"**. What it is that moves is decided by the cross with the catalogs and the model (`model.md`).

- **Code:** `motor/insomnio.py` (the computation), `motor/geo.py` (grids and projections) and `motor/pipeline_insomnio.py` (reading NISAR, outputs and web).
- **Data:** NISAR L2 GUNW (coherence) and GCOV (echo), from NASA/ISRO via ASF DAAC, on the 80 m layer. Water from JRC Global Surface Water v1.4.
- **Outputs:** `data/salidas/indice_80m.*`, `resumen_80m.json`, `fichas_80m.json` and `calibracion_80m.json`.

```bash
cd motor
python pipeline_insomnio.py indice      # AMBA, 14 s with the crops already made
python pipeline_insomnio.py calibrar    # sweeps the thresholds
```

## First check: a single pair
With one GUNW (orbit 10, from 30 September to 12 October 2026) and the 20 m coherence, the median inside each site against a 1.5 km ring gave:

| Site | Inside | Ring | Reading |
|---|---|---|---|
| Norte III (CEAMSE) | 0.38 | 0.51 | Darker than its surroundings: active |
| González Catán | 0.42 | 0.53 | Darker: the site's footprint shows |
| Luján dump site | 0.66 | 0.62 | Quiet, consistent with the closure |
| Control: CABA (Palermo) | 0.74 | 0.73 | Stable |

With a single pair, coherence finds **water** before dump sites: the Roggero reservoir, the Nordelta lakes, the Delta. That's where the water mask, the echo filter and the shape filter come from.

## How it's computed
Over 15 GUNWs and 19 GCOVs of the AMBA (orbits 10 and 161, from 25 June to 12 October 2026):

| Step | What it does |
|---|---|
| **Water mask** | JRC Global Surface Water, with occurrence of 10 % or more, widened by 80 m. It removes 97,493 ha of the grid's 718,952 |
| **Comparison with the surroundings** | A pair counts as "awake" if the coherence is lower than 0.80 × the median of the surroundings (land within 2 km). Since each pair is compared with itself, mixing 12-, 24- and 36-day pairs doesn't affect it |
| **Per orbit** | The fraction of awake pairs is computed per orbit and averaged |
| **Persistence** | The series is split into three segments and the minimum is taken. It needs 0.5 or more in all three. That leaves out 4,226 ha that only move seasonally |
| **Shape** | Linear blobs (roads, streams) are discarded |
| **Echo** | Blobs with a mean echo below −13 dB are smooth surfaces (water, runways) and are discarded |
| **Size** | 10 ha minimum, about 16 pixels of 80 m |

For a site, the insomnia is the fraction of pairs in which the median coherence inside the site is lower than 0.80 × that of its 1.5 km ring. Water and **all the catalog polygons** are removed from the ring, so a neighboring landfill or an airfield doesn't lower the reference.

## AMBA sites (80 m)
| Site | Registry | ha | Insomnia | Radar |
|---|---|---|---|---|
| Norte III (calibration) | active | 265 | **0.86** | awake |
| González Catán (calibration) | not listed | 155 | **1.00** | awake |
| Norte III, final disposal | active | 72 | 1.00 | awake |
| Landfill next to Norte III (west) | not listed | 150 | 0.93 | awake |
| **Luján dump site** | closed on 1/07/2026 | 44 | **0.00** | **quiet** |
| Unnamed landfill, Benavídez | not listed | 11 | 0.13 | quiet |
| Villa Domínico | closed in 2004 | 8 | 0.33 | can't tell |
| Controls: CABA, Delta, Roggero reservoir, countryside | — | — | 0.00 | quiet |

- The two calibration sites come out awake and the controls, quiet.
- The Norte III complex polygons that were **not** used for calibration also come out awake (0.93 to 1.00).
- **Luján gets 0.00 in all 15 pairs.**

**Candidate blobs: 219, totaling 7,050 ha (1.1 % of the land).** Of those, 7 overlap an OSM landfill, 22 are known land uses (airfields, golf courses, cemeteries) and 190 remain unexplained. **The unexplained ones are not verified.**

## Thresholds
A combination of thresholds is valid if Norte III and González Catán come out awake, CABA comes out quiet and the blobs cover less than 5 % of each control.

| Threshold | Value | Valid range |
|---|---|---|
| `razon` (coherence / surroundings) | 0.80 | 0.725 to 0.825 |
| `min_insomnio` | 0.70 | 0.5 to 0.8 |
| `eco_min_db` | −13 | −16.6 to −11.6 |
| `min_persistencia` | 0.50 | not calibrated |
| `min_ha` | 10 | not calibrated |

**It's not an independent validation:** it's two positives and five controls. Outside the calibration, the cross with the AMBA catalogs gives an **AUC of 0.88** with 4 dump-site complexes and 274 negatives. With so few positives, the number only says that the index separates. It can't be used as a precision measure.

## Limits
- **The grass of an airfield or a forest loses coherence in every pair,** just like a landfill. The index can't tell them apart: that's left to the cross with the negatives and the model.
- The thresholds were calibrated **only in the AMBA** and weren't recalibrated per frame.
- The **20 m layer** isn't the reference: at 20 m Norte III gets 0.79 and "can't tell". It would need recalibration.

## Discarded variant: percentile of the surroundings
We tested counting a pair as awake if the coherence is below percentile P of the surroundings. With P = 20 there are 494 blobs instead of 219 and the cross AUC drops from 0.88 to 0.77. It loses because a large site lowers the percentile of its own surroundings. The code stayed in the repo history (commit "motor: environment-percentile variant of the index").

## Activity index (experimental)
A site's insomnia is the median of the **whole** polygon, so it fails in two ways: it marks a grass-covered closed landfill as awake and it misses a small tipping front in a large site. For that there are three new columns in `tabla_radar.parquet` and `insomnio_catalogo.parquet`:

| Column | What it measures |
|---|---|
| `contraste_p10` | Coherence of the least coherent 10 % of the site over that of the ring |
| `eco_var_p90` | Variation of the echo over time, 90th percentile of the site |
| `indice_actividad` | Logistic regression with the two above, from 0 to 1. **It's not a probability** |

It was fitted with 53 sites from 9 frames with optical labels assigned by AI. Against the registry (59 sites not used to fit it) it gives an AUC of 0.69, versus 0.50 for the insomnia. It's the idea the active-front model later took over (`model.md`).
