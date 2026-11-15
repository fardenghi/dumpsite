# VM to process NISAR

A single CPU VM with lots of RAM, close to where the data is. No GPU or Kubernetes: the download is the bottleneck and the computation is light.

## The existing VM (14/11/2026)
| | |
|---|---|
| GCP project | `basurales-514714` (billing account with credits) |
| Name | `insomnio-vm`, zone `us-west1-b` |
| Type | `n2-custom-12-98304` (12 vCPU, 96 GB) |
| Disk | 200 GB `pd-balanced`; the 35 `.h5` files (100 GB) are in `/mnt/datos` |
| Service account | none (`--no-service-account`): the VM doesn't touch GCP |
| Status | **stopped** (the last run, on 15/11, shut itself down when it finished; the Earthdata token was already removed from the metadata). Start it with `gcloud compute instances start insomnio-vm --zone=us-west1-b` |

**Why 12 vCPU and not 16:** the account's global quota is `CPUS_ALL_REGIONS = 12` and can't be raised. `n2-highmem-12` doesn't exist, so it's a custom N2 with the maximum memory (8 GB per vCPU). The 200 GB disk comes from the `SSD_TOTAL_GB = 250` quota in us-west1.

**Measured times** (details in "Full AMBA run" below): downloading the 35 files (100 GB) takes 531 s; processing and the index take 8 s at 80 m and ~50 s at 20 m.

## Why us-west1
- The NISAR data is in NASA Earthdata Cloud, in **AWS us-west-2 (Oregon)**. The closest regions are **GCP us-west1 (Oregon)** and **Azure West US 2 (Washington)**.
- **Lots of RAM:** stacking 15 pairs at 20 m is 15-30 GB in memory.
- **No GPU:** it doesn't speed up the download and the computation is already fast on CPU.

## Spending cap (automatic)
- **Budget "Space Apps tope 275"** on the billing account, filtered to the project, from 1/11/2026 to 31/12/2027 and **without subtracting credits**: it measures what's consumed from the credits. It alerts at 91 % (USD 250) and at 100 % (USD 275).
- **Automatic cutoff:** the budget publishes to the `corte-budget` Pub/Sub topic. The `corte-budget` Cloud Function (us-west1, code in `corte-budget/`) **stops every VM in the project** when the cost reaches the budget amount. Disks and data are kept.
- **Tested on 14/11:** with a message of 10 out of 275 it does nothing; with 275 out of 275 it stopped `insomnio-vm`.
- **It's not an exact cap:** GCP reports costs with hours of delay. That's why the cutoff is at 275 and not at 300.
- The function runs with the `corte-budget` service account, which has `compute.instanceAdmin.v1`, `cloudbuild.builds.builder` and permission to invoke the function.

## Running it without SSH (as done on 14/11)
From a cloud session there's no SSH: the proxy only lets HTTPS through. Everything is handled with the Compute API:
1. **Code:** the repo was private and the VM has no GitHub token, so `pipeline_insomnio.py`, `manchas.py` and `requirements.txt` go as VM metadata (`pipeline-py`, `manchas-py`, `requirements-txt`).
2. **Earthdata token:** each person their own, in the `earthdata-token` metadata key. It's loaded from the person's machine, never through chat or into the repo:
   ```bash
   gcloud compute instances add-metadata insomnio-vm --zone=us-west1-b --metadata=earthdata-token=YOUR_TOKEN
   ```
   Anyone with read access to the project can read it. Remove it with `gcloud compute instances remove-metadata insomnio-vm --zone=us-west1-b --keys=earthdata-token`.
3. **What runs:** a startup script (`vm-sin-ssh/`) that runs once and writes its progress to the serial port, with the `INSOMNIO:` prefix:
   - `arranque-prueba.sh` tests downloading, `procesar --remoto` and GCOV;
   - `arranque-pipeline.sh` runs the full pipeline;
   - `arranque-subida.sh` uploads `/opt/salidas` to a single-use upload URL.
   - `arranque-frames.sh` (prompt 6, 15/11) runs `buscar` and `procesar --remoto` over a list of frames, uploads one tar per frame to its single-use URL (`upload-url-<FRAME>`) and **shuts the VM down when it finishes**. The code goes in a single metadata key (`codigo-tgz-b64`). That's how 18 of the 20 new frames were read (`../../docs/results.md`).
   - `arranque-optico.sh` (15/11) runs `optico_catalogo_frames.py correr` and shuts the VM down. It was used for comparison: the same Sentinel-2 reading took 319 s on the VM and 254 s in a container. **For the optical step the VM doesn't help.**
   It's loaded with `add-metadata --metadata-from-file=startup-script=...` and run with `gcloud compute instances reset`.
