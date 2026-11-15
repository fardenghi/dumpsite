"""Quick check of the "Insomnes" idea: coherence layer of a NISAR GUNW.

Usage:
    python coherencia_gunw.py <file.h5> [output_folder]

It does three things:
1. Lists the file's datasets with "coherence" in the name.
2. Crops the coherence around sites of interest (approximate coordinates) and computes statistics.
3. Saves a figure with the AMBA overview and the crops.
"""
import math
import os
import sys

import h5py
import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Sites: (name, lat, lon, description). APPROXIMATE coordinates, to be confirmed with an optical image.
SITIOS = [
    ("Norte III (CEAMSE)", -34.535, -58.615, "relleno activo: control positivo"),
    ("Basural de Luján", -34.520, -59.110, "cerrado el 1/07/2026 (ubicación estimada)"),
    ("CABA urbano", -34.585, -58.420, "control urbano: coherencia alta esperada"),
    ("Campo rural", -34.750, -59.400, "control rural: variable por cultivos"),
]
VENTANA_M = 3000  # half window of the crop, in meters


def utm_desde_latlon(lat, lon, zona, sur):
    """UTM projection (WGS84) without external dependencies. Returns (easting, northing) in meters."""
    a, f = 6378137.0, 1 / 298.257223563
    k0 = 0.9996
    e2 = f * (2 - f)
    ep2 = e2 / (1 - e2)
    lat_r, lon_r = math.radians(lat), math.radians(lon)
    lon0 = math.radians((zona - 1) * 6 - 180 + 3)
    n = a / math.sqrt(1 - e2 * math.sin(lat_r) ** 2)
    t = math.tan(lat_r) ** 2
    c = ep2 * math.cos(lat_r) ** 2
    aa = math.cos(lat_r) * (lon_r - lon0)
    m = a * ((1 - e2 / 4 - 3 * e2**2 / 64 - 5 * e2**3 / 256) * lat_r
             - (3 * e2 / 8 + 3 * e2**2 / 32 + 45 * e2**3 / 1024) * math.sin(2 * lat_r)
             + (15 * e2**2 / 256 + 45 * e2**3 / 1024) * math.sin(4 * lat_r)
             - (35 * e2**3 / 3072) * math.sin(6 * lat_r))
    este = k0 * n * (aa + (1 - t + c) * aa**3 / 6 + (5 - 18 * t + t**2 + 72 * c - 58 * ep2) * aa**5 / 120) + 500000.0
    norte = k0 * (m + n * math.tan(lat_r) * (aa**2 / 2 + (5 - t + 9 * c + 4 * c**2) * aa**4 / 24
                                             + (61 - 58 * t + t**2 + 600 * c - 330 * ep2) * aa**6 / 720))
    if sur:
        norte += 10000000.0
    return este, norte


def listar(f):
    encontrados = []

    def visitar(nombre, obj):
        if isinstance(obj, h5py.Dataset):
            if "coherence" in nombre.lower() or nombre.lower().endswith(("xcoordinates", "ycoordinates", "projection")):
                encontrados.append((nombre, obj.shape, obj.dtype))

    f.visititems(visitar)
    return encontrados


def epsg_de(f, grupo):
    """Looks for the EPSG in the 'projection' dataset of the group or its parents."""
    partes = grupo.split("/")
    for i in range(len(partes), 0, -1):
        ruta = "/".join(partes[:i]) + "/projection"
        if ruta in f:
            ds = f[ruta]
            for clave in ("epsg_code", "EPSG", "epsg"):
                if clave in ds.attrs:
                    return int(np.array(ds.attrs[clave]).ravel()[0])
            try:
                return int(np.array(ds[()]).ravel()[0])
            except Exception:
                pass
    return None


