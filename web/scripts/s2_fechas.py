"""Finds, for each site, Sentinel-2 scenes (10 m) with few clouds.

Queries the Microsoft Planetary Computer STAC catalog (open, no account),
reads src/data/seed/sitios.json, writes src/data/seed/imagenes.json and saves a
JPG crop per site and per date in public/escenas/ (the web uses them offline).
Run after contornos.py, which sets each site's center and outline.
Usage: python3 scripts/s2_fechas.py [from] [to]   (dates YYYY-MM-DD)

Data: Copernicus Sentinel-2 L2A (ESA). The cloud percentage is the one of the
whole scene (about 110 km per side), not the site's.
"""
import json
import math
import sys
import urllib.request
from pathlib import Path

SEED = Path(__file__).resolve().parent.parent / "src" / "data" / "seed"
STAC = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
DATOS = "https://planetarycomputer.microsoft.com/api/data/v1"
RECORTES = SEED.parent.parent.parent / "public" / "escenas"
MAX_POR_SITIO = 8
MAX_NUBE = 10  # % of the scene


def buscar(lat, lon, desde, hasta):
    cuerpo = {
        "collections": ["sentinel-2-l2a"],
        "intersects": {"type": "Point", "coordinates": [lon, lat]},
        "datetime": f"{desde}/{hasta}",
        "query": {"eo:cloud_cover": {"lt": MAX_NUBE}},
        "limit": 200,
    }
    pedido = urllib.request.Request(STAC, json.dumps(cuerpo).encode(), {"content-type": "application/json"})
    return json.load(urllib.request.urlopen(pedido, timeout=60))["features"]


def repartir(lista, n):
    """Up to n elements spread over the period."""
    if len(lista) <= n:
        return lista
    paso = (len(lista) - 1) / (n - 1)
    return [lista[round(i * paso)] for i in range(n)]


def caja(sitio, contorno):
    """Box around the site: west, south, east, north. Between 3 and 10 km per side."""
    kx, ky = 111320 * math.cos(math.radians(sitio["lat"])), 110540
    if contorno:
        lons = [p[0] for p in contorno["coordinates"][0]]
        lats = [p[1] for p in contorno["coordinates"][0]]
        ancho = max((max(lons) - min(lons)) * kx, (max(lats) - min(lats)) * ky)
        centro = ((max(lons) + min(lons)) / 2, (max(lats) + min(lats)) / 2)
    else:
        ancho, centro = math.sqrt(sitio["ha"] * 10000), (sitio["lon"], sitio["lat"])
    medio = min(5000, max(1500, ancho * 0.9))
    return [round(centro[0] - medio / kx, 5), round(centro[1] - medio / ky, 5), round(centro[0] + medio / kx, 5), round(centro[1] + medio / ky, 5)], medio


def bajar_recorte(item, c, medio, destino):
    lado = min(1024, round(2 * medio / 10))  # one pixel per 10 m: the real resolution
    url = (f"{DATOS}/item/bbox/{c[0]},{c[1]},{c[2]},{c[3]}/{lado}x{lado}.jpg"
           f"?collection=sentinel-2-l2a&item={item}&assets=visual&asset_bidx=visual%7C1%2C2%2C3")
    destino.write_bytes(urllib.request.urlopen(url, timeout=120).read())


def main():
    desde = sys.argv[1] if len(sys.argv) > 1 else "2026-06-15"
    hasta = sys.argv[2] if len(sys.argv) > 2 else "2026-11-14"
    contornos = json.loads((SEED / "contornos.json").read_text()) if (SEED / "contornos.json").exists() else {}
    salida = {}
    for s in json.loads((SEED / "sitios.json").read_text()):
        por_fecha = {}
        # from the clearest to the cloudiest: one scene per day is kept
        for e in sorted(buscar(s["lat"], s["lon"], desde, hasta), key=lambda e: e["properties"]["eo:cloud_cover"]):
            por_fecha.setdefault(e["properties"]["datetime"][:10], e["id"])
        elegidas = repartir(sorted(por_fecha), MAX_POR_SITIO)
        c, medio = caja(s, contornos.get(s["id"]))
        carpeta = RECORTES / s["id"]
        if carpeta.exists():
            for viejo in carpeta.glob("*.jpg"):
                viejo.unlink()
        carpeta.mkdir(parents=True, exist_ok=True)
        escenas = []
        for f in elegidas:
            try:
                bajar_recorte(por_fecha[f], c, medio, carpeta / f"{f}.jpg")
                escenas.append({"fecha": f, "item": por_fecha[f]})
            except Exception as e:
                print(f"   {s['id']} {f}: no se pudo bajar el recorte ({e})")
        salida[s["id"]] = {"caja": c, "escenas": escenas}
        print(f"{s['id']:16s} {len(por_fecha):3d} fechas con pocas nubes, guardo {len(escenas)} recortes de {2 * medio / 1000:.1f} km", flush=True)
    (SEED / "imagenes.json").write_text(json.dumps(salida, indent=2) + "\n")


if __name__ == "__main__":
    main()
