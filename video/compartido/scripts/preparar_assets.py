"""Prepares the video's real assets in public/.

Everything comes from repo files (pipeline outputs and the web seed) plus cloud-free Sentinel-2 imagery
from EOX (s2maps.eu, "Sentinel-2 cloudless 2021 by EOX IT Services GmbH, contains modified Copernicus
Sentinel data 2021", CC BY-NC-SA 4.0). No data is made up: what doesn't exist yet stays as a
placeholder in compartido/data.ts. The Sentinel-2 series and the catalog crops are built by
compartido/scripts/serie_y_catalogo.py (this script keeps those keys). The AI clip isn't touched here.

Usage (from video/):  python3 -I compartido/scripts/preparar_assets.py
"""
import io
import json
import math
import pathlib
import shutil
import urllib.request

from PIL import Image, ImageDraw

VIDEO = pathlib.Path(__file__).resolve().parents[2]   # the video/ folder
REPO = VIDEO.parent
SALIDAS = REPO / "data" / "salidas"
MOTOR = REPO / "motor"
SEED = REPO / "web" / "src" / "data" / "seed"
PUB = VIDEO / "public"
PUB.mkdir(exist_ok=True)

TILE = "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2021_3857/default/g/{z}/{y}/{x}.jpg"
CACHE = VIDEO / ".cache-tiles"
CACHE.mkdir(exist_ok=True)


def merc_y(lat):
    return math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))


def lonlat_to_global_px(lon, lat, z):
    n = 256 * 2 ** z
    return (lon + 180) / 360 * n, (1 - merc_y(lat) / math.pi) / 2 * n


def tile_img(z, x, y):
    f = CACHE / f"{z}_{x}_{y}.jpg"
    if not f.exists():
        f.write_bytes(urllib.request.urlopen(TILE.format(z=z, x=x, y=y), timeout=30).read())
    return Image.open(f).convert("RGB")


