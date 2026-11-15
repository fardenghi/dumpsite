#!/bin/bash
# Script de arranque v6 de insomnio-vm (prompt 6): `buscar` y `procesar --remoto` de una lista de frames, uno por uno.
# Por cada frame sube un tar con sus recortes a una URL de subida de un solo uso, y al final apaga la VM.
#
# Metadatos que lee (los carga quien tiene permisos, desde su máquina; ver ../README.md):
#   codigo-tgz-b64     tar.gz en base64 con motor/*.py y data/catalogos/frames.json
#   frames-p6          nombres de los frames, separados por espacios, en el orden en que se procesan
#   upload-url-<FRAME> URL de subida resumible de GCS para el tar de ese frame
#   earthdata-token    token de Earthdata de quien corre (se borra al terminar)
#   procesos-p6        procesos en paralelo de `procesar` (opcional; por defecto 16)
#   tanda-p6           nombre de la tanda (opcional; por defecto 1). Cada tanda corre una sola vez: para volver a
#                      correr (por ejemplo, los frames que fallaron) hay que cambiarla
# El avance sale por el puerto serie con el prefijo INSOMNIO:
#   gcloud compute instances get-serial-port-output insomnio-vm --zone=us-west1-b | grep INSOMNIO
md() { curl -sf -H "Metadata-Flavor: Google" "http://metadata.google.internal/computeMetadata/v1/instance/attributes/$1"; }
T=$(md tanda-p6 || echo 1)
[ -f /opt/p6-hecho-$T ] && { echo "INSOMNIO: p6 tanda $T ya corrió"; exit 0; }
export HOME=/root USER=root DEBIAN_FRONTEND=noninteractive
log() { echo "INSOMNIO: $*"; }
D=/opt/insomnio6; rm -rf $D/data $D/motor; mkdir -p $D; cd $D
md codigo-tgz-b64 | base64 -d | tar xz || { log "p6 no pude desarmar el código"; exit 1; }
PY=/opt/insomnio/.venv/bin/python
$PY -c "import h5py, earthaccess, scipy" 2>/dev/null || {
  log "p6 armo el entorno de Python"
  apt-get update -qq && apt-get install -y -qq python3-venv >/dev/null
  python3 -m venv /opt/insomnio/.venv && /opt/insomnio/.venv/bin/pip install -q numpy scipy h5py earthaccess
}
export EARTHDATA_TOKEN=$(md earthdata-token)
N=$(md procesos-p6 || echo 16)
S=$D/data/salidas
P="$PY $D/motor/pipeline_insomnio.py"
log "p6 tanda $T inicio $(date -u +%FT%TZ): $(nproc) vCPU, $N procesos, token de ${#EARTHDATA_TOKEN} caracteres, frames: $(md frames-p6)"
t0=$(date +%s)
for F in $(md frames-p6); do
  t1=$(date +%s); L=$S/$F/procesar.log; mkdir -p $S/$F
  for i in 1 2 3 4 5 6; do  # la API de ASF devuelve un 502 cada tanto
    $P buscar --frame $F > $S/$F/buscar.log 2>&1 && break
    sleep $((10 * i))
  done
  grep -q "^Lista:" $S/$F/buscar.log || { log "p6 $F ERROR en buscar: $(tail -1 $S/$F/buscar.log)"; continue; }
  for vuelta in 1 2 3; do  # lo que ya está recortado no se vuelve a leer: las vueltas 2 y 3 sólo reintentan los errores
    # Con tope de tiempo: una lectura remota colgada no tiene que frenar a los demás frames (pasó con USA_OH_HAMILTON).
    timeout -k 10 ${TOPE:-600} $P procesar --frame $F --remoto --procesos $N > $L 2>&1; rc=$?
    pkill -9 -f multiprocessing 2>/dev/null
    [ $rc = 0 ] && ! grep -q "ERROR" $L && break
    log "p6 $F vuelta $vuelta: rc=$rc (124 = se pasó del tope), $(grep -c ERROR $L) con error; reintento"
  done
  ok=$(ls $S/$F/recortes_80m/*.npz 2>/dev/null | wc -l)
  tar czf /tmp/$F.tgz -C $S $F
  U=$(md upload-url-$F); code=sin-url
  [ -n "$U" ] && code=$(curl -sS -o /dev/null -w "%{http_code}" -X PUT -H "Content-Type: application/gzip" --upload-file /tmp/$F.tgz "$U")
  log "p6 $F listo: $(sed -n 's/^\(GUNW\|GCOV\): //p' $S/$F/buscar.log | tr '\n' ' ')productos, $ok recortes, $(grep -c ERROR $L) errores, $(du -h /tmp/$F.tgz | cut -f1), subida http=$code, $(( $(date +%s) - t1 )) s"
  rm -f /tmp/$F.tgz
done
touch /opt/p6-hecho-$T
log "p6 tanda $T fin $(date -u +%FT%TZ), $(( $(date +%s) - t0 )) s en total; apago la VM"
shutdown -h now
