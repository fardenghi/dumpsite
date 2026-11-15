"""Generates the voice-over with Azure AI Speech, with emotion per sentence (mstts:express-as styles).

Reads a script (default ingles/guion.json) (sentences -> parts with style, intensity, rate and pitch), synthesizes one take per
sentence, places them one after another with the script's gaps and writes public/<audio>/frase-N.wav and
the timing json (start and duration of each sentence). The video scenes sync to those timings.
The key is read from video/.env.local (AZURE_SPEECH_KEY, AZURE_SPEECH_REGION) and is never printed.

Usage (from video/):
  English:  python3 -I compartido/scripts/voz_azure.py
  Spanish:  python3 -I compartido/scripts/voz_azure.py --guion espanol/guion-es.json --salida espanol/voz-es.json --audio voz-es --max 180
"""
import http.client
import json
import pathlib
import time
import urllib.error
import urllib.request
import wave
from xml.sax.saxutils import escape

VIDEO = pathlib.Path(__file__).resolve().parents[2]   # the video/ folder
MAX_VIDEO_S = 29.8   # the Space Apps limit is 30 s
COLA_FINAL_S = 1.6   # how long the end card lasts after the last word


def leer_env():
    env = {}
    for linea in (VIDEO / ".env.local").read_text().splitlines():
        if "=" in linea and not linea.strip().startswith("#"):
            k, v = linea.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def ssml_de(voz, frase, idioma="en-US"):
    cuerpo = ""
    for p in frase["partes"]:
        # "decir": how a word is pronounced, e.g. {"ResNet-50": "resnet fifty"} (SSML <sub alias>)
        cuerpo_texto = escape(p["texto"])
        for palabra, alias in p.get("decir", {}).items():
            cuerpo_texto = cuerpo_texto.replace(escape(palabra), f'<sub alias="{escape(alias)}">{escape(palabra)}</sub>')
        prosodia = (f'<prosody rate="{p.get("velocidad", "+0%")}" pitch="{p.get("tono", "+0%")}" volume="{p.get("volumen", "+0%")}">'
                    f'{cuerpo_texto}</prosody>')
        # Optional style: same narrator; only used if the script asks for it explicitly.
        cuerpo += (f'<mstts:express-as style="{p["estilo"]}" styledegree="{p.get("grado", 1)}">{prosodia}</mstts:express-as>'
                   if p.get("estilo") else prosodia)
        if p.get("pausa_ms"):
            cuerpo += f'<break time="{int(p["pausa_ms"])}ms"/>'
    return ('<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
            f'xmlns:mstts="https://www.w3.org/2001/mstts" xml:lang="{idioma}">'
            f'<voice name="{voz}">{cuerpo}</voice></speak>')


def sintetizar(env, ssml, destino):
    req = urllib.request.Request(
        f"https://{env['AZURE_SPEECH_REGION']}.tts.speech.microsoft.com/cognitiveservices/v1",
        data=ssml.encode("utf-8"), method="POST",
        headers={"Ocp-Apim-Subscription-Key": env["AZURE_SPEECH_KEY"], "Content-Type": "application/ssml+xml",
                 "X-Microsoft-OutputFormat": "riff-48khz-16bit-mono-pcm", "User-Agent": "basurales-video"})
    for intento in range(4):
        try:
            destino.write_bytes(urllib.request.urlopen(req, timeout=60).read())
            break
        except (http.client.IncompleteRead, urllib.error.URLError, TimeoutError):
            if intento == 3:
                raise
            time.sleep(2 + 2 * intento)
    return recortar_silencio(destino)


def recortar_silencio(destino, umbral=400, colchon_s=0.09):
    """Trims the silence at the start and end of the take; leaves a short cushion."""
    import array
    with wave.open(str(destino)) as w:
        params, fr = w.getparams(), w.getframerate()
        muestras = array.array("h", w.readframes(w.getnframes()))
    fuertes = [i for i in range(0, len(muestras), 48) if abs(muestras[i]) > umbral]
    if fuertes:
        a = max(0, fuertes[0] - int(colchon_s * fr))
        b = min(len(muestras), fuertes[-1] + int(colchon_s * fr))
        muestras = muestras[a:b]
    with wave.open(str(destino), "wb") as w:
        w.setparams(params)
        w.writeframes(muestras.tobytes())
    return len(muestras) / fr


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--guion", default="ingles/guion.json")
    ap.add_argument("--salida", default="ingles/voz.json")
    ap.add_argument("--audio", default="voz-en", help="carpeta dentro de public/")
    ap.add_argument("--max", type=float, default=MAX_VIDEO_S)
    args = ap.parse_args()
    guion = json.loads((VIDEO / args.guion).read_text())
    idioma = guion.get("idioma", "en-US")
    env = leer_env()
    salida = VIDEO / "public" / args.audio
    salida.mkdir(parents=True, exist_ok=True)
    for viejo in salida.glob("*.wav"):
        viejo.unlink()
    h = guion["huecos_s"]
    t = h["antes_de_la_primera"]
    frases = []
    for i, f in enumerate(guion["frases"], start=1):
        if i == 2:
            t += h["antes_de_la_2"] - h["entre_frases"]
        dur = sintetizar(env, ssml_de(guion["voz"], f, idioma), salida / f"frase-{i}.wav")
        texto = " ".join(p["texto"] for p in f["partes"])
        frases.append({"id": f["id"], "archivo": f"{args.audio}/frase-{i}.wav", "inicio": round(t, 2), "duracion": round(dur, 2), "texto": texto})
        print(f"{i}. {t:5.2f}-{t + dur:5.2f} s  ({dur:4.2f} s, {len(texto.split())} palabras)  {texto}")
        t += dur + h["entre_frases"]
    fin_voz = frases[-1]["inicio"] + frases[-1]["duracion"]
    total = min(args.max, round(fin_voz + guion.get("cola_s", COLA_FINAL_S), 1))
    print(f"La voz termina a los {fin_voz:.2f} s; el video dura {total} s.")
    if fin_voz + 1.0 > args.max:
        print("ATENCIÓN: no queda lugar para la placa final. Acortar el guion.")
    (VIDEO / args.salida).write_text(json.dumps({"voz": guion["voz"], "duracion_video": total, "frases": frases},
                                                      ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
