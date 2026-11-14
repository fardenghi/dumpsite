#!/bin/bash
# Script de arranque v3 de insomnio-vm: corre una vez el pipeline completo
# (órbitas 10 y 161, capa 80 m y después 20 m) y escribe el avance y los resúmenes en el puerto serie.
[ -f /opt/pipeline-hecho-v3 ] && { echo "INSOMNIO: v3 ya corrió"; exit 0; }
export HOME=/root USER=root DEBIAN_FRONTEND=noninteractive
log() { echo "INSOMNIO: $*"; }
md() { curl -sf -H "Metadata-Flavor: Google" "http://metadata.google.internal/computeMetadata/v1/instance/attributes/$1"; }
D=/opt/insomnio; S=/opt/salidas; mkdir -p $D/herramientas $S /mnt/datos; cd $D
md pipeline-py > herramientas/pipeline_insomnio.py; md manchas-py > herramientas/manchas.py; md requirements-txt > herramientas/requirements.txt
[ -x .venv/bin/python ] || { python3 -m venv .venv && .venv/bin/pip install -q -r herramientas/requirements.txt; }
export EARTHDATA_TOKEN=$(md earthdata-token)
log "v3 inicio $(date -u +%FT%TZ) $(nproc) vCPU, token ${#EARTHDATA_TOKEN} caracteres"
P="$D/.venv/bin/python herramientas/pipeline_insomnio.py"
t0=$(date +%s)
$P buscar --salida $S --orbitas 10 161 2>&1 | sed 's/^/PIPE: /'
$P bajar --datos /mnt/datos --salida $S --orbitas 10 161 --hilos 8 > /var/log/bajar.log 2>&1
log "bajar rc=$? $(( $(date +%s) - t0 )) s; $(ls /mnt/datos/*.h5 | wc -l) archivos, $(du -sh /mnt/datos | cut -f1)"
grep -iE "error|fail" /var/log/bajar.log | tail -5 | sed 's/^/PIPE: /'
for capa in 80m 20m; do
  $P procesar --datos /mnt/datos --salida $S --orbitas 10 161 --capa $capa --procesos 6 2>&1 | sed 's/^/PIPE: /'
  $P indice --salida $S --orbitas 10 161 --capa $capa 2>&1 | sed 's/^/PIPE: /'
  log "capa $capa lista $(( $(date +%s) - t0 )) s"
  sed "s/^/RESUMEN_$capa: /" $S/resumen_$capa.json
done
du -sh $S $S/* | sed 's/^/PIPE: /'
touch /opt/pipeline-hecho-v3
log "pipeline fin $(date -u +%FT%TZ)"
