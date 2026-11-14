"""Pipeline del índice de insomnio sobre el AMBA con NISAR (Idea B).

Pasos (se pueden correr sueltos o todos con `todo`):
  buscar    consulta la API pública de ASF y guarda la lista de GUNW (y GCOV) sobre el AMBA
  bajar     baja los .h5 con earthaccess (credenciales por variable de entorno), en paralelo
  procesar  recorta la coherencia (y el backscatter de los GCOV, si hay) a una grilla común del AMBA, en paralelo
  indice    apila los recortes y calcula el índice de insomnio, estadísticas por sitio, manchas y una figura

Ejemplo:
  python pipeline_insomnio.py todo --datos /mnt/datos --salida salidas --orbitas 10 161 --capa 80m

Credenciales: EARTHDATA_TOKEN, o EARTHDATA_USERNAME y EARTHDATA_PASSWORD. Nunca en el repo.
"""
import argparse
import concurrent.futures as cf
import glob
import json
import math
import os
import re
import sys
import urllib.parse
import urllib.request

import h5py
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from manchas import latlon, utm  # noqa: E402

# Caja del AMBA (lat_norte, lon_oeste, lat_sur, lon_este). Incluye Luján.
CAJA = (-34.25, -59.35, -34.90, -58.25)
POLIGONO_AMBA = "POLYGON((-59.35 -34.25,-58.25 -34.25,-58.25 -34.90,-59.35 -34.90,-59.35 -34.25))"
API_ASF = "https://api.daac.asf.alaska.edu/services/search/param"
CAPAS = {
    "80m": ("unwrappedInterferogram", 80.0),
    "20m": ("wrappedInterferogram", 20.0),
}
# Sitios para las estadísticas: (lat_min, lat_max, lon_min, lon_max). Fuentes en context/README.md.
SITIOS = {
    "luján_poligono_osm": (-34.5271, -34.5150, -59.1228, -59.1152),
    "luján_mancha_oeste": (-34.5240, -34.5190, -59.1290, -59.1230),
    "norte_iii_aprox": (-34.550, -34.525, -58.630, -58.595),
    "gonzalez_catan_osm": (-34.7921, -34.7791, -58.6738, -58.6498),
    "control_caba_palermo": (-34.590, -34.575, -58.430, -58.410),
}


# ---------------------------------------------------------------- grilla común
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


def recortar(ds, xs_src, ys_src, xs_dst, ys_dst):
    """Lleva ds (2D) a la grilla destino por vecino más cercano. Lee sólo la ventana necesaria."""
    dx, dy = xs_src[1] - xs_src[0], ys_src[1] - ys_src[0]
    cols = np.rint((xs_dst - xs_src[0]) / dx).astype(int)
    filas = np.rint((ys_dst - ys_src[0]) / dy).astype(int)
    vc = (cols >= 0) & (cols < len(xs_src))
    vf = (filas >= 0) & (filas < len(ys_src))
    salida = np.full((len(ys_dst), len(xs_dst)), np.nan, dtype=np.float32)
    if not vc.any() or not vf.any():
        return salida
    c0, c1 = cols[vc].min(), cols[vc].max() + 1
    f0, f1 = filas[vf].min(), filas[vf].max() + 1
    ventana = np.asarray(ds[f0:f1, c0:c1], dtype=np.float32)
    salida[np.ix_(vf, vc)] = ventana[np.ix_(filas[vf] - f0, cols[vc] - c0)]
    return salida


