#!/bin/bash
# Script de arranque de insomnio-vm para leer Sentinel-2 (`optico_catalogo_frames.py correr`) y comparar con una laptop.
# Lee de los metadatos: optico-tgz-b64 (tar.gz en base64 con herramientas/*.py y trabajo.json), upload-url-optico
# (URL de subida de un solo uso de GCS), hilos-optico (opcional, 16) y tanda-optico (cada tanda corre una vez).
# Avance por el puerto serie, con prefijo INSOMNIO:. Al terminar apaga la VM.
md() { curl -sf -H "Metadata-Flavor: Google" "http://metadata.google.internal/computeMetadata/v1/instance/attributes/$1"; }
T=$(md tanda-optico || echo 1)
[ -f /opt/optico-hecho-$T ] && { echo "INSOMNIO: óptico tanda $T ya corrió"; exit 0; }
export HOME=/root USER=root DEBIAN_FRONTEND=noninteractive
log() { echo "INSOMNIO: $*"; }
D=/opt/optico; rm -rf $D; mkdir -p $D; cd $D
md optico-tgz-b64 | base64 -d | tar xz || { log "óptico: no pude desarmar el código"; exit 1; }
t0=$(date +%s)
[ -x /opt/venv-optico/bin/python ] || { apt-get update -qq; apt-get install -y -qq python3-venv >/dev/null; python3 -m venv /opt/venv-optico; }
/opt/venv-optico/bin/pip install -q numpy pandas pyarrow shapely rasterio > /var/log/pip-optico.log 2>&1 || { log "óptico: falló pip: $(tail -1 /var/log/pip-optico.log)"; }
log "óptico tanda $T inicio $(date -u +%FT%TZ): $(nproc) vCPU, entorno listo en $(( $(date +%s) - t0 )) s"
/opt/venv-optico/bin/python herramientas/optico_catalogo_frames.py correr --trabajo trabajo.json --salida optico.parquet --hilos $(md hilos-optico || echo 16) > correr.log 2>&1
grep "^OPTICO" correr.log | sed 's/^/INSOMNIO: /'
[ -f optico.parquet ] || log "óptico ERROR: $(tail -3 correr.log | tr '\n' ' ')"
tar czf /tmp/optico.tgz optico.parquet correr.log 2>/dev/null
U=$(md upload-url-optico); code=sin-url
[ -n "$U" ] && code=$(curl -sS -o /dev/null -w "%{http_code}" -X PUT -H "Content-Type: application/gzip" --upload-file /tmp/optico.tgz "$U")
touch /opt/optico-hecho-$T
log "óptico tanda $T fin, subida http=$code; apago la VM"
shutdown -h now
