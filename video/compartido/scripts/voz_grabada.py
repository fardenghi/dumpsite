"""Uses a voice recorded by a person instead of the Azure synthetic voice (meant for the Spanish video).

It does the same as voz_azure.py but without synthesizing: takes the recordings, converts them to 48 kHz mono WAV,
trims the silence at the start and end, places them one after another with the script's gaps and writes
public/<audio>/frase-N.wav and the timing json (default espanol/voz-es.json). The video scenes and the
subtitles sync themselves with that json: Local.tsx doesn't need changes if the sentence ids don't change.

Two ways to pass the recording (see video/VOZ-GRABADA.md):

  A. One file per sentence, named with the sentence id (problema.wav, dumpsite.m4a, ...), in a folder:
       python3 -I compartido/scripts/voz_grabada.py --carpeta ~/grabacion

  B. A single take with the cuts marked in Audacity (Edit > Labels > Export Labels: a .txt with
     "start<TAB>end<TAB>id" per line, in seconds):
       python3 -I compartido/scripts/voz_grabada.py --toma toma.wav --cortes etiquetas.txt
     With --tiempos-originales the pace of the take is kept (each sentence starts where it starts in the recording)
     instead of using the script's gaps.

The subtitle text comes from the script (espanol/guion-es.json): if the person said something different, first fix
that sentence's "texto" in the script. Needs ffmpeg and ffprobe on the PATH.
"""
import argparse
import json
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from voz_azure import recortar_silencio  # noqa: E402  (same function the synthetic voice uses)

VIDEO = pathlib.Path(__file__).resolve().parents[2]
EXTENSIONES = [".wav", ".mp3", ".m4a", ".ogg", ".opus", ".flac", ".aac", ".webm"]


def a_wav(origen, destino, desde=None, hasta=None):
    cmd = ["ffmpeg", "-loglevel", "error", "-y"]
    if desde is not None:
        cmd += ["-ss", f"{desde:.3f}"]
    if hasta is not None:
        cmd += ["-to", f"{hasta:.3f}"]
    # loudnorm evens out the volume between sentences recorded at different times
    cmd += ["-i", str(origen), "-ac", "1", "-ar", "48000", "-sample_fmt", "s16", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", str(destino)]
    subprocess.run(cmd, check=True)


def leer_cortes(path):
    cortes = {}
    for linea in pathlib.Path(path).read_text().splitlines():
        partes = linea.strip().split("\t")
        if len(partes) >= 3 and partes[0]:
            cortes[partes[2].strip()] = (float(partes[0].replace(",", ".")), float(partes[1].replace(",", ".")))
    return cortes


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--guion", default="espanol/guion-es.json")
    ap.add_argument("--salida", default="espanol/voz-es.json")
    ap.add_argument("--audio", default="voz-es", help="folder inside public/ (old .wav files are deleted)")
    ap.add_argument("--max", type=float, default=180.0, help="maximum video duration in seconds (local: 3 min)")
    ap.add_argument("--carpeta", help="option A: folder with one file per sentence, named with the id")
    ap.add_argument("--toma", help="option B: single recording")
    ap.add_argument("--cortes", help="forma B: etiquetas de Audacity (inicio, fin, id)")
    ap.add_argument("--tiempos-originales", action="store_true", help="option B: keep the pauses of the take")
    ap.add_argument("--umbral", type=int, default=400, help="level below which it counts as silence (raise it if there's background noise)")
    ap.add_argument("--sin-recorte", action="store_true", help="don't trim silences")
    args = ap.parse_args()
    if bool(args.carpeta) == bool(args.toma) or (args.toma and not args.cortes):
        ap.error("usar --carpeta, o --toma junto con --cortes")

    guion = json.loads((VIDEO / args.guion).read_text())
    ids = [f["id"] for f in guion["frases"]]
    salida = VIDEO / "public" / args.audio
    salida.mkdir(parents=True, exist_ok=True)

    # 1. find the recording of each sentence
    fuentes = {}
    if args.carpeta:
        carpeta = pathlib.Path(args.carpeta).expanduser()
        for i in ids:
            hallados = [carpeta / f"{i}{e}" for e in EXTENSIONES if (carpeta / f"{i}{e}").exists()]
            if hallados:
                fuentes[i] = (hallados[0], None, None)
    else:
        cortes = leer_cortes(args.cortes)
        for i in ids:
            if i in cortes:
                fuentes[i] = (pathlib.Path(args.toma).expanduser(), *cortes[i])
    faltan = [i for i in ids if i not in fuentes]
    if faltan:
        sys.exit(f"Faltan grabaciones para: {', '.join(faltan)}. Los ids válidos son: {', '.join(ids)}")

    for viejo in salida.glob("*.wav"):
        viejo.unlink()

    # 2. convert, trim and place in time
    h = guion["huecos_s"]
    t = h["antes_de_la_primera"]
    t0_toma = min(v[1] for v in fuentes.values()) if args.tiempos_originales else None
    frases = []
    for n, f in enumerate(guion["frases"], start=1):
        origen, desde, hasta = fuentes[f["id"]]
        destino = salida / f"frase-{n}.wav"
        a_wav(origen, destino, desde, hasta)
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(destino)],
                                   capture_output=True, text=True, check=True).stdout)
        if not args.sin_recorte:
            dur = recortar_silencio(destino, umbral=args.umbral)
        if args.tiempos_originales:
            t = h["antes_de_la_primera"] + (desde - t0_toma)
        elif n == 2:
            t += h["antes_de_la_2"] - h["entre_frases"]
        texto = " ".join(p["texto"] for p in f["partes"])
        frases.append({"id": f["id"], "archivo": f"{args.audio}/frase-{n}.wav", "inicio": round(t, 2), "duracion": round(dur, 2), "texto": texto})
        print(f"{n:2}. {f['id']:<11} {t:6.2f}-{t + dur:6.2f} s  ({dur:5.2f} s)  {origen.name}")
        if not args.tiempos_originales:
            t += dur + h["entre_frases"]

    for a, b in zip(frases, frases[1:]):
        if b["inicio"] < a["inicio"] + a["duracion"]:
            print(f"ATENCIÓN: '{b['id']}' empieza antes de que termine '{a['id']}'. Revisar los cortes.")
    fin_voz = frases[-1]["inicio"] + frases[-1]["duracion"]
    total = min(args.max, round(fin_voz + guion.get("cola_s", 3.0), 1))
    print(f"La voz termina a los {fin_voz:.2f} s; el video dura {total} s.")
    if fin_voz + 1.0 > args.max:
        print(f"ATENCIÓN: la voz no entra en {args.max:.0f} s. Acortar el texto o grabar un poco más rápido.")
    (VIDEO / args.salida).write_text(json.dumps({"voz": "grabada", "duracion_video": total, "frases": frases}, ensure_ascii=False, indent=1))
    print(f"Escrito {args.salida}. Revisar con: npx remotion studio  (composición DumpsiteLocal)")


if __name__ == "__main__":
    main()
