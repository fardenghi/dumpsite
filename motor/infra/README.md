# VM para procesar NISAR (Idea B)

Una sola VM de CPU con mucha RAM, cerca de donde están los datos. Sin GPU ni Kubernetes: la descarga es el cuello de botella y el cálculo es liviano.

## La VM que existe (14/11/2026)
| | |
|---|---|
| Proyecto GCP | `basurales-514714` (cuenta de facturación con créditos) |
| Nombre | `insomnio-vm`, zona `us-west1-b` |
| Tipo | `n2-custom-12-98304` (12 vCPU, 96 GB) |
| Disco | 200 GB `pd-balanced`; los 35 `.h5` (100 GB) están en `/mnt/datos` |
| Cuenta de servicio | ninguna (`--no-service-account`): la VM no toca GCP |
| Estado | **apagada** (la última corrida, del 15/11, se apagó sola al terminar; el token de Earthdata ya se borró de los metadatos). Se prende con `gcloud compute instances start insomnio-vm --zone=us-west1-b` |

**Por qué 12 vCPU y no 16:** la cuota global de la cuenta es `CPUS_ALL_REGIONS = 12` y no se puede subir. `n2-highmem-12` no existe, así que es una N2 a medida con el máximo de memoria (8 GB por vCPU). Los 200 GB de disco vienen de la cuota `SSD_TOTAL_GB = 250` en us-west1.

**Tiempos medidos** (detalle en `../idea/corrida-completa-vm.md`): bajar los 35 archivos (100 GB) tarda 531 s; procesar e índice tardan 8 s a 80 m y ~50 s a 20 m.

## Por qué us-west1
- Los datos de NISAR están en NASA Earthdata Cloud, en **AWS us-west-2 (Oregón)**. Las regiones más cercanas son **GCP us-west1 (Oregón)** y **Azure West US 2 (Washington)**.
- **Mucha RAM:** apilar 15 pares a 20 m son 15-30 GB en memoria.
- **Sin GPU:** no acelera la descarga y el cálculo ya es rápido en CPU.

## Tope de gasto (automático)
- **Budget "Space Apps tope 275"** en la cuenta de facturación, filtrado al proyecto, del 1/11/2026 al 31/12/2027 y **sin descontar créditos**: mide lo que se consume de los créditos. Avisa al 91 % (USD 250) y al 100 % (USD 275).
- **Corte automático:** el budget publica en el tema de Pub/Sub `corte-budget`. La Cloud Function `corte-budget` (us-west1, código en `corte-budget/`) **detiene todas las VMs del proyecto** cuando el costo llega al monto del budget. Los discos y los datos se conservan.
- **Probado el 14/11:** con un mensaje de 10 de 275 no hace nada; con 275 de 275 detuvo `insomnio-vm`.
- **No es un tope exacto:** GCP informa los costos con horas de atraso. Por eso el corte está en 275 y no en 300.
- La función corre con la cuenta de servicio `corte-budget`, que tiene `compute.instanceAdmin.v1`, `cloudbuild.builds.builder` y permiso de invocar la función.

## Correrla sin SSH (como se hizo el 14/11)
Desde una sesión de Claude Code en la nube no hay SSH: el proxy sólo deja pasar HTTPS. Todo se maneja con la API de Compute:
1. **Código:** el repo es privado y la VM no tiene token de GitHub, así que `pipeline_insomnio.py`, `manchas.py` y `requirements.txt` van como metadatos de la VM (`pipeline-py`, `manchas-py`, `requirements-txt`).
2. **Token de Earthdata:** cada uno el suyo, en el metadato `earthdata-token`. Se carga desde la máquina de la persona, nunca por el chat ni en el repo:
   ```bash
   gcloud compute instances add-metadata insomnio-vm --zone=us-west1-b --metadata=earthdata-token=TU_TOKEN
   ```
   Lo puede leer cualquiera con acceso de lectura al proyecto. Se borra con `gcloud compute instances remove-metadata insomnio-vm --zone=us-west1-b --keys=earthdata-token`.
