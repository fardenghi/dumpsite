# Model context for the video

Written on 14/11/2026 from the repo's code and outputs (`motor/entrenar.py`, `motor/insomnio.py`, `data/salidas/metricas.json`, `data/salidas/modelo.txt`). It tells whoever edits the video which model we actually trained, so the script doesn't make anything up. The full technical description is in [`../docs/model.md`](../docs/model.md).

## What the video has to change
The video said we used a **ResNet-50** (a neural network that looks at images). **That isn't true: the ResNet-50 was a proposal that was never implemented.** What we trained is a **LightGBM**, a gradient-boosting model over decision trees that works on a table of numbers per blob, not on images.

- **Keep the visual sequence:** the grid of mapped dump-site images, the images going into the model and a classifier that says "dump site" or "something else".
- **Keep the line** "trained on thousands of mapped dumps". It's still true.
- **Change only the model:** wherever it said or showed ResNet-50, CNN, neural network or deep learning, it now says **LightGBM** (or "gradient boosting").
- **Wording:** what the model marks is "**classified as a dump site by the model**", not a "confirmed dump site". Nobody verified it on the ground.
- **For the voice-over:** a LightGBM doesn't "look at pixels". Variables are computed from each image (vegetation, bare soil, water, infrared) and that's what it learns. "Images → model → classifier" is fine as a visual; don't say "the network looks at the image" or "computer vision".
- **Numbers:** don't put accuracy figures on screen until the team provides them for the current run.

## The real flow, in two steps
| Step | What it does | Is it trained? | Question it answers |
|---|---|---|---|
| 1. Insomnia index | A formula over the NISAR radar, pixel by pixel | No. A fixed rule with calibrated thresholds | Does this place move? |
| 2. LightGBM | Classifies each awake blob with 29 variables | Yes. Supervised learning with labeled examples | Is what moves a dump site or something else? |

The radar says **whether** a place changes, not **what** it is: a quarry, a construction site, a watered golf course or an airport also "move". Step 2 exists to separate dump sites from everything else. How step 1 works is in [`../docs/insomnia-index.md`](../docs/insomnia-index.md).

## Step 2: LightGBM
- **Gradient boosting:** many small decision trees trained in a row, each one correcting the errors of the sum of the previous ones. The final score goes through a sigmoid and ends up between 0 and 1.
- **LightGBM** is an open-source implementation published by Microsoft in 2017. It trains in seconds on a CPU.
- **Why not a neural network:** with 592 examples a deep network memorizes instead of learning. For small tables gradient boosting is the standard, and it tells which variables weighed the most.
- **Inputs, 29 numbers per blob:** 12 radar (insomnia, persistence, mean coherence, trend, echo in dB, HV/HH), 11 optical from Sentinel-2 (NDVI, BSI, NDWI, SWIR B11 and B12 and their contrast with the surroundings), 3 shape (area, elongation, compactness) and 3 surroundings (water, urban and cropland fraction in the ring). The optical part is spectral indices averaged per blob, not a network looking at the image: that's where the ResNet confusion came from.
- **Configuration:** 300 small trees (depth 3, up to 7 leaves), learning rate 0.05, 80 % of rows and variables per tree, classes balanced by weight and a fixed seed.
- **Training data:** the world catalog (`data/catalogos/basurales/basurales_mundo.json`) has **66,981 mapped sites** from OpenStreetMap via Overture Maps, Climate TRACE, EPA LMOP and NASA EMIT: that's where "thousands of mapped dumps" comes from. The run in `data/salidas/` used **592 blobs** from 9 zones outside Argentina: **39 dump sites** against **553 other things** (golf courses, forests, parks, reserves, cemeteries, airfields, military sites and quarries from OpenStreetMap). Buenos Aires was held out as the final test.
- **Validation per zone:** a whole city is left out, the model trains on the other eight and predicts the one left out, so the metric says whether it generalizes to a place it never saw.

## Results of the run in the repo (not for the video)
| Metric | Value | Meaning |
|---|---|---|
| AUC | **0.79** (95 % CI: 0.72 to 0.87) | Given a random dump site and a random non-dump site, the model orders the pair correctly 79 % of the time. Chance is 0.50 |
| Recall (threshold 0.5) | 0.23 (95 % CI: 0.13 to 0.38) | It finds 9 of the 39 known dump sites |
| Precision (threshold 0.5) | 0.29 (95 % CI: 0.16 to 0.47) | Of the 31 blobs it marks, 9 are dump sites |

- **What weighs the most:** bare-soil contrast with the surroundings, radar echo intensity and its variation, the water index and how much cropland is around.
- **Insomnia weighs little inside the model**, as expected: every blob that reaches step 2 already passed the insomnia filter.
- **Radar and optical add up:** radar only gives AUC 0.73, optical only 0.76 and both 0.79. The intervals overlap, so it's a trend, not a proven difference.
- **Where it fails:** it confuses quarries (3 of 6 marked as dump sites) and airfields (5 of 21).

## What can and can't be said
Safe lines:
- "Trained on thousands of mapped dumps." / "Entrenado con miles de basurales mapeados de todo el mundo."
- "Our model classifies each blob: dump site or something else."
- "More than 66,000 mapped dump sites" (the catalog has 66,981).
- "The radar sees 42 dump sites from the catalogs awake; 13 of them are listed as closed." That number comes from the **insomnia index crossed with the catalogs**, not from the LightGBM.

Don't say, because it's false and can be checked:
- That we used ResNet-50, neural networks, deep learning or computer vision.
- That the blobs the model marks are "real", "confirmed" or "discovered" dump sites. The safe line is "the model classifies them as dump sites".
- Accuracy figures we don't have ("90 % accuracy" or similar). Precision (0.29) and recall (0.23) at 0.5 are low: know them in case the jury asks.
- "Illegal dump" or "clandestine dump" about an unverified blob. The team's rule is "signal compatible with activity".

## Suggested lines for the script
- Short: "First, a radar index marks the places that never stay still. Then our model classifies each one: dump site or something else."
- Technical: "A LightGBM trained on more than 66,000 mapped dump sites, which classifies each radar blob as a dump site or something else."
- Closing: "The radar says where there's movement. The model says which ones are dump sites."

## To cite
- LightGBM: Ke et al., "LightGBM: A Highly Efficient Gradient Boosting Decision Tree", NeurIPS 2017.
- Gradient boosting: Friedman, "Greedy Function Approximation: A Gradient Boosting Machine", Annals of Statistics, 2001.
- Data: NISAR (NASA/ISRO), Sentinel-2 (ESA/Copernicus), OpenStreetMap (ODbL).
