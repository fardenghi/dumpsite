"""Busca manchas de coherencia baja en el AMBA y las clasifica por forma.

Uso: python manchas.py <archivo GUNW .h5>

Por cada mancha da: superficie, centro (lat/lon), coherencia media y elongación
(1 = compacta; valores altos = alargada, típica de autopistas, vías y ríos).
"""
import math
import sys

import h5py
import numpy as np
from scipy import ndimage

G = "science/LSAR/GUNW/grids/frequencyA/unwrappedInterferogram/HH/"
CAJA = (-34.25, -59.35, -34.90, -58.25)  # lat_norte, lon_oeste, lat_sur, lon_este (AMBA)


def utm(lat, lon, zona=21):
    a, f = 6378137.0, 1 / 298.257223563
    k0, e2 = 0.9996, f * (2 - f)
    ep2 = e2 / (1 - e2)
    la, lo = math.radians(lat), math.radians(lon)
    lo0 = math.radians((zona - 1) * 6 - 180 + 3)
    n = a / math.sqrt(1 - e2 * math.sin(la) ** 2)
    t, c, A = math.tan(la) ** 2, ep2 * math.cos(la) ** 2, math.cos(la) * (lo - lo0)
    m = a * ((1 - e2 / 4 - 3 * e2**2 / 64 - 5 * e2**3 / 256) * la - (3 * e2 / 8 + 3 * e2**2 / 32 + 45 * e2**3 / 1024) * math.sin(2 * la)
             + (15 * e2**2 / 256 + 45 * e2**3 / 1024) * math.sin(4 * la) - (35 * e2**3 / 3072) * math.sin(6 * la))
    x = k0 * n * (A + (1 - t + c) * A**3 / 6 + (5 - 18 * t + t**2 + 72 * c - 58 * ep2) * A**5 / 120) + 500000
    y = k0 * (m + n * math.tan(la) * (A**2 / 2 + (5 - t + 9 * c + 4 * c**2) * A**4 / 24 + (61 - 58 * t + t**2 + 600 * c - 330 * ep2) * A**6 / 720)) + 10000000
    return x, y


def latlon(x, y, zona=21):
    a, f = 6378137.0, 1 / 298.257223563
    k0, e2 = 0.9996, f * (2 - f)
    ep2 = e2 / (1 - e2)
    xx, m = x - 500000, (y - 10000000) / k0
    mu = m / (a * (1 - e2 / 4 - 3 * e2**2 / 64 - 5 * e2**3 / 256))
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    p = mu + (3 * e1 / 2 - 27 * e1**3 / 32) * math.sin(2 * mu) + (21 * e1**2 / 16 - 55 * e1**4 / 32) * math.sin(4 * mu) + (151 * e1**3 / 96) * math.sin(6 * mu)
    n1 = a / math.sqrt(1 - e2 * math.sin(p) ** 2)
    t1, c1 = math.tan(p) ** 2, ep2 * math.cos(p) ** 2
    r1 = a * (1 - e2) / (1 - e2 * math.sin(p) ** 2) ** 1.5
    d = xx / (n1 * k0)
    lat = p - (n1 * math.tan(p) / r1) * (d**2 / 2 - (5 + 3 * t1 + 10 * c1 - 4 * c1**2 - 9 * ep2) * d**4 / 24)
    lon = (d - (1 + 2 * t1 + c1) * d**3 / 6) / math.cos(p)
    return math.degrees(lat), (zona - 1) * 6 - 180 + 3 + math.degrees(lon)


def main():
    with h5py.File(sys.argv[1], "r") as f:
        xs, ys = f[G + "xCoordinates"][()], f[G + "yCoordinates"][()]
        x0, y0 = utm(CAJA[0], CAJA[1])
        x1, y1 = utm(CAJA[2], CAJA[3])
        c0, c1 = int((min(x0, x1) - xs[0]) / 80), int((max(x0, x1) - xs[0]) / 80)
        f0, f1 = int((ys[0] - max(y0, y1)) / 80), int((ys[0] - min(y0, y1)) / 80)
        coh = f[G + "coherenceMagnitude"][f0:f1, c0:c1].astype(float)
    xs, ys = xs[c0:c1], ys[f0:f1]
    valido = np.isfinite(coh) & (coh > 0)
    base = np.where(valido, coh, 1.0)
    suave = ndimage.uniform_filter(base, 3)
    fondo = ndimage.uniform_filter(base, 31)  # entorno de ~2,5 km
    mascara = valido & (suave < 0.30) & (suave < fondo - 0.20)
    etiquetas, n = ndimage.label(mascara)
    filas = []
    for i, sl in enumerate(ndimage.find_objects(etiquetas), start=1):
        sub = etiquetas[sl] == i
        px = int(sub.sum())
        if px < 8:  # menos de ~5 ha
            continue
        rr, cc = np.nonzero(sub)
        cov = np.cov(np.vstack([rr, cc])) if px > 2 else np.eye(2)
        ev = np.sort(np.linalg.eigvalsh(cov))
        elong = math.sqrt(ev[1] / max(ev[0], 1e-6))
        fi, ci = rr.mean() + sl[0].start, cc.mean() + sl[1].start
        lat, lon = latlon(xs[0] + ci * 80, ys[0] - fi * 80)
        filas.append((px * 0.64, lat, lon, float(coh[etiquetas == i].mean()), elong))
    filas.sort(reverse=True)
    print("ha | lat | lon | coherencia | elongación | forma")
    for ha, lat, lon, m, el in filas[:30]:
        forma = "compacta" if el < 2.5 else ("alargada" if el < 5 else "lineal")
        print(f"{ha:6.1f} | {lat:.4f} | {lon:.4f} | {m:.2f} | {el:4.1f} | {forma}")


if __name__ == "__main__":
    main()