def main():
    ruta = sys.argv[1]
    salida = sys.argv[2] if len(sys.argv) > 2 else os.path.dirname(os.path.abspath(ruta))
    os.makedirs(salida, exist_ok=True)
    with h5py.File(ruta, "r") as f:
        print("Datasets relevantes:")
        datasets = listar(f)
        for nombre, forma, tipo in datasets:
            print(f"  {nombre}  {forma}  {tipo}")
        coh = [d for d in datasets if "coherence" in d[0].lower() and len(d[1]) == 2]
        if not coh:
            print("No encontré una capa 2D de coherencia.")
            return
        # We prefer the one from the unwrapped interferogram (80 m), and if there isn't one, the first.
        coh.sort(key=lambda d: ("unwrapped" not in d[0].lower(), d[1][0] * d[1][1]))
        nombre_coh = coh[0][0]
        grupo = nombre_coh.rsplit("/", 2)[0] if nombre_coh.count("/") > 2 else nombre_coh.rsplit("/", 1)[0]
        # Coordinates: look for xCoordinates/yCoordinates in the closest group.
        gx = gy = None
        g = nombre_coh
        while "/" in g and gx is None:
            g = g.rsplit("/", 1)[0]
            if g + "/xCoordinates" in f and g + "/yCoordinates" in f:
                gx, gy = f[g + "/xCoordinates"][()], f[g + "/yCoordinates"][()]
                grupo = g
        epsg = epsg_de(f, grupo)
        print(f"\nCapa usada: {nombre_coh}\nGrupo de coordenadas: {grupo}\nEPSG: {epsg}")
        if gx is None or epsg is None:
            print("Faltan coordenadas o EPSG; revisar la estructura con la lista de arriba.")
            return
        zona, sur = epsg % 100, (epsg // 100) == 327
        datos = f[nombre_coh]
        dx = float(gx[1] - gx[0])
        dy = float(gy[1] - gy[0])
        print(f"Grilla: {datos.shape}, paso x={dx:.1f} m, y={dy:.1f} m, zona UTM {zona}{'S' if sur else 'N'}")

        def recorte(lat, lon, media=VENTANA_M):
            este, norte = utm_desde_latlon(lat, lon, zona, sur)
            ci = int(round((este - gx[0]) / dx))
            fi = int(round((norte - gy[0]) / dy))
            r = int(media / abs(dx))
            f0, f1 = max(fi - r, 0), min(fi + r + 1, datos.shape[0])
            c0, c1 = max(ci - r, 0), min(ci + r + 1, datos.shape[1])
            if f0 >= f1 or c0 >= c1:
                return None
            return np.array(datos[f0:f1, c0:c1], dtype=float)

        resultados = []
        for nombre, lat, lon, desc in SITIOS:
            arr = recorte(lat, lon)
            if arr is None or not np.isfinite(arr).any():
                print(f"  {nombre}: fuera del frame o sin datos")
                resultados.append((nombre, desc, None))
                continue
            v = arr[np.isfinite(arr) & (arr > 0)]
            centro = recorte(lat, lon, media=600)
            vc = centro[np.isfinite(centro) & (centro > 0)] if centro is not None else np.array([])
            print(f"  {nombre}: mediana ventana 6 km = {np.median(v):.2f}, "
                  f"mediana centro 1,2 km = {np.median(vc) if vc.size else float('nan'):.2f}, "
                  f"fracción < 0,3 = {(v < 0.3).mean():.2f}  ({desc})")
            resultados.append((nombre, desc, arr))

        # AMBA overview (subsampled) and crops.
        este0, norte0 = utm_desde_latlon(-34.25, -59.35, zona, sur)
        este1, norte1 = utm_desde_latlon(-34.85, -58.25, zona, sur)
        c0 = max(int((min(este0, este1) - gx[0]) / dx), 0)
        c1 = min(int((max(este0, este1) - gx[0]) / dx), datos.shape[1])
        f0 = max(int((max(norte0, norte1) - gy[0]) / dy), 0) if dy < 0 else max(int((min(norte0, norte1) - gy[0]) / dy), 0)
        f1 = min(int((min(norte0, norte1) - gy[0]) / dy), datos.shape[0]) if dy < 0 else min(int((max(norte0, norte1) - gy[0]) / dy), datos.shape[0])
        panorama = np.array(datos[f0:f1, c0:c1], dtype=float) if f1 > f0 and c1 > c0 else None

        fig, ejes = plt.subplots(1, 1 + len(resultados), figsize=(4 * (1 + len(resultados)), 4.5))
        if panorama is not None:
            ejes[0].imshow(panorama, cmap="gray", vmin=0, vmax=1)
            ejes[0].set_title("AMBA (coherencia)")
        ejes[0].axis("off")
        for eje, (nombre, desc, arr) in zip(ejes[1:], resultados):
            if arr is not None:
                im = eje.imshow(arr, cmap="gray", vmin=0, vmax=1)
            eje.set_title(nombre, fontsize=9)
            eje.axis("off")
        fig.suptitle(os.path.basename(ruta)[:60] + "...  (blanco = coherencia alta, negro = baja)", fontsize=8)
        fig.tight_layout()
        destino = os.path.join(salida, "coherencia_" + os.path.basename(ruta).replace(".h5", ".png"))
        fig.savefig(destino, dpi=130)
        print(f"\nFigura: {destino}")


if __name__ == "__main__":
    main()