4. **Progress:** `gcloud compute instances get-serial-port-output insomnio-vm --zone=us-west1-b | grep INSOMNIO`.
5. **Results:** the VM has no GCP permissions. Someone with permissions creates a resumable upload session on the `gs://basurales-514714-salidas` bucket and passes the URL in the `upload-url` metadata key. The full tar of `salidas/`, with the 20 m crops, ended up in `gs://basurales-514714-salidas/salidas-v3.tgz` (1.1 GB). The small products are in `../../data/salidas/`.

**gcloud in a cloud session:** the environment sets `CLOUDSDK_AUTH_ACCESS_TOKEN` to a placeholder value for the proxy. If no Google credential is loaded in the environment, run `env -u CLOUDSDK_AUTH_ACCESS_TOKEN gcloud ...` after `gcloud auth login --no-launch-browser`. The organization policy (`iam.disableServiceAccountKeyCreation`) doesn't allow creating service account keys; instead of keys, impersonation of the `claude-vm` account is used (`auth/impersonate_service_account`).

## Running it with SSH (from a laptop)
```bash
gcloud compute instances start insomnio-vm --zone=us-west1-b
```
```bash
gcloud compute ssh insomnio-vm --zone=us-west1-b
```
To clone a private repo inside the VM you need a GitHub token or an SSH key of whoever clones it. Then set it up with `bash dumpsite/motor/infra/setup-vm.sh` (the `.h5` files are already in `/mnt/datos`, so `bajar` doesn't download them again):
```bash
export EARTHDATA_TOKEN='...'
```
```bash
python motor/pipeline_insomnio.py todo --datos /mnt/datos --salida data/salidas --orbitas 10 161 --capa 80m
```
**Without downloading the .h5 files** (remote windowed reading; tested, ~240 MB per GUNW):
```bash
python motor/pipeline_insomnio.py buscar --salida data/salidas && python motor/pipeline_insomnio.py procesar --remoto --salida data/salidas --capa 80m && python motor/pipeline_insomnio.py indice --salida data/salidas --capa 80m
```
**Other frames** (stage 4; the frames come from `data/catalogos/frames.json`). Each one writes to `salidas/<FRAME>/`:
```bash
python motor/pipeline_insomnio.py todo --frame todos --remoto --salida data/salidas
```
If remote reading misbehaves, download instead: `todo --frame todos --datos /mnt/datos --borrar` downloads, crops and deletes each `.h5`, frame by frame, so the 200 GB disk never holds more than one frame. Details in `../README.md`.

Use `tmux` so it doesn't stop if SSH drops (`tmux new -s nisar`; to come back, `tmux attach -t nisar`).

## Shutting down (important)
```bash
gcloud compute instances stop insomnio-vm --zone=us-west1-b
```
When the hackathon is over, delete it together with the disk and the bucket: `gcloud compute instances delete insomnio-vm --zone=us-west1-b` and `gcloud storage rm -r gs://basurales-514714-salidas`.

## Azure alternative
`Standard_E16s_v5` (16 vCPU, 128 GB) in `westus2`, 300 GB Premium SSD, Ubuntu 24.04:
```bash
az group create --name spaceapps-rg --location westus2
```
```bash
az vm create --resource-group spaceapps-rg --name insomnio-vm --image Ubuntu2404 --size Standard_E16s_v5 --os-disk-size-gb 300 --storage-sku Premium_LRS --admin-username equipo --generate-ssh-keys
```
To shut it down without paying for compute: `az vm deallocate --resource-group spaceapps-rg --name insomnio-vm`.

## Full AMBA run (14/11/2026)
The first run with all the NISAR data over the AMBA: 15 GUNWs and 20 GCOVs from orbits 10 and 161, on a GCP VM in us-west1.

| Step | Measured |
|---|---|
| `buscar` | 15 GUNWs and 20 GCOVs, in 2 s |
| `bajar` (everything) | 35 files, 100 GB, in 531 s (~190 MB/s). A GUNW weighs ~2.1 GB and a GCOV ~3.4 GB |
| `procesar --remoto` | 8 GUNWs from orbit 10 in 20 s, reading ~240 MB per file (~11 % of the file) |
| `procesar` + `indice` | 8 s at 80 m and ~50 s at 20 m, 35 of 35 files without errors |

That run was the v0 of the index: with an absolute coherence threshold, the river came out as the largest blob and no known landfill passed the threshold. That's where the water mask, the comparison with the surroundings and the calibration in `docs/insomnia-index.md` came from.
