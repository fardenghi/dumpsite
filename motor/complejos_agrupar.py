"""Agrupa en "complejos" los basurales del catálogo que están a menos de 1 km entre sí.

Para qué: un mismo predio puede figurar varias veces (por ejemplo, Norte III aparece como
"Complejo Ambiental Norte III" y como "Environmental Complex Norte III C Module"). Si no se agrupan:
- el anillo de control de una entrada incluye a la otra;
- el mismo complejo cuenta dos veces y puede caer una parte en entrenamiento y otra en validación.

Cada complejo hereda un estado agregado:
- `abierto` si alguna entrada está abierta y ninguna cerrada;
- `cerrado` si alguna está cerrada y ninguna abierta;
- `contradictorio` si hay entradas abiertas y cerradas, o alguna ya era contradictoria;
- `desconocido` si ninguna tiene estado.

Uso:
    python complejos_agrupar.py ../../data            # escribe data/basurales/complejos.json
"""

from __future__ import annotations

import json
import math
import os
import sys

from pyproj import Geod
from shapely import STRtree
from shapely.geometry import shape
from shapely.ops import nearest_points

DIST_M = 1000.0
# Los polígonos de menos de 1 ha no unen a otros: hay ciudades con cientos de micro basurales mapeados
# que, encadenados de a menos de 1 km, armaban "complejos" de 10-18 km. Quedan como complejos de un sitio.
AREA_MIN_UNE_HA = 1.0
GEOD = Geod(ellps="WGS84")


def distancia_m(a, b):
    """Distancia geodésica entre los puntos más cercanos de dos geometrías (0 si se tocan)."""
    if a.intersects(b):
        return 0.0
    p, q = nearest_points(a, b)
    return GEOD.inv(p.x, p.y, q.x, q.y)[2]


def estado_agregado(estados):
    e = set(estados)
    if "contradictorio" in e or {"abierto", "cerrado"} <= e:
        return "contradictorio"
    if "abierto" in e:
        return "abierto"
    if "cerrado" in e:
        return "cerrado"
    return "desconocido"


def main(dir_data):
    sitios = {s["id"]: s for s in json.load(open(os.path.join(dir_data, "basurales", "basurales_mundo.json"), encoding="utf-8"))["sitios"]}
    feats = json.load(open(os.path.join(dir_data, "basurales", "geometrias.geojson"), encoding="utf-8"))["features"]
    ids = [f["id"] for f in feats]
    geoms = [shape(f["geometry"]) for f in feats]
    arbol = STRtree(geoms)

    # Unión de componentes conexas (union-find) con aristas entre geometrías a menos de DIST_M.
    padre = list(range(len(ids)))

    def raiz(i):
        while padre[i] != i:
            padre[i] = padre[padre[i]]
            i = padre[i]
        return i

    def une(i):
        g = geoms[i]
        if g.geom_type == "Point":
            return True  # puntos de la EPA o Climate TRACE: suelen ser rellenos grandes
        return (sitios[ids[i]].get("area_ha") or 0) >= AREA_MIN_UNE_HA

    for i, g in enumerate(geoms):
        if not une(i):
            continue
        lat = g.representative_point().y
        dlat = DIST_M / 111_320.0
        dlon = DIST_M / (111_320.0 * max(math.cos(math.radians(lat)), 0.01))
        x0, y0, x1, y1 = g.bounds
        for j in arbol.query(shape({"type": "Polygon", "coordinates": [[[x0 - dlon, y0 - dlat], [x1 + dlon, y0 - dlat], [x1 + dlon, y1 + dlat], [x0 - dlon, y1 + dlat], [x0 - dlon, y0 - dlat]]]})):
            j = int(j)
            if j <= i or not une(j) or raiz(i) == raiz(j):
                continue
            if distancia_m(g, geoms[j]) <= DIST_M:
                padre[raiz(j)] = raiz(i)

    grupos = {}
    for i in range(len(ids)):
        grupos.setdefault(raiz(i), []).append(i)

    complejos, por_sitio = [], {}
    for n, miembros in enumerate(sorted(grupos.values(), key=lambda m: ids[min(m)]), start=1):
        cid = f"CPX-{n:06d}"
        sids = sorted(ids[i] for i in miembros)
        estados = [sitios[s]["estado"] for s in sids]
        areas = [sitios[s].get("area_ha") or 0 for s in sids]
        lat = sum(sitios[s]["lat"] for s in sids) / len(sids)
        lon = sum(sitios[s]["lon"] for s in sids) / len(sids)
        complejos.append({
            "id": cid, "sitios": sids, "n_sitios": len(sids),
            "estado": estado_agregado(estados), "estados_sitios": dict(zip(sids, estados)),
            "area_ha_suma": round(sum(areas), 2), "lat": round(lat, 6), "lon": round(lon, 6),
            "nombres": sorted({sitios[s].get("nombre") for s in sids if sitios[s].get("nombre")}),
        })
        for s in sids:
            por_sitio[s] = cid

    multi = [c for c in complejos if c["n_sitios"] > 1]
    salida = {
        "meta": {
            "titulo": "Complejos: basurales del catálogo a menos de 1 km entre sí",
            "generado_por": "idea-basurales-nisar/herramientas/complejos_agrupar.py",
            "criterio": f"distancia geodésica entre geometrías <= {DIST_M:.0f} m, agrupada por componentes conexas; los polígonos de menos de {AREA_MIN_UNE_HA:g} ha no unen (quedan solos)",
            "uso": "Validación por grupos (un complejo entero en la misma partición) y una sola etiqueta por complejo. Al extraer, el anillo excluye todos los polígonos de los catálogos.",
            "conteos": {
                "sitios": len(ids), "complejos": len(complejos), "complejos_con_varios_sitios": len(multi),
                "sitios_en_complejos_multiples": sum(c["n_sitios"] for c in multi),
                "estados": {e: sum(1 for c in complejos if c["estado"] == e) for e in ("abierto", "cerrado", "contradictorio", "desconocido")},
            },
        },
        "complejo_por_sitio": por_sitio,
        "complejos": complejos,
    }
    destino = os.path.join(dir_data, "basurales", "complejos.json")
    with open(destino, "w", encoding="utf-8") as fh:
        json.dump(salida, fh, ensure_ascii=False, separators=(",", ":"))
    print(json.dumps(salida["meta"]["conteos"], indent=1, ensure_ascii=False))
    print("Escrito:", destino)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "../../data")
