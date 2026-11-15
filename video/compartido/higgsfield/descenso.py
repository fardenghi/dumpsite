"""First attempt (discarded): Higgsfield Seedance 2.5 text-to-video, descent from space to a dump site.

It was discarded because the dump looked like dirt and bulldozers showed up. The clip in use comes from satelite.py.

Usage:
    python descenso.py            # 480p draft, about USD 0.59 per 5 s
    python descenso.py --720p     # normal 720p generation (price not published in the docs)

The credential is read from video/.env.local (HF_KEY=key-id:key-secret). The script never prints it.
"""
import argparse
import json
import pathlib
import sys
import time
import urllib.request

from dotenv import load_dotenv

HERE = pathlib.Path(__file__).parent
load_dotenv(HERE.parents[1] / ".env.local")  # video/.env.local

import os  # noqa: E402

import higgsfield_client  # noqa: E402

MODEL = "bytedance/seedance-2.5/text-to-video"

PROMPT = (
    "Photorealistic cinematic shot, one continuous camera move. It begins in orbit: the whole "
    "Earth against black space, sunlit, with a thin blue atmospheric glow. The camera slowly "
    "descends toward South America, passing through layers of white clouds. Below the clouds, "
    "green farmland and the edge of a large city appear. The descent ends hovering low over a "
    "massive open-air landfill: a grey-brown mountain of garbage, bulldozers and trucks moving "
    "on top, flocks of seagulls, dust in the air, late-afternoon golden light. Aerial "
    "documentary look, natural colors, ultra realistic, smooth slow motion. No text, no logos, "
    "no cartoon or CGI look."
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--720p", dest="hd", action="store_true", help="normal 720p generation instead of a draft")
    args = parser.parse_args()

    if not os.getenv("HF_KEY"):
        print("Falta HF_KEY: creá video/.env.local con la línea HF_KEY=key-id:key-secret.", file=sys.stderr)
        return 2

    arguments = {
        "prompt": PROMPT,
        "duration": 5,
        "aspect_ratio": "16:9",
        "output_format": "mp4",
        "generate_audio": False,
    }
    if args.hd:
        arguments["resolution"] = "720p"
    else:
        arguments["draft"] = True  # 480p, to review before paying for 1080p

    def on_enqueue(request_id: str) -> None:
        print(f"Pedido encolado: {request_id}", flush=True)

    def on_update(status: object) -> None:
        print(f"  estado: {type(status).__name__}", flush=True)

    t0 = time.time()
    try:
        result = higgsfield_client.subscribe(MODEL, arguments=arguments, on_enqueue=on_enqueue, on_queue_update=on_update)
    except higgsfield_client.CredentialsMissedError:
        print("Credencial ausente o mal formada en .env.local.", file=sys.stderr)
        return 2
    except Exception as e:  # HTTP errors: invalid key, no balance, parameters
        print(f"La API rechazó el pedido: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    status = str(result.get("status", "")).lower()
    video = result.get("video") or {}
    url = video.get("url") if isinstance(video, dict) else None
    out = HERE / "salidas"
    out.mkdir(exist_ok=True)
    (out / "ultima-respuesta.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))

    if status != "completed" or not url:
        motivos = {"nsfw": "lo bloqueó el filtro de contenido", "failed": "falló", "canceled": "se canceló"}
        print(f"No se generó el video: {motivos.get(status, 'estado ' + repr(status))}. Detalle en salidas/ultima-respuesta.json", file=sys.stderr)
        return 1

    nombre = out / f"descenso-{'720p' if args.hd else 'draft'}-{time.strftime('%H%M%S')}.mp4"
    urllib.request.urlretrieve(url, nombre)
    print(f"Listo en {time.time() - t0:.0f} s.")
    print(f"URL: {url}")
    print(f"Guardado en: {nombre}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
