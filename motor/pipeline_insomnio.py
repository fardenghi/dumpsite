"""NISAR insomnia index pipeline, for any frame. Without `--frame` it works on the AMBA.

Steps (they can be run separately or all together with `todo`):
  buscar    queries the public ASF API and saves the list of GUNWs (and GCOVs) that cross the frame's box
  bajar     downloads the .h5 files with earthaccess (credentials through environment variables), in parallel
  procesar  crops the coherence (and the GCOV backscatter, if any) to the frame's common grid, in parallel.
            The UTM zone and hemisphere come from each product's EPSG (`projection` dataset)
  indice    computes the final insomnia index (insomnio.py), the per-site records, the candidate blobs
            and the figure; for the AMBA, also the files the web reads (web/)
  calibrar  sweeps the thresholds and says with which ones the known sites get in and the controls don't (AMBA only)

With the crops already made, a single command reproduces everything reported for the AMBA:
  python pipeline_insomnio.py indice

Another frame, without downloading the .h5 files (remote windowed reading; that's how it runs on the VM):
  python pipeline_insomnio.py todo --frame DELHI --remoto
  python pipeline_insomnio.py todo --frame todos --remoto          # all those in data/catalogos/frames.json, in order
  python pipeline_insomnio.py todo --frame PRUEBA --caja -118.40 33.90 -118.00 34.20 --remoto

Downloading the .h5 files (frame by frame: downloads, processes and deletes before moving to the next one):
  python pipeline_insomnio.py todo --frame todos --datos /mnt/datos --borrar

The frames come from `../data/catalogos/frames.json` (stage 2) or from `--caja lon_west lat_south lon_east lat_north`.
Each frame that isn't the AMBA writes to `<salida>/<FRAME>/`, downloads to `<datos>/<FRAME>/` and caches its fixed
sources (JRC water, Overture land uses and catalog polygons) in `fijos/<FRAME>/`.

Credentials: EARTHDATA_TOKEN, or EARTHDATA_USERNAME and EARTHDATA_PASSWORD. Never in the repo.
"""
import argparse
import concurrent.futures as cf
import concurrent.futures.process  # noqa: F401  (BrokenProcessPool)
import contextlib
import dataclasses
import glob
import json
import math
import multiprocessing
import os
import re
import sys
import urllib.parse
import urllib.request

import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import fuentes_fijas as ff  # noqa: E402
import geo  # noqa: E402
import insomnio as ins  # noqa: E402

RAIZ = os.path.dirname(AQUI)
FIJOS = os.path.join(AQUI, "fijos")
WEB = os.path.join(RAIZ, "web")
API_ASF = "https://api.daac.asf.alaska.edu/services/search/param"
CAPAS = {
    "80m": ("unwrappedInterferogram", 80.0),
    "20m": ("wrappedInterferogram", 20.0),
}


# ---------------------------------------------------------------- common grid
def recortar(ds, xs_src, ys_src, xs_dst, ys_dst, epsg_src=None, epsg_dst=None):
    """Brings ds (2D) to the destination grid by nearest neighbor. Reads only the needed window.

    If the product is in a different UTM zone than the grid (it happens when the box is near a zone edge
    and two orbits fall in different zones), each destination cell is looked up in the product via lat/lon.
    """
    dx, dy = xs_src[1] - xs_src[0], ys_src[1] - ys_src[0]
    if epsg_src and epsg_dst and int(epsg_src) != int(epsg_dst):
        lat, lon = geo.latlon(xs_dst[None, :], ys_dst[:, None], epsg_dst)
        x, y = geo.utm(lat, lon, epsg_src)
        cols, filas = np.rint((x - xs_src[0]) / dx).astype(int), np.rint((y - ys_src[0]) / dy).astype(int)
        ok = (cols >= 0) & (cols < len(xs_src)) & (filas >= 0) & (filas < len(ys_src))
        salida = np.full((len(ys_dst), len(xs_dst)), np.nan, dtype=np.float32)
        if not ok.any():
            return salida
        c0, c1, f0, f1 = cols[ok].min(), cols[ok].max() + 1, filas[ok].min(), filas[ok].max() + 1
        ventana = np.asarray(ds[f0:f1, c0:c1], dtype=np.float32)
        salida[ok] = ventana[filas[ok] - f0, cols[ok] - c0]
        return salida
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


# ---------------------------------------------------------------- frames
def _guardar_frame(args):
    """Leaves in `<salida>/frame.json` the frame that was used (box, EPSG and orbits)."""
    _json(os.path.join(args.salida, "frame.json"), args.fr.dict(), indent=1)


def _partes(nombre):
    """(type, orbit, NISAR frame) from the name of a GUNW or GCOV product."""
    m = re.search(r"_(GUNW|GCOV)_\d{3}_(\d{3})_[AD]_(\d{3})_", nombre)
    return m.group(1), int(m.group(2)), int(m.group(3))