# ---------------------------------------------------------------- buscar
def buscar(args):
    os.makedirs(args.salida, exist_ok=True)
    params = {
        "dataset": "NISAR",
        "processingLevel": "GUNW,GCOV",
        "intersectsWith": POLIGONO_AMBA,
        "output": "jsonlite",
        "maxResults": "5000",
    }
    url = API_ASF + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=120) as r:
        resultados = json.load(r)["results"]
    elegidos = {}
    for g in resultados:
        nombre = g["granuleName"]
        if g.get("path") not in args.orbitas or not g.get("downloadUrl"):
            continue
        tipo = g["productType"]
        if tipo == "GUNW":
            fechas = re.findall(r"_(\d{8})T\d{6}", nombre)
            clave = (tipo, g["path"], fechas[0], fechas[2] if len(fechas) > 2 else fechas[-1])
        else:
            clave = (tipo, g["path"], g["startTime"][:10])
        # Preferimos frame completo (_F_) y la versión más nueva (sufijo _NNN).
        rango = ("_F_" in nombre, nombre[-3:])
        if clave not in elegidos or rango > elegidos[clave][0]:
            elegidos[clave] = (rango, g)
    lista = [
        {"tipo": k[0], "orbita": k[1], "fechas": list(k[2:]), "nombre": v[1]["granuleName"],
         "url": v[1]["downloadUrl"], "direccion": v[1].get("flightDirection")}
        for k, v in sorted(elegidos.items())
    ]
    destino = os.path.join(args.salida, "lista_productos.json")
    with open(destino, "w", encoding="utf-8") as fh:
        json.dump(lista, fh, indent=1, ensure_ascii=False)
    for t in ("GUNW", "GCOV"):
        print(f"{t}: {sum(1 for x in lista if x['tipo'] == t)}")
    print("Lista:", destino)


# ---------------------------------------------------------------- bajar
def bajar(args):
    import earthaccess

    with open(os.path.join(args.salida, "lista_productos.json"), encoding="utf-8") as fh:
        lista = json.load(fh)
    if args.solo_gunw:
        lista = [x for x in lista if x["tipo"] == "GUNW"]
    os.makedirs(args.datos, exist_ok=True)
    faltan = [x["url"] for x in lista if not os.path.exists(os.path.join(args.datos, os.path.basename(x["url"])))]
    print(f"Productos: {len(lista)}; ya bajados: {len(lista) - len(faltan)}; a bajar: {len(faltan)}")
    if not faltan:
        return
    earthaccess.login(strategy="environment")
    earthaccess.download(faltan, local_path=args.datos, threads=args.hilos)


# ---------------------------------------------------------------- procesar
def _buscar_capa(f, grupo):
    """Devuelve (dataset de coherencia, xs, ys) para la primera polarización disponible del grupo."""
    base = f"science/LSAR/GUNW/grids/frequencyA/{grupo}"
    for pol in ("HH", "VV", "HV", "VH"):
        ruta = f"{base}/{pol}/coherenceMagnitude"
        if ruta in f:
            return f[ruta], f[f"{base}/xCoordinates"][()], f[f"{base}/yCoordinates"][()]
    raise KeyError(f"No hay coherencia en {base}")


def _buscar_eco(f):
    """Busca la capa de backscatter de un GCOV (HHHH o VVVV) y sus coordenadas."""
    encontrado = []

    def visitar(nombre, obj):
        if isinstance(obj, h5py.Dataset) and obj.ndim == 2 and nombre.split("/")[-1] in ("HHHH", "VVVV"):
            encontrado.append(nombre)

    f.visititems(visitar)
    if not encontrado:
        raise KeyError("No hay HHHH ni VVVV en el GCOV")
    ruta = sorted(encontrado)[0]
    grupo = ruta.rsplit("/", 1)[0]
    return f[ruta], f[grupo + "/xCoordinates"][()], f[grupo + "/yCoordinates"][()]


def _procesar_uno(tarea):
    ruta, capa, carpeta = tarea
    nombre = os.path.basename(ruta).replace(".h5", "")
    fechas = re.findall(r"_(\d{8})T\d{6}", nombre)
    orbita = int(re.search(r"_(?:GUNW|GCOV)_\d{3}_(\d{3})_", nombre).group(1))
    fecha_sec = fechas[2] if len(fechas) > 2 else fechas[0]
    prefijo = "gunw" if "_GUNW_" in nombre else "gcov"
    # Nombre corto: los nombres de NISAR superan el límite de rutas de Windows.
    destino = os.path.join(carpeta, f"{prefijo}_{orbita:03d}_{fechas[0]}_{fecha_sec}_{capa}.npz")
    if os.path.exists(destino):
        return destino, "ya estaba"
    xs_dst, ys_dst = grilla(CAPAS[capa][1])
    try:
        with h5py.File(ruta, "r") as f:
            if "_GUNW_" in nombre:
                ds, xs, ys = _buscar_capa(f, CAPAS[capa][0])
                valor = recortar(ds, xs, ys, xs_dst, ys_dst)
                valor[(valor <= 0) | (valor > 1)] = np.nan
                tipo = "coherencia"
            else:
                ds, xs, ys = _buscar_eco(f)
                lin = recortar(ds, xs, ys, xs_dst, ys_dst)
                with np.errstate(divide="ignore", invalid="ignore"):
                    valor = (10 * np.log10(lin)).astype(np.float32)
                valor[~np.isfinite(valor)] = np.nan
                tipo = "eco_db"
    except Exception as e:  # un archivo roto no frena a los demás
        return destino, f"ERROR {e}"
    np.savez_compressed(destino, valor=valor.astype(np.float16), tipo=tipo, orbita=orbita,
                        fecha_ref=fechas[0], fecha_sec=fecha_sec, producto=nombre)
    return destino, f"ok {tipo} cobertura {np.isfinite(valor).mean():.0%}"


