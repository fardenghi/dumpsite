# VM para procesar NISAR (Idea B)

Una sola VM de CPU con mucha RAM, cerca de donde están los datos. Sin GPU, Kubernetes ni buckets: la descarga es el cuello de botella y el cálculo es liviano.

## Por qué esta VM
- Los datos de NISAR están en NASA Earthdata Cloud, en **AWS us-west-2 (Oregón)**. Las regiones más cercanas son **GCP us-west1 (Oregón)** y **Azure West US 2 (Washington)**.
- **Mucha RAM:** apilar unos 15 pares a 20 m son 15-30 GB en memoria.
- **16 vCPU:** se procesan los pares en paralelo, y la VM tiene más ancho de banda de red.
- **Sin GPU:** no acelera la descarga, el cálculo ya es rápido en CPU y la cuota de GPU suele estar en cero en cuentas nuevas.

| | GCP (recomendada) | Azure (alternativa) |
|---|---|---|
| Tipo | `n2-highmem-16` (16 vCPU, 128 GB) | `Standard_E16s_v5` (16 vCPU, 128 GB) |
| Región | `us-west1` (zona `us-west1-b`) | `westus2` |
| Disco | 300 GB SSD (`pd-ssd`) | 300 GB Premium SSD |
| Sistema | Ubuntu 24.04 LTS | Ubuntu 24.04 LTS |
| Costo aprox. | del orden de USD 1/h (confirmar en la calculadora oficial) | del orden de USD 1/h |

Con USD 300 + 200 de créditos alcanza de sobra: 48 h prendida son unos USD 50. **Apáguenla cuando no se use.**

## 1. Crear la VM (la crea una persona del equipo, con su cuenta)

**GCP** (con `gcloud` instalado y logueado, y el proyecto de los créditos seleccionado):
```bash
gcloud compute instances create insomnio-vm --zone=us-west1-b --machine-type=n2-highmem-16 --image-family=ubuntu-2404-lts-amd64 --image-project=ubuntu-os-cloud --boot-disk-size=300GB --boot-disk-type=pd-ssd
```
```bash
gcloud compute ssh insomnio-vm --zone=us-west1-b
```

**Azure** (con `az` instalado y logueado en la suscripción de los créditos):
```bash
az group create --name spaceapps-rg --location westus2
```
```bash
az vm create --resource-group spaceapps-rg --name insomnio-vm --image Ubuntu2404 --size Standard_E16s_v5 --os-disk-size-gb 300 --storage-sku Premium_LRS --admin-username equipo --generate-ssh-keys
```
Para entrar: `ssh equipo@<ip-publica que devuelve el comando>`.

Si el tipo de máquina no está disponible o falta cuota, sirve cualquier equivalente con unos 16 vCPU y 64-128 GB de RAM: GCP `n2-highmem-8` o `e2-highmem-16`; Azure `E8s_v5` o `D16s_v5`.

## 2. Preparar la VM (una vez)
El repo es privado: para clonarlo hace falta un token de GitHub (PAT) o una llave SSH de quien lo clona.
```bash
git clone https://github.com/nicopriotto/nasa-space-apps-context.git
```
```bash
bash nasa-space-apps-context/idea-basurales-nisar/infra/setup-vm.sh
```

## 3. Credenciales de NASA Earthdata (cada uno las suyas, nunca en el repo)
Generar un token en https://urs.earthdata.nasa.gov/ (perfil → Generate Token) y exportarlo **sólo en la sesión de la VM**:
```bash
export EARTHDATA_TOKEN='...'
```
Alternativa: `EARTHDATA_USERNAME` y `EARTHDATA_PASSWORD`. La primera vez que usen la cuenta con datos de ASF tienen que autorizar la aplicación de ASF en el sitio de Earthdata.

## 4. Correr el pipeline
```bash
cd nasa-space-apps-context/idea-basurales-nisar && source .venv/bin/activate
```
```bash
python herramientas/pipeline_insomnio.py todo --datos /mnt/datos --salida salidas --orbitas 10 161 --capa 80m
```
**Sin bajar los .h5** (lectura remota por ventana, sin probar todavía):
```bash
python herramientas/pipeline_insomnio.py buscar --salida salidas && python herramientas/pipeline_insomnio.py procesar --remoto --salida salidas --capa 80m && python herramientas/pipeline_insomnio.py indice --salida salidas --capa 80m
```
Pasos sueltos: `buscar`, `bajar`, `procesar` e `indice` (ver `python herramientas/pipeline_insomnio.py -h`). Corran `--capa 20m` cuando la de 80 m funcione.

Para que no se corte si se cae el SSH, usen `tmux` (`tmux new -s nisar`; para volver, `tmux attach -t nisar`).

## 5. Traer los resultados
Sólo los productos chicos (`salidas/`: PNG, NPZ y JSON) se suben al repo o se copian con `gcloud compute scp` o `scp`. **Los `.h5` no se suben** (están en `.gitignore`).

## 6. Apagar (importante)
**GCP:**
```bash
gcloud compute instances stop insomnio-vm --zone=us-west1-b
```
**Azure** (`deallocate` para que deje de cobrar el cómputo):
```bash
az vm deallocate --resource-group spaceapps-rg --name insomnio-vm
```
Al terminar el hackathon, bórrenla: `gcloud compute instances delete ...` o `az group delete --name spaceapps-rg`.

## Control de gastos
- Configuren una **alerta de presupuesto** en la consola: en GCP, Billing → Budgets & alerts; en Azure, Cost Management → Budgets. Por ejemplo, avisos al 25%, 50% y 90% de los créditos.
- Si después hace falta GPU, **pidan la cuota ahora** (es gratis pedirla y puede tardar horas en aprobarse), pero no la usen si no hay un motivo concreto.
