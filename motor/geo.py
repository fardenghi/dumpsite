"""Geometría de la grilla de un frame: UTM <-> lat/lon, grilla común y rasterizado de polígonos.

Todo vectorizado con numpy y sin pyproj. Sirve para cualquier zona UTM de los dos hemisferios: la zona y el
hemisferio salen del EPSG (326xx norte, 327xx sur), que es el del producto de NISAR (dataset `projection`).
Sin parámetros, todo trabaja sobre el AMBA (UTM 21 sur), como antes.

La conversión está verificada con el Obelisco (-34.6037, -58.3816 -> 373317.5, 6170036.2 en EPSG 32721), con un
punto de Ciudad de México (19.4270, -99.1677 -> 482395.1, 2148083.7 en EPSG 32614) y, contra pyproj, con 500 puntos
al azar en cada una de 8 zonas de los dos hemisferios: la diferencia máxima es de 2 mm.

Un **frame** es un área de trabajo: una caja en lat/lon, el EPSG de su grilla y las órbitas de NISAR que la cubren.
Sale de `../../data/frames.json` (etapa 2), de `<salida>/<FRAME>/frame.json` (lo escribe el pipeline) o de `--caja`.
"""
import json
import math
import os
from dataclasses import dataclass

import numpy as np

# Caja del AMBA (lat_norte, lon_oeste, lat_sur, lon_este). Incluye Luján.
CAJA = (-34.25, -59.35, -34.90, -58.25)
EPSG = 32721  # UTM 21 sur, la de los GUNW del AMBA
FRAMES_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "frames.json")

_A, _F, _K0 = 6378137.0, 1 / 298.257223563, 0.9996
_E2 = _F * (2 - _F)
_EP2 = _E2 / (1 - _E2)


def zona_de_epsg(epsg):
    """EPSG de una zona UTM en WGS84 -> (zona, es_sur). 326xx es norte y 327xx es sur."""
    epsg = int(epsg)
    if not (32601 <= epsg <= 32660 or 32701 <= epsg <= 32760):
        raise ValueError(f"EPSG {epsg}: sólo se aceptan zonas UTM en WGS84 (32601 a 32660 y 32701 a 32760). "
                         "Los productos polares de NISAR (3413 y 3031) no se usan.")
    return epsg % 100, epsg // 100 == 327


def epsg_de(lat, lon):
    """EPSG de la zona UTM que le corresponde a un punto (sin las excepciones de Noruega y Svalbard)."""
    zona = min(60, int(math.floor((float(lon) + 180) / 6)) + 1)
    return (32700 if float(lat) < 0 else 32600) + zona


def utm(lat, lon, epsg=EPSG):
    """lat, lon (grados, escalares o arreglos) -> x, y en la zona UTM de `epsg`."""
    zona, sur = zona_de_epsg(epsg)
    la, lo = np.radians(lat), np.radians(lon)
    lo0 = math.radians((zona - 1) * 6 - 180 + 3)
    n = _A / np.sqrt(1 - _E2 * np.sin(la) ** 2)
    t, c, a = np.tan(la) ** 2, _EP2 * np.cos(la) ** 2, np.cos(la) * (lo - lo0)
    m = _A * ((1 - _E2 / 4 - 3 * _E2**2 / 64 - 5 * _E2**3 / 256) * la
              - (3 * _E2 / 8 + 3 * _E2**2 / 32 + 45 * _E2**3 / 1024) * np.sin(2 * la)
              + (15 * _E2**2 / 256 + 45 * _E2**3 / 1024) * np.sin(4 * la) - (35 * _E2**3 / 3072) * np.sin(6 * la))
    x = _K0 * n * (a + (1 - t + c) * a**3 / 6 + (5 - 18 * t + t**2 + 72 * c - 58 * _EP2) * a**5 / 120) + 500000
    y = _K0 * (m + n * np.tan(la) * (a**2 / 2 + (5 - t + 9 * c + 4 * c**2) * a**4 / 24
                                     + (61 - 58 * t + t**2 + 600 * c - 330 * _EP2) * a**6 / 720)) + (10000000 if sur else 0)
    return x, y