def procesar(args):
    carpeta = os.path.join(args.salida, f"recortes_{args.capa}")
    os.makedirs(carpeta, exist_ok=True)
    archivos = sorted(glob.glob(os.path.join(args.datos, "NISAR_*_GUNW_*.h5")) + glob.glob(os.path.join(args.datos, "NISAR_*_GCOV_*.h5")))
    archivos = [a for a in archivos if int(re.search(r"_(?:GUNW|GCOV)_\d{3}_(\d{3})_", os.path.basename(a)).group(1)) in args.orbitas]
    print(f"Archivos a procesar: {len(archivos)} (capa {args.capa}, {args.procesos} procesos)")
    with cf.ProcessPoolExecutor(max_workers=args.procesos) as ex:
        for destino, estado in ex.map(_procesar_uno, [(a, args.capa, carpeta) for a in archivos]):
            print(f"  {os.path.basename(destino)}: {estado}")


# ---------------------------------------------------------------- índice
def _ventana(caja, xs, ys):
    xa, ya = utm(caja[1], caja[2])
    xb, yb = utm(caja[0], caja[3])
    c = np.where((xs >= min(xa, xb)) & (xs <= max(xa, xb)))[0]
    f = np.where((ys <= max(ya, yb)) & (ys >= min(ya, yb)))[0]
    return slice(f.min(), f.max() + 1), slice(c.min(), c.max() + 1)


