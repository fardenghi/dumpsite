"""Coherencia dentro de predios conocidos (bounding box de OSM) contra un anillo alrededor.

Uso: python predios.py <archivo GUNW .h5> <carpeta_salida>
"""
import os
import sys

import h5py
import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from manchas import utm

G = "science/LSAR/GUNW/grids/frequencyA/"
# name: (lat_min, lat_max, lon_min, lon_max) — OpenStreetMap (Nominatim) bounding boxes, except where noted.
PREDIOS = {
    "Basural de Luján (OSM landfill; cerrado 1/07/2026)": (-34.5271, -34.5150, -59.1228, -59.1152),
    "CEAMSE González Catán (OSM landfill)": (-34.7921, -34.7791, -58.6738, -58.6498),
    "CEAMSE Ensenada (OSM landfill)": (-34.8558, -34.8423, -57.9741, -57.9600),
    "Norte III (bbox APROXIMADA, sin polígono OSM)": (-34.550, -34.525, -58.630, -58.595),
    "Control: CABA (Palermo)": (-34.590, -34.575, -58.430, -58.410),
}
ANILLO_M = 1500


def stats(capa, xs, ys, paso, caja, extra=0.0):
    la0, la1, lo0, lo1 = caja
    x0, y0 = utm(la1, lo0)
    x1, y1 = utm(la0, lo1)
    x0, x1, y0, y1 = x0 - extra, x1 + extra, y0 + extra, y1 - extra
    c0, c1 = int((x0 - xs[0]) / paso), int((x1 - xs[0]) / paso) + 1
    f0, f1 = int((ys[0] - y0) / paso), int((ys[0] - y1) / paso) + 1
    return (f0, f1, c0, c1)


def main():
    ruta, salida = sys.argv[1], sys.argv[2]
    os.makedirs(salida, exist_ok=True)
    with h5py.File(ruta, "r") as f:
        capas = {
            "80 m": (f[G + "unwrappedInterferogram/HH/coherenceMagnitude"], f[G + "unwrappedInterferogram/HH/xCoordinates"][()], f[G + "unwrappedInterferogram/HH/yCoordinates"][()], 80.0),
            "20 m": (f[G + "wrappedInterferogram/HH/coherenceMagnitude"], f[G + "wrappedInterferogram/HH/xCoordinates"][()], f[G + "wrappedInterferogram/HH/yCoordinates"][()], 20.0),
        }
        print("predio | capa | mediana adentro | mediana anillo 1,5 km | diferencia")
        figs = []
        for nombre, caja in PREDIOS.items():
            for etiqueta, (ds, xs, ys, paso) in capas.items():
                f0, f1, c0, c1 = stats(ds, xs, ys, paso, caja, extra=ANILLO_M)
                if f0 < 0 or c0 < 0 or f1 > ds.shape[0] or c1 > ds.shape[1]:
                    print(f"{nombre} | {etiqueta} | fuera del frame")
                    continue
                grande = np.array(ds[f0:f1, c0:c1], dtype=float)
                n_anillo = int(ANILLO_M / paso)
                adentro = grande[n_anillo:-n_anillo, n_anillo:-n_anillo]
                mascara = np.ones_like(grande, bool)
                mascara[n_anillo:-n_anillo, n_anillo:-n_anillo] = False
                anillo = grande[mascara]
                ok = lambda a: a[np.isfinite(a) & (a > 0)]
                ma, mr = np.median(ok(adentro)), np.median(ok(anillo))
                print(f"{nombre} | {etiqueta} | {ma:.2f} | {mr:.2f} | {ma - mr:+.2f}")
                if etiqueta == "20 m":
                    figs.append((nombre, grande, n_anillo))
    fig, ejes = plt.subplots(1, len(figs), figsize=(4.2 * len(figs), 4.6))
    for eje, (nombre, grande, n) in zip(ejes, figs):
        eje.imshow(grande, cmap="gray", vmin=0, vmax=1)
        h, w = grande.shape
        eje.add_patch(plt.Rectangle((n, n), w - 2 * n, h - 2 * n, fill=False, ec="red", lw=1.5))
        eje.set_title(nombre, fontsize=8)
        eje.axis("off")
    fig.suptitle("Coherencia NISAR 20 m, par 30/09-12/10/2026 (blanco = estable, negro = cambió). Rojo: predio", fontsize=9)
    fig.tight_layout()
    destino = os.path.join(salida, "predios_coherencia_20m.png")
    fig.savefig(destino, dpi=130)
    print("Figura:", destino)


if __name__ == "__main__":
    main()