# ---------------------------------------------------------------- buscar
def buscar(args):
    fr = args.fr
    os.makedirs(args.salida, exist_ok=True)
    norte, oeste, sur, este = fr.caja
    params = {
        "dataset": "NISAR",
        "intersectsWith": f"POLYGON(({oeste} {norte},{este} {norte},{este} {sur},{oeste} {sur},{oeste} {norte}))",
        "output": "jsonlite",
        "maxResults": "5000",
    }
    # One query per type: where there are many products, the response for both together exceeds the size the API
    # returns and gives a 502 (it happened with USA_TX_HARRIS and USA_CA_SAN_JOAQUIN: 3 MB of GUNW plus 4 MB of GCOV).
    resultados = []
    for nivel in ("GUNW", "GCOV"):
        url = API_ASF + "?" + urllib.parse.urlencode({**params, "processingLevel": nivel})
        with urllib.request.urlopen(url, timeout=120) as r:
            resultados += json.load(r)["results"]
    desde, hasta = (fr.desde or "").replace("-", ""), (fr.hasta or "").replace("-", "")
    solo = {(int(x.split("_")[0]), int(x.split("_")[-1])) for x in fr.frames_nisar}  # (orbit, NISAR frame) from frames.json
    elegidos = {}
    for g in resultados:
        nombre = g["granuleName"]
        # Only PR products (UR ones, urgent response, duplicate dates) and from the requested orbits.
        if not nombre.startswith("NISAR_L2_PR_") or not g.get("downloadUrl") or (args.orbitas and g.get("path") not in args.orbitas):
            continue
        tipo = g["productType"]
        _, _, frame_nisar = _partes(nombre)
        if solo and (g["path"], frame_nisar) not in solo:
            continue
        if tipo == "GUNW":
            fechas = re.findall(r"_(\d{8})T\d{6}", nombre)
            dias = (fechas[0], fechas[2] if len(fechas) > 2 else fechas[-1])
        else:
            dias = (g["startTime"][:10].replace("-", ""),) * 2
        if (desde and dias[0] < desde) or (hasta and dias[1] > hasta):
            continue
        # A box can cross two NISAR frames of the same orbit: both are kept and `indice` joins them.
        clave = (tipo, g["path"], frame_nisar) + ((_fecha(dias[0]), _fecha(dias[1])) if tipo == "GUNW" else (_fecha(dias[0]),))
        # We prefer a full frame (_F_) and the newest version (suffix _NNN).
        rango = ("_F_" in nombre, nombre[-3:])
        if clave not in elegidos or rango > elegidos[clave][0]:
            elegidos[clave] = (rango, g)
    lista = [
        {"tipo": k[0], "orbita": k[1], "frame_nisar": k[2], "fechas": list(k[3:]), "nombre": v[1]["granuleName"],
         "url": v[1]["downloadUrl"], "direccion": v[1].get("flightDirection")}
        for k, v in sorted(elegidos.items())
    ]
    destino = os.path.join(args.salida, "lista_productos.json")
    with open(destino, "w", encoding="utf-8") as fh:
        json.dump(lista, fh, indent=1, ensure_ascii=False)
    _guardar_frame(args)
    por_orbita = {}
    for x in lista:
        por_orbita.setdefault(x["orbita"], {"GUNW": 0, "GCOV": 0})[x["tipo"]] += 1
    print(f"{fr.nombre}: caja {fr.bbox}, período {fr.desde or '...'} a {fr.hasta or '...'}")
    for t in ("GUNW", "GCOV"):
        print(f"{t}: {sum(1 for x in lista if x['tipo'] == t)}")
    print("Por órbita:", ", ".join(f"{o}: {n['GUNW']} GUNW y {n['GCOV']} GCOV" for o, n in sorted(por_orbita.items())))
    print("Lista:", destino)
    if not any(x["tipo"] == "GUNW" for x in lista):
        sys.exit(f"No hay GUNW de NISAR sobre {fr.nombre} con esas órbitas y fechas.")


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
def _epsg(f, grupo):
    """EPSG of a product's grid: the group's `projection` dataset (its value, or the `epsg_code` attribute)."""
    for ruta in (f"{grupo}/projection", f"{grupo.rsplit('/', 1)[0]}/projection"):
        if ruta in f:
            ds = f[ruta]
            valor = ds.attrs.get("epsg_code")
            if valor is None:
                valor = ds[()]
            return int(np.asarray(valor).ravel()[0])
    raise KeyError(f"No hay `projection` en {grupo}")


def _buscar_capa(f, grupo):
    """Returns (coherence dataset, xs, ys, epsg) for the first available polarization of the group."""
    base = f"science/LSAR/GUNW/grids/frequencyA/{grupo}"
    for pol in ("HH", "VV", "HV", "VH"):
        ruta = f"{base}/{pol}/coherenceMagnitude"
        if ruta in f:
            return f[ruta], f[f"{base}/xCoordinates"][()], f[f"{base}/yCoordinates"][()], _epsg(f, base)
    raise KeyError(f"No hay coherencia en {base}")


def _buscar_eco(f):
    """Looks for a GCOV's backscatter. Returns (co, cross, xs, ys, epsg): the datasets of the like
    polarization (HHHH or VVVV) and the cross one of the same group (HVHV or VHVH, or None if the product doesn't carry it)."""
    encontrado = []

    import h5py

    def visitar(nombre, obj):
        if isinstance(obj, h5py.Dataset) and obj.ndim == 2 and nombre.split("/")[-1] in ("HHHH", "VVVV"):
            encontrado.append(nombre)

    f.visititems(visitar)
    if not encontrado:
        raise KeyError("No hay HHHH ni VVVV en el GCOV")
    ruta = sorted(encontrado)[0]
    grupo = ruta.rsplit("/", 1)[0]
    cruzada = next((f[f"{grupo}/{c}"] for c in ("HVHV", "VHVH") if f"{grupo}/{c}" in f), None)
    return f[ruta], cruzada, f[grupo + "/xCoordinates"][()], f[grupo + "/yCoordinates"][()], _epsg(f, grupo)


_SESION_REMOTA = None


@contextlib.contextmanager
def _abrir(ruta, remoto, intentos=4):
    """Opens a local .h5, or a remote one by URL with earthaccess (reads only the requested chunks).

    The login and the remote opening are retried: Earthdata drops connections every now and then. On exit it also closes
    the remote file, to release its chunk cache (otherwise each process piles up hundreds of MB).
    """
    import h5py

    if not remoto:
        with h5py.File(ruta, "r") as f:
            yield f
        return
    global _SESION_REMOTA
    import time

    import earthaccess

    for i in range(intentos):
        try:
            if _SESION_REMOTA is None:  # once per process
                _SESION_REMOTA = earthaccess.login(strategy="environment")
            archivo = earthaccess.open([ruta])[0]
            f = h5py.File(archivo, "r")
            break
        except Exception:
            if i == intentos - 1:
                raise
            _SESION_REMOTA = None
            time.sleep(5 * (i + 1))
    try:
        yield f
    finally:
        f.close()
        archivo.close()


