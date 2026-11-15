# Roadmap

Dumpsite was built in two days. It works end to end, but several pieces are first versions. This is what we would do next, ordered by priority. Each item points to the document where the limitation is measured.

## Next weeks: make what exists trustworthy
- **Review by people.** Have people check, in optical imagery and before naming any site:
  - the 89 optical labels assigned by AI and the 16 "closed but awake" cases ([`results.md`](results.md), [`model.md`](model.md));
  - the 183 possible new dump sites highlighted on the map, starting with the 5 Argentine blobs outside the AMBA ([`argentina.md`](argentina.md)).
- **Known pipeline fixes:**
  - the fallback to frequency B/VV in 3 GCOVs that lack frequency A;
  - the looks metadata of the BETA products;
  - using a single product maturity once there are enough VALIDATED products ([`model.md`](model.md), resolution test).
- **Calibrate outside the AMBA.** The thresholds come from 2 positives and 5 controls in Buenos Aires. We'd build a calibration set per region and recalibrate ([`insomnia-index.md`](insomnia-index.md)). The 7 Argentine frames already processed have no known status, so they need field or registry labels first ([`argentina.md`](argentina.md)).
- **Reproducibility:**
  - a single entry point to run a frame end to end;
  - pinned dependencies;
  - CI that runs the tests;
  - moving heavy data out of git (release assets or DVC).
- **Web:**
  - deploy it at dumpsite.earth;
  - measure whether the 0.4 threshold for possible new sites and the low threshold for "not enough" sites hold up, since the team set both for the map without calibration ([`../web/README.md`](../web/README.md)).

## Next months: a better model
- **Longer series.** Use the NISAR archive as it grows past a year, to separate seasonal from permanent activity. Add a "before" for recent closures with Sentinel-1 or SAOCOM, which Luján doesn't have today ([`idea.md`](idea.md)).
- **Small sites.** Below about 40 ha the open-versus-closed AUC drops to 0.76, and below 10 ha the radar can't tell ([`model.md`](model.md)). Options:
  - recalibrated 20 m coherence;
  - native 10 m GCOV;
  - front variables that depend less on size.
- **Less US bias.** 179 of the 193 known-status sites the radar measured are in the US and come from the EPA ([`results.md`](results.md)). Add Argentine provincial registries (OPDS, the ACUMAR 2017 dump-site baseline), the CIM-FADU database and other national inventories ([`data.md`](data.md), [`argentina.md`](argentina.md)). Clean the Argentine catalog too: 9 sites aren't municipal waste.
- **Per-blob classifier.** Its AUC is 0.79, which isn't enough as a verdict ([`model.md`](model.md)). Ways to improve it:
  - the pending negative classes: FIRMS fires, GHSL settlements, a DEM layover mask;
  - the proposed optical CNN (ResNet-50 SSL4EO-S12) as one more variable.
- **Calibrated scores.** Turn `p_abierto` into a calibrated probability, validated on held-out frames, and show the uncertainty in the web.

## Long term: an operational tool
- **Monitoring.** Ingest each new NISAR pass every 12 days automatically and alert when a closed site "wakes up".
- **Scale.** Process all of Argentina, or any region on demand:
  - processing close to the data (AWS us-west-2);
  - the backend API the web is already prepared for (`web/src/data/api.ts`).
- **Field validation with authorities.** Work with municipal and provincial authorities, and feed their findings back into the labels.
- **Open data.** Publish the catalog and the verdicts as an open dataset, with its licenses.
- **Engineering cleanup:**
  - `motor/` as a package;
  - typed data contracts;
  - consistent naming in English;
  - fixtures with real data for the tests.
