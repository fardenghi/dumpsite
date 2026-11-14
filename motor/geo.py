"""Geometría de la grilla del AMBA: UTM 21S <-> lat/lon, grilla común y rasterizado de polígonos.

Todo vectorizado con numpy y sin pyproj. La conversión está verificada con el Obelisco
(-34.6037, -58.3816 -> 373317.5, 6170036.2 en EPSG 32721).
"""
import math

import numpy as np

# Caja del AMBA (lat_norte, lon_oeste, lat_sur, lon_este). Incluye Luján.
CAJA = (-34.25, -59.35, -34.90, -58.25)

_A, _F, _K0 = 6378137.0, 1 / 298.257223563, 0.9996
_E2 = _F * (2 - _F)
_EP2 = _E2 / (1 - _E2)


def utm(lat, lon, zona=21):
    """lat, lon (grados, escalares o arreglos) -> x, y en UTM sur."""
    la, lo = np.radians(lat), np.radians(lon)
    lo0 = math.radians((zona - 1) * 6 - 180 + 3)
    n = _A / np.sqrt(1 - _E2 * np.sin(la) ** 2)
    t, c, a = np.tan(la) ** 2, _EP2 * np.cos(la) ** 2, np.cos(la) * (lo - lo0)
    m = _A * ((1 - _E2 / 4 - 3 * _E2**2 / 64 - 5 * _E2**3 / 256) * la
              - (3 * _E2 / 8 + 3 * _E2**2 / 32 + 45 * _E2**3 / 1024) * np.sin(2 * la)
              + (15 * _E2**2 / 256 + 45 * _E2**3 / 1024) * np.sin(4 * la) - (35 * _E2**3 / 3072) * np.sin(6 * la))
    x = _K0 * n * (a + (1 - t + c) * a**3 / 6 + (5 - 18 * t + t**2 + 72 * c - 58 * _EP2) * a**5 / 120) + 500000
    y = _K0 * (m + n * np.tan(la) * (a**2 / 2 + (5 - t + 9 * c + 4 * c**2) * a**4 / 24
                                     + (61 - 58 * t + t**2 + 600 * c - 330 * _EP2) * a**6 / 720)) + 10000000
    return x, y


def latlon(x, y, zona=21):
    """x, y en UTM sur (escalares o arreglos) -> lat, lon en grados."""
    xx, m = np.asarray(x) - 500000, (np.asarray(y) - 10000000) / _K0
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


def grilla(paso):
    """Centros de píxel de la grilla común del AMBA en UTM 21S, alineados como los GUNW (centro = paso/2 mod paso)."""
    xa, ya = utm(CAJA[0], CAJA[1])
    xb, yb = utm(CAJA[2], CAJA[3])
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


def mascara_poligonos(anillos_lonlat, xs, ys):
    """Unión de varios anillos dados en (lon, lat)."""
    mascara = np.zeros((len(ys), len(xs)), dtype=bool)
    for anillo in anillos_lonlat:
        lon, lat = np.asarray(anillo, dtype=float).T
        mascara |= dentro(np.column_stack(utm(lat, lon)), xs, ys)
    return mascara


def caja_a_anillo(caja):
    """(lat_min, lat_max, lon_min, lon_max) -> anillo (lon, lat)."""
    la0, la1, lo0, lo1 = caja
    return [(lo0, la0), (lo1, la0), (lo1, la1), (lo0, la1), (lo0, la0)]


def area_y_centro(anillo_lonlat):
    """Superficie (ha) y centroide (lat, lon) de un anillo, calculados en UTM."""
    lon, lat = np.asarray(anillo_lonlat, dtype=float).T
    x, y = utm(lat, lon)
    x2, y2 = np.roll(x, -1), np.roll(y, -1)
    cruz = x * y2 - x2 * y
    a = cruz.sum() / 2
    if abs(a) < 1:
        return 0.0, (float(lat.mean()), float(lon.mean()))
    cx, cy = ((x + x2) * cruz).sum() / (6 * a), ((y + y2) * cruz).sum() / (6 * a)
    la, lo = latlon(cx, cy)
    return abs(a) / 1e4, (float(la), float(lo))


def a_mercator(capa, xs, ys, ancho=1400):
    """Remuestrea una capa de la grilla UTM a una imagen norte-arriba, regular en lon y en la y de Web Mercator.

    Devuelve (imagen, limites) con limites = (oeste, sur, este, norte). Es lo que espera una fuente
    `image` de MapLibre con las cuatro esquinas de esa caja. Vecino más cercano.
    """
    norte, oeste, sur, este = CAJA
    my = lambda la: np.log(np.tan(np.pi / 4 + np.radians(la) / 2))  # noqa: E731
    alto = int(round(ancho * (my(norte) - my(sur)) / np.radians(este - oeste)))
    lon = oeste + (np.arange(ancho) + 0.5) * (este - oeste) / ancho
    yy = my(norte) + (np.arange(alto) + 0.5) * (my(sur) - my(norte)) / alto
    lat = np.degrees(2 * np.arctan(np.exp(yy)) - np.pi / 2)
    x, y = utm(lat[:, None], lon[None, :])
    paso = xs[1] - xs[0]
    c = np.rint((x - xs[0]) / paso).astype(int)
    f = np.rint((ys[0] - y) / paso).astype(int)
    ok = (c >= 0) & (c < len(xs)) & (f >= 0) & (f < len(ys))
    salida = np.full((alto, ancho), np.nan, dtype=np.float32)
    salida[ok] = capa[f[ok], c[ok]]
    return salida, (oeste, sur, este, norte)