def latlon(x, y, epsg=EPSG):
    """x, y en la zona UTM de `epsg` (escalares o arreglos) -> lat, lon en grados."""
    zona, sur = zona_de_epsg(epsg)
    xx, m = np.asarray(x) - 500000, (np.asarray(y) - (10000000 if sur else 0)) / _K0
    mu = m / (_A * (1 - _E2 / 4 - 3 * _E2**2 / 64 - 5 * _E2**3 / 256))
    e1 = (1 - math.sqrt(1 - _E2)) / (1 + math.sqrt(1 - _E2))
    p = (mu + (3 * e1 / 2 - 27 * e1**3 / 32) * np.sin(2 * mu) + (21 * e1**2 / 16 - 55 * e1**4 / 32) * np.sin(4 * mu)
         + (151 * e1**3 / 96) * np.sin(6 * mu))
    n1 = _A / np.sqrt(1 - _E2 * np.sin(p) ** 2)
    t1, c1 = np.tan(p) ** 2, _EP2 * np.cos(p) ** 2
    r1 = _A * (1 - _E2) / (1 - _E2 * np.sin(p) ** 2) ** 1.5
    d = xx / (n1 * _K0)
    lat = p - (n1 * np.tan(p) / r1) * (d**2 / 2 - (5 + 3 * t1 + 10 * c1 - 4 * c1**2 - 9 * _EP2) * d**4 / 24
                                       + (61 + 90 * t1 + 298 * c1 + 45 * t1**2 - 252 * _EP2 - 3 * c1**2) * d**6 / 720)
    lon = math.radians((zona - 1) * 6 - 180 + 3) + (d - (1 + 2 * t1 + c1) * d**3 / 6
                                                    + (5 - 2 * c1 + 28 * t1 - 3 * c1**2 + 8 * _EP2 + 24 * t1**2) * d**5 / 120) / np.cos(p)
    return np.degrees(lat), np.degrees(lon)


def grilla(paso, caja=CAJA, epsg=EPSG):
    """Centros de píxel de la grilla común de una caja, en la zona UTM de `epsg`, alineados como los GUNW
    (centro = paso/2 mod paso). Sin parámetros es la grilla del AMBA en UTM 21S."""
    xa, ya = utm(caja[0], caja[1], epsg)
    xb, yb = utm(caja[2], caja[3], epsg)
    x0, x1 = min(xa, xb), max(xa, xb)
    y0, y1 = min(ya, yb), max(ya, yb)
    med = paso / 2
    xs = np.arange(math.floor((x0 - med) / paso) * paso + med, x1, paso)
    ys = np.arange(math.ceil((y1 - med) / paso) * paso + med, y0, -paso)  # de norte a sur
    return xs, ys


def dentro(anillo_xy, xs, ys):
    """Máscara (len(ys), len(xs)) de los centros de píxel adentro de un anillo cerrado [(x, y), ...].

    Regla par-impar, evaluada sólo en la caja del anillo.
    """
    p = np.asarray(anillo_xy, dtype=float)
    mascara = np.zeros((len(ys), len(xs)), dtype=bool)
    cols = np.nonzero((xs >= p[:, 0].min()) & (xs <= p[:, 0].max()))[0]
    filas = np.nonzero((ys >= p[:, 1].min()) & (ys <= p[:, 1].max()))[0]
    if not len(cols) or not len(filas):
        return mascara
    x, y = xs[cols][None, :], ys[filas][:, None]
    sub = np.zeros((len(filas), len(cols)), dtype=bool)
    for (x1, y1), (x2, y2) in zip(p, np.roll(p, -1, axis=0)):
        if y1 == y2:
            continue
        cruza = (y1 > y) != (y2 > y)
        sub ^= cruza & (x < (x2 - x1) * (y - y1) / (y2 - y1) + x1)
    mascara[np.ix_(filas, cols)] = sub
    return mascara


def mascara_poligonos(anillos_lonlat, xs, ys, epsg=EPSG):
    """Unión de varios anillos dados en (lon, lat), sobre una grilla en la zona UTM de `epsg`."""
    mascara = np.zeros((len(ys), len(xs)), dtype=bool)
    for anillo in anillos_lonlat:
        lon, lat = np.asarray(anillo, dtype=float)[:, :2].T
        mascara |= dentro(np.column_stack(utm(lat, lon, epsg)), xs, ys)
    return mascara


