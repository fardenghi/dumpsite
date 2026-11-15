#!/usr/bin/env bash
# Recorta y re-temporiza el clip de 10 s de Higgsfield (satelite.py) en el clip de 4,73 s que usan los dos videos:
# satélite 5 s -> 1 s, nubes 2,5 s -> 1 s, basural 2,54 s -> 2,72 s (un poco más lento). Deja public/clip1-ai.mp4.
# Uso (desde video/compartido/higgsfield):  ./montar_clip.sh salidas/satelite-draft-203402.mp4
set -euo pipefail
ENTRADA="${1:?Pasá el mp4 de Higgsfield}"
DESTINO="$(cd "$(dirname "$0")/../.." && pwd)/public/clip1-ai.mp4"
ffmpeg -loglevel error -y -i "$ENTRADA" -filter_complex \
  "[0:v]trim=0:5,setpts=(PTS-STARTPTS)/5[a];[0:v]trim=5:7.5,setpts=(PTS-STARTPTS)/2.5[b];[0:v]trim=7.5:10.04,setpts=(PTS-STARTPTS)*1.07[c];[a][b][c]concat=n=3:v=1:a=0,fps=30[v]" \
  -map "[v]" -c:v libx264 -pix_fmt yuv420p -crf 16 "$DESTINO"
ffprobe -v error -show_entries format=duration -of csv=p=0 "$DESTINO"
echo "Listo: $DESTINO (si cambia la duración, ajustar CLIP_IA en espanol/Local.tsx y el playbackRate de EscenaIA)"
