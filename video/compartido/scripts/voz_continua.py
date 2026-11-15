"""Arma una sola pista de voz continua para el video en castellano, sin huecos de silencio digital entre frases.

voz_grabada.py deja cada frase en su propio .wav y entre una y otra queda silencio absoluto: con voz grabada eso se
nota, porque el ruido de fondo de la sala desaparece de golpe en cada corte. Este script toma un tramo de "ruido de
sala" de la toma (sin voz), lo repite a lo largo de todo el video y encima pone cada frase en su lugar, con fundidos
cortos en los bordes. El resultado es public/<audio>/voz-completa.wav, que Local.tsx reproduce como una sola pista.

Correr después de voz_grabada.py (que borra los .wav de la carpeta):
  python3 -I compartido/scripts/voz_continua.py --toma grabacion/toma-v1-limpia.wav --sala 90.45:92.15 --sala 70.70:71.80

Cada --sala es un tramo de la toma (en segundos) donde solo hay ruido de fondo. Conviene usar la toma ya limpia
(limpiar_toma.sh) para que el ruido de sala sea el mismo que queda debajo de la voz.
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
    ap.add_argument("--audio", default="voz-es", help="carpeta dentro de public/ con las frases")
    ap.add_argument("--toma", required=True, help="toma de donde sale el ruido de sala")
    ap.add_argument("--sala", action="append", required=True, help="tramo inicio:fin (s) con solo ruido de fondo; se puede repetir")
    ap.add_argument("--fundido-ms", type=float, default=40.0, help="fundido entre ruido de sala y frase")
    args = ap.parse_args()

    voz_path = VIDEO / args.voz
    voz = json.loads(voz_path.read_text())
    n = int(round(voz["duracion_video"] * SR))

    # 1. cama de ruido de sala: trozos de los tramos elegidos, encadenados con fundidos para que no se note la costura
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

    # 2. cada frase reemplaza a la cama en su lugar, con un fundido corto en cada borde
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