def indice(args):
    from scipy import ndimage
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    carpeta = os.path.join(args.salida, f"recortes_{args.capa}")
    coh, eco = [], []
    for ruta in sorted(glob.glob(os.path.join(carpeta, "*.npz"))):
        d = np.load(ruta)
        if int(d["orbita"]) not in args.orbitas:
            continue
        (coh if str(d["tipo"]) == "coherencia" else eco).append(d["valor"].astype(np.float32))
    if not coh:
        print("No hay recortes de coherencia: corré `procesar` primero.")
        return
    pila = np.stack(coh)
    validos = np.isfinite(pila)
    n = validos.sum(0)
    with np.errstate(invalid="ignore"):
        baja = np.where(validos, pila < args.umbral, False).sum(0)
        insomnio = np.where(n > 0, baja / np.maximum(n, 1), np.nan)
        media = np.nanmean(pila, axis=0)
    eco_med = np.nanmedian(np.stack(eco), axis=0) if eco else None
    xs, ys = grilla(CAPAS[args.capa][1])

    # Candidatos: insomnes en la mayoría de los pares, sin ser superficie lisa (si hay eco).
    cand = (n >= max(2, int(0.5 * len(coh)))) & (insomnio >= args.min_insomnio)
    if eco_med is not None:
        cand &= np.nan_to_num(eco_med, nan=-99) > args.eco_min_db
    etiquetas, _ = ndimage.label(cand)
    manchas = []
    paso = CAPAS[args.capa][1]
    for i, sl in enumerate(ndimage.find_objects(etiquetas), start=1):
        sub = etiquetas[sl] == i
        px = int(sub.sum())
        ha = px * paso * paso / 1e4
        if ha < args.min_ha:
            continue
        rr, cc = np.nonzero(sub)
        ev = np.sort(np.linalg.eigvalsh(np.cov(np.vstack([rr, cc])))) if px > 2 else np.array([1.0, 1.0])
        elong = math.sqrt(ev[1] / max(ev[0], 1e-6))
        lat, lon = latlon(xs[int(cc.mean()) + sl[1].start], ys[int(rr.mean()) + sl[0].start])
        manchas.append({"ha": round(ha, 1), "lat": round(lat, 5), "lon": round(lon, 5),
                        "insomnio_medio": round(float(np.nanmean(insomnio[sl][sub])), 2),
                        "elongacion": round(elong, 1), "forma": "compacta" if elong < 2.5 else ("alargada" if elong < 5 else "lineal")})
    manchas.sort(key=lambda m: -m["ha"])

    sitios = {}
    for nombre, caja in SITIOS.items():
        fs, cs = _ventana(caja, xs, ys)
        sitios[nombre] = {
            "insomnio": round(float(np.nanmean(insomnio[fs, cs])), 2),
            "coherencia_media": round(float(np.nanmean(media[fs, cs])), 2),
            "pares": int(np.median(n[fs, cs])),
            "eco_db": round(float(np.nanmedian(eco_med[fs, cs])), 1) if eco_med is not None else None,
        }

    os.makedirs(args.salida, exist_ok=True)
    np.savez_compressed(os.path.join(args.salida, f"indice_{args.capa}.npz"), insomnio=insomnio.astype(np.float16),
                        coherencia_media=media.astype(np.float16), pares=n.astype(np.uint8),
                        eco_db=(eco_med if eco_med is not None else np.zeros(1)).astype(np.float16), xs=xs, ys=ys)
    resumen = {"capa": args.capa, "pares": len(coh), "gcov": len(eco), "umbral_coherencia": args.umbral,
               "min_insomnio": args.min_insomnio, "eco_min_db": args.eco_min_db if eco else None,
               "sitios": sitios, "manchas": manchas[:50]}
    with open(os.path.join(args.salida, f"resumen_{args.capa}.json"), "w", encoding="utf-8") as fh:
        json.dump(resumen, fh, indent=1, ensure_ascii=False)

    fig, ejes = plt.subplots(1, 2, figsize=(15, 7))
    im0 = ejes[0].imshow(insomnio, cmap="magma", vmin=0, vmax=1)
    ejes[0].set_title(f"Índice de insomnio ({len(coh)} pares, coherencia < {args.umbral})")
    fig.colorbar(im0, ax=ejes[0], fraction=0.035)
    im1 = ejes[1].imshow(media, cmap="gray", vmin=0, vmax=1)
    ejes[1].set_title("Coherencia media")
    fig.colorbar(im1, ax=ejes[1], fraction=0.035)
    for eje in ejes:
        eje.axis("off")
    fig.tight_layout()
    fig.savefig(os.path.join(args.salida, f"indice_{args.capa}.png"), dpi=110)

    print(json.dumps(sitios, indent=1, ensure_ascii=False))
    print(f"Manchas candidatas: {len(manchas)} (las primeras 50 en resumen_{args.capa}.json)")


# ---------------------------------------------------------------- main
def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("paso", choices=["buscar", "bajar", "procesar", "indice", "todo"])
    p.add_argument("--datos", default="datos", help="carpeta de los .h5 (fuera del repo en la VM, por ejemplo /mnt/datos)")
    p.add_argument("--salida", default="salidas", help="carpeta de productos chicos (lista, recortes, índice, figuras)")
    p.add_argument("--orbitas", type=int, nargs="+", default=[10, 161], help="órbitas (path) a usar; 10 y 161 cubren todo el AMBA")
    p.add_argument("--capa", choices=list(CAPAS), default="80m")
    p.add_argument("--procesos", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    p.add_argument("--hilos", type=int, default=8, help="descargas en paralelo")
    p.add_argument("--solo-gunw", action="store_true", help="no bajar GCOV")
    p.add_argument("--umbral", type=float, default=0.30, help="coherencia por debajo de la cual un par cuenta como 'despierto'")
    p.add_argument("--min-insomnio", type=float, default=0.6, help="fracción mínima de pares despiertos para ser candidato")
    p.add_argument("--eco-min-db", type=float, default=-15.0, help="backscatter mínimo (dB) para no ser superficie lisa; supuesto a calibrar")
    p.add_argument("--min-ha", type=float, default=2.0, help="superficie mínima de una mancha candidata")
    args = p.parse_args()
    pasos = ["buscar", "bajar", "procesar", "indice"] if args.paso == "todo" else [args.paso]
    for paso in pasos:
        print(f"== {paso}")
        globals()[paso](args)


if __name__ == "__main__":
    main()
