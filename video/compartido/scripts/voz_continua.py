"""Builds a single continuous voice track for the Spanish video, without gaps of digital silence between sentences.

voz_grabada.py leaves each sentence in its own .wav with absolute silence between them: with a recorded voice that
shows, because the room's background noise disappears suddenly at every cut. This script takes a stretch of "room
tone" from the take (no voice), repeats it along the whole video and puts each sentence on top in its place, with
short fades at the edges. The result is public/<audio>/voz-completa.wav, which Local.tsx plays as a single track.

Run after voz_grabada.py (which deletes the .wav files in the folder):
  python3 -I compartido/scripts/voz_continua.py --toma grabacion/toma-v1-limpia.wav --sala 90.45:92.15 --sala 70.70:71.80

Each --sala is a stretch of the take (in seconds) with only background noise. It's best to use the already cleaned take
(limpiar_toma.sh) so the room tone is the same one left under the voice.
"""
import argparse
import array
import json
import pathlib
import random
import subprocess
import wave

VIDEO = pathlib.Path(__file__).resolve().parents[2]
SR = 48000


def leer(path, desde=None, hasta=None):
    cmd = ["ffmpeg", "-loglevel", "error"]
    if desde is not None:
        cmd += ["-ss", f"{desde:.3f}", "-to", f"{hasta:.3f}"]
    cmd += ["-i", str(path), "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"]
    datos = array.array("h")
    datos.frombytes(subprocess.run(cmd, capture_output=True, check=True).stdout)
    return [float(x) for x in datos]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--voz", default="espanol/voz-es.json")
    ap.add_argument("--audio", default="voz-es", help="folder inside public/ with the sentences")
    ap.add_argument("--toma", required=True, help="take the room tone comes from")
    ap.add_argument("--sala", action="append", required=True, help="start:end stretch (s) with only background noise; can be repeated")
    ap.add_argument("--fundido-ms", type=float, default=40.0, help="fundido entre ruido de sala y frase")
    args = ap.parse_args()

    voz_path = VIDEO / args.voz
    voz = json.loads(voz_path.read_text())
    n = int(round(voz["duracion_video"] * SR))

    # 1. room-tone bed: pieces of the chosen stretches, chained with fades so the seam doesn't show
    trozos = []
    for t in args.sala:
        a, b = (float(x) for x in t.split(":"))
        trozos.append(leer(VIDEO / args.toma, a, b))
    xf = int(0.05 * SR)
    rnd = random.Random(7)
    cama = []
    while len(cama) < n:
        tr = rnd.choice(trozos)
        ini = rnd.randrange(0, max(1, len(tr) - xf * 4))
        pedazo = tr[ini:]
        if not cama:
            cama.extend(pedazo)
            continue
        k = min(xf, len(pedazo), len(cama))
        base = len(cama) - k
        for i in range(k):
            w = (i + 1) / (k + 1)
            cama[base + i] = cama[base + i] * (1 - w) + pedazo[i] * w
        cama.extend(pedazo[k:])
    salida = cama[:n]

    # 2. each sentence replaces the bed in its place, with a short fade at each edge
    f = max(1, int(args.fundido_ms / 1000 * SR))
    for fr in voz["frases"]:
        frase = leer(VIDEO / "public" / fr["archivo"])
        s = int(round(fr["inicio"] * SR))
        largo = min(len(frase), n - s)
        for i in range(largo):
            w = min(1.0, (i + 1) / f, (largo - i) / f)
            salida[s + i] = salida[s + i] * (1 - w) + frase[i] * w

    pcm = array.array("h", (max(-32768, min(32767, int(round(x)))) for x in salida))
    destino = VIDEO / "public" / args.audio / "voz-completa.wav"
    with wave.open(str(destino), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    voz["pista"] = f"{args.audio}/voz-completa.wav"
    voz_path.write_text(json.dumps(voz, ensure_ascii=False, indent=1))
    print(f"Escrito public/{voz['pista']} ({n / SR:.1f} s) y agregado 'pista' a {args.voz}")


if __name__ == "__main__":
    main()
