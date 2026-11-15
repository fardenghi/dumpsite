"""Usa una voz grabada por una persona en vez de la voz sintética de Azure (pensado para el video en castellano).

Hace lo mismo que voz_azure.py pero sin sintetizar: toma las grabaciones, las pasa a WAV 48 kHz mono, les
recorta el silencio del principio y del final, las ubica una detrás de otra con los huecos del guion y escribe
public/<audio>/frase-N.wav y el json de tiempos (por defecto espanol/voz-es.json). Las escenas del video y los
subtítulos se sincronizan solos con ese json: no hace falta tocar Local.tsx si los ids de las frases no cambian.

Dos formas de pasar la grabación (ver video/VOZ-GRABADA.md):

  A. Un archivo por frase, con el id de la frase como nombre (problema.wav, dumpsite.m4a, ...), en una carpeta:
       python3 -I compartido/scripts/voz_grabada.py --carpeta ~/grabacion

  B. Una sola toma con los cortes marcados en Audacity (Edición > Etiquetas > Exportar etiquetas: un .txt con
     "inicio<TAB>fin<TAB>id" por línea, en segundos):
       python3 -I compartido/scripts/voz_grabada.py --toma toma.wav --cortes etiquetas.txt
     Con --tiempos-originales se respeta el ritmo de la toma (cada frase empieza donde empieza en la grabación)
     en vez de usar los huecos del guion.

El texto de los subtítulos sale del guion (espanol/guion-es.json): si la persona dijo algo distinto, corregir
primero el "texto" de esa frase en el guion. Necesita ffmpeg y ffprobe en el PATH.
"""
import argparse
import json
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from voz_azure import recortar_silencio  # noqa: E402  (misma función que usa la voz sintética)

VIDEO = pathlib.Path(__file__).resolve().parents[2]
EXTENSIONES = [".wav", ".mp3", ".m4a", ".ogg", ".opus", ".flac", ".aac", ".webm"]


def a_wav(origen, destino, desde=None, hasta=None):
    cmd = ["ffmpeg", "-loglevel", "error", "-y"]
    if desde is not None:
        cmd += ["-ss", f"{desde:.3f}"]
    if hasta is not None:
        cmd += ["-to", f"{hasta:.3f}"]
    # loudnorm empareja el volumen entre frases grabadas en momentos distintos
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
    ap.add_argument("--audio", default="voz-es", help="carpeta dentro de public/ (se borran los .wav viejos)")
    ap.add_argument("--max", type=float, default=180.0, help="duración máxima del video en segundos (local: 3 min)")
    ap.add_argument("--carpeta", help="forma A: carpeta con un archivo por frase, nombrado con el id")
    ap.add_argument("--toma", help="forma B: grabación única")
    ap.add_argument("--cortes", help="forma B: etiquetas de Audacity (inicio, fin, id)")
    ap.add_argument("--tiempos-originales", action="store_true", help="forma B: respetar las pausas de la toma")
    ap.add_argument("--umbral", type=int, default=400, help="nivel bajo el cual se considera silencio (subir si hay ruido de fondo)")
    ap.add_argument("--sin-recorte", action="store_true", help="no recortar silencios")
    args = ap.parse_args()
    if bool(args.carpeta) == bool(args.toma) or (args.toma and not args.cortes):
        ap.error("usar --carpeta, o --toma junto con --cortes")

    guion = json.loads((VIDEO / args.guion).read_text())
    ids = [f["id"] for f in guion["frases"]]
    salida = VIDEO / "public" / args.audio
    salida.mkdir(parents=True, exist_ok=True)

    # 1. ubicar la grabación de cada frase
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

    # 2. convertir, recortar y ubicar en el tiempo
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
