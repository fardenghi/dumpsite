#!/usr/bin/env bash
# Limpia una toma de voz grabada antes de cortarla: saca el ruido de fondo y nivela el volumen de toda la toma de una vez
# (así el ruido que queda es parejo entre frases, en vez de que loudnorm lo suba o lo baje frase por frase).
#   compartido/scripts/limpiar_toma.sh grabacion/toma-v1.mp4 grabacion/toma-v1-limpia.wav [inicio_silencio fin_silencio] [ganancia_dB]
# El tramo de silencio (por defecto 0.3-2.9 s) es de donde afftdn aprende el ruido: tiene que ser solo ruido, sin voz.
# La ganancia lleva la toma a unos -16 LUFS: medirla con  ffmpeg -i toma -af loudnorm=print_format=summary -f null -  (input_i) y usar -16 - input_i.
set -euo pipefail
ENTRADA="$1"; SALIDA="$2"; DESDE="${3:-0.3}"; HASTA="${4:-2.9}"; GANANCIA="${5:-14.2}"
ffmpeg -hide_banner -loglevel error -y -i "$ENTRADA" \
  -af "highpass=f=70,asendcmd=c='${DESDE} afftdn sn start; ${HASTA} afftdn sn stop',afftdn=nr=20:nf=-50:tn=1,volume=${GANANCIA}dB,alimiter=limit=0.84:attack=5:release=60:level=disabled" \
  -ar 48000 -ac 1 -sample_fmt s16 "$SALIDA"
echo "Escrito $SALIDA"