def _procesar_uno(tarea):
    """Crops a product to the frame's grid. A GUNW gives one coherence crop; a GCOV gives two: the echo
    of the like polarization (`gcov_*`) and that of the cross one (`gcovhv_*`), used for the HV/HH ratio."""
    ruta, capa, carpeta, remoto, caja, epsg = tarea
    nombre = os.path.basename(ruta).replace(".h5", "")
    fechas = re.findall(r"_(\d{8})T\d{6}", nombre)
    tipo, orbita, frame_nisar = _partes(nombre)
    fecha_sec = fechas[2] if len(fechas) > 2 else fechas[0]

    def destino(prefijo):
        # Short name: NISAR names exceed the Windows path limit.
        return os.path.join(carpeta, f"{prefijo}_{orbita:03d}_{frame_nisar:03d}_{fechas[0]}_{fecha_sec}_{capa}.npz")

    def hecho(prefijo):  # the name of the crops from before frames existed, without the NISAR frame, is also valid
        return os.path.exists(destino(prefijo)) or os.path.exists(os.path.join(carpeta, f"{prefijo}_{orbita:03d}_{fechas[0]}_{fecha_sec}_{capa}.npz"))

    principal = destino(tipo.lower())
    salidas = {"gunw": "coherencia"} if tipo == "GUNW" else {"gcov": "eco_db", "gcovhv": "eco_hv_db"}
    faltan = [p for p in salidas if not hecho(p)]
    if not faltan:
        return principal, "ya estaba"
    xs_dst, ys_dst = geo.grilla(CAPAS[capa][1], caja, epsg)

    def en_db(ds, xs, ys, epsg_src):
        lin = recortar(ds, xs, ys, xs_dst, ys_dst, epsg_src, epsg)
        with np.errstate(divide="ignore", invalid="ignore"):
            valor = (10 * np.log10(lin)).astype(np.float32)
        valor[~np.isfinite(valor)] = np.nan
        return valor

    intentos = 3 if remoto else 1  # reading by URL drops every now and then: the whole file is retried
    for i in range(intentos):
        try:
            valores = {}
            with _abrir(ruta, remoto) as f:
                if tipo == "GUNW":
                    ds, xs, ys, epsg_src = _buscar_capa(f, CAPAS[capa][0])
                    valor = recortar(ds, xs, ys, xs_dst, ys_dst, epsg_src, epsg)
                    valor[(valor <= 0) | (valor > 1)] = np.nan
                    valores["gunw"] = valor
                else:
                    co, cruzada, xs, ys, epsg_src = _buscar_eco(f)
                    if "gcov" in faltan:
                        valores["gcov"] = en_db(co, xs, ys, epsg_src)
                    if "gcovhv" in faltan and cruzada is not None:
                        valores["gcovhv"] = en_db(cruzada, xs, ys, epsg_src)
            break
        except Exception as e:  # a broken file doesn't stop the others
            if i == intentos - 1:
                return principal, f"ERROR {type(e).__name__}: {e}"
    for prefijo, valor in valores.items():
        parcial = destino(prefijo) + ".parcial.npz"  # written separately and renamed: an interruption doesn't leave a broken crop
        np.savez_compressed(parcial, valor=valor.astype(np.float16), tipo=salidas[prefijo], orbita=orbita, frame_nisar=frame_nisar,
                            fecha_ref=fechas[0], fecha_sec=fecha_sec, producto=nombre, epsg=epsg, epsg_producto=epsg_src)
        os.replace(parcial, destino(prefijo))
    if not valores:
        return principal, "ya estaba (el producto no trae polarización cruzada)"
    otra = "" if epsg_src == epsg else f", reproyectado de EPSG {epsg_src}"
    que = " y ".join(salidas[p] for p in valores)
    return principal, f"ok {que} cobertura {np.isfinite(next(iter(valores.values()))).mean():.0%}{otra}"


def _fijar_epsg(args, archivos):
    """If the frame came from `--caja` without an EPSG, the grid takes the UTM zone of the first GUNW (`projection` dataset)."""
    fr = args.fr
    if fr.epsg_fijo:
        return
    primero = next((a for a in archivos if "_GUNW_" in os.path.basename(a)), None)
    if primero is None:
        return
    with _abrir(primero, args.remoto) as f:
        epsg = _buscar_capa(f, CAPAS[args.capa][0])[3]
    geo.zona_de_epsg(epsg)  # fails if it isn't UTM
    if epsg != fr.epsg:
        print(f"  La grilla de {fr.nombre} pasa de EPSG {fr.epsg} (centro de la caja) a {epsg} (el del producto)")
    args.fr = dataclasses.replace(fr, epsg=epsg, epsg_fijo=True)
    _guardar_frame(args)


def procesar(args):
    carpeta = os.path.join(args.salida, f"recortes_{args.capa}")
    os.makedirs(carpeta, exist_ok=True)
    if args.remoto:
        # Without downloading anything: reads by URL only the frame's window (needs `buscar` first and credentials).
        with open(os.path.join(args.salida, "lista_productos.json"), encoding="utf-8") as fh:
            lista = json.load(fh)
        archivos = [x["url"] for x in lista if x["tipo"] == "GUNW" or not args.solo_gunw]
    else:
        archivos = sorted(glob.glob(os.path.join(args.datos, "NISAR_*_GUNW_*.h5")) + glob.glob(os.path.join(args.datos, "NISAR_*_GCOV_*.h5")))
        if args.solo_gunw:
            archivos = [a for a in archivos if "_GUNW_" in os.path.basename(a)]
    if args.orbitas:
        archivos = [a for a in archivos if _partes(os.path.basename(a))[1] in args.orbitas]
    _fijar_epsg(args, archivos)
    fr = args.fr
    _guardar_frame(args)
    modo = "remoto, sin bajar" if args.remoto else "local"
    print(f"{fr.nombre} (EPSG {fr.epsg}): {len(archivos)} archivos a procesar (capa {args.capa}, {args.procesos} procesos, {modo})")
    errores = 0
    tareas = {a: (a, args.capa, carpeta, args.remoto, fr.caja, fr.epsg) for a in archivos}
    # New processes (spawn), not copies (fork): the remote session and h5py don't survive a fork well. Each process
    # is recycled every few files, so it doesn't pile up memory. If the system kills a process, it continues with what's left.
    # Only from Python 3.12.4: on the VM, recycling processes left the pool hanging (consistent with cpython gh-115634)
    # (Ubuntu 24.04, Python 3.12.3): `procesar` would wait forever; without recycling, it didn't happen again.
    reciclar = {"max_tasks_per_child": 6} if sys.version_info >= (3, 12, 4) else {}
    for vuelta in range(4):
        hechos = set()
        try:
            with cf.ProcessPoolExecutor(max_workers=args.procesos, mp_context=multiprocessing.get_context("spawn"), **reciclar) as ex:
                for archivo, (destino, estado) in zip(tareas, ex.map(_procesar_uno, tareas.values())):
                    hechos.add(archivo)
                    print(f"  {os.path.basename(destino)}: {estado}", flush=True)
                    errores += estado.startswith("ERROR")
                    if args.borrar and not args.remoto and not estado.startswith("ERROR"):
                        os.remove(archivo)  # frame by frame: the disk never holds the .h5 files of more than one frame
            break
        except cf.process.BrokenProcessPool:
            tareas = {a: t for a, t in tareas.items() if a not in hechos}
            if vuelta == 3:
                raise
            print(f"  El sistema mató un proceso (¿memoria?): sigo con los {len(tareas)} archivos que faltan", flush=True)
    if errores:
        print(f"  {errores} archivo(s) con error: se pueden reintentar corriendo `procesar` de nuevo")


# ---------------------------------------------------------------- index
def _fecha(aaaammdd):
    return f"{aaaammdd[:4]}-{aaaammdd[4:6]}-{aaaammdd[6:]}"