3. **Qué corre:** un script de arranque (`vm-sin-ssh/`) que corre una vez y escribe el avance en el puerto serie, con prefijo `INSOMNIO:`:
   - `arranque-prueba.sh` prueba bajar, `procesar --remoto` y GCOV;
   - `arranque-pipeline.sh` corre el pipeline completo;
   - `arranque-subida.sh` sube `/opt/salidas` a una URL de subida de un solo uso.
   - `arranque-frames.sh` (prompt 6, 15/11) corre `buscar` y `procesar --remoto` sobre una lista de frames, sube un tar por frame a su URL de un solo uso (`upload-url-<FRAME>`) y **apaga la VM al terminar**. El código va en un solo metadato (`codigo-tgz-b64`). Así se leyeron 18 de los 20 frames nuevos (`../idea/etapa4-manchas.md`).
   - `arranque-optico.sh` (15/11) corre `optico_catalogo_frames.py correr` y apaga la VM. Se usó para comparar: la misma lectura de Sentinel-2 tardó 319 s en la VM y 254 s en un contenedor. **Para el óptico la VM no ayuda.**
   Se carga con `add-metadata --metadata-from-file=startup-script=...` y se ejecuta con `gcloud compute instances reset`.
4. **Avance:** `gcloud compute instances get-serial-port-output insomnio-vm --zone=us-west1-b | grep INSOMNIO`.
5. **Resultados:** la VM no tiene permisos de GCP. Quien tiene permisos crea una sesión de subida resumible en el bucket `gs://basurales-514714-salidas` y pasa la URL en el metadato `upload-url`. El tar completo de `salidas/`, con los recortes de 20 m, quedó en `gs://basurales-514714-salidas/salidas-v3.tgz` (1,1 GB). Los productos chicos están en `../salidas/`.

**gcloud en Claude Code en la nube:** el entorno define `CLOUDSDK_AUTH_ACCESS_TOKEN` con un valor de relleno para el proxy. Si no hay una credencial de Google cargada en el entorno, hay que correr `env -u CLOUDSDK_AUTH_ACCESS_TOKEN gcloud ...` después de `gcloud auth login --no-launch-browser`. La política de la organización (`iam.disableServiceAccountKeyCreation`) no deja crear claves de cuentas de servicio; en lugar de claves se usa la personificación de `claude-vm` (`auth/impersonate_service_account`).

## Correrla con SSH (desde una laptop)
```bash
gcloud compute instances start insomnio-vm --zone=us-west1-b
```
```bash
gcloud compute ssh insomnio-vm --zone=us-west1-b
```
Para clonar el repo privado adentro de la VM hace falta un token de GitHub o una llave SSH de quien lo clona. Después se prepara con `bash nasa-space-apps-context/idea-basurales-nisar/infra/setup-vm.sh` (los `.h5` ya están en `/mnt/datos`, así que `bajar` no vuelve a bajarlos):
```bash
export EARTHDATA_TOKEN='...'
```
```bash
python herramientas/pipeline_insomnio.py todo --datos /mnt/datos --salida salidas --orbitas 10 161 --capa 80m
```
**Sin bajar los .h5** (lectura remota por ventana; probada, ~240 MB por GUNW):
```bash
python herramientas/pipeline_insomnio.py buscar --salida salidas && python herramientas/pipeline_insomnio.py procesar --remoto --salida salidas --capa 80m && python herramientas/pipeline_insomnio.py indice --salida salidas --capa 80m
```
**Otros frames** (etapa 4; los frames salen de `data/frames.json`). Cada uno escribe en `salidas/<FRAME>/`:
```bash
python herramientas/pipeline_insomnio.py todo --frame todos --remoto --salida salidas
```
Si la lectura remota anda mal, bajando: `todo --frame todos --datos /mnt/datos --borrar` baja, recorta y borra cada `.h5`, frame por frame, así el disco de 200 GB nunca junta más de un frame. Detalle en `../herramientas/README.md`.

Usen `tmux` para que no se corte si se cae el SSH (`tmux new -s nisar`; para volver, `tmux attach -t nisar`).

## Apagar (importante)
```bash
gcloud compute instances stop insomnio-vm --zone=us-west1-b
```
Al terminar el hackathon, bórrenla junto con el disco y el bucket: `gcloud compute instances delete insomnio-vm --zone=us-west1-b` y `gcloud storage rm -r gs://basurales-514714-salidas`.

## Alternativa en Azure
`Standard_E16s_v5` (16 vCPU, 128 GB) en `westus2`, 300 GB Premium SSD, Ubuntu 24.04:
```bash
az group create --name spaceapps-rg --location westus2
```
```bash
az vm create --resource-group spaceapps-rg --name insomnio-vm --image Ubuntu2404 --size Standard_E16s_v5 --os-disk-size-gb 300 --storage-sku Premium_LRS --admin-username equipo --generate-ssh-keys
```
Para apagarla sin que cobre el cómputo: `az vm deallocate --resource-group spaceapps-rg --name insomnio-vm`.