def caja_a_anillo(caja):
    """(lat_min, lat_max, lon_min, lon_max) -> anillo (lon, lat)."""
    la0, la1, lo0, lo1 = caja
    return [(lo0, la0), (lo1, la0), (lo1, la1), (lo0, la1), (lo0, la0)]


def area_y_centro(anillo_lonlat, epsg=None):
    """Superficie (ha) y centroide (lat, lon) de un anillo, calculados en UTM.

    Sin `epsg` usa la zona UTM del propio anillo, así sirve en cualquier lugar del mundo.
    """
    lon, lat = np.asarray(anillo_lonlat, dtype=float)[:, :2].T
    if epsg is None:
        epsg = epsg_de(lat.mean(), lon.mean())
    x, y = utm(lat, lon, epsg)
    x2, y2 = np.roll(x, -1), np.roll(y, -1)
    cruz = x * y2 - x2 * y
    a = cruz.sum() / 2
    if abs(a) < 1:
        return 0.0, (float(lat.mean()), float(lon.mean()))
    cx, cy = ((x + x2) * cruz).sum() / (6 * a), ((y + y2) * cruz).sum() / (6 * a)
    la, lo = latlon(cx, cy, epsg)
    return abs(a) / 1e4, (float(la), float(lo))


def a_mercator(capa, xs, ys, ancho=1400, caja=CAJA, epsg=EPSG):
    """Remuestrea una capa de la grilla UTM a una imagen norte-arriba, regular en lon y en la y de Web Mercator.

    Devuelve (imagen, limites) con limites = (oeste, sur, este, norte). Es lo que espera una fuente
    `image` de MapLibre con las cuatro esquinas de esa caja. Vecino más cercano.
    """
    norte, oeste, sur, este = caja
    my = lambda la: np.log(np.tan(np.pi / 4 + np.radians(la) / 2))  # noqa: E731
    alto = int(round(ancho * (my(norte) - my(sur)) / np.radians(este - oeste)))
    lon = oeste + (np.arange(ancho) + 0.5) * (este - oeste) / ancho
    yy = my(norte) + (np.arange(alto) + 0.5) * (my(sur) - my(norte)) / alto
    lat = np.degrees(2 * np.arctan(np.exp(yy)) - np.pi / 2)
    x, y = utm(lat[:, None], lon[None, :], epsg)
    paso = xs[1] - xs[0]
    c = np.rint((x - xs[0]) / paso).astype(int)
    f = np.rint((ys[0] - y) / paso).astype(int)
    ok = (c >= 0) & (c < len(xs)) & (f >= 0) & (f < len(ys))
    salida = np.full((alto, ancho), np.nan, dtype=np.float32)
    salida[ok] = capa[f[ok], c[ok]]
    return salida, (oeste, sur, este, norte)


