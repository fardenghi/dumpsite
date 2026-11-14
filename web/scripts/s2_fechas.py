"""Busca, para cada sitio, escenas Sentinel-2 (10 m) con pocas nubes.

Consulta el catálogo STAC de Microsoft Planetary Computer (abierto, sin cuenta),
lee src/data/seed/sitios.json, escribe src/data/seed/imagenes.json y guarda un
recorte JPG por sitio y por fecha en public/escenas/ (la web los usa sin conexión).
Correr después de contornos.py, que fija el centro y el contorno de cada sitio.
Uso: python3 scripts/s2_fechas.py [desde] [hasta]   (fechas AAAA-MM-DD)

Datos: Copernicus Sentinel-2 L2A (ESA). El porcentaje de nubes es el de la
escena entera (unos 110 km de lado), no el del sitio.
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
MAX_NUBE = 10  # % de la escena


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
    """Hasta n elementos repartidos a lo largo del período."""
    if len(lista) <= n:
        return lista
    paso = (len(lista) - 1) / (n - 1)
    return [lista[round(i * paso)] for i in range(n)]


def caja(sitio, contorno):
    """Caja alrededor del sitio: oeste, sur, este, norte. Entre 3 y 10 km de lado."""
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
    lado = min(1024, round(2 * medio / 10))  # un píxel por cada 10 m: la resolución real
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
        # de la más despejada a la más nublada: queda una escena por día
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
