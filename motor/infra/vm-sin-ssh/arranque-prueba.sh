#!/bin/bash
# Script de arranque de insomnio-vm: prepara la VM y prueba bajar / procesar --remoto / GCOV.
# Corre una sola vez (marca en /opt/insomnio-hecho-v2). Resultados con prefijo INSOMNIO: en el puerto serie.
exec > >(tee -a /var/log/insomnio.log) 2>&1
[ -f /opt/insomnio-hecho-v2 ] && { echo "INSOMNIO: ya corrió antes"; exit 0; }
export HOME=/root USER=root DEBIAN_FRONTEND=noninteractive
log() { echo "INSOMNIO: $*"; }
IF=$(ip route show default | awk '{print $5; exit}')
rx() { cat /sys/class/net/$IF/statistics/rx_bytes; }
medir() {  # medir <etiqueta> <comando...>
  local et=$1; shift; local b0=$(rx) t0=$(date +%s.%N)
  "$@"; local rc=$?
  local t1=$(date +%s.%N) b1=$(rx)
  log "$et rc=$rc segundos=$(echo "$t1 - $t0" | bc) MB_recibidos=$(( (b1 - b0) / 1000000 ))"
}

log "inicio $(date -u +%FT%TZ) $(nproc) vCPU"
apt-get update -y -q && apt-get install -y -q git bc python3-venv python3-pip tmux htop
# El repo es privado: los archivos llegan por metadatos.
D=/opt/insomnio; mkdir -p $D/herramientas && cd $D
md() { curl -sf -H "Metadata-Flavor: Google" "http://metadata.google.internal/computeMetadata/v1/instance/attributes/$1"; }
md pipeline-py > herramientas/pipeline_insomnio.py; md manchas-py > herramientas/manchas.py; md requirements-txt > herramientas/requirements.txt
log "archivos: $(wc -c herramientas/* | tail -1)"
mkdir -p /mnt/datos
medir setup bash -c "python3 -m venv .venv && .venv/bin/pip install -q --upgrade pip && .venv/bin/pip install -q -r herramientas/requirements.txt"
. .venv/bin/activate
log "earthaccess $(python -c 'import earthaccess; print(earthaccess.__version__)')"

EARTHDATA_TOKEN=$(curl -sf -H "Metadata-Flavor: Google" \
  http://metadata.google.internal/computeMetadata/v1/instance/attributes/earthdata-token)
export EARTHDATA_TOKEN
[ -n "$EARTHDATA_TOKEN" ] && log "token cargado (${#EARTHDATA_TOKEN} caracteres)" || log "SIN TOKEN"

P=herramientas/pipeline_insomnio.py
S=/opt/salidas; mkdir -p $S

# 1. buscar
medir buscar python $P buscar --salida $S

# 2. procesar --remoto: GUNW de la órbita 10, capa 80 m, sin bajar nada
medir remoto_80m_orb10 python $P procesar --remoto --solo-gunw --orbitas 10 --capa 80m --salida $S --procesos 6
log "recortes remotos: $(ls $S/recortes_80m 2>/dev/null | wc -l)"

# 3. bajar 1 GUNW + 1 GCOV de la órbita 10 (lista reducida)
B=/opt/salidas_bajar; mkdir -p $B
python - "$S/lista_productos.json" "$B/lista_productos.json" <<'EOF'
import json, sys
l = json.load(open(sys.argv[1]))
sel = [next(x for x in l if x["tipo"] == t and x["orbita"] == 10) for t in ("GUNW", "GCOV")]
json.dump(sel, open(sys.argv[2], "w"), indent=1)
for x in sel: print("INSOMNIO: a bajar", x["tipo"], x["nombre"])
EOF
medir bajar_1gunw_1gcov python $P bajar --datos /mnt/datos --salida $B --orbitas 10 --hilos 8
ls -l --block-size=M /mnt/datos | sed 's/^/INSOMNIO: archivo /'

# 4. procesar local (incluye el primer GCOV -> eco en dB) a 80 m
medir local_80m python $P procesar --datos /mnt/datos --salida $B --orbitas 10 --capa 80m --procesos 2
python - $B/recortes_80m <<'EOF'
import glob, sys, numpy as np
for r in sorted(glob.glob(sys.argv[1] + "/*.npz")):
    d = np.load(r); v = d["valor"].astype(np.float32)
    print(f"INSOMNIO: recorte {r.split('/')[-1]} tipo={d['tipo']} cobertura={np.isfinite(v).mean():.0%} "
          f"p5={np.nanpercentile(v,5):.2f} p50={np.nanpercentile(v,50):.2f} p95={np.nanpercentile(v,95):.2f}")
EOF

touch /opt/insomnio-hecho-v2
log "fin $(date -u +%FT%TZ)"
