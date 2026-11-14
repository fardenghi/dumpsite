"""Polígonos de los catálogos (`../data/basurales/` y `../data/negativos/`) y de las manchas, como shapely, para cruzar.

Lo usan `cruce_manchas.py` y `extraer_optico.py`. No calcula nada del radar.

- Basurales: `basurales/geometrias.geojson`, con `complejo` (de `complejos.json`), `estado` y `area_ha`.
- Negativos: en el AMBA, `negativos/geometrias_amba.geojson`; fuera, `negativos/geometrias_mundo.parquet`
  (geometría WKB). Con `clase`, `rol` y `prioridad`.
- Todo se filtra por la caja de trabajo y se puede pasar a la UTM del frame para medir áreas en metros.
"""
import json
import os

import shapely
from shapely.geometry import box, shape
from rasterio.warp import transform_geom

AQUI = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(AQUI, "..", "..", "data")
# Caja del AMBA en el orden de GeoJSON: [lon_oeste, lat_sur, lon_este, lat_norte] (geo.CAJA va en otro orden).
BBOX_AMBA = (-59.35, -34.90, -58.25, -34.25)


def epsg_utm(lon, lat):
    """EPSG de la zona UTM WGS84 que contiene el punto (326xx norte, 327xx sur)."""
    zona = int((lon + 180) // 6) + 1
    return (32600 if lat >= 0 else 32700) + zona


def _valida(g):
    if g is None or g.is_empty:
        return None
    if not g.is_valid:
        g = shapely.make_valid(g)
        g = shapely.union_all([p for p in getattr(g, "geoms", [g]) if p.geom_type in ("Polygon", "MultiPolygon")]) if g.geom_type == "GeometryCollection" else g
    return g if g.geom_type in ("Polygon", "MultiPolygon") and not g.is_empty else None


def a_utm(g, epsg):
    """Geometría shapely en grados -> en la UTM `epsg` (metros)."""
    return _valida(shape(transform_geom("EPSG:4326", f"EPSG:{epsg}", shapely.geometry.mapping(g))))


def manchas(fc, solo_candidatas=True):
    """Lista de (props, geometría en grados) de un FeatureCollection de manchas."""
    salida = []
    for f in fc["features"]:
        if solo_candidatas and f["properties"].get("descartada"):
            continue
        g = _valida(shape(f["geometry"]))
        if g is not None:
            salida.append((f["properties"], g))
    return salida


def _toca(bbox):
    caja = box(*bbox)
    return lambda g: g is not None and g.intersects(caja)


def basurales(bbox):
    """Basurales cuya geometría toca la caja: lista de dicts con id, catalogo, complejo, estado, area_ha, nombre y geom."""
    with open(os.path.join(DATA, "basurales", "geometrias.geojson"), encoding="utf-8") as fh:
        feats = json.load(fh)["features"]
    with open(os.path.join(DATA, "basurales", "complejos.json"), encoding="utf-8") as fh:
        cpx = json.load(fh)["complejo_por_sitio"]
    toca, salida = _toca(bbox), []
    o, s, e, n = bbox
    for f in feats:
        if not f.get("geometry") or f["geometry"]["type"] not in ("Polygon", "MultiPolygon"):
            continue
        v = f["geometry"]["coordinates"]
        # descarte rápido por un vértice cualquiera, antes de armar el shapely
        while isinstance(v[0], list):
            v = v[0]
        if not (o - 0.5 <= v[0] <= e + 0.5 and s - 0.5 <= v[1] <= n + 0.5):
            continue
        g = _valida(shape(f["geometry"]))
        if not toca(g):
            continue
        p = f["properties"]
        salida.append({"id_catalogo": p["id"], "catalogo": "basurales", "complejo": cpx.get(p["id"]),
                       "estado": p.get("estado"), "area_ha": p.get("area_ha"), "nombre": p.get("nombre"),
                       "clase": None, "rol": None, "geom": g})
    return salida


def negativos(bbox, fuente="auto"):
    """Negativos cuya geometría toca la caja. `fuente`: "amba", "mundo" o "auto" (amba si la caja cae en el AMBA)."""
    if fuente == "auto":
        b = BBOX_AMBA
        fuente = "amba" if b[0] <= (bbox[0] + bbox[2]) / 2 <= b[2] and b[1] <= (bbox[1] + bbox[3]) / 2 <= b[3] else "mundo"
    toca, salida = _toca(bbox), []
    if fuente == "amba":
        with open(os.path.join(DATA, "negativos", "geometrias_amba.geojson"), encoding="utf-8") as fh:
            filas = [(f["properties"], shape(f["geometry"]) if f.get("geometry") else None) for f in json.load(fh)["features"]]
    else:
        import pyarrow.parquet as pq
        t = pq.read_table(os.path.join(DATA, "negativos", "geometrias_mundo.parquet")).to_pylist()
        filas = [({k: v for k, v in r.items() if k != "geometry"}, shapely.from_wkb(r["geometry"]) if r["geometry"] else None) for r in t]
    for p, g in filas:
        g = _valida(g)
        if not toca(g):
            continue
        salida.append({"id_catalogo": p["id"], "catalogo": "negativos", "complejo": None, "estado": None,
                       "area_ha": p.get("area_ha"), "nombre": p.get("nombre"), "clase": p.get("clase"),
                       "rol": p.get("rol"), "geom": g})
    return salida


def catalogo(bbox, fuente_negativos="auto"):
    """Basurales y negativos que tocan la caja."""
    return basurales(bbox) + negativos(bbox, fuente_negativos)


def bbox_de(geoms, margen=0.02):
    """Caja [o, s, e, n] que contiene todas las geometrías, con un margen en grados."""
    o, s, e, n = shapely.total_bounds(geoms)
    return (o - margen, s - margen, e + margen, n + margen)
