"""Builds two assets that preparar_assets.py doesn't (and that script keeps them when it rewrites datos-reales.json).

1. public/s2serie/: 6 real Sentinel-2 L2A dates over Norte III (Jun-Oct 2026), from the
   Microsoft Planetary Computer tiles, and the "serie_s2" key of compartido/datos-reales.json with the polygon.
2. public/entreno/: 28 crops of dump sites from the world catalog (one per country, 40 ha or more), from
   EOX Sentinel-2 cloudless 2021, and the "entreno" key with the catalog total (66,981 sites).

Usage (from video/):  python3 -I compartido/scripts/serie_y_catalogo.py [--solo serie|catalogo]
"""
import argparse
import io
import json
import math
import pathlib
import random
import urllib.parse
import urllib.request

from PIL import Image

VIDEO = pathlib.Path(__file__).resolve().parents[2]
REPO = VIDEO.parent
PUB = VIDEO / "public"
DATOS = VIDEO / "compartido" / "datos-reales.json"
CACHE = VIDEO / ".cache-tiles"

# Scenes picked by hand among the least cloudy in the Planetary Computer STAC (date, % clouds, item)
ESCENAS_S2 = [
    ["2026-06-26", 1.1, "S2C_MSIL2A_20260626T134701_R024_T21HUB_20260626T200121"],
    ["2026-08-07", 0.1, "S2A_MSIL2A_20260807T135131_R024_T21HUB_20260807T233312"],
    ["2026-08-10", 0.0, "S2B_MSIL2A_20260810T134659_R024_T21HUB_20260810T185613"],
    ["2026-09-04", 0.0, "S2C_MSIL2A_20260904T134701_R024_T21HUB_20260904T201714"],
    ["2026-09-19", 4.8, "S2B_MSIL2A_20260919T134659_R024_T21HUB_20260919T190912"],
    ["2026-10-04", 0.1, "S2C_MSIL2A_20261004T134711_R024_T21HUB_20261004T184116"],
]
CENTRO_NORTE3 = (-58.6175, -34.5266)  # lon, lat
LADO_KM = 2.6


def mer(lat):
    return math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))


def serie():
    lon, lat = CENTRO_NORTE3
    z = 15

    def gpx(lo, la):
        n = 512 * 2 ** z
        return (lo + 180) / 360 * n, (1 - mer(la) / math.pi) / 2 * n

    dlat = LADO_KM / 2 / 111
    dlon = LADO_KM / 2 / (111 * math.cos(math.radians(lat)))
    x0, y0 = gpx(lon - dlon, lat + dlat)
    x1, y1 = gpx(lon + dlon, lat - dlat)
    (PUB / "s2serie").mkdir(parents=True, exist_ok=True)
    out = []
    for fecha, nubes, item in ESCENAS_S2:
        tx0, ty0, tx1, ty1 = int(x0 // 512), int(y0 // 512), int(x1 // 512), int(y1 // 512)
        big = Image.new("RGB", ((tx1 - tx0 + 1) * 512, (ty1 - ty0 + 1) * 512))
        for tx in range(tx0, tx1 + 1):
            for ty in range(ty0, ty1 + 1):
                q = urllib.parse.urlencode({"collection": "sentinel-2-l2a", "item": item, "assets": "visual",
                                            "asset_bidx": "visual|1,2,3", "nodata": "0", "format": "png"})
                u = f"https://planetarycomputer.microsoft.com/api/data/v1/item/tiles/WebMercatorQuad/{z}/{tx}/{ty}@2x?{q}"
                big.paste(Image.open(io.BytesIO(urllib.request.urlopen(u, timeout=60).read())).convert("RGB"),
                          ((tx - tx0) * 512, (ty - ty0) * 512))
        im = big.crop((round(x0 - tx0 * 512), round(y0 - ty0 * 512), round(x1 - tx0 * 512), round(y1 - ty0 * 512)))
        archivo = f"s2serie/{fecha}.jpg"
        im.resize((900, 900), Image.LANCZOS).save(PUB / archivo, quality=88)
        out.append({"fecha": fecha, "nubes": nubes, "item": item, "archivo": archivo})
        print(archivo, f"{nubes} % nubes")
    caja = [lon - dlon, lat - dlat, lon + dlon, lat + dlat]
    w, s, e, n = caja
    contornos = json.loads((REPO / "web" / "src" / "data" / "seed" / "contornos.json").read_text())
    poligono = [[round((lo - w) / (e - w), 5), round((mer(n) - mer(la)) / (mer(n) - mer(s)), 5)]
                for lo, la in contornos["norte-iii"]["coordinates"][0]]
    d = json.loads(DATOS.read_text())
    d["serie_s2"] = {"caja": caja, "imagenes": out, "poligono": poligono,
                     "fuente": "Sentinel-2 L2A, Microsoft Planetary Computer (Copernicus)"}
    DATOS.write_text(json.dumps(d, ensure_ascii=False, indent=1))


def catalogo():
    cat = json.loads((REPO / "data" / "basurales" / "basurales_mundo.json").read_text())
    sitios = cat["sitios"]
    print("sitios en el catálogo:", len(sitios))
    random.seed(7)
    grandes = [s for s in sitios if (s.get("area_ha") or 0) >= 40 and s.get("lat") is not None]
    por_pais = {}
    for s in grandes:
        por_pais.setdefault(s.get("pais") or "?", []).append(s)
    elegidos = []
    for p in sorted(por_pais, key=lambda p: -len(por_pais[p])):
        if p != "?":
            elegidos.append(random.choice(por_pais[p]))
        if len(elegidos) >= 28:
            break
    (PUB / "entreno").mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(exist_ok=True)

    def tile(z, x, y):
        f = CACHE / f"{z}_{x}_{y}.jpg"
        if not f.exists():
            f.write_bytes(urllib.request.urlopen(
                f"https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2021_3857/default/g/{z}/{y}/{x}.jpg", timeout=30).read())
        return Image.open(f).convert("RGB")

    z, out = 15, []
    for k, s in enumerate(elegidos):
        n = 256 * 2 ** z
        gx = (s["lon"] + 180) / 360 * n
        gy = (1 - mer(s["lat"]) / math.pi) / 2 * n
        tx, ty = int(gx // 256), int(gy // 256)
        big = Image.new("RGB", (768, 768))
        try:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    big.paste(tile(z, tx + dx, ty + dy), ((dx + 1) * 256, (dy + 1) * 256))
        except Exception as e:  # missing tile: that country is skipped
            print("salteo", s["pais"], e)
            continue
        cx, cy = gx - (tx - 1) * 256, gy - (ty - 1) * 256
        archivo = f"entreno/{k:02d}.jpg"
        big.crop((int(cx - 170), int(cy - 170), int(cx + 170), int(cy + 170))).resize((240, 240), Image.LANCZOS).save(PUB / archivo, quality=85)
        out.append({"archivo": archivo, "pais": s.get("pais"), "nombre": s.get("nombre"), "ha": round(s.get("area_ha") or 0)})
    d = json.loads(DATOS.read_text())
    d["entreno"] = {"total_catalogo": len(sitios), "muestras": out,
                    "fuente": "data/catalogos/basurales/basurales_mundo.json (OSM/Overture, Climate TRACE, EPA LMOP, ...)"}
    DATOS.write_text(json.dumps(d, ensure_ascii=False, indent=1))
    print(len(out), "recortes")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--solo", choices=["serie", "catalogo"])
    a = ap.parse_args()
    if a.solo != "catalogo":
        serie()
    if a.solo != "serie":
        catalogo()