def mosaic_bbox(w, s, e, n, z):
    """Web Mercator mosaic cropped exactly to the box (west, south, east, north)."""
    x0, y0 = lonlat_to_global_px(w, n, z)
    x1, y1 = lonlat_to_global_px(e, s, z)
    tx0, ty0, tx1, ty1 = int(x0 // 256), int(y0 // 256), int(x1 // 256), int(y1 // 256)
    big = Image.new("RGB", ((tx1 - tx0 + 1) * 256, (ty1 - ty0 + 1) * 256))
    for tx in range(tx0, tx1 + 1):
        for ty in range(ty0, ty1 + 1):
            big.paste(tile_img(z, tx, ty), ((tx - tx0) * 256, (ty - ty0) * 256))
    return big.crop((round(x0 - tx0 * 256), round(y0 - ty0 * 256), round(x1 - tx0 * 256), round(y1 - ty0 * 256)))


def caja_centro(lat, lon, km):
    dlat = km / 2 / 111.0
    dlon = km / 2 / (111.0 * math.cos(math.radians(lat)))
    return lon - dlon, lat - dlat, lon + dlon, lat + dlat


def to_norm(lon, lat, caja):
    """Normalized 0..1 coordinates within a Web Mercator box (x to the right, y downward)."""
    w, s, e, n = caja
    return (lon - w) / (e - w), (merc_y(n) - merc_y(lat)) / (merc_y(n) - merc_y(s))


def main():
    indice = json.loads((SEED / "indice.json").read_text())
    amba = (indice["oeste"], indice["sur"], indice["este"], indice["norte"])

    # 1. Real index (the web's PNG) and AMBA Sentinel-2 with the same box and aspect ratio
    shutil.copy(REPO / "web" / "public" / indice["url"], PUB / "insomnio-amba.png")
    s2 = mosaic_bbox(*amba, z=12).resize((2800, 2010), Image.LANCZOS)
    s2.save(PUB / "s2-amba.jpg", quality=88)
    print("s2-amba.jpg", s2.size)

    # 2. Norte III: 6 km crop at z15 with its OSM polygon
    contornos = json.loads((SEED / "contornos.json").read_text())
    anillo = contornos["norte-iii"]["coordinates"][0]
    lat_c = sum(p[1] for p in anillo) / len(anillo)
    lon_c = sum(p[0] for p in anillo) / len(anillo)
    caja_n3 = caja_centro(lat_c, lon_c, 6.0)
    n3 = mosaic_bbox(*caja_n3, z=15).resize((1920, 1920), Image.LANCZOS)
    n3.save(PUB / "s2-norte3.jpg", quality=88)
    print("s2-norte3.jpg", n3.size)

    # 3. Crops of the four candidate blobs for the CNN clip (2.24 km, like the network's input)
    candidatos = json.loads((SEED / "candidatos.json").read_text())
    elegidos = [
        ("norte3-disp", -34.5440, -58.6069),
        ("tres-febrero", -34.5773, -58.6277),
        ("el-palomar", -34.6047, -58.6090),
        ("santos-lugares", -34.6081, -58.5416),
    ]
    chips = []
    for nombre, la, lo in elegidos:
        c = min(candidatos, key=lambda k: (k["lat"] - la) ** 2 + (k["lon"] - lo) ** 2)
        img = mosaic_bbox(*caja_centro(c["lat"], c["lon"], 2.24), z=15).resize((448, 448), Image.LANCZOS)
        img.save(PUB / f"chip-{nombre}.jpg", quality=88)
        x, y = to_norm(c["lon"], c["lat"], amba)
        chips.append({"id": nombre, "lat": c["lat"], "lon": c["lon"], "ha": c["ha"], "insomnio": c["insomnio"],
                      "clase_osm": c["clase"], "que_osm": c["que"], "x": round(x, 5), "y": round(y, 5)})

    # 4. World (z3) for the zoom-out of clip 5
    mundo = Image.new("RGB", (2048, 2048))
    for tx in range(8):
        for ty in range(8):
            mundo.paste(tile_img(3, tx, ty), (tx * 256, ty * 256))
    mundo.save(PUB / "s2-mundo.jpg", quality=85)

    # 5. Pipeline data to animate
    fichas = json.loads((SALIDAS / "fichas_80m.json").read_text())
    resumen = json.loads((SALIDAS / "resumen_80m.json").read_text())
    f = fichas["norte-iii"]
    pares = sorted(f["pares"], key=lambda p: (p["orbita"], p["fecha"]))
    # Keep what was built in separate steps (Sentinel-2 series by date and training mosaic).
    previo_path = VIDEO / "compartido" / "datos-reales.json"
    previo = json.loads(previo_path.read_text()) if previo_path.exists() else {}
    data = {
        "fuente": "data/salidas/fichas_80m.json, data/salidas/resumen_80m.json, web/src/data/seed",
        "norte3": {
            "insomnio": f["insomnio"], "persistencia": f["persistencia"], "radar": f["radar"],
            "insomnio_orbita": f["insomnio_orbita"], "pares": pares,
            "poligono_norm": [to_norm(lo, la, caja_n3) for lo, la in anillo],
            "poligono_amba": [to_norm(lo, la, amba) for lo, la in anillo],
        },
        "razon": resumen["parametros"]["razon"],
        "n_pares_gunw": len(resumen["pares"]),
        "candidatos_amba": [[round(v, 5) for v in to_norm(c["lon"], c["lat"], amba)] + [c["clase"]] for c in candidatos],
        "chips": chips,
        "caja_amba": amba,
        "caja_norte3": caja_n3,
    }
    for clave in ("serie_s2", "entreno"):
        if clave in previo:
            data[clave] = previo[clave]
    (VIDEO / "compartido" / "datos-reales.json").write_text(json.dumps(data, ensure_ascii=False, indent=1))
    print("datos-reales.json:", len(pares), "pares de Norte III,", len(candidatos), "candidatos")

    # 5b. What NISAR sees: real mean coherence of the 15 pass comparisons (GUNW, 80 m),
    # cropped to the same 6 km area. Light = the ground didn't change between passes; dark = it changed.
    import sys
    import numpy as np
    sys.path.insert(0, str(MOTOR))
    from geo import utm  # noqa: E402
    z = np.load(SALIDAS / "indice_80m.npz")
    coh, xs, ys = z["coherencia_media"].astype("float32"), z["xs"], z["ys"]
    cx, cy = utm(lat_c, lon_c)
    lado = 6000.0
    cols = np.where((xs >= cx - lado / 2) & (xs <= cx + lado / 2))[0]
    filas = np.where((ys >= cy - lado / 2) & (ys <= cy + lado / 2))[0]
    rec = coh[filas.min():filas.max() + 1, cols.min():cols.max() + 1]
    rec = np.nan_to_num(rec, nan=0.0)
    v = np.clip((rec - 0.25) / (0.9 - 0.25), 0, 1)
    # ramp: near black -> radar blue -> cold white
    paleta = np.array([[4, 8, 14], [20, 52, 78], [64, 150, 190], [190, 230, 240], [250, 252, 255]], dtype=float)
    pos = v * (len(paleta) - 1)
    i0 = np.floor(pos).astype(int).clip(0, len(paleta) - 2)
    t = (pos - i0)[..., None]
    rgb = (paleta[i0] * (1 - t) + paleta[i0 + 1] * t).astype("uint8")
    Image.fromarray(rgb).resize((1080, 1080), Image.BICUBIC).save(PUB / "nisar-coherencia-norte3.png")
    x0, x1 = xs[cols.min()] - 40, xs[cols.max()] + 40
    y0, y1 = ys[filas.min()] + 40, ys[filas.max()] - 40
    pol_utm = [utm(la, lo) for lo, la in anillo]
    data["norte3"]["poligono_nisar"] = [[round((x - x0) / (x1 - x0), 5), round((y0 - y) / (y0 - y1), 5)] for x, y in pol_utm]
    # Wide (14 km) smoothed version, to show "what the radar sees" without the pixelated look.
    from PIL import ImageFilter
    lado2 = 14000.0
    cols2 = np.where((xs >= cx - lado2 / 2) & (xs <= cx + lado2 / 2))[0]
    filas2 = np.where((ys >= cy - lado2 / 2) & (ys <= cy + lado2 / 2))[0]
    rec2 = np.nan_to_num(coh[filas2.min():filas2.max() + 1, cols2.min():cols2.max() + 1], nan=0.0)
    v2 = np.clip((rec2 - 0.25) / (0.9 - 0.25), 0, 1)
    pos2 = v2 * (len(paleta) - 1)
    j0 = np.floor(pos2).astype(int).clip(0, len(paleta) - 2)
    t2 = (pos2 - j0)[..., None]
    rgb2 = (paleta[j0] * (1 - t2) + paleta[j0 + 1] * t2).astype("uint8")
    img2 = Image.fromarray(rgb2).resize((540, 540), Image.BICUBIC).filter(ImageFilter.GaussianBlur(1.6)).resize((1080, 1080), Image.LANCZOS)
    img2.save(PUB / "nisar-coherencia-amplia.png")
    ax0, ax1 = xs[cols2.min()] - 40, xs[cols2.max()] + 40
    ay0, ay1 = ys[filas2.min()] + 40, ys[filas2.max()] - 40
    data["norte3"]["poligono_nisar_amplio"] = [[round((x - ax0) / (ax1 - ax0), 5), round((ay0 - y) / (ay0 - ay1), 5)] for x, y in pol_utm]
    (VIDEO / "compartido" / "datos-reales.json").write_text(json.dumps(data, ensure_ascii=False, indent=1))
    print("nisar-coherencia-norte3.png", rec.shape, "· nisar-coherencia-amplia.png", rec2.shape)


if __name__ == "__main__":
    main()
