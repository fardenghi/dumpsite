"""The insomnia index of each frame as an image for the web, like the AMBA one.

    python indice_png_web.py                 # every frame with data/salidas/<FRAME>/indice_80m.npz
    python indice_png_web.py --frame DELHI CDMX

Reads `data/salidas/<FRAME>/indice_80m.npz`, written by `pipeline_insomnio.py indice --frame <FRAME>` (not in the repo:
it needs the frame's crops; see README.md). It recomputes nothing: it only resamples the `insomnio` layer
to Web Mercator and paints it with the same palette and transparency as the pipeline's `_png_web`.

Writes to web/:
- `public/indice/insomnio-<frame>.png`, one per frame;
- `src/data/seed/indices.json`, the list with the corners of each image. The web reads it if it exists.
The AMBA isn't touched: its image and its `indice.json` are written by the pipeline.
"""
import argparse
import json
import os

import numpy as np

import geo

AQUI = os.path.dirname(os.path.abspath(__file__))
SALIDAS = os.path.join(AQUI, "..", "data", "salidas")
WEB = os.path.join(AQUI, "..", "web")
PX_POR_GRADO = 1270  # like the AMBA PNG: 1400 px for 1.1° of width
NIVELES = 64  # palette tones


def exportar(frame, salidas, web):
    ruta = os.path.join(salidas, frame, "indice_80m.npz")
    with np.load(ruta) as z:
        insomnio = z["insomnio"].astype(np.float32)
        if "agua" in z.files and z["agua"].shape == insomnio.shape:
            insomnio[z["agua"]] = np.nan
        xs, ys, epsg = z["xs"], z["ys"], int(z["epsg"])
        o, s, e, n = (float(v) for v in z["bbox"])
    import matplotlib
    from PIL import Image

    ancho = max(200, int(round((e - o) * PX_POR_GRADO)))
    img, (o, s, e, n) = geo.a_mercator(insomnio, xs, ys, ancho=ancho, caja=(n, o, s, e), epsg=epsg)
    # Same palette and transparency as the pipeline's `_png_web` (magma; transparent below 0.3 and over water),
    # but as a palette PNG with NIVELES tones: several times lighter than RGBA and it looks the same on the map.
    valor = np.linspace(0, 1, NIVELES)
    rgb = (matplotlib.colormaps["magma"](valor)[:, :3] * 255).round().astype(np.uint8)
    alfa = (np.clip((valor - 0.3) / 0.4, 0, 1) * 0.85 * 255).round().astype(np.uint8)
    nivel = np.where(np.isfinite(img), np.rint(np.clip(np.nan_to_num(img), 0, 1) * (NIVELES - 1)), 0).astype(np.uint8)
    nivel[alfa[nivel] == 0] = 0  # everything transparent is a single index: it compresses better
    nombre = f"insomnio-{frame.lower()}.png"
    destino = os.path.join(web, "public", "indice", nombre)
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    png = Image.fromarray(nivel, mode="P")
    png.putpalette(rgb.tobytes())
    png.save(destino, transparency=alfa.tobytes(), optimize=True)
    return {"frame": frame, "url": f"indice/{nombre}", "oeste": o, "sur": s, "este": e, "norte": n,
            "coordinates": [[o, n], [e, n], [e, s], [o, s]], "ancho": img.shape[1], "alto": img.shape[0]}


def main():
    a = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    a.add_argument("--frame", nargs="+", help="frames to export (by default, every one that has indice_80m.npz)")
    a.add_argument("--salidas", default=SALIDAS)
    a.add_argument("--web", default=WEB)
    args = a.parse_args()
    frames = args.frame or sorted(f for f in os.listdir(args.salidas) if os.path.isfile(os.path.join(args.salidas, f, "indice_80m.npz")))
    frames = [f for f in frames if f != "AMBA"]
    if not frames:
        raise SystemExit(f"No hay ningún salidas/<FRAME>/indice_80m.npz en {os.path.relpath(args.salidas)}: "
                         "corré antes `python pipeline_insomnio.py indice --frame <FRAME>` con los recortes del frame.")
    destino = os.path.join(args.web, "src", "data", "seed", "indices.json")
    try:  # existing ones are kept: frames can be exported one at a time
        with open(destino, encoding="utf-8") as fh:
            lista = {x["frame"]: x for x in json.load(fh)}
    except FileNotFoundError:
        lista = {}
    for f in frames:
        lista[f] = exportar(f, args.salidas, args.web)
        print(f"{f}: {lista[f]['ancho']} × {lista[f]['alto']} px -> public/{lista[f]['url']}")
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    with open(destino, "w", encoding="utf-8") as fh:
        json.dump([lista[k] for k in sorted(lista)], fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print(f"{len(lista)} frames en {os.path.relpath(destino)}")


if __name__ == "__main__":
    main()
