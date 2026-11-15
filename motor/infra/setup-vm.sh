#!/usr/bin/env bash
# Prepara una VM Ubuntu 24.04 para procesar NISAR (Idea B). Se corre una vez, desde el home.
set -euo pipefail

sudo apt-get update -y
sudo apt-get install -y python3-venv python3-pip git tmux htop

# Carpeta para los .h5 (grandes): fuera del repo.
sudo mkdir -p /mnt/datos
sudo chown "$USER" /mnt/datos

cd "$(dirname "$0")/../.."   # raíz del repo
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r motor/requirements.txt

echo
echo "Listo. Próximos pasos:"
echo "  export EARTHDATA_TOKEN='...'   (token de https://urs.earthdata.nasa.gov/, nunca en el repo)"
echo "  source .venv/bin/activate"
echo "  python motor/pipeline_insomnio.py todo --datos /mnt/datos --salida data/salidas --orbitas 10 161 --capa 80m"