# ------------------------------------------------------------------ frames
@dataclass(frozen=True)
class Frame:
    """Un área de trabajo. `caja` va como `CAJA`: (lat_norte, lon_oeste, lat_sur, lon_este).

    `epsg` es el de la grilla común. Si `epsg_fijo` es False, es el que le toca al centro de la caja y
    `pipeline_insomnio.py procesar` lo reemplaza por el del primer GUNW (dataset `projection`).
    `orbitas` vacío quiere decir todas las que crucen la caja. `frames_nisar` (de `frames.json`) limita
    además a esos frames de NISAR, que son los que cubren la caja; vacío quiere decir todos.
    """
    nombre: str = "AMBA"
    caja: tuple = CAJA
    epsg: int = EPSG
    orbitas: tuple = (10, 161)
    desde: str = "2026-06-25"  # período de los productos, AAAA-MM-DD ("" = sin límite)
    hasta: str = "2026-10-12"
    epsg_fijo: bool = True
    ciudad: str = "Buenos Aires"
    pais: str = "ARG"
    frames_nisar: tuple = ()  # frames de NISAR a usar, como "034_A_019" (órbita, dirección y frame); vacío = los que crucen la caja

    @property
    def bbox(self):
        """La caja en el orden de GeoJSON y de `frames.json`: [lon_oeste, lat_sur, lon_este, lat_norte]."""
        n, o, s, e = self.caja
        return [o, s, e, n]

    @property
    def hemisferio(self):
        return "S" if zona_de_epsg(self.epsg)[1] else "N"

    def grilla(self, paso):
        return grilla(paso, self.caja, self.epsg)

    def utm(self, lat, lon):
        return utm(lat, lon, self.epsg)

    def latlon(self, x, y):
        return latlon(x, y, self.epsg)

    def mascara_poligonos(self, anillos_lonlat, xs, ys):
        return mascara_poligonos(anillos_lonlat, xs, ys, self.epsg)

    def contiene(self, lat, lon):
        n, o, s, e = self.caja
        return (s <= lat) & (lat <= n) & (o <= lon) & (lon <= e)

    def dict(self):
        return {"frame": self.nombre, "orbita": list(self.orbitas), "ciudad": self.ciudad, "pais": self.pais,
                "hemisferio": self.hemisferio, "epsg": self.epsg, "epsg_fijo": self.epsg_fijo, "bbox": self.bbox,
                "fecha_inicio": self.desde, "fecha_fin": self.hasta, "frames_nisar": list(self.frames_nisar)}


AMBA = Frame()


def frame_de_dict(d):
    """Arma un Frame con una entrada de `frames.json` o de `frame.json` (bbox en el orden de GeoJSON)."""
    o, s, e, n = (float(v) for v in d["bbox"])
    epsg = d.get("epsg")
    orbitas = d.get("orbita", [])
    return Frame(nombre=str(d["frame"]).upper(), caja=(n, o, s, e), epsg=int(epsg) if epsg else epsg_de((n + s) / 2, (o + e) / 2),
                 orbitas=tuple(int(x) for x in (orbitas if isinstance(orbitas, (list, tuple)) else [orbitas])),
                 desde=d.get("fecha_inicio") or "", hasta=d.get("fecha_fin") or "",
                 epsg_fijo=bool(epsg) and d.get("epsg_fijo", True), ciudad=d.get("ciudad") or "", pais=d.get("pais") or "",
                 frames_nisar=tuple(d.get("frames_nisar") or ()))


def frame_de_caja(nombre, bbox, epsg=None, orbitas=()):
    """Frame a partir de una caja [lon_oeste, lat_sur, lon_este, lat_norte] (el orden de GeoJSON)."""
    return frame_de_dict({"frame": nombre, "bbox": list(bbox), "epsg": epsg, "orbita": list(orbitas)})


def frames_conocidos(ruta=FRAMES_JSON):
    """Los frames de `data/frames.json` (etapa 2), en su orden de prioridad. El AMBA está siempre."""
    frames = {}
    if os.path.exists(ruta):
        with open(ruta, encoding="utf-8") as fh:
            for d in json.load(fh).get("frames", []):
                frames[str(d["frame"]).upper()] = frame_de_dict(d)
    frames.setdefault("AMBA", AMBA)
    return frames


def frame(nombre="AMBA", carpeta=None, ruta=FRAMES_JSON):
    """Busca un frame por nombre: primero en `frames.json` y, si no está, en `<carpeta>/frame.json` (lo que guardó
    el pipeline para un frame definido con `--caja`).

    El AMBA siempre usa la grilla de referencia (`CAJA`, UTM 21 sur), para que los recortes y los productos ya
    calculados sigan valiendo, aunque `frames.json` traiga otra caja.
    """
    nombre = str(nombre).upper()
    if nombre == "AMBA":
        return AMBA
    frames = frames_conocidos(ruta)
    if nombre in frames:
        return frames[nombre]
    if carpeta and os.path.exists(os.path.join(carpeta, "frame.json")):
        with open(os.path.join(carpeta, "frame.json"), encoding="utf-8") as fh:
            return frame_de_dict(json.load(fh))
    raise KeyError(f"No conozco el frame {nombre}. Está(n): {', '.join(frames)}. "
                   f"Agregalo a data/frames.json o pasá --caja lon_oeste lat_sur lon_este lat_norte.")
