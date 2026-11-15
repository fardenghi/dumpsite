#!/usr/bin/env bash
# Cleans a recorded voice take before cutting it: removes the background noise and levels the volume of the whole take at once
# (so the remaining noise is even across sentences, instead of loudnorm raising or lowering it sentence by sentence).
#   compartido/scripts/limpiar_toma.sh grabacion/toma-v1.mp4 grabacion/toma-v1-limpia.wav [inicio_silencio fin_silencio] [ganancia_dB]
# The silence stretch (default 0.3-2.9 s) is where afftdn learns the noise: it has to be noise only, no voice.
# The gain takes the take to about -16 LUFS: measure it with  ffmpeg -i toma -af loudnorm=print_format=summary -f null -  (input_i) and use -16 - input_i.
set -euo pipefail
ENTRADA="$1"; SALIDA="$2"; DESDE="${3:-0.3}"; HASTA="${4:-2.9}"; GANANCIA="${5:-14.2}"
ffmpeg -hide_banner -loglevel error -y -i "$ENTRADA" \
  -af "highpass=f=70,asendcmd=c='${DESDE} afftdn sn start; ${HASTA} afftdn sn stop',afftdn=nr=20:nf=-50:tn=1,volume=${GANANCIA}dB,alimiter=limit=0.84:attack=5:release=60:level=disabled" \
  -ar 48000 -ac 1 -sample_fmt s16 "$SALIDA"
echo "Escrito $SALIDA"
