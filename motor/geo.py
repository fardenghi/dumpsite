"""Geometry of a frame's grid: UTM <-> lat/lon, common grid and polygon rasterization.

All vectorized with numpy and without pyproj. It works for any UTM zone in both hemispheres: the zone and the
hemisphere come from the EPSG (326xx north, 327xx south), which is the NISAR product's (`projection` dataset).
Without parameters, everything works on the AMBA (UTM 21 south), as before.

The conversion is checked with the Obelisco (-34.6037, -58.3816 -> 373317.5, 6170036.2 in EPSG 32721), with a
point in Mexico City (19.4270, -99.1677 -> 482395.1, 2148083.7 in EPSG 32614) and, against pyproj, with 500 random
points in each of 8 zones of both hemispheres: the maximum difference is 2 mm.

A **frame** is a working area: a box in lat/lon, the EPSG of its grid and the NISAR orbits that cover it.
It comes from `../data/catalogos/frames.json` (stage 2), from `<salida>/<FRAME>/frame.json` (written by the pipeline) or from `--caja`.
"""
import json
import math
import os
from dataclasses import dataclass

import numpy as np

# AMBA box (lat_north, lon_west, lat_south, lon_east). It includes Luján.
CAJA = (-34.25, -59.35, -34.90, -58.25)
EPSG = 32721  # UTM 21 south, the one of the AMBA GUNWs
FRAMES_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "catalogos", "frames.json")

_A, _F, _K0 = 6378137.0, 1 / 298.257223563, 0.9996
_E2 = _F * (2 - _F)
_EP2 = _E2 / (1 - _E2)


def zona_de_epsg(epsg):
    """EPSG of a WGS84 UTM zone -> (zone, is_south). 326xx is north and 327xx is south."""
    epsg = int(epsg)
    if not (32601 <= epsg <= 32660 or 32701 <= epsg <= 32760):
        raise ValueError(f"EPSG {epsg}: sólo se aceptan zonas UTM en WGS84 (32601 a 32660 y 32701 a 32760). "
                         "Los productos polares de NISAR (3413 y 3031) no se usan.")
    return epsg % 100, epsg // 100 == 327


def epsg_de(lat, lon):
    """EPSG of the UTM zone that corresponds to a point (without the Norway and Svalbard exceptions)."""
    zona = min(60, int(math.floor((float(lon) + 180) / 6)) + 1)
    return (32700 if float(lat) < 0 else 32600) + zona


def utm(lat, lon, epsg=EPSG):
    """lat, lon (degrees, scalars or arrays) -> x, y in the UTM zone of `epsg`."""
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
    """x, y in the UTM zone of `epsg` (scalars or arrays) -> lat, lon in degrees."""
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
    """Pixel centers of a box's common grid, in the UTM zone of `epsg`, aligned like the GUNWs
    (center = step/2 mod step). Without parameters it's the AMBA grid in UTM 21S."""
    xa, ya = utm(caja[0], caja[1], epsg)
    xb, yb = utm(caja[2], caja[3], epsg)
    x0, x1 = min(xa, xb), max(xa, xb)
    y0, y1 = min(ya, yb), max(ya, yb)
    med = paso / 2
    xs = np.arange(math.floor((x0 - med) / paso) * paso + med, x1, paso)
    ys = np.arange(math.ceil((y1 - med) / paso) * paso + med, y0, -paso)  # de norte a sur
    return xs, ys


def dentro(anillo_xy, xs, ys):
    """Mask (len(ys), len(xs)) of the pixel centers inside a closed ring [(x, y), ...].

    Even-odd rule, evaluated only within the ring's box.
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
    """Union of several rings given in (lon, lat), over a grid in the UTM zone of `epsg`."""
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
    """Area (ha) and centroid (lat, lon) of a ring, computed in UTM.

    Without `epsg` it uses the ring's own UTM zone, so it works anywhere in the world.
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
    """Resamples a layer of the UTM grid to a north-up image, regular in lon and in Web Mercator y.

    Returns (image, limits) with limits = (west, south, east, north). It's what a MapLibre `image` source
    expects with the four corners of that box. Nearest neighbor.
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
    """A working area. `caja` goes like `CAJA`: (lat_north, lon_west, lat_south, lon_east).

    `epsg` is that of the common grid. If `epsg_fijo` is False, it's the one for the center of the box and
    `pipeline_insomnio.py procesar` replaces it with that of the first GUNW (`projection` dataset).
    Empty `orbitas` means all those that cross the box. `frames_nisar` (from `frames.json`) further limits
    it to those NISAR frames, which are the ones that cover the box; empty means all.
    """
    nombre: str = "AMBA"
    caja: tuple = CAJA
    epsg: int = EPSG
    orbitas: tuple = (10, 161)
    desde: str = "2026-06-25"  # product period, YYYY-MM-DD ("" = no limit)
    hasta: str = "2026-10-12"
    epsg_fijo: bool = True
    ciudad: str = "Buenos Aires"
    pais: str = "ARG"
    frames_nisar: tuple = ()  # NISAR frames to use, like "034_A_019" (orbit, direction and frame); empty = those that cross the box

    @property
    def bbox(self):
        """The box in GeoJSON and `frames.json` order: [lon_west, lat_south, lon_east, lat_north]."""
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
    """Builds a Frame from an entry of `frames.json` or `frame.json` (bbox in GeoJSON order)."""
    o, s, e, n = (float(v) for v in d["bbox"])
    epsg = d.get("epsg")
    orbitas = d.get("orbita", [])
    return Frame(nombre=str(d["frame"]).upper(), caja=(n, o, s, e), epsg=int(epsg) if epsg else epsg_de((n + s) / 2, (o + e) / 2),
                 orbitas=tuple(int(x) for x in (orbitas if isinstance(orbitas, (list, tuple)) else [orbitas])),
                 desde=d.get("fecha_inicio") or "", hasta=d.get("fecha_fin") or "",
                 epsg_fijo=bool(epsg) and d.get("epsg_fijo", True), ciudad=d.get("ciudad") or "", pais=d.get("pais") or "",
                 frames_nisar=tuple(d.get("frames_nisar") or ()))


def frame_de_caja(nombre, bbox, epsg=None, orbitas=()):
    """Frame from a box [lon_west, lat_south, lon_east, lat_north] (GeoJSON order)."""
    return frame_de_dict({"frame": nombre, "bbox": list(bbox), "epsg": epsg, "orbita": list(orbitas)})


def frames_conocidos(ruta=FRAMES_JSON):
    """The frames in `data/catalogos/frames.json` (stage 2), in priority order. The AMBA is always there."""
    frames = {}
    if os.path.exists(ruta):
        with open(ruta, encoding="utf-8") as fh:
            for d in json.load(fh).get("frames", []):
                frames[str(d["frame"]).upper()] = frame_de_dict(d)
    frames.setdefault("AMBA", AMBA)
    return frames


def frame(nombre="AMBA", carpeta=None, ruta=FRAMES_JSON):
    """Looks up a frame by name: first in `frames.json` and, if it's not there, in `<carpeta>/frame.json` (what the
    pipeline saved for a frame defined with `--caja`).

    The AMBA always uses the reference grid (`CAJA`, UTM 21 south), so the crops and the already computed
    products stay valid, even if `frames.json` carries another box.
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
