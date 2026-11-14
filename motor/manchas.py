"""Busca manchas de coherencia baja en un GUNW y las clasifica por forma. Es la prueba de la primera hora.

Uso: python manchas.py <archivo GUNW .h5> [--frame AMBA | --caja lon_oeste lat_sur lon_este lat_norte]

Por cada mancha da: superficie, centro (lat/lon), coherencia media y elongación
(1 = compacta; valores altos = alargada, típica de autopistas, vías y ríos).

La zona UTM y el hemisferio salen del producto (dataset `projection`), así que sirve para cualquier frame.
Sin `--frame` ni `--caja` mira el AMBA. Las manchas del índice final no salen de acá: salen de
`insomnio.manchas()`, que usa todos los pares (`pipeline_insomnio.py indice`).
"""
import argparse
import math
import os
import sys

import h5py
import numpy as np
from scipy import ndimage

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo  # noqa: E402

G = "science/LSAR/GUNW/grids/frequencyA/unwrappedInterferogram/"


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("gunw", help="archivo GUNW .h5")
    p.add_argument("--frame", default="AMBA", help="frame de data/frames.json (por defecto, AMBA)")
    p.add_argument("--caja", type=float, nargs=4, metavar=("LON_O", "LAT_S", "LON_E", "LAT_N"), help="caja a mirar, en el orden de GeoJSON")
    args = p.parse_args()
    fr = geo.frame_de_caja("CAJA", args.caja) if args.caja else geo.frame(args.frame)
    norte, oeste, sur, este = fr.caja
    with h5py.File(args.gunw, "r") as f:
        pol = next(q for q in ("HH", "VV", "HV", "VH") if f"{G}{q}/coherenceMagnitude" in f)
        proyeccion = f[G + "projection"]
        epsg = int(np.asarray(proyeccion.attrs.get("epsg_code", proyeccion[()])).ravel()[0])  # la zona UTM del producto
        xs, ys = f[G + "xCoordinates"][()], f[G + "yCoordinates"][()]
        paso = float(abs(xs[1] - xs[0]))
        x0, y0 = geo.utm(norte, oeste, epsg)
        x1, y1 = geo.utm(sur, este, epsg)
        c0, c1 = max(int((min(x0, x1) - xs[0]) / paso), 0), min(int((max(x0, x1) - xs[0]) / paso), len(xs))
        f0, f1 = max(int((ys[0] - max(y0, y1)) / paso), 0), min(int((ys[0] - min(y0, y1)) / paso), len(ys))
        if c1 <= c0 or f1 <= f0:
            sys.exit(f"La caja {fr.bbox} no cae en este producto (EPSG {epsg}).")
        coh = f[f"{G}{pol}/coherenceMagnitude"][f0:f1, c0:c1].astype(float)
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
        lat, lon = geo.latlon(xs[0] + ci * paso, ys[0] - fi * paso, epsg)
        filas.append((px * paso * paso / 1e4, float(lat), float(lon), float(coh[sl][sub].mean()), elong))
    filas.sort(reverse=True)
    print(f"{fr.nombre}: EPSG {epsg}, {paso:.0f} m, polarización {pol}")
    print("ha | lat | lon | coherencia | elongación | forma")
    for ha, lat, lon, m, el in filas[:30]:
        forma = "compacta" if el < 2.5 else ("alargada" if el < 5 else "lineal")
        print(f"{ha:6.1f} | {lat:.4f} | {lon:.4f} | {m:.2f} | {el:4.1f} | {forma}")


if __name__ == "__main__":
    main()
