"""Momento exacto de cada palabra de la voz, para los subtítulos y para sincronizar las escenas (video en castellano).

Pasa cada frase grabada (public/<audio>/frase-N.wav) por whisper.cpp con tiempos por palabra, ajusta el comienzo de las
palabras que vienen después de una pausa al final de esa pausa (whisper suele adelantarlas) y alinea lo reconocido con
el texto del guion: las palabras que whisper escribió distinto ("5.000" por "cinco mil") toman el tiempo de sus vecinas,
repartido por cantidad de letras. Escribe en voz-es.json, por frase, "palabras": [[palabra, segundo absoluto], ...].

  python3 -I compartido/scripts/palabras_voz.py
  (necesita whisper-cli y ffmpeg en el PATH y el modelo en ~/.cache/whisper-cpp/ggml-large-v3-turbo.bin)

Correr después de voz_grabada.py y voz_continua.py, cada vez que cambie la voz.
"""
import argparse
import difflib
import json
import pathlib
import re
import subprocess
import tempfile
import unicodedata

VIDEO = pathlib.Path(__file__).resolve().parents[2]
MODELO = pathlib.Path.home() / ".cache/whisper-cpp/ggml-large-v3-turbo.bin"
PISTA = "Dumpsite, NISAR, EMIT, LightGBM, Climate TRACE, OpenStreetMap, Sentinel-2, Norte Tres, Luján, González Catán, Spaceship."


def norm(p):
    p = unicodedata.normalize("NFD", p.lower())
    p = "".join(c for c in p if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]", "", p)


def whisper(wav16, tmp):
    base = pathlib.Path(tmp) / "w"
    subprocess.run(["whisper-cli", "-m", str(MODELO), "-l", "es", "-f", str(wav16), "-ml", "1", "-sow", "-oj", "-of", str(base), "-np", "--prompt", PISTA],
                   capture_output=True, check=True)
    out = []
    for w in json.loads(base.with_suffix(".json").read_text())["transcription"]:
        txt = w["text"].strip()
        if txt:
            out.append((txt, w["offsets"]["from"] / 1000, w["offsets"]["to"] / 1000))
    return out


def silencios(wav16):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(wav16), "-af", "silencedetect=noise=-40dB:d=0.12", "-f", "null", "-"], capture_output=True, text=True)
    v = [float(x) for x in re.findall(r"silence_(?:start|end): ([0-9.]+)", r.stderr)]
    return list(zip(v[0::2], v[1::2]))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--voz", default="espanol/voz-es.json")
    args = ap.parse_args()
    ruta = VIDEO / args.voz
    voz = json.loads(ruta.read_text())
    with tempfile.TemporaryDirectory() as tmp:
        wav16 = pathlib.Path(tmp) / "f.wav"
        for fr in voz["frases"]:
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(VIDEO / "public" / fr["archivo"]), "-ar", "16000", "-ac", "1", str(wav16)], check=True)
            rec = whisper(wav16, tmp)
            sil = silencios(wav16)
            # la palabra que sigue a una pausa empieza cuando termina la pausa
            ajust = []
            for txt, a, b in rec:
                for s0, s1 in sil:
                    if s0 - 0.15 <= a <= s1 + 0.05 and s1 - s0 > 0.12:
                        a = max(a, s1 - 0.03)
                ajust.append((txt, a))
            # monótonas
            for k in range(1, len(ajust)):
                if ajust[k][1] < ajust[k - 1][1]:
                    ajust[k] = (ajust[k][0], ajust[k - 1][1])
            # palabras amontonadas en el mismo instante (whisper las puso dentro de una pausa): se reparten por letras
            # hasta la siguiente palabra con otro tiempo, a no más de 0,09 s por letra
            k = 0
            while k < len(ajust) - 1:
                j = k
                while j + 1 < len(ajust) and ajust[j + 1][1] - ajust[k][1] < 0.04:
                    j += 1
                if j > k:
                    t0 = ajust[k][1]
                    letras = [len(ajust[i][0]) + 1 for i in range(k, j + 1)]
                    t1 = ajust[j + 1][1] if j + 1 < len(ajust) else t0 + 0.09 * sum(letras)
                    t1 = min(t1, t0 + 0.09 * sum(letras))
                    acc = 0
                    for i in range(k, j + 1):
                        ajust[i] = (ajust[i][0], t0 + (t1 - t0) * acc / sum(letras))
                        acc += letras[i - k]
                k = j + 1
            guion = fr["texto"].split(" ")
            tiempos = [None] * len(guion)
            sm = difflib.SequenceMatcher(a=[norm(x) for x in guion], b=[norm(x[0]) for x in ajust], autojunk=False)
            for bl in sm.get_matching_blocks():
                for k in range(bl.size):
                    tiempos[bl.a + k] = ajust[bl.b + k][1]
            # bordes: la primera palabra arranca con la frase; huecos interpolados por letras
            if tiempos[0] is None:
                tiempos[0] = 0.0
            fin = fr["duracion"]
            k = 0
            while k < len(guion):
                if tiempos[k] is None:
                    j = k
                    while j < len(guion) and tiempos[j] is None:
                        j += 1
                    t0 = tiempos[k - 1]
                    t1 = tiempos[j] if j < len(guion) else fin - 0.25
                    pesos = [len(guion[i]) + 1 for i in range(k - 1, j)]
                    total = sum(pesos)
                    acc = 0
                    for i in range(k, j):
                        acc += pesos[i - k]
                        tiempos[i] = t0 + (t1 - t0) * acc / total
                    k = j
                k += 1
            fr["palabras"] = [[p, round(fr["inicio"] + t, 3)] for p, t in zip(guion, tiempos)]
            sin = sum(1 for i in range(len(guion)) if not any(bl.a <= i < bl.a + bl.size for bl in sm.get_matching_blocks()))
            print(f"{fr['id']:<11} {len(guion):3} palabras, {sin:2} interpoladas")
    ruta.write_text(json.dumps(voz, ensure_ascii=False, indent=1))
    print(f"Escrito {args.voz}")


if __name__ == "__main__":
    main()
