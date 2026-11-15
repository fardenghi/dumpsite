"""El índice de insomnio de cada frame como imagen para la web, igual que el del AMBA.

    python indice_png_web.py                 # todos los frames con salidas/<FRAME>/indice_80m.npz
    python indice_png_web.py --frame DELHI CDMX

Lee `salidas/<FRAME>/indice_80m.npz`, que escribe `pipeline_insomnio.py indice --frame <FRAME>` (no va al repo:
hace falta tener los recortes del frame; ver README.md). No vuelve a calcular nada: sólo remuestrea la capa
`insomnio` a Web Mercator y la pinta con la misma paleta y transparencia que `_png_web` del pipeline.

Escribe en insomnes-web:
- `public/indice/insomnio-<frame>.png`, uno por frame;
- `src/data/seed/indices.json`, la lista con las esquinas de cada imagen. La web la lee si está.
El AMBA no se toca: su imagen y su `indice.json` los escribe el pipeline.
"""
import argparse
import json
import os

import numpy as np

import geo

AQUI = os.path.dirname(os.path.abspath(__file__))
SALIDAS = os.path.join(AQUI, "..", "data", "salidas")
WEB = os.path.join(AQUI, "..", "web")
PX_POR_GRADO = 1270  # como el PNG del AMBA: 1400 px para 1,1° de ancho
NIVELES = 64  # tonos de la paleta


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
    # Misma paleta y transparencia que `_png_web` del pipeline (magma; transparente por debajo de 0,3 y en el agua),
    # pero como PNG de paleta con NIVELES tonos: pesa varias veces menos que el RGBA y en el mapa se ve igual.
    valor = np.linspace(0, 1, NIVELES)
    rgb = (matplotlib.colormaps["magma"](valor)[:, :3] * 255).round().astype(np.uint8)
    alfa = (np.clip((valor - 0.3) / 0.4, 0, 1) * 0.85 * 255).round().astype(np.uint8)
    nivel = np.where(np.isfinite(img), np.rint(np.clip(np.nan_to_num(img), 0, 1) * (NIVELES - 1)), 0).astype(np.uint8)
    nivel[alfa[nivel] == 0] = 0  # todo lo transparente es un solo índice: comprime mejor
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
    a.add_argument("--frame", nargs="+", help="frames a exportar (por defecto, todos los que tengan indice_80m.npz)")
    a.add_argument("--salidas", default=SALIDAS)
    a.add_argument("--web", default=WEB)
    args = a.parse_args()
    frames = args.frame or sorted(f for f in os.listdir(args.salidas) if os.path.isfile(os.path.join(args.salidas, f, "indice_80m.npz")))
    frames = [f for f in frames if f != "AMBA"]
    if not frames:
        raise SystemExit(f"No hay ningún salidas/<FRAME>/indice_80m.npz en {os.path.relpath(args.salidas)}: "
                         "corré antes `python pipeline_insomnio.py indice --frame <FRAME>` con los recortes del frame.")
    destino = os.path.join(args.web, "src", "data", "seed", "indices.json")
    try:  # los que ya estaban se conservan: se puede exportar de a un frame
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