def _dias(a, b):
    import datetime as dt

    return (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days


def _json(ruta, datos, **kw):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as fh:
        json.dump(datos, fh, ensure_ascii=False, **kw)
        fh.write("\n")


def _juntar(piezas):
    """Joins the crops of the same pair or date that come from neighboring NISAR frames: the one covering most wins."""
    piezas = sorted(piezas, key=lambda v: -np.isfinite(v).sum())
    salida = piezas[0]
    for otra in piezas[1:]:
        salida = np.where(np.isfinite(salida), salida, otra)
    return salida


def _fijo(args, archivo, armar):
    """Path of a fixed source of the frame. If it's not cached, it builds it (with the network) and leaves it in `fijos/<FRAME>/`."""
    ruta = os.path.join(args.fijos, archivo)
    if not os.path.exists(ruta):
        print(f"Falta {os.path.relpath(ruta)}: lo armo (fuentes_fijas.py)")
        armar()
    return ruta


def cargar(args):
    """Reads once the crops, the water mask, the sites, the known land uses and the catalog polygons.

    `args` only needs `salida`, `capa` and `orbitas`: without `fr` the AMBA is assumed (that's how `insomnio_catalogo.py` calls it).
    """
    fr = getattr(args, "fr", geo.AMBA)
    if not hasattr(args, "fijos"):
        args.fijos = ff.carpeta(fr)
    paso = CAPAS[args.capa][1]
    xs, ys = fr.grilla(paso)
    grupos = {}
    for ruta in sorted(glob.glob(os.path.join(args.salida, f"recortes_{args.capa}", "*.npz"))):
        with np.load(ruta) as d:
            if args.orbitas and int(d["orbita"]) not in args.orbitas:
                continue
            clave = (str(d["tipo"]), int(d["orbita"]), str(d["fecha_ref"]), str(d["fecha_sec"]))
            grupos.setdefault(clave, []).append((d["valor"].astype(np.float32), str(d["producto"])))
    coh, pares, eco, orb_eco, eco_hv, orb_eco_hv = [], [], [], [], [], []
    for (tipo, orbita, f_ref, f_sec), piezas in sorted(grupos.items(), key=lambda kv: (kv[0][0] != "coherencia", kv[0][1:])):
        if any(v.shape != (len(ys), len(xs)) for v, _ in piezas):
            sys.exit(f"Los recortes miden {piezas[0][0].shape} y la grilla de {fr.nombre} {(len(ys), len(xs))}: "
                     f"son de otra caja o de otro EPSG. Borrá {os.path.join(args.salida, f'recortes_{args.capa}')} y corré `procesar`.")
        valor = _juntar([v for v, _ in piezas])
        if tipo == "coherencia":
            ref, sec = _fecha(f_ref), _fecha(f_sec)
            coh.append(valor)
            pares.append({"orbita": orbita, "desde": ref, "hasta": sec, "dias": _dias(ref, sec), "producto": piezas[0][1]})
        elif np.isfinite(valor).mean() >= 0.5:  # some GCOVs don't cover the box
            (eco if tipo == "eco_db" else eco_hv).append(valor)
            (orb_eco if tipo == "eco_db" else orb_eco_hv).append(orbita)
    if not coh:
        sys.exit("No hay recortes de coherencia: corré `procesar` primero (o bajá los recortes, ver README).")
    coh = np.stack(coh)
    with np.load(_fijo(args, f"agua_jrc_{args.capa}.npz", lambda: ff.agua(fr, (args.capa,), args.fijos))) as d:
        ocurrencia = d["ocurrencia"]
    if ocurrencia.shape != (len(ys), len(xs)):
        sys.exit(f"La máscara de agua mide {ocurrencia.shape} y la grilla de {fr.nombre} {(len(ys), len(xs))}: "
                 f"rehacela con `python fuentes_fijas.py agua --frame {fr.nombre}`.")
    # Sites with a record: those in the registry, which today are all in the AMBA (`frame` in the registry, AMBA by default).
    with open(os.path.join(AQUI, "sitios_registro.json"), encoding="utf-8") as fh:
        registro = [s for s in json.load(fh)["sitios"] if s.get("frame", "AMBA") == fr.nombre]
    contornos = {}
    if any("osm" in s for s in registro):
        with open(os.path.join(FIJOS, "contornos_osm.json"), encoding="utf-8") as fh:
            contornos = json.load(fh)["sitios"]
    sitios = []
    for s in registro:
        anillos = contornos[s["id"]]["anillos"] if "osm" in s else [geo.caja_a_anillo(s["caja"])]
        mayor = max(anillos, key=lambda a: geo.area_y_centro(a)[0])
        sitios.append({**s, "anillos": anillos, "mascara": fr.mascara_poligonos(anillos, xs, ys),
                       "ha": sum(geo.area_y_centro(a)[0] for a in anillos), "centro": geo.area_y_centro(mayor)[1],
                       "lugar": s.get("lugar") or contornos.get(s["id"], {}).get("lugar_osm", "")})
    try:
        with open(_fijo(args, "usos_osm.json", lambda: ff.usos(fr, args.fijos)), encoding="utf-8") as fh:
            usos = json.load(fh)["usos"]
    except Exception as e:  # offline or without duckdb: the index comes out anyway, without the "known land use" class
        print(f"AVISO: no hay usos conocidos para {fr.nombre} ({type(e).__name__}: {e}). Las manchas salen sin esa clase.")
        usos = []
    uso_px = np.zeros((len(ys), len(xs)), dtype=np.int16)  # 0 = no known land use; i = usos[i - 1]
    for i, u in enumerate(usos, start=1):
        uso_px[fr.mascara_poligonos(u["anillos"], xs, ys) & (uso_px == 0)] = i
    # Catalog polygons (dump sites and negatives) of the frame: each site's ring excludes all of them.
    try:
        with open(_fijo(args, "catalogo.json", lambda: ff.catalogo(fr, args.fijos)), encoding="utf-8") as fh:
            catalogo = json.load(fh)["poligonos"]
    except Exception as e:
        print(f"AVISO: no hay polígonos de los catálogos para {fr.nombre} ({type(e).__name__}: {e}). El anillo excluye sólo el sitio y el agua.")
        catalogo = []
    catalogo_px = np.zeros((len(ys), len(xs)), dtype=bool)
    for c in catalogo:
        catalogo_px |= fr.mascara_poligonos(c["anillos"], xs, ys)
    # Known landfills, to say what each blob overlaps: the registry sites or, if the frame has none, the catalog dump sites.
    sitio_px = np.zeros_like(uso_px)
    rellenos = []
    if registro:
        for s in sitios:
            if s["rol"] != "control":
                rellenos.append(s["id"])
                sitio_px[s["mascara"] & (sitio_px == 0)] = len(rellenos)
    else:
        for c in catalogo:
            if c["catalogo"] == "basurales":
                rellenos.append(c["id"])
                sitio_px[fr.mascara_poligonos(c["anillos"], xs, ys) & (sitio_px == 0)] = len(rellenos)
    return {"fr": fr, "paso": paso, "xs": xs, "ys": ys, "coh": coh, "pares": pares,
            "orbitas": np.array([x["orbita"] for x in pares]), "dias": np.array([x["dias"] for x in pares]),
            "fechas": np.array([x["hasta"] for x in pares]),
            "eco": np.stack(eco) if eco else None, "orbitas_eco": np.array(orb_eco), "ocurrencia": ocurrencia,
            "eco_hv": np.stack(eco_hv) if eco_hv else None, "orbitas_eco_hv": np.array(orb_eco_hv),
            "sitios": sitios, "usos": usos, "uso_px": uso_px, "sitio_px": sitio_px, "rellenos": rellenos,
            "catalogo": catalogo, "catalogo_px": catalogo_px, "sin_catalogos": getattr(args, "sin_catalogos", False)}


def evaluar(ctx, p, cociente=None, eco_db=None):
    """Runs the index with parameters p. Returns layers, classified blobs and records."""
    paso = ctx["paso"]
    agua = ins.mascara_agua(ctx["ocurrencia"], paso, p)
    capas = ins.calcular(ctx["coh"], ctx["orbitas"], ctx["dias"], ctx["fechas"], agua, paso, p,
                         eco=ctx["eco"], orbitas_eco=ctx["orbitas_eco"], cociente=cociente, eco_db=eco_db)
    lista, etiquetas = ins.manchas(capas["candidato"], capas, paso, p)
    n = len(lista)
    # what each blob overlaps: an OSM landfill, a known land use or nothing
    ok = etiquetas > 0
    px = np.bincount(etiquetas[ok], minlength=n + 1)

    def mayoritario(ids):
        """Per blob, the most frequent id (not counting 0) and the fraction of the blob it covers."""
        sel = ok & (ids > 0)
        pares_ = np.unique(np.column_stack([etiquetas[sel], ids[sel]]), axis=0, return_counts=True)
        mejor = {}
        for (e, i), c in zip(*pares_):
            if c > mejor.get(int(e), (0, 0))[1]:
                mejor[int(e)] = (int(i), int(c))
        return {e: (i, c / px[e]) for e, (i, c) in mejor.items()}

    en_sitio, en_uso = mayoritario(ctx["sitio_px"]), mayoritario(ctx["uso_px"])
    for m in lista:
        lat, lon = ctx["fr"].latlon(ctx["xs"][0] + m["columna"] * paso, ctx["ys"][0] - m["fila"] * paso)
        m["lat"], m["lon"] = round(float(lat), 5), round(float(lon), 5)
        s, u = en_sitio.get(m["etiqueta"], (0, 0)), en_uso.get(m["etiqueta"], (0, 0))
        if s[1] >= 0.3:
            m["clase"], m["que"] = "relleno_osm", ctx["rellenos"][s[0] - 1]
        elif u[1] >= 0.3:
            uso = ctx["usos"][u[0] - 1]
            m["clase"], m["que"] = "uso_conocido", f"{uso['uso']}: {uso['nombre']}".rstrip(": ")
        else:
            m["clase"], m["que"] = "sin_explicar", None
    fichas = {}
    excluir = ctx["catalogo_px"] if ctx["catalogo_px"].any() and not ctx["sin_catalogos"] else None
    for s in ctx["sitios"]:
        f = ins.ficha(s["mascara"], ctx["coh"], ctx["orbitas"], ctx["fechas"], ~agua, paso, p, eco_db=capas["eco_db"], excluir=excluir)
        tierra_px = max(int((s["mascara"] & ~agua).sum()), 1)
        buenas = np.isin(etiquetas, [m["etiqueta"] for m in lista if not m["descartada"]])
        f["cubierto_por_manchas"] = round(float((buenas & s["mascara"]).sum() / tierra_px), 2)
        f["agua"] = round(float((s["mascara"] & agua).sum() / max(int(s["mascara"].sum()), 1)), 2)
        fichas[s["id"]] = f
    return capas, lista, etiquetas, fichas


def _figura(ctx, capas, lista, etiquetas, p, destino):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap

    norte, oeste, sur, este = ctx["fr"].caja
    fig, ejes = plt.subplots(1, 3, figsize=(21, 6.6))
    marco = dict(extent=(oeste, este, sur, norte), aspect=1 / math.cos(math.radians((norte + sur) / 2)), interpolation="nearest")
    magma = plt.get_cmap("magma").copy()
    magma.set_bad("#9fb6c9")  # agua
    for eje, clave, titulo in ((ejes[0], "insomnio_abs", f"Absoluto: fracción de pares con coherencia < {p.umbral_abs}"),
                               (ejes[1], "insomnio", f"Relativo: fracción de pares con coherencia < {p.razon} × entorno")):
        im = eje.imshow(capas[clave], cmap=magma, vmin=0, vmax=1, **marco)
        eje.set_title(titulo, fontsize=10)
        fig.colorbar(im, ax=eje, fraction=0.03)
    clases = np.zeros(etiquetas.shape, dtype=np.uint8)
    for valor, clase in ((1, "uso_conocido"), (2, "sin_explicar"), (3, "relleno_osm")):
        clases[np.isin(etiquetas, [m["etiqueta"] for m in lista if not m["descartada"] and m["clase"] == clase])] = valor
    ejes[2].imshow(np.where(capas["agua"], np.nan, capas["coherencia_media"]), cmap="gray", vmin=0, vmax=1, **marco)
    ejes[2].imshow(np.ma.masked_equal(clases, 0), cmap=ListedColormap(["#3b82f6", "#f59e0b", "#ef4444"]), vmin=1, vmax=3, **marco)
    ejes[2].set_title("Manchas candidatas: rojo = relleno de OSM, naranja = sin explicar, azul = uso conocido (OSM)", fontsize=10)
    for s in ctx["sitios"]:
        if s["rol"] != "control":
            for a in s["anillos"]:
                lon, lat = np.array(a).T
                for eje in ejes:
                    eje.plot(lon, lat, color="#22d3ee", lw=0.8)
    fig.suptitle(f"Índice de insomnio, {ctx['fr'].nombre}, {len(ctx['pares'])} pares de NISAR (GUNW, {ctx['paso']:.0f} m), órbitas "
                 f"{sorted(set(ctx['orbitas'].tolist()))}. Agua: JRC Global Surface Water. Contornos: © OpenStreetMap", fontsize=10)
    fig.tight_layout()
    fig.savefig(destino, dpi=110)
    plt.close(fig)


# Below this insomnia the web PNG is fully transparent (written to indice.json so the web legend reads it)
INDICE_TRANSPARENTE_BAJO = 0.3


def _png_web(capas, ctx, destino):
    """RGBA PNG of the relative index, north up and regular in Web Mercator. Transparent over water and where the index is low."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    img, limites = geo.a_mercator(capas["insomnio"], ctx["xs"], ctx["ys"], caja=ctx["fr"].caja, epsg=ctx["fr"].epsg)
    rgba = plt.get_cmap("magma")(np.clip(np.nan_to_num(img), 0, 1))
    rgba[..., 3] = np.where(np.isfinite(img), np.clip((img - INDICE_TRANSPARENTE_BAJO) / 0.4, 0, 1) * 0.85, 0)
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    plt.imsave(destino, rgba)
    return limites, img.shape


def _escribir_web(ctx, capas, lista, fichas, p, web):
    """The files the web reads. `sitios.json` has the exact shape of `Sitio[]` (src/data/types.ts)."""
    seed = os.path.join(web, "src", "data", "seed")
    try:
        with open(os.path.join(seed, "imagenes.json"), encoding="utf-8") as fh:
            imagenes = json.load(fh)
    except FileNotFoundError:
        imagenes = {}
    sitios, contornos, detalle = [], {}, {}
    for s in ctx["sitios"]:
        f = fichas[s["id"]]
        if s["rol"] == "control" or not f["pares"]:
            continue
        mayor = max(s["anillos"], key=lambda a: geo.area_y_centro(a)[0])
        lon, lat = np.array([q for a in s["anillos"] for q in a]).T
        margen = 0.018  # ~1.6 km: the site with its ring
        img = imagenes.get(s["id"]) or {}
        escenas = img.get("escenas", []) if isinstance(img, dict) else img
        caja = (img.get("caja") if isinstance(img, dict) else None) or [
            round(float(lon.min()) - margen / math.cos(math.radians(lat.mean())), 4), round(float(lat.min()) - margen, 4),
            round(float(lon.max()) + margen / math.cos(math.radians(lat.mean())), 4), round(float(lat.max()) + margen, 4)]
        fila = {"id": s["id"], "nombre": s["nombre"], "lugar": s["lugar"], "pais": s["pais"],
                "lat": round(s["centro"][0], 4), "lon": round(s["centro"][1], 4), "ha": round(s["ha"]),
                "registro": s["registro"]}
        if s.get("cierre"):
            fila["cierre"] = s["cierre"]
        fila.update(radar=f["radar"], insomnio=f["insomnio"],
                    pares=sorted(({"fecha": x["fecha"], "sitio": x["sitio"], "anillo": x["anillo"]} for x in f["pares"]), key=lambda x: x["fecha"]),
                    imagenes=escenas)
        if "osm" in s:
            fila["contorno"] = contornos[s["id"]] = {"type": "Polygon", "coordinates": [[[round(x, 5), round(y, 5)] for x, y in mayor]]}
        fila["caja"] = caja
        sitios.append(fila)
        detalle[s["id"]] = {"motivo": f["motivo"], "persistencia": f["persistencia"], "insomnio_orbita": f["insomnio_orbita"],
                            "eco_db": f["eco_db"], "px": f["px"], "cubierto_por_manchas": f["cubierto_por_manchas"],
                            "pares": f["pares"], "osm": s.get("osm", []), "nota": s.get("nota", ""), "fuentes": s.get("fuentes", [])}
    sitios.sort(key=lambda x: -x["insomnio"])
    filas = ",\n".join("  " + json.dumps(x, ensure_ascii=False) for x in sitios)
    with open(os.path.join(seed, "sitios.json"), "w", encoding="utf-8") as fh:
        fh.write(f"[\n{filas}\n]\n")
    _json(os.path.join(seed, "contornos.json"), contornos, separators=(",", ":"))
    _json(os.path.join(seed, "fichas.json"), detalle, indent=1)
    _json(os.path.join(seed, "candidatos.json"),
          [{k: m[k] for k in ("lat", "lon", "ha", "insomnio", "persistencia", "eco_db", "forma", "clase", "que")} for m in lista if not m["descartada"]],
          indent=0)
    limites, forma = _png_web(capas, ctx, os.path.join(web, "public", "indice", "insomnio-amba.png"))
    o, s_, e, n = limites
    _json(os.path.join(seed, "indice.json"), {
        "url": "indice/insomnio-amba.png", "oeste": o, "sur": s_, "este": e, "norte": n,
        "coordinates": [[o, n], [e, n], [e, s_], [o, s_]], "ancho": forma[1], "alto": forma[0],
        "que": f"Índice de insomnio relativo (0 a 1), paleta magma; transparente por debajo de {INDICE_TRANSPARENTE_BAJO:g} y en el agua".replace(".", ","),
        "transparente_bajo": INDICE_TRANSPARENTE_BAJO,
        "pares": len(ctx["pares"]), "desde": min(x["desde"] for x in ctx["pares"]), "hasta": max(x["hasta"] for x in ctx["pares"]),
        "parametros": {"razon": p.razon, "min_insomnio": p.min_insomnio, "min_persistencia": p.min_persistencia},
        "fuentes": ["NISAR GUNW (NASA/ISRO), vía ASF DAAC", "JRC Global Surface Water v1.4 (máscara de agua)"],
    }, indent=1)
    return len(sitios)


def indice(args):
    import time

    t0 = time.time()
    p = ins.Parametros()
    ctx = cargar(args)
    fr = ctx["fr"]
    capas, lista, etiquetas, fichas = evaluar(ctx, p)
    capa, paso = args.capa, ctx["paso"]
    buenas = [m for m in lista if not m["descartada"]]
    tierra = ~capas["agua"]

    f16 = lambda a: np.asarray(a).astype(np.float16)  # noqa: E731
    np.savez_compressed(
        os.path.join(args.salida, f"indice_{capa}.npz"), insomnio=f16(capas["insomnio"]), insomnio_abs=f16(capas["insomnio_abs"]),
        persistencia=f16(capas["persistencia"]), coherencia_media=f16(capas["coherencia_media"]),
        eco_db=f16(capas["eco_db"] if capas["eco_db"] is not None else np.zeros(1)), agua=capas["agua"], candidato=capas["candidato"],
        manchas=etiquetas.astype(np.int32), pares=capas["pares_validos"].astype(np.uint8), xs=ctx["xs"], ys=ctx["ys"],
        frame=fr.nombre, epsg=fr.epsg, bbox=np.array(fr.bbox), catalogo=ctx["catalogo_px"],
        **{f"insomnio_orbita_{o}": f16(v) for o, v in capas["insomnio_orbita"].items()})

    limpio = lambda m: {k: v for k, v in m.items() if k not in ("etiqueta", "fila", "columna")}  # noqa: E731
    resumen = {
        "capa": capa, "version": "final", "frame": fr.dict(), "parametros": p.dict(),
        "anillo_excluye": None if ctx["sin_catalogos"] else {"basurales": sum(1 for c in ctx["catalogo"] if c["catalogo"] == "basurales"),
                           "negativos": sum(1 for c in ctx["catalogo"] if c["catalogo"] == "negativos"),
                           "ha": round(float(ctx["catalogo_px"].sum() * paso * paso / 1e4))},
        "pares": [{**x, "mediana_tierra": round(float(m), 3), "factor_separacion": round(float(f), 3)}
                  for x, m, f in zip(ctx["pares"], capas["mediana_par"], capas["factor_separacion"])],
        "gcov": int(len(ctx["orbitas_eco"])),
        "superficie": {
            "agua_ha": round(float(capas["agua"].sum() * paso * paso / 1e4)), "tierra_ha": round(float(tierra.sum() * paso * paso / 1e4)),
            "candidata_ha": round(float(sum(m["ha"] for m in buenas))),
            "estacional_ha": round(float(capas["estacional"].sum() * paso * paso / 1e4)),
            "lisa_ha": round(float(sum(m["ha"] for m in lista if m["descartada"] == "lisa"))),
        },
        "sitios": {s["id"]: {"nombre": s["nombre"], "rol": s["rol"], "registro": s.get("registro"), "cierre": s.get("cierre"),
                             "ha": round(s["ha"], 1), **{k: v for k, v in fichas[s["id"]].items() if k != "pares"}}
                   for s in ctx["sitios"]},
        "manchas": {"candidatas": len(buenas), "por_clase": {c: sum(1 for m in buenas if m["clase"] == c) for c in ("relleno_osm", "sin_explicar", "uso_conocido")},
                    "descartadas_lineales": sum(1 for m in lista if m["descartada"] == "lineal"),
                    "descartadas_lisas": sum(1 for m in lista if m["descartada"] == "lisa"),
                    "descartadas_chicas": sum(1 for m in lista if m["descartada"] == "chica"),
                    "primeras": [limpio(m) for m in buenas[:50]]},
        "fuentes": ["NISAR L2 GUNW y GCOV (NASA/ISRO), ASF DAAC", "JRC Global Surface Water v1.4",
                    "© colaboradores de OpenStreetMap (ODbL), por Nominatim y por Overture Maps 2026-10-21.0"],
    }
    _json(os.path.join(args.salida, f"resumen_{capa}.json"), resumen, indent=1)
    _json(os.path.join(args.salida, f"fichas_{capa}.json"), {k: v for k, v in fichas.items()}, indent=1)
    _figura(ctx, capas, lista, etiquetas, p, os.path.join(args.salida, f"indice_{capa}.png"))
    # The web reads the AMBA: the other frames don't touch the web.
    n_web = _escribir_web(ctx, capas, lista, fichas, p, args.web) if args.web and os.path.isdir(args.web) and capa == "80m" and fr.nombre == "AMBA" else 0

    print(f"{fr.nombre}: {len(ctx['pares'])} pares GUNW y {len(ctx['orbitas_eco'])} GCOV, órbitas {sorted(set(ctx['orbitas'].tolist()))}, "
          f"grilla {len(ctx['ys'])} × {len(ctx['xs'])} de {paso:.0f} m en EPSG {fr.epsg}. " + ("El anillo NO excluye los catálogos" if ctx["sin_catalogos"] else
          f"El anillo excluye {resumen['anillo_excluye']['basurales']} basurales y {resumen['anillo_excluye']['negativos']} negativos de los catálogos"))
    if ctx["sitios"]:
        print(f"{'sitio':26s} {'radar':10s} insomnio persist.  órbitas          eco   px  manchas")
    for s in ctx["sitios"]:
        f = fichas[s["id"]]
        orb = " ".join(f"{o}:{v:.2f}" for o, v in f["insomnio_orbita"].items())
        print(f"{s['id']:26s} {f['radar']:10s} {f['insomnio'] if f['insomnio'] is not None else '-':>8} {f['persistencia'] if f['persistencia'] is not None else '-':>8}  "
              f"{orb:16s} {f['eco_db'] if f['eco_db'] is not None else '-':>5} {f['px']:4d}  {f['cubierto_por_manchas']:.2f}")
    print(f"Manchas candidatas: {len(buenas)} ({resumen['manchas']['por_clase']}), {resumen['superficie']['candidata_ha']} ha "
          f"= {resumen['superficie']['candidata_ha'] / resumen['superficie']['tierra_ha']:.1%} de la tierra")
    for m in buenas[:10]:
        print(f"  {m['ha']:7.1f} ha  {m['lat']:.4f}, {m['lon']:.4f}  insomnio {m['insomnio']:.2f}  eco {m['eco_db']}  {m['forma']:9s} {m['clase']}: {m['que'] or ''}")
    if n_web:
        print(f"Web: {n_web} sitios en {os.path.relpath(args.web)}/src/data/seed/sitios.json y el PNG del índice")
    print(f"Listo en {time.time() - t0:.1f} s. Resumen: {os.path.join(args.salida, f'resumen_{capa}.json')}")


# ---------------------------------------------------------------- calibrar
def calibrar(args):
    """Sweeps `razon` and `min_insomnio` and marks the combinations in which the calibration sites get in and the controls don't.

    Criteria (all at once):
      - the sites with role `calibracion` get the "awake" verdict and the candidate blobs cover at least 5 % of each one;
      - the city control comes out "quiet";
      - the candidate blobs cover less than 5 % of each control.
    """
    import dataclasses

    if args.fr.nombre != "AMBA":
        sys.exit("`calibrar` usa los sitios y los controles del AMBA (sitios_registro.json): no corre sobre otro frame.")
    base = ins.Parametros()
    ctx = cargar(args)
    agua = ins.mascara_agua(ctx["ocurrencia"], ctx["paso"], base)
    cociente = ins.cocientes(ctx["coh"], ~agua, ctx["paso"], base)
    eco_db = ins.eco_medio(ctx["eco"], ctx["orbitas_eco"])
    tierra_px = (~agua).sum()
    positivos = [s["id"] for s in ctx["sitios"] if s["rol"] == "calibracion"]
    controles = [s["id"] for s in ctx["sitios"] if s["rol"] == "control"]
    razones, minimos = [round(0.60 + 0.025 * i, 3) for i in range(15)], [0.5, 0.6, 0.7, 0.8, 0.9]
    tabla = []
    for r in razones:
        for t in minimos:
            p = dataclasses.replace(base, razon=r, min_insomnio=t)
            capas, lista, _, fichas = evaluar(ctx, p, cociente=cociente, eco_db=eco_db)
            cumple = (all(fichas[i]["radar"] == "despierto" and fichas[i]["cubierto_por_manchas"] >= 0.05 for i in positivos)
                      and fichas["control-caba"]["radar"] == "quieto"
                      and all(fichas[i]["cubierto_por_manchas"] < 0.05 for i in controles))
            tabla.append({"razon": r, "min_insomnio": t, "cumple": bool(cumple),
                          "tierra_candidata": round(float(sum(m["ha"] for m in lista if not m["descartada"]) * 1e4 / (ctx["paso"] ** 2) / tierra_px), 4),
                          "manchas": sum(1 for m in lista if not m["descartada"]),
                          **{i: {"radar": fichas[i]["radar"], "insomnio": fichas[i]["insomnio"], "cubierto": fichas[i]["cubierto_por_manchas"]}
                             for i in positivos + controles}})
    print("Filas: razon. Columnas: min_insomnio. Celda: '*' si cumple, % de la tierra que queda candidata.")
    print("        " + "".join(f"{t:>10.1f}" for t in minimos))
    for r in razones:
        print(f"  {r:.3f} " + "".join(f"{('*' if x['cumple'] else ' ') + format(x['tierra_candidata'], '.1%'):>10s}" for x in tabla if x["razon"] == r))
    # echo: the threshold has to fall between the known smooth surfaces and the known landfills
    eco_sitio = lambda i: float(np.nanmedian(eco_db[next(s for s in ctx["sitios"] if s["id"] == i)["mascara"]]))  # noqa: E731
    lisos = {i: round(eco_sitio(i), 1) for i in ("control-rio", "lujan-oeste")}
    rellenos = {i: round(eco_sitio(i), 1) for i in positivos}
    print(f"Eco (dB): lisos {lisos}; rellenos {rellenos}. El umbral tiene que caer entre {max(lisos.values())} y {min(rellenos.values())}; "
          f"usamos {base.eco_min_db}.")
    aguas = {str(a): round(float(ins.mascara_agua(ctx["ocurrencia"], ctx["paso"], dataclasses.replace(base, agua_min=a)).mean()), 4) for a in (5, 10, 25, 50, 75)}
    print("Fracción de la grilla que queda como agua según `agua_min` (% de ocurrencia JRC):", aguas)
    _json(os.path.join(args.salida, f"calibracion_{args.capa}.json"),
          {"criterios": calibrar.__doc__.split("Criterios")[1].strip(), "elegido": {"razon": base.razon, "min_insomnio": base.min_insomnio, "eco_min_db": base.eco_min_db},
           "eco_db": {"lisos": lisos, "rellenos": rellenos}, "agua_fraccion_por_umbral": aguas, "tabla": tabla}, indent=1)


# ---------------------------------------------------------------- main
def preparar(args, nombre):
    """Copy of the arguments for one frame: the frame, its orbits and its own folders."""
    a = argparse.Namespace(**vars(args))
    nombre = nombre.upper()
    amba = nombre == "AMBA"
    a.salida = args.salida if amba else os.path.join(args.salida, nombre)
    a.datos = args.datos if amba else os.path.join(args.datos, nombre)
    if args.caja and not amba:
        fr = geo.frame_de_caja(nombre, args.caja)
        guardado = os.path.join(a.salida, "frame.json")
        if os.path.exists(guardado):  # the EPSG that `procesar` already fixed with the first product
            with open(guardado, encoding="utf-8") as fh:
                previo = geo.frame_de_dict(json.load(fh))
            if previo.bbox == fr.bbox:
                fr = previo
    else:
        fr = geo.frame(nombre, a.salida)
    if args.epsg and not amba:
        fr = dataclasses.replace(fr, epsg=args.epsg, epsg_fijo=True)
    if args.orbitas:
        fr = dataclasses.replace(fr, orbitas=tuple(args.orbitas))
    if args.desde is not None:
        fr = dataclasses.replace(fr, desde=args.desde)
    if args.hasta is not None:
        fr = dataclasses.replace(fr, hasta=args.hasta)
    a.fr, a.orbitas, a.fijos = fr, list(fr.orbitas), ff.carpeta(fr, args.fijos)
    return a


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("paso", choices=["buscar", "bajar", "procesar", "indice", "calibrar", "todo"])
    p.add_argument("--frame", nargs="+", default=["AMBA"], help="one or more frames from data/catalogos/frames.json, or `todos` (in priority order). Default: AMBA")
    p.add_argument("--caja", type=float, nargs=4, metavar=("LON_O", "LAT_S", "LON_E", "LAT_N"),
                   help="box of a frame that isn't in frames.json, in GeoJSON order (goes with a single --frame NAME)")
    p.add_argument("--epsg", type=int, help="EPSG of the grid (UTM). If not given: the one in frames.json or, with --caja, the first GUNW's")
    p.add_argument("--datos", default=os.path.join(AQUI, "datos"), help="folder of the .h5 files (outside the repo on the VM, for example /mnt/datos)")
    p.add_argument("--salida", default=os.path.join(RAIZ, "data", "salidas"), help="folder of small products (list, crops, index, figures)")
    p.add_argument("--fijos", default=FIJOS, help="folder of the fixed sources: each frame caches its own in <fijos>/<FRAME>/ (the AMBA's, loose)")
    p.add_argument("--web", default=WEB, help="web folder; `indice` for the AMBA at 80 m writes the web data there ('' to skip writing)")
    p.add_argument("--orbitas", type=int, nargs="+", help="orbits (path) to use. Default: the frame's (AMBA: 10 and 161) or all those crossing the box")
    p.add_argument("--desde", help="YYYY-MM-DD: first date of the products `buscar` takes (default: the frame's; '' = no limit)")
    p.add_argument("--hasta", help="YYYY-MM-DD: last date of the products `buscar` takes (default: the frame's; '' = no limit)")
    p.add_argument("--capa", choices=list(CAPAS), default="80m")
    p.add_argument("--procesos", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    p.add_argument("--hilos", type=int, default=8, help="descargas en paralelo")
    p.add_argument("--solo-gunw", action="store_true", help="don't download or process GCOV")
    p.add_argument("--remoto", action="store_true", help="process by reading only the needed window by URL, without downloading the .h5 files (needs credentials)")
    p.add_argument("--sin-catalogos", action="store_true", help="each site's ring excludes only the site and water, as before stage 1 (for comparison)")
    p.add_argument("--borrar", action="store_true", help="delete each local .h5 after cropping it (to download, process and delete frame by frame)")
    args = p.parse_args()
    nombres = list(geo.frames_conocidos()) if args.frame == ["todos"] else args.frame
    if args.caja and len(nombres) != 1:
        sys.exit("--caja define un solo frame: pasá un único --frame NOMBRE.")
    pasos = ["buscar"] + ([] if args.remoto else ["bajar"]) + ["procesar", "indice"] if args.paso == "todo" else [args.paso]
    fallados = []
    for nombre in nombres:
        try:
            a = preparar(args, nombre)
            for paso in pasos:
                print(f"== {paso}" + ("" if nombres == ["AMBA"] else f" [{a.fr.nombre}]"), flush=True)
                globals()[paso](a)
        except (Exception, SystemExit) as e:
            if len(nombres) == 1:
                raise
            fallados.append(nombre)  # a failing frame doesn't stop the others
            print(f"ERROR en {nombre}: {type(e).__name__}: {e}", flush=True)
    if fallados:
        sys.exit(f"Frames con error: {', '.join(fallados)}")


if __name__ == "__main__":
    main()
