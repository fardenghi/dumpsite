"""Downloads from OpenStreetMap the outline of each site (landuse=landfill polygons).

Reads src/data/seed/sitios.json, writes src/data/seed/contornos.json and updates
in sitios.json the center and area of the sites that have a polygon.
Usage: python3 scripts/contornos.py
Data: © OpenStreetMap contributors, ODbL license.
"""
import json
import math
import time
import urllib.parse
import urllib.request
from pathlib import Path

SEED = Path(__file__).resolve().parent.parent / "src" / "data" / "seed"
SERVIDOR = "https://overpass-api.de/api/interpreter"
RADIO = 5000  # meters around the site's point


def overpass(consulta):
    """The public server is often overloaded: a single query and several retries."""
    for intento in range(10):
        try:
            pedido = urllib.request.Request(SERVIDOR, urllib.parse.urlencode({"data": consulta}).encode(), {"User-Agent": "insomnes-contornos/0.1"})
            return json.load(urllib.request.urlopen(pedido, timeout=90))["elements"]
        except Exception as e:
            print(f"   reintento {intento + 1}: {e}", flush=True)
            time.sleep(8)
    raise SystemExit("Overpass no respondió")


def anillos(elemento):
    """Closed exterior rings of a way or a relation."""
    if elemento["type"] == "way":
        partes = [elemento.get("geometry", [])]
    else:
        partes = [m.get("geometry", []) for m in elemento.get("members", []) if m.get("role") in ("outer", "") and m["type"] == "way"]
    tramos = [[(round(n["lon"], 5), round(n["lat"], 5)) for n in p] for p in partes if len(p) >= 2]
    salida = []
    # in a relation the edge often comes split into several open segments: they are joined end to end
    while tramos:
        anillo = tramos.pop()
        while anillo[0] != anillo[-1]:
            sigue = next((t for t in tramos if anillo[-1] in (t[0], t[-1])), None)
            if sigue is None:
                break
            tramos.remove(sigue)
            anillo += (sigue if sigue[0] == anillo[-1] else sigue[::-1])[1:]
        if len(anillo) >= 4 and anillo[0] == anillo[-1]:
            salida.append(anillo)
    return salida


def medir(anillo):
    """Area in hectares and centroid (lon, lat), on a local plane."""
    lat0 = sum(p[1] for p in anillo) / len(anillo)
    kx, ky = 111320 * math.cos(math.radians(lat0)), 110540
    pts = [(lon * kx, lat * ky) for lon, lat in anillo]
    a = cx = cy = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        f = x1 * y2 - x2 * y1
        a += f
        cx += (x1 + x2) * f
        cy += (y1 + y2) * f
    a /= 2
    if abs(a) < 1:
        return 0.0, anillo[0]
    return abs(a) / 10000, (cx / (6 * a) / kx, cy / (6 * a) / ky)


def distancia(lon1, lat1, lon2, lat2):
    return math.hypot((lon1 - lon2) * 111320 * math.cos(math.radians(lat1)), (lat1 - lat2) * 110540)


def main():
    sitios = json.loads((SEED / "sitios.json").read_text(encoding="utf-8"))
    contornos = {}
    con_predio = [s for s in sitios if s["registro"] != "sin_registro"]  # blobs without a known site don't have their own polygon
    zonas = "".join(f"way[landuse=landfill](around:{RADIO},{s['lat']},{s['lon']});relation[landuse=landfill](around:{RADIO},{s['lat']},{s['lon']});" for s in con_predio)
    poligonos = []
    for e in overpass(f"[out:json][timeout:180];({zonas});out geom;"):
        for anillo in anillos(e):
            ha, centro = medir(anillo)
            if ha >= 1:
                poligonos.append((ha, centro, anillo))
    for s in con_predio:
        candidatos = [(distancia(c[0], c[1], s["lon"], s["lat"]), ha, c, a) for ha, c, a in poligonos]
        # far from the point only a large site is accepted: a small one several km away is usually another landfill
        candidatos = [c for c in candidatos if c[0] <= 2500 or (c[0] <= RADIO + 1500 and c[1] >= 100)]
        if not candidatos:
            print(f"{s['id']:16s} sin polígono")
            continue
        # the largest among those near the point
        cerca = [c for c in candidatos if c[0] <= min(c[0] for c in candidatos) + 800]
        _, ha, centro, anillo = max(cerca, key=lambda c: c[1])
        contornos[s["id"]] = {"type": "Polygon", "coordinates": [[list(p) for p in anillo]]}
        s["lon"], s["lat"], s["ha"] = round(centro[0], 4), round(centro[1], 4), round(ha)
        print(f"{s['id']:16s} {ha:7.0f} ha, {len(anillo)} vértices")
    (SEED / "contornos.json").write_text(json.dumps(contornos, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")
    filas = ",\n".join("  " + json.dumps(s, ensure_ascii=False) for s in sitios)
    (SEED / "sitios.json").write_text(f"[\n{filas}\n]\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
