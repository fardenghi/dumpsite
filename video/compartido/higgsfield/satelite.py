"""Clip 1 v2: starts at the NISAR satellite (official render as the first frame) and descends to a dump site.

Seedance 2.5 image-to-video, 480p draft, 10 s (sped up in Remotion), no audio. The credential comes from video/.env.local (HF_KEY).
Usage (from video/compartido/higgsfield, with a venv that has higgsfield-client, python-dotenv and pillow):
    python -u satelite.py
Then: ./montar_clip.sh salidas/satelite-draft-HHMMSS.mp4  (leaves public/clip1-ai.mp4)
"""
import json
import os
import pathlib
import sys
import time
import urllib.request

from dotenv import load_dotenv

HERE = pathlib.Path(__file__).parent
load_dotenv(HERE.parents[1] / ".env.local")  # video/.env.local
import higgsfield_client  # noqa: E402

MODEL = "bytedance/seedance-2.5/image-to-video"
RENDER = HERE / "nisar-primer-cuadro.jpg"  # official NISAR render (NASA/JPL-Caltech) used as the first frame

PROMPT = (
    "Cinematic, slow and smooth continuous shot that starts exactly on this image: the NISAR satellite in orbit above Earth, "
    "with its large golden mesh reflector antenna. For the first seconds the satellite gently rotates in place, turning its "
    "antenna to face the planet, while the camera glides around it. There is no beam, no laser, no ray and no light coming out "
    "of the satellite.\n\n"
    "Then the camera leaves the satellite behind and descends straight down toward Earth: the planet grows, the camera passes "
    "through layers of soft white clouds, and the ground appears below.\n\n"
    "The shot ends on a low, slow aerial drone view over a huge open-air garbage dump at the edge of a city. It must clearly read "
    "as trash, not dirt: endless layers of colorful household waste, torn plastic bags in white, blue, black and red, bottles, "
    "packaging, tangled debris and scattered paper, wet and shiny in places, with small dark puddles between the piles. Flocks of "
    "seagulls circle over the garbage, a thin haze hangs in the air, and in the background the city fades into the distance. "
    "Gritty, realistic, documentary look, overcast natural light, high detail on the waste.\n\n"
    "No bulldozers, no trucks on top of the piles, no people, no text, no logos, no flags, no cartoon or CGI look."
)


def main() -> int:
    if not os.getenv("HF_KEY"):
        print("Falta HF_KEY en video/.env.local", file=sys.stderr)
        return 2
    salidas = HERE / "salidas"
    salidas.mkdir(exist_ok=True)
    url_imagen = higgsfield_client.upload_file(RENDER)
    print("Imagen subida.", flush=True)
    args = {"image_url": url_imagen, "prompt": PROMPT, "duration": 10, "output_format": "mp4", "generate_audio": False, "draft": True}
    t0 = time.time()
    try:
        result = higgsfield_client.subscribe(MODEL, arguments=args, on_enqueue=lambda r: print(f"Pedido encolado: {r}", flush=True))
    except Exception as e:
        print(f"La API rechazó el pedido: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    (salidas / "ultima-respuesta-satelite.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
    estado = str(result.get("status", "")).lower()
    video = result.get("video") or {}
    url = video.get("url") if isinstance(video, dict) else None
    if estado != "completed" or not url:
        print(f"No se generó el video (estado {estado!r}). Detalle en salidas/ultima-respuesta-satelite.json", file=sys.stderr)
        return 1
    destino = salidas / f"satelite-draft-{time.strftime('%H%M%S')}.mp4"
    urllib.request.urlretrieve(url, destino)
    print(f"Listo en {time.time() - t0:.0f} s. Guardado en: {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
