"""Resolution test: does the front model (`radar_frente.py`) improve if measured at 20 m instead of 80 m?

Three variants, each one separately against the 10 variables at 80 m of `../data/salidas/radar_frente.parquet`:
  1. eco_80m_promediado  the echo (GCOV) averaged in linear power over each 80 m cell (all the native pixels
                         that fall inside: 8×8 if the GCOV comes at 10 m, 4×4 if it comes at 20 m), instead of the nearest
                         neighbor of `pipeline_insomnio.recortar`
  2. eco_20m             the echo on a 20 m grid, by nearest neighbor (as `--capa 20m` would do)
  3. coherencia_20m      the coherence of the `wrappedInterferogram` layer (20 m), the one of `--capa 20m`
And the control rows, fixed here before looking at any result:
  replica_80m               the 10 variables at 80 m recomputed with this test's windows (nearest neighbor):
                            measures how much this reading path departs from the original table's
  todo_20m                  echo and coherence at 20 m together (variants 2 and 3 at once)
  eco_20m_promediado        echo at 20 m averaging the native pixels (only changes where the GCOV comes at 10 m)
  eco_80m_sin_frecuencia_B  the 80 m series without the dates on which the GCOV lacks frequency A and `_buscar_eco` falls back to B

In each variant only the variables that change are replaced (the 4 echo ones or the 6 coherence ones); the rest are
the 80 m ones of the original table. The variables are computed with `radar_frente.medir`, untouched: at 20 m the 3×3
pixel patch is 60 m per side, not 240 m. No variables or thresholds are chosen by looking at the result.

Addendum (also fixed before evaluating), at 80 m, at 80 m averaged and at 20 m:
  - two more statistics of the echo's temporal variation, instead of the deviation: the coefficient of variation in
    linear power and the range between the 10th and 90th percentiles (robust to dates with interference);
  - `coh_y_eco_*`: per pixel, fraction of pairs in which it loses coherence and its echo also changes between those two dates;
  - what is read today (dataset, frequency, spacing and looks) and whether the ring echo jumps between BETA and PROVISIONAL products.

It doesn't reread whole frames: it reads by URL, from each product, one window per site (polygon + 1.5 km ring + margin).

    python prueba_resolucion.py preparar   # fixed sources of each frame (JRC water at 80 m and catalog polygons)
    python prueba_resolucion.py leer       # windows by URL; can be stopped and repeated: what's been read isn't read again
    python prueba_resolucion.py medir      # the variables of each variant, per site (one table per frame in datos/)
    python prueba_resolucion.py evaluar    # AUC, terciles, paired differences -> ../data/salidas/prueba_resolucion.json

In cloud containers: `env -u FSSPEC_GCS timeout -k 10 900 python prueba_resolucion.py leer`,
repeated until it says nothing is missing. Credentials: EARTHDATA_TOKEN as an environment variable, never in the repo.

Data: NISAR L2 GUNW and GCOV (NASA/ISRO), via ASF DAAC. Water: JRC Global Surface Water v1.4. Catalog: `../data/README.md`.
"""
import argparse
import glob
import json
import os
import re
import sys
import time
import warnings

import numpy as np
import pandas as pd

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import extraer_manchas as em  # noqa: E402
import fuentes_fijas as ff  # noqa: E402
import geo  # noqa: E402
import insomnio as ins  # noqa: E402
import modelo_estado as me  # noqa: E402
import pipeline_insomnio as pl  # noqa: E402
import radar_frente as rf  # noqa: E402

RAIZ = os.path.dirname(AQUI)
SALIDAS = os.path.join(RAIZ, "data", "salidas")
DATOS = os.path.join(AQUI, "datos", "prueba_resolucion")
SALIDA_JSON = os.path.join(SALIDAS, "prueba_resolucion.json")
MARGEN_PX80 = 2  # 80 m cells of margin around the polygon plus the ring
ECO = rf.NUEVAS[:4]
COH = rf.NUEVAS[4:]
# Which columns come from which measurement. "base" is the original 80 m table.
VARIANTES = {
    "replica_80m": {"eco": "rep80", "coh": "rep80", "que": "control: las 10 a 80 m, releídas por ventana (vecino más cercano)"},
    "eco_80m_promediado": {"eco": "prom80", "coh": "base", "que": "1. eco promediado en potencia lineal sobre la celda de 80 m"},
    "eco_20m": {"eco": "m20", "coh": "base", "que": "2. eco a 20 m, vecino más cercano"},
    "coherencia_20m": {"eco": "base", "coh": "m20", "que": "3. coherencia a 20 m (wrappedInterferogram)"},
    "todo_20m": {"eco": "m20", "coh": "m20", "que": "control: eco y coherencia a 20 m juntos"},
    "eco_80m_sin_frecuencia_B": {"eco": "sinB80", "coh": "base", "que": "agregado: eco a 80 m sin las fechas en que el producto sólo trae la frecuencia B (cambia en 3 frames)"},
    "eco_20m_promediado": {"eco": "prom20", "coh": "base", "que": "control: eco a 20 m promediando los píxeles nativos (sólo cambia donde el GCOV viene a 10 m)"},
}
N_REMUESTREO = 2000
MEDICIONES = ("rep80", "prom80", "m20")
MEDICIONES_QUE = {"rep80": "80 m, vecino más cercano", "prom80": "80 m, eco promediado", "m20": "20 m"}


# ------------------------------------------------------------------ predios y ventanas
def predios():
    """The sites of the `radar_frente.py` evaluation in the frames with `criterio = abiertos`: same rows, same order."""
    with open(geo.FRAMES_JSON, encoding="utf-8") as fh:
        abiertos = {str(d["frame"]).upper() for d in json.load(fh)["frames"] if d.get("criterio") == "abiertos"}
    f = pd.read_parquet(rf.TABLA)
    d = me.cargar().merge(f[["id_catalogo"] + rf.NUEVAS + ["n_pares", "n_eco"]], on="id_catalogo", how="inner", suffixes=("", "_frente"))
    e = d[d["y"].notna() & ~d["frame"].isin(me.PRUEBA) & d["frame"].isin(abiertos)].reset_index(drop=True)
    return e


def args_frame(nombre):
    ns = argparse.Namespace(frame=[nombre], caja=None, epsg=None, datos="", salida=SALIDAS, fijos=pl.FIJOS, web="", orbitas=None,
                            desde=None, hasta=None, capa="80m", sin_catalogos=False)
    return pl.preparar(ns, nombre)


def _fino(centros, paso_fino=20.0, paso=80.0):
    """Centers of the 20 m pixels that fall in each 80 m cell (4 per cell), in the same direction as `centros`."""
    k = int(round(paso / paso_fino))
    signo = 1.0 if centros[1] > centros[0] else -1.0
    desvios = signo * ((np.arange(k) + 0.5) * paso_fino - paso / 2)
    return (centros[:, None] + desvios[None, :]).ravel()


def ventanas_frame(nombre, ids):
    """For each site in the frame: its window in the frame's 80 m grid and everything fixed (masks, water, catalog)
    at 80 m and at 20 m. The 20 m window is exactly the 4×4 pixels of each 80 m cell."""
    a = args_frame(nombre)
    fr, p = a.fr, ins.Parametros()
    xs, ys = fr.grilla(80.0)
    with np.load(os.path.join(a.fijos, "agua_jrc_80m.npz")) as d:
        agua = ins.mascara_agua(d["ocurrencia"], 80.0, p)
    with open(os.path.join(a.fijos, "catalogo.json"), encoding="utf-8") as fh:
        catalogo = json.load(fh)["poligonos"]
    catalogo_px = np.zeros((len(ys), len(xs)), dtype=bool)
    cajas = []
    for c in catalogo:
        catalogo_px |= fr.mascara_poligonos(c["anillos"], xs, ys)
        lon, lat = np.array([q[:2] for an in c["anillos"] for q in an], dtype=float).T
        cajas.append((lon.min(), lon.max(), lat.min(), lat.max()))
    por_id = {c["id"]: c for c in catalogo if c["catalogo"] == "basurales"}
    salida = {}
    for i in ids:
        s = por_id[i]
        mascara = fr.mascara_poligonos(s["anillos"], xs, ys)
        v = em._ventana(mascara, int(round(p.anillo_m / 80.0)) + 1 + MARGEN_PX80)
        x80, y80 = xs[v[1]], ys[v[0]]
        x20, y20 = _fino(x80), _fino(y80)
        # At 20 m: the polygon and the catalog ones are rasterized again; the water is the 80 m one repeated.
        lat_v, lon_v = fr.latlon(np.array([x20.min(), x20.max()]), np.array([y20.min(), y20.max()]))
        cat20 = np.zeros((len(y20), len(x20)), dtype=bool)
        for c, (o, e_, s_, n) in zip(catalogo, cajas):
            if o <= lon_v.max() + 0.01 and e_ >= lon_v.min() - 0.01 and s_ <= lat_v.max() + 0.01 and n >= lat_v.min() - 0.01:
                cat20 |= fr.mascara_poligonos(c["anillos"], x20, y20)
        salida[i] = {"fr": fr, "x80": x80, "y80": y80, "x20": x20, "y20": y20,
                     "m80": mascara[v], "agua80": agua[v], "cat80": catalogo_px[v],
                     "m20": fr.mascara_poligonos(s["anillos"], x20, y20), "agua20": np.kron(agua[v], np.ones((4, 4), dtype=bool)), "cat20": cat20}
    return salida


# ------------------------------------------------------------------ preparar
def cmd_preparar(args):
    e = predios()
    for nombre in sorted(e["frame"].unique()):
        a = args_frame(nombre)
        if not os.path.exists(os.path.join(a.fijos, "catalogo.json")):
            ff.catalogo(a.fr, a.fijos)
        if not os.path.exists(os.path.join(a.fijos, "agua_jrc_80m.npz")):
            ff.agua(a.fr, ("80m",), a.fijos)
    print(f"Fuentes fijas listas para {e['frame'].nunique()} frames y {len(e)} predios")


# ------------------------------------------------------------------ leer
class _Contador:
    """Wraps an h5py dataset to know which window `recortar` asked for and how much its compressed chunks weigh."""

    def __init__(self, ds):
        self.ds, self.bytes, self.px, self.bloques = ds, 0, 0, set()

    def __getitem__(self, clave):
        sf, sc = clave
        self.px += (sf.stop - sf.start) * (sc.stop - sc.start)
        bf, bc = self.ds.chunks
        for f in range(sf.start // bf, (sf.stop - 1) // bf + 1):
            for c in range(sc.start // bc, (sc.stop - 1) // bc + 1):
                if (f, c) not in self.bloques:  # a chunk already read stays in the file's cache
                    self.bloques.add((f, c))
                    try:
                        self.bytes += int(self.ds.id.get_chunk_info_by_coord((f * bf, c * bc)).size)
                    except Exception:
                        pass
        return self.ds[clave]


def _promedio(lin, k):
    """Mean in linear power of the k×k pixels of each cell, in dB. Pixels without signal (below
    `radar_frente.ECO_SIN_SENAL_DB`) don't count; at least half the cell needs data."""
    lin = np.where(np.isfinite(lin) & (lin > 10.0 ** (rf.ECO_SIN_SENAL_DB / 10.0)), lin.astype(np.float64), np.nan)
    f, c = lin.shape[0] // k, lin.shape[1] // k
    bloques = lin.reshape(f, k, c, k).transpose(0, 2, 1, 3).reshape(f, c, k * k)
    n = np.isfinite(bloques).sum(-1)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        media = np.nanmean(bloques, axis=-1)
    media[n < (k * k + 1) // 2] = np.nan
    with np.errstate(divide="ignore", invalid="ignore"):
        return (10 * np.log10(media)).astype(np.float32)


def _escalar(f, ruta):
    """A single value from the product (text or number), or None if it doesn't carry it."""
    if ruta not in f:
        return None
    v = f[ruta][()]
    if isinstance(v, bytes):
        return v.decode()
    v = np.asarray(v)
    if v.dtype.kind in "SO":
        return [x.decode() if isinstance(x, bytes) else str(x) for x in v.ravel()]
    return float(v.ravel()[0]) if v.size == 1 else [float(x) for x in v.ravel()[:8]]


def _que_se_lee(f, x, capas, vs):
    """Which dataset the pipeline picked, with what spacing and how many looks, and the product's maturity. Goes to the metadata."""
    ident = "science/LSAR/identification"
    m = {"madurez": "BETA" if "_BETA_" in x["url"] else "PROVISIONAL" if "_PROVISIONAL_" in x["url"] else "otra",
         "compositeReleaseId": _escalar(f, f"{ident}/compositeReleaseId"), "productVersion": _escalar(f, f"{ident}/productVersion"),
         "listOfFrequencies": _escalar(f, f"{ident}/listOfFrequencies"), "boundingPolygon": _escalar(f, f"{ident}/boundingPolygon"),
         "datasets": {k: {"ruta": ds.name, "espaciado_m": [float(xs[1] - xs[0]), float(ys[1] - ys[0])]}
                      for k, (ds, xs, ys, _) in capas.items() if not k.endswith("nativo")}}
    if x["tipo"] == "GUNW":
        par = "science/LSAR/GUNW/metadata/processingInformation/parameters"
        m["looks"] = {c: [_escalar(f, f"{par}/{c}/frequencyA/numberOfRangeLooks"), _escalar(f, f"{par}/{c}/frequencyA/numberOfAzimuthLooks")]
                      for c in (pl.CAPAS["20m"][0], pl.CAPAS["80m"][0])}
        m["frecuencias"] = sorted(f["science/LSAR/GUNW/grids"].keys())
    else:
        grids = "science/LSAR/GCOV/grids"
        m["frecuencias"] = {fq: _escalar(f, f"{grids}/{fq}/xCoordinateSpacing") for fq in sorted(f[grids].keys())}
        cal = "science/LSAR/GCOV/metadata/calibrationInformation/frequencyA"
        m["rfiLikelihood_A"] = {pol: _escalar(f, f"{cal}/{pol}/rfiLikelihood") for pol in ("HH", "HV")}
        m["rfiMitigationApplied"] = _escalar(f, "science/LSAR/GCOV/metadata/processingInformation/parameters/rfiMitigationApplied")
        # Looks: the `numberOfLooks` raster of the chosen group, in the window of the first site with data.
        ds, xs, ys, epsg_src = capas["eco20"]
        looks = f[ds.name.rsplit("/", 1)[0] + "/numberOfLooks"]
        for v in vs.values():
            fino = abs(float(xs[1] - xs[0]))
            w = pl.recortar(looks, xs, ys, _fino(v["x80"], fino), _fino(v["y80"], fino), epsg_src, v["fr"].epsg)
            if np.isfinite(w).any():
                m["numberOfLooks_ventana"] = {"mediana": float(np.nanmedian(w)), "p10": float(np.nanpercentile(w, 10)), "p90": float(np.nanpercentile(w, 90))}
                break
    return m


def _corto(x):
    fechas = re.findall(r"_(\d{8})T\d{6}", x["nombre"])
    sec = fechas[2] if len(fechas) > 2 else fechas[0]
    return f"{x['tipo'].lower()}_{x['orbita']:03d}_{x['frame_nisar']:03d}_{fechas[0]}_{sec}"


def _leer_uno(tarea):
    """Reads from a product the windows of all the sites in its frame and saves them in a single .npz."""
    nombre_frame, x, destino = tarea
    if os.path.exists(destino):
        return destino, "ya estaba"
    try:
        e = _leer_uno.predios
        vs = _leer_uno.ventanas.get(nombre_frame)
        if vs is None:
            vs = _leer_uno.ventanas[nombre_frame] = ventanas_frame(nombre_frame, list(e.loc[e["frame"] == nombre_frame, "id_catalogo"]))
        fechas = re.findall(r"_(\d{8})T\d{6}", x["nombre"])
        datos, meta = {}, {"producto": x["nombre"], "tipo": x["tipo"], "orbita": x["orbita"], "frame_nisar": x["frame_nisar"],
                           "fecha_ref": fechas[0], "fecha_sec": fechas[2] if len(fechas) > 2 else fechas[0], "capas": {}}
        t0 = time.time()
        with pl._abrir(x["url"], True) as f:
            meta["s_abrir"] = round(time.time() - t0, 2)
            if x["tipo"] == "GUNW":
                capas = {"coh20": pl._buscar_capa(f, pl.CAPAS["20m"][0]), "coh80": pl._buscar_capa(f, pl.CAPAS["80m"][0])}
            else:
                co, cruzada, xs, ys, epsg_src = pl._buscar_eco(f)
                # native: to average; 20 and 80: the nearest neighbor of `recortar`, as the pipeline does
                capas = {k: (co, xs, ys, epsg_src) for k in ("econativo", "eco20", "eco80")}
                if cruzada is not None:
                    capas.update({k: (cruzada, xs, ys, epsg_src) for k in ("ecohvnativo", "ecohv20", "ecohv80")})
                meta["espaciado_gcov_m"] = [float(xs[1] - xs[0]), float(ys[1] - ys[0])]
            t = time.time()
            meta["que_se_lee"] = _que_se_lee(f, x, capas, vs)
            meta["s_metadatos"] = round(time.time() - t, 2)
            for clave, (ds, xs, ys, epsg_src) in capas.items():
                cuenta, t = _Contador(ds), time.time()
                for i, v in vs.items():
                    fr = v["fr"]
                    if clave.endswith("nativo"):
                        # Window at the GCOV's native spacing (10 or 20 m depending on the mode) and, from there, the mean in linear
                        # power of each 80 m cell and each 20 m cell. The native window isn't saved.
                        fino = abs(float(xs[1] - xs[0]))
                        nativo = pl.recortar(cuenta, xs, ys, _fino(v["x80"], fino), _fino(v["y80"], fino), epsg_src, fr.epsg)
                        k = max(1, int(round(80.0 / fino)))
                        datos[f"{i}|{clave[:-6]}80p"] = _promedio(nativo, k).astype(np.float16)
                        if fino <= 20.0:
                            datos[f"{i}|{clave[:-6]}20p"] = _promedio(nativo, k // 4).astype(np.float16)
                        else:  # some GCOVs have frequency A at 80 m (5 MHz mode): at 20 m there's nothing to average
                            lin = pl.recortar(cuenta, xs, ys, v["x20"], v["y20"], epsg_src, fr.epsg)
                            datos[f"{i}|{clave[:-6]}20p"] = _promedio(lin, 1).astype(np.float16)
                        continue
                    xd, yd = (v["x80"], v["y80"]) if clave.endswith("80") else (v["x20"], v["y20"])
                    valor = pl.recortar(cuenta, xs, ys, xd, yd, epsg_src, fr.epsg)
                    if clave.startswith("coh"):
                        valor[(valor <= 0) | (valor > 1)] = np.nan
                    else:  # to dB, like `_procesar_uno`
                        with np.errstate(divide="ignore", invalid="ignore"):
                            valor = (10 * np.log10(valor)).astype(np.float32)
                        valor[~np.isfinite(valor)] = np.nan
                    datos[f"{i}|{clave}"] = valor.astype(np.float16)
                meta["capas"][clave] = {"s": round(time.time() - t, 2), "bytes_comprimidos": cuenta.bytes, "px": int(cuenta.px),
                                        "bloques": len(cuenta.bloques), "epsg": int(epsg_src)}
        parcial = destino + ".parcial.npz"
        np.savez_compressed(parcial, meta=json.dumps(meta, default=float), **datos)
        os.replace(parcial, destino)
        return destino, f"ok {time.time() - t0:.0f} s"
    except Exception as ex:  # a broken product doesn't stop the others; it's retried in the next batch
        return destino, f"ERROR {type(ex).__name__}: {ex}"


def _iniciar_proceso():
    """Each process dies if the one that launched it dies (so `timeout` leaves no loose processes) and loads the sites once."""
    import ctypes
    import signal

    try:
        ctypes.CDLL("libc.so.6").prctl(1, signal.SIGKILL)
    except Exception:
        pass
    warnings.filterwarnings("ignore")
    _leer_uno.predios = predios()
    _leer_uno.ventanas = {}


def cmd_leer(args):
    import multiprocessing

    e = predios()
    tareas = []
    for nombre in sorted(e["frame"].unique()):
        if args.frame and nombre not in [f.upper() for f in args.frame]:
            continue
        with open(os.path.join(SALIDAS, nombre, "lista_productos.json"), encoding="utf-8") as fh:
            lista = json.load(fh)
        os.makedirs(os.path.join(DATOS, nombre), exist_ok=True)
        tareas += [(nombre, x, os.path.join(DATOS, nombre, _corto(x) + ".npz")) for x in lista]
    faltan = [t for t in tareas if not os.path.exists(t[2])]
    print(f"Productos: {len(tareas)}; ya leídos: {len(tareas) - len(faltan)}; a leer: {len(faltan)}", flush=True)
    if not faltan:
        return
    errores = 0
    with multiprocessing.get_context("spawn").Pool(args.procesos, initializer=_iniciar_proceso) as pool:
        for destino, estado in pool.imap_unordered(_leer_uno, faltan):
            errores += estado.startswith("ERROR")
            print(f"  {os.path.relpath(destino, DATOS)}: {estado}", flush=True)
    if errores:
        sys.exit(f"{errores} producto(s) con error: repetí `leer`")


# ------------------------------------------------------------------ medir
CLAVES = ("coh80", "coh20", "eco20", "ecohv20", "eco20p", "ecohv20p", "eco80", "ecohv80", "eco80p", "ecohv80p")
# Addendum (decided before evaluating): two other statistics of the echo's temporal variation and the per-pair coincidence.
ESTADISTICOS = {"cv": "coeficiente de variación en potencia lineal", "rango": "rango entre los percentiles 10 y 90 del eco en dB"}
EXTRA_ECO = {s: [f"eco_{s}_rel_p90", f"ecohv_{s}_rel_p90", f"eco_{s}_rel_max3"] for s in ESTADISTICOS}
STD_ECO = ["eco_std_rel_p90", "ecohv_std_rel_p90", "eco_std_rel_max3"]  # the three that get replaced
COINCIDE = ["coh_y_eco_rel_max3", "coh_y_eco_rel_p90"]
MADUREZ = ["mad_n_beta", "mad_n_prov", "mad_intercalado", "mad_salto_db", "mad_frontera_db", "mad_paso_tipico_db"]
PERCENTIL_CAMBIO = 90  # "its echo changes": the change between the two dates exceeds the 90th percentile of the ring's change in that pair


def cargar_frame(nombre):
    """The products read for a frame: [(metadata, .npz path)]."""
    productos = []
    for ruta in sorted(glob.glob(os.path.join(DATOS, nombre, "*.npz"))):
        if not ruta.endswith(".parcial.npz"):
            with np.load(ruta) as d:
                productos.append((json.loads(str(d["meta"])), ruta))  # the windows are loaded later, one site at a time
    return productos


def cobertura_frame(fr, productos):
    """Fraction of the frame covered by the echo of each (orbit, date), with the product's polygon (`boundingPolygon`).
    It's the rule of `pipeline_insomnio.cargar` (a GCOV covering less than half the frame doesn't count), which there is
    measured with the pixels with data of the whole crop and here, without the crop, with the product's footprint."""
    xs, ys = fr.grilla(80.0)
    xs, ys = xs[::10], ys[::10]
    cubre = {}
    for m, _ in productos:
        if m["tipo"] == "GCOV":
            puntos = [[float(t) for t in par.split()[:2]] for par in re.search(r"\(\((.*?)\)", m["que_se_lee"]["boundingPolygon"]).group(1).split(",")]
            k = (m["orbita"], m["fecha_ref"])
            cubre[k] = cubre.get(k, False) | fr.mascara_poligonos([puntos], xs, ys)
    return {k: float(v.mean()) for k, v in cubre.items()}


def _pilas(productos, i, cubre, sin_b=False):
    """A site's series, grouped and sorted as in `pipeline_insomnio.cargar`: the pieces of neighboring NISAR frames
    for the same pair or date are joined (the one covering most wins) and an echo covering less than half the frame doesn't count."""
    grupos, madurez = {}, {}
    for m, ruta in productos:
        if sin_b and m["tipo"] == "GCOV" and "frequencyB" in m["que_se_lee"]["datasets"]["eco80"]["ruta"]:
            continue  # GCOV without frequency A: `_buscar_eco` falls back to B (and VV)
        with np.load(ruta) as d:
            for clave in CLAVES:
                if f"{i}|{clave}" in d.files:
                    k = (clave, m["orbita"], m["fecha_ref"], m["fecha_sec"])
                    grupos.setdefault(k, []).append(d[f"{i}|{clave}"].astype(np.float32))
                    madurez[k] = m["que_se_lee"]["madurez"]
    s = {k: {"v": [], "orbitas": [], "fechas": [], "ref": [], "sec": [], "madurez": []} for k in CLAVES}
    for (clave, orbita, f_ref, f_sec), piezas in sorted(grupos.items(), key=lambda kv: kv[0]):
        if clave.startswith("eco") and cubre.get((orbita, f_ref), 0.0) < 0.5:
            continue
        s[clave]["v"].append(pl._juntar(piezas))
        s[clave]["orbitas"].append(orbita)
        s[clave]["fechas"].append(pl._fecha(f_sec))
        s[clave]["ref"].append(f_ref)
        s[clave]["sec"].append(f_sec)
        s[clave]["madurez"].append(madurez[(clave, orbita, f_ref, f_sec)])
    return s


def _percentil(serie, q):
    """Percentile q over time, per pixel, ignoring NaNs (like `np.nanpercentile`, but fast)."""
    orden = np.sort(serie, axis=0)  # NaNs end up last
    n = np.isfinite(serie).sum(0)
    pos = np.clip(q / 100.0 * (n - 1), 0, None)
    abajo, arriba = np.floor(pos).astype(int), np.ceil(pos).astype(int)
    va = np.take_along_axis(orden, abajo[None], 0)[0]
    vb = np.take_along_axis(orden, arriba[None], 0)[0]
    salida = va + (vb - va) * (pos - abajo)
    salida[n == 0] = np.nan
    return salida


def _estadisticos(pila_db, orbitas):
    """Per pixel and within each orbit (3 dates or more), averaged across orbits: the coefficient of variation in
    linear power and the range between the 10th and 90th percentiles in dB."""
    partes = {k: [] for k in ESTADISTICOS}
    for o in np.unique(orbitas):
        serie = pila_db[orbitas == o]
        if len(serie) >= 3:
            lin = 10.0 ** (serie.astype(np.float64) / 10.0)
            partes["cv"].append(np.nanstd(lin, axis=0) / np.nanmean(lin, axis=0))
            partes["rango"].append(_percentil(serie, 90) - _percentil(serie, 10))
    return {k: np.nanmean(np.stack(v), axis=0) for k, v in partes.items()} if partes["cv"] else None


def medir_extra(mascara, agua, catalogo_px, paso, coh, eco, eco_hv, p, con_madurez=False):
    """What isn't in `radar_frente.medir`, with the same site and the same ring: the two other statistics of the
    echo variation, the per-pair coincidence (loses coherence and its echo also changes) and the maturity jump."""
    v = em._ventana(mascara, int(round(p.anillo_m / paso)) + 1)
    m, tierra = mascara[v], ~agua[v]
    adentro = m & tierra
    aro = ins.anillo(m, tierra, paso, p, excluir=catalogo_px[v])
    fila = {k: np.nan for cols in EXTRA_ECO.values() for k in cols}
    fila.update({k: np.nan for k in COINCIDE}, n_pares_coh_y_eco=0)
    if adentro.sum() < p.min_px_sitio or not aro.any():
        return fila
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        pilas = {}
        for clave, serie in (("eco", eco), ("ecohv", eco_hv)):
            if not serie["v"]:
                continue
            pila = np.stack(serie["v"])[(slice(None),) + v]
            pila = np.where(pila < rf.ECO_SIN_SENAL_DB, np.nan, pila)
            pilas[clave] = pila
            est = _estadisticos(pila, np.asarray(serie["orbitas"]))
            if est is None:
                continue
            for nombre, mapa in est.items():
                if not np.isfinite(mapa[adentro]).any() or not np.isfinite(mapa[aro]).any():
                    continue
                ref = np.nanmedian(mapa[aro])
                fila[f"{clave}_{nombre}_rel_p90"] = float(np.nanpercentile(mapa[adentro], 90) - ref)
                if clave == "eco":
                    m3 = rf.media3(mapa, adentro)
                    fila[f"eco_{nombre}_rel_max3"] = float(np.nanmax(m3) - ref) if np.isfinite(m3).any() else np.nan
        # ---- coincidence: per pixel, fraction of pairs in which it loses coherence and its echo also changes between those two dates
        if "eco" in pilas and coh["v"]:
            c = np.stack(coh["v"])[(slice(None),) + v]
            m_aro = np.nanmedian(c[:, aro], axis=1)
            donde = {(o, f): k for k, (o, f) in enumerate(zip(eco["orbitas"], eco["ref"]))}
            ambos, validos = np.zeros(adentro.shape), np.zeros(adentro.shape)
            for k, (o, ref, sec) in enumerate(zip(coh["orbitas"], coh["ref"], coh["sec"])):
                if not (np.isfinite(m_aro[k]) and m_aro[k] > 0 and np.isfinite(c[k][adentro]).mean() >= 0.5) or (o, ref) not in donde or (o, sec) not in donde:
                    continue
                d = pilas["eco"][donde[(o, sec)]] - pilas["eco"][donde[(o, ref)]]
                if not np.isfinite(d[aro]).any():
                    continue
                d = np.abs(d - np.nanmedian(d[aro]))
                umbral = np.nanpercentile(d[aro], PERCENTIL_CAMBIO)
                ok = np.isfinite(d) & np.isfinite(c[k])
                ambos += ok & (d > umbral) & (c[k] / m_aro[k] < p.razon)
                validos += ok
                fila["n_pares_coh_y_eco"] += 1
            if fila["n_pares_coh_y_eco"] >= 3:
                frac = np.where(validos >= 3, ambos / np.maximum(validos, 1), np.nan)
                if np.isfinite(frac[adentro]).any() and np.isfinite(frac[aro]).any():
                    ref = np.nanmedian(frac[aro])
                    m3 = rf.media3(frac, adentro)
                    fila["coh_y_eco_rel_max3"] = float(np.nanmax(m3) - ref) if np.isfinite(m3).any() else np.nan
                    fila["coh_y_eco_rel_p90"] = float(np.nanpercentile(frac[adentro], 90) - ref)
        # ---- maturity: does the ring's mean echo jump between the BETA and PROVISIONAL products?
        if con_madurez and "eco" in pilas:
            fila.update({k: np.nan for k in MADUREZ})
            lin = 10.0 ** (pilas["eco"][:, aro].astype(np.float64) / 10.0)
            medio = 10 * np.log10(np.nanmean(lin, axis=1))  # ring mean echo per date, in dB
            orb, mad, fec = np.asarray(eco["orbitas"]), np.asarray(eco["madurez"]), np.asarray(eco["ref"])
            fila["mad_n_beta"], fila["mad_n_prov"] = int((mad == "BETA").sum()), int((mad == "PROVISIONAL").sum())
            saltos, fronteras, pasos, intercalado = [], [], [], False
            for o in np.unique(orb):
                s_ = orb == o
                x, g, f = medio[s_], mad[s_], fec[s_]  # they already come sorted by date
                ok = np.isfinite(x)
                x, g, f = x[ok], g[ok], f[ok]
                pasos += [abs(b - a) for a, b, ga, gb in zip(x[:-1], x[1:], g[:-1], g[1:]) if ga == gb]
                if (g == "BETA").sum() >= 2 and (g == "PROVISIONAL").sum() >= 2:
                    saltos.append(x[g == "PROVISIONAL"].mean() - x[g == "BETA"].mean())
                    fronteras += [b - a for a, b, ga, gb in zip(x[:-1], x[1:], g[:-1], g[1:]) if ga == "BETA" and gb == "PROVISIONAL"]
                    fronteras += [a - b for a, b, ga, gb in zip(x[:-1], x[1:], g[:-1], g[1:]) if ga == "PROVISIONAL" and gb == "BETA"]
                    cambios = sum(ga != gb for ga, gb in zip(g[:-1], g[1:]))
                    intercalado |= cambios > 1
            fila["mad_intercalado"] = bool(intercalado)
            if saltos:
                fila["mad_salto_db"] = float(np.mean(saltos))
                fila["mad_frontera_db"] = float(np.mean(fronteras)) if fronteras else np.nan
            if pasos:
                fila["mad_paso_tipico_db"] = float(np.median(pasos))
    return fila


def medir_predio(v, s, p):
    """A site's front variables with each measurement (rep80, prom80, m20 and prom20) and the addendum ones."""
    def ctx(paso, coh, k):
        eco, eco_hv = s["eco" + k], s["ecohv" + k]
        return {"paso": paso, "catalogo_px": v["cat80"] if paso == 80.0 else v["cat20"],
                "coh": np.stack(s[coh]["v"]), "fechas": np.array(s[coh]["fechas"]),
                "eco": np.stack(eco["v"]) if eco["v"] else None, "orbitas_eco": np.array(eco["orbitas"]),
                "eco_hv": np.stack(eco_hv["v"]) if eco_hv["v"] else None, "orbitas_eco_hv": np.array(eco_hv["orbitas"])}

    salida = {}
    for medicion, paso, k in (("rep80", 80.0, "80"), ("prom80", 80.0, "80p"), ("m20", 20.0, "20"), ("prom20", 20.0, "20p")):
        n = "80" if paso == 80.0 else "20"
        salida[medicion] = rf.medir(v["m" + n], ctx(paso, "coh" + n, k), v["agua" + n], p)
        if medicion != "prom20":
            salida[medicion].update(medir_extra(v["m" + n], v["agua" + n], v["cat" + n], paso, s["coh" + n], s["eco" + k], s["ecohv" + k], p,
                                                con_madurez=medicion == "rep80"))
    return salida


def _medir_frame(nombre):
    """Measures a frame's sites and leaves the frame's table in `datos/` (if it's already there, it's not repeated)."""
    warnings.filterwarnings("ignore")
    destino = os.path.join(DATOS, f"variables_{nombre}.parquet")
    if os.path.exists(destino):
        return destino
    e, p, filas = predios(), ins.Parametros(), []
    ids = list(e.loc[e["frame"] == nombre, "id_catalogo"])
    vs = ventanas_frame(nombre, ids)
    productos = cargar_frame(nombre)
    cubre = cobertura_frame(vs[ids[0]]["fr"], productos)
    for i in ids:
        s = _pilas(productos, i, cubre)
        if not s["coh80"]["v"] or not s["coh20"]["v"]:
            print(f"  {nombre} {i}: sin ventanas de coherencia, no se mide", flush=True)
            continue
        medidas = medir_predio(vs[i], s, p)
        # Addendum variant: the 80 m series without the dates on which the echo comes from frequency B. Where there are none, it's the replica.
        if any(m["tipo"] == "GCOV" and "frequencyB" in m["que_se_lee"]["datasets"]["eco80"]["ruta"] for m, _ in productos):
            sb = _pilas(productos, i, cubre, sin_b=True)
            ctx = {"paso": 80.0, "catalogo_px": vs[i]["cat80"], "coh": np.stack(sb["coh80"]["v"]), "fechas": np.array(sb["coh80"]["fechas"]),
                   "eco": np.stack(sb["eco80"]["v"]) if sb["eco80"]["v"] else None, "orbitas_eco": np.array(sb["eco80"]["orbitas"]),
                   "eco_hv": np.stack(sb["ecohv80"]["v"]) if sb["ecohv80"]["v"] else None, "orbitas_eco_hv": np.array(sb["ecohv80"]["orbitas"])}
            medidas["sinB80"] = rf.medir(vs[i]["m80"], ctx, vs[i]["agua80"], p)
        else:
            medidas["sinB80"] = {k: medidas["rep80"][k] for k in rf.NUEVAS + ["px", "px_anillo", "n_pares", "n_eco"]}
        for medicion, fila in medidas.items():
            filas.append({"id_catalogo": i, "frame": nombre, "medicion": medicion, **fila})
    pd.DataFrame(filas).to_parquet(destino + ".parcial", index=False)
    os.replace(destino + ".parcial", destino)
    print(f"{nombre}: {len(ids)} predios, {len(productos)} productos", flush=True)
    return destino


def cmd_medir(args):
    import concurrent.futures as cf
    import multiprocessing

    warnings.filterwarnings("ignore")
    nombres = [n for n in sorted(predios()["frame"].unique()) if not args.frame or n in [f.upper() for f in args.frame]]
    for vuelta in range(3):  # if the system kills a process, it continues with the remaining frames
        try:
            with cf.ProcessPoolExecutor(min(args.procesos, 4), mp_context=multiprocessing.get_context("spawn")) as ex:
                rutas = list(ex.map(_medir_frame, nombres))
            break
        except cf.process.BrokenProcessPool:
            if vuelta == 2:
                raise
            print("  El sistema mató un proceso: sigo con los frames que faltan", flush=True)
    t = pd.concat([pd.read_parquet(r) for r in rutas], ignore_index=True)
    t.to_parquet(args.variables, index=False)
    print(args.variables, len(t))


# ------------------------------------------------------------------ evaluar
def _auc(y, p):
    """AUC by ranks (ties averaged): gives the same as `roc_auc_score`, much faster for resampling."""
    from scipy.stats import rankdata

    n1 = y.sum()
    n0 = len(y) - n1
    if n1 == 0 or n0 == 0:
        return np.nan
    return float((rankdata(p)[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def _pareado(y, pa, pb, filtro=None):
    """AUC of b minus AUC of a, resampling the same sites for both. 95 % CI by percentiles."""
    idx = np.arange(len(y)) if filtro is None else np.nonzero(filtro)[0]
    rng, vals = np.random.default_rng(me.SEMILLA), []
    for _ in range(N_REMUESTREO):
        j = rng.choice(idx, len(idx))
        if 0 < y[j].sum() < len(j):
            vals.append(_auc(y[j], pb[j]) - _auc(y[j], pa[j]))
    vals = np.array(vals)
    lo, hi = np.percentile(vals, [2.5, 97.5])
    return {"diferencia": round(_auc(y[idx], pb[idx]) - _auc(y[idx], pa[idx]), 3), "ic95": [round(float(lo), 3), round(float(hi), 3)],
            "fraccion_remuestreos_mejora": round(float((vals > 0).mean()), 3)}


def _metas():
    """The metadata each product recorded when it was read."""
    salida = []
    for ruta in sorted(glob.glob(os.path.join(DATOS, "*", "*.npz"))):
        if not ruta.endswith(".parcial.npz"):
            with np.load(ruta) as d:
                salida.append({**json.loads(str(d["meta"])), "frame": os.path.basename(os.path.dirname(ruta)), "bytes_npz": os.path.getsize(ruta)})
    return salida


def _costo(metas):
    """Reading time and size per layer, summed from what each product recorded when it was read."""
    tot = {}
    productos = {"GUNW": 0, "GCOV": 0}
    abrir = {"GUNW": 0.0, "GCOV": 0.0}
    for m in metas:
        productos[m["tipo"]] += 1
        abrir[m["tipo"]] += m["s_abrir"]
        for clave, c in m["capas"].items():
            t = tot.setdefault(clave, {"s": 0.0, "bytes_comprimidos": 0, "px": 0, "bloques": 0, "productos": 0})
            for k in ("s", "bytes_comprimidos", "px", "bloques"):
                t[k] += c[k]
            t["productos"] += 1
    for t in tot.values():
        t["s"] = round(t["s"], 1)
        t["MB_comprimidos"] = round(t.pop("bytes_comprimidos") / 1e6, 1)
    return {"productos": productos, "s_abrir": {k: round(v, 1) for k, v in abrir.items()}, "por_capa": tot,
            "MB_en_disco_ventanas": round(sum(m["bytes_npz"] for m in metas) / 1e6, 1),
            "nota": "s = segundos de proceso sumados (la lectura corrió en paralelo); MB = bloques comprimidos de HDF5 que tocan las ventanas. "
                    "Las capas de un mismo dataset comparten bloques: la primera que se lee (nativo) carga con el tiempo y las otras salen de la caché"}


def _resumen_lectura(metas):
    """What the pipeline reads today: dataset, spacing, looks and maturity, counted over all the products read."""
    from collections import Counter

    def cuenta(valores):
        return dict(Counter(str(v) for v in valores).most_common())

    gcov = [m for m in metas if m["tipo"] == "GCOV"]
    gunw = [m for m in metas if m["tipo"] == "GUNW"]
    q = lambda m: m["que_se_lee"]  # noqa: E731
    looks = {}
    for m in gcov:
        if "numberOfLooks_ventana" in q(m):
            looks.setdefault(f"{abs(m['espaciado_gcov_m'][0]):g} m", []).append(q(m)["numberOfLooks_ventana"]["mediana"])
    rfi = [q(m)["rfiLikelihood_A"]["HH"] for m in gcov if q(m)["rfiLikelihood_A"]["HH"] is not None]
    por_frame = {}
    for m in metas:
        f = por_frame.setdefault(m["frame"], {"GCOV": Counter(), "GUNW": Counter(), "espaciado_gcov_m": Counter()})
        f[m["tipo"]][q(m)["madurez"]] += 1
        if m["tipo"] == "GCOV":
            f["espaciado_gcov_m"][f"{abs(m['espaciado_gcov_m'][0]):g}"] += 1
    return {
        "gcov": {"productos": len(gcov),
                 "dataset_que_elige_buscar_eco": cuenta(q(m)["datasets"]["eco80"]["ruta"] for m in gcov),
                 "dataset_cruzada": cuenta(q(m)["datasets"].get("ecohv80", {}).get("ruta") for m in gcov),
                 "espaciado_m_de_ese_dataset": cuenta(abs(m["espaciado_gcov_m"][0]) for m in gcov),
                 "frecuencias_del_producto_y_su_espaciado_m": cuenta(json.dumps(q(m)["frecuencias"]) for m in gcov),
                 "numberOfLooks_mediana_en_la_ventana_por_espaciado": {k: {"productos": len(v), "mediana": round(float(np.median(v)), 1),
                                                                         "min": round(float(np.min(v)), 1), "max": round(float(np.max(v)), 1)} for k, v in looks.items()},
                 "madurez_y_version": cuenta(f"{q(m)['madurez']} {q(m)['compositeReleaseId']} v{q(m)['productVersion']}" for m in gcov),
                 "rfiMitigationApplied": cuenta(q(m)["rfiMitigationApplied"] for m in gcov),
                 "rfiLikelihood_HH": {"productos": len(rfi), "entre_0_y_1": int(sum(0 <= r <= 1 for r in rfi)), "fuera_de_rango": int(sum(not (0 <= r <= 1) for r in rfi)),
                                      "mayor_a_0.1_entre_los_validos": int(sum(0.1 < r <= 1 for r in rfi))}},
        "gunw": {"productos": len(gunw),
                 "dataset_80m": cuenta(q(m)["datasets"]["coh80"]["ruta"] for m in gunw), "espaciado_80m": cuenta(abs(q(m)["datasets"]["coh80"]["espaciado_m"][0]) for m in gunw),
                 "dataset_20m": cuenta(q(m)["datasets"]["coh20"]["ruta"] for m in gunw), "espaciado_20m": cuenta(abs(q(m)["datasets"]["coh20"]["espaciado_m"][0]) for m in gunw),
                 "looks_rango_x_azimut_80m": cuenta(f"{q(m)['madurez']} {q(m)['compositeReleaseId']}: {q(m)['looks'][pl.CAPAS['80m'][0]]}" for m in gunw),
                 "looks_rango_x_azimut_20m": cuenta(f"{q(m)['madurez']} {q(m)['compositeReleaseId']}: {q(m)['looks'][pl.CAPAS['20m'][0]]}" for m in gunw),
                 "frecuencias": cuenta(q(m)["frecuencias"] for m in gunw),
                 "madurez_y_version": cuenta(f"{q(m)['madurez']} {q(m)['compositeReleaseId']} v{q(m)['productVersion']}" for m in gunw)},
        "por_frame": {k: {a: dict(b) for a, b in v.items()} for k, v in sorted(por_frame.items())},
        "frames_con_las_dos_madureces_en_gcov": sorted(k for k, v in por_frame.items() if len(v["GCOV"]) > 1),
        "frames_con_mas_de_un_espaciado_de_gcov": sorted(k for k, v in por_frame.items() if len(v["espaciado_gcov_m"]) > 1)}


def cmd_evaluar(args):
    from sklearn.model_selection import GroupKFold

    warnings.filterwarnings("ignore")
    e = predios()
    t = pd.read_parquet(args.variables)
    y, g = e["y"].values, e["frame"].values
    tablas = {"base": e[["id_catalogo"] + rf.NUEVAS].set_index("id_catalogo")}
    for medicion in MEDICIONES + ("prom20", "sinB80"):
        tablas[medicion] = t[t["medicion"] == medicion].set_index("id_catalogo").reindex(e["id_catalogo"])
    faltan = sorted(set(e["id_catalogo"]) - set(t["id_catalogo"]))
    terc = pd.qcut(e["area_ha"], 3, labels=["chicos", "medianos", "grandes"])
    cortes = [round(float(e.loc[terc == c, "area_ha"].max()), 1) for c in ("chicos", "medianos")]

    def evaluar(X):
        pred = me.fuera_de_frame(me.logistica, X, y, g)
        r = me.auc_ic(y, pred)
        p5 = np.full(len(y), np.nan)
        for tr, te in GroupKFold(n_splits=5).split(X, y, g):
            p5[te] = me.logistica().fit(X[tr], y[tr]).predict_proba(X[te])[:, 1]
        r["auc_5_grupos_de_frames"] = round(_auc(y, p5), 3)
        r["por_tercil"] = {c: me.auc_ic(y[(terc == c).values], pred[(terc == c).values]) for c in terc.cat.categories}
        return r, pred, p5

    def dif(pa, pb):
        return {"total": _pareado(y, pa, pb), **{c: _pareado(y, pa, pb, (terc == c).values) for c in terc.cat.categories}}

    metas = _metas()
    base, p_base, p5_base = evaluar(tablas["base"][rf.NUEVAS].values)
    salida = {"generado_por": "motor/prueba_resolucion.py evaluar",
              "fuentes": "NISAR L2 GUNW y GCOV (NASA/ISRO), vía ASF DAAC; agua: JRC Global Surface Water v1.4; estado y polígonos: data/catalogos/basurales",
              "muestras": {"n": int(len(e)), "abiertos": int(y.sum()), "cerrados": int((1 - y).sum()), "frames": int(e["frame"].nunique()),
                           "sin_medir": faltan, "cortes_terciles_ha": cortes,
                           "por_tercil": {c: {"n": int((terc == c).sum()), "abiertos": int(y[(terc == c).values].sum())} for c in terc.cat.categories}},
              "validacion": "regresión logística de modelo_estado.py; un frame afuera por vez; IC 95 % por remuestreo de predios (2000); "
                            "diferencias por remuestreo pareado de los mismos predios",
              "que_se_lee_hoy": _resumen_lectura(metas), "base_80m": base, "variantes": {}, "costo_lectura": _costo(metas)}
    print(f"{len(e)} predios ({int(y.sum())} abiertos, {int((1 - y).sum())} cerrados); sin medir: {len(faltan)}; terciles en {cortes} ha")
    print(f"  {'base 80 m (tabla original)':24s} AUC {base['auc']:.3f} {base['ic95']}  5 grupos {base['auc_5_grupos_de_frames']:.3f}  "
          f"terciles {[base['por_tercil'][c]['auc'] for c in terc.cat.categories]}")
    for nombre, v in VARIANTES.items():
        X = np.column_stack([tablas[v["eco"]][ECO].values, tablas[v["coh"]][COH].values])
        r, pred, p5 = evaluar(X)
        r["que"] = v["que"]
        r["faltantes_por_variable"] = {c: int(n) for c, n in zip(rf.NUEVAS, np.isnan(X).sum(0)) if n}
        r["diferencia_con_80m"] = {"total": _pareado(y, p_base, pred),
                                   **{c: _pareado(y, p_base, pred, (terc == c).values) for c in terc.cat.categories}}
        r["diferencia_con_80m_5_grupos"] = _pareado(y, p5_base, p5)
        # Each replaced variable, alone and in the direction of activity: 80 m versus the variant, same sites.
        solas = {}
        for c, col in zip(rf.NUEVAS, X.T):
            origen = v["eco"] if c in ECO else v["coh"]
            if origen == "base":
                continue
            b = tablas["base"][c].values
            ok = np.isfinite(col) & np.isfinite(b)
            sg = rf.SENTIDO_ACTIVIDAD[c]
            solas[c] = {"auc_80m": round(_auc(y[ok], sg * b[ok]), 3), "auc_variante": round(_auc(y[ok], sg * col[ok]), 3), "n": int(ok.sum()),
                        "auc_variante_por_tercil": [round(_auc(y[ok & (terc == k).values], sg * col[ok & (terc == k).values]), 2) for k in terc.cat.categories],
                        "auc_80m_por_tercil": [round(_auc(y[ok & (terc == k).values], sg * b[ok & (terc == k).values]), 2) for k in terc.cat.categories],
                        "correlacion_con_80m": round(float(np.corrcoef(col[ok], b[ok])[0, 1]), 3)}
        r["variables_solas"] = solas
        salida["variantes"][nombre] = r
        d = r["diferencia_con_80m"]
        print(f"  {nombre:24s} AUC {r['auc']:.3f} {r['ic95']}  5 grupos {r['auc_5_grupos_de_frames']:.3f}  "
              f"terciles {[r['por_tercil'][c]['auc'] for c in terc.cat.categories]}  "
              f"dif {d['total']['diferencia']:+.3f} {d['total']['ic95']}  dif terciles {[(d[c]['diferencia'], d[c]['ic95']) for c in terc.cat.categories]}")
    # Reading control: how many dates and pairs went into each site versus the original table.
    rep = tablas["rep80"]
    salida["control_replica"] = {
        "predios_con_otro_n_pares": int((rep["n_pares"].values != e["n_pares_frente"].values).sum()),
        "predios_con_otro_n_eco": int((rep["n_eco"].values != e["n_eco"].values).sum()),
        "correlacion_con_la_tabla_original": {c: round(float(pd.Series(rep[c].values).corr(pd.Series(tablas["base"][c].values))), 4) for c in rf.NUEVAS},
        "diferencia_absoluta_mediana": {c: round(float(np.nanmedian(np.abs(rep[c].values - tablas["base"][c].values))), 4) for c in rf.NUEVAS}}
    print("  control de la réplica:", salida["control_replica"])
    # ---- addendum 3: two other statistics of the echo's temporal variation, instead of the deviation
    salida["estadisticos_del_eco"] = {}
    for m_, etiqueta in MEDICIONES_QUE.items():
        X0 = np.column_stack([tablas[m_][ECO].values, tablas["base"][COH].values])
        r0, p0, _ = evaluar(X0)
        bloque = {"que": etiqueta, "desvio": {"auc": r0["auc"], "ic95": r0["ic95"], "por_tercil": {c: r0["por_tercil"][c]["auc"] for c in terc.cat.categories}}}
        for s_ in ESTADISTICOS:
            X = X0.copy()
            X[:, :3] = tablas[m_][EXTRA_ECO[s_]].values
            r, pred, _ = evaluar(X)
            solas = {}
            for c_std, c_nueva in zip(STD_ECO, EXTRA_ECO[s_]):
                a, b = tablas[m_][c_std].values, tablas[m_][c_nueva].values
                ok = np.isfinite(a) & np.isfinite(b)
                solas[c_nueva] = {"auc": round(_auc(y[ok], b[ok]), 3), "auc_del_desvio": round(_auc(y[ok], a[ok]), 3), "n": int(ok.sum()),
                                  "diferencia": _pareado(y, np.where(ok, a, 0.0), np.where(ok, b, 0.0), ok),
                                  "auc_por_tercil": [round(_auc(y[ok & (terc == k).values], b[ok & (terc == k).values]), 2) for k in terc.cat.categories]}
            bloque[s_] = {"que": ESTADISTICOS[s_], "auc": r["auc"], "ic95": r["ic95"], "auc_5_grupos_de_frames": r["auc_5_grupos_de_frames"],
                          "por_tercil": {c: r["por_tercil"][c]["auc"] for c in terc.cat.categories},
                          "diferencia_con_80m": dif(p_base, pred), "diferencia_con_el_desvio_a_esta_resolucion": dif(p0, pred), "variables_solas": solas}
            print(f"  eco {s_:5s} @ {m_:6s} AUC {r['auc']:.3f} {r['ic95']}  contra el desvío a esa resolución {bloque[s_]['diferencia_con_el_desvio_a_esta_resolucion']['total']}  "
                  f"solas {[(k, v_['auc'], v_['auc_del_desvio']) for k, v_ in solas.items()]}")
        salida["estadisticos_del_eco"][m_] = bloque
    # ---- addendum 5: pairs in which the pixel loses coherence and its echo also changes
    salida["coherencia_y_eco"] = {"definicion": f"por píxel, fracción de pares en que la coherencia queda por debajo de {ins.Parametros().razon} × la mediana del "
                                                f"anillo y además el cambio del eco HH entre las dos fechas del par (menos el del anillo) supera el percentil "
                                                f"{PERCENTIL_CAMBIO} del anillo en ese par; se resume como el parche de 3×3 con más fracción y el percentil 90 "
                                                f"del predio, menos la mediana del anillo"}
    for m_, etiqueta in MEDICIONES_QUE.items():
        cols = tablas[m_][COINCIDE].values
        solas = {}
        for c, col in zip(COINCIDE, cols.T):
            ok = np.isfinite(col)
            solas[c] = {**me.auc_ic(y[ok], col[ok]), "mediana_abiertos": round(float(np.nanmedian(col[y == 1])), 3), "mediana_cerrados": round(float(np.nanmedian(col[y == 0])), 3),
                        "auc_por_tercil": [round(_auc(y[ok & (terc == k).values], col[ok & (terc == k).values]), 2) for k in terc.cat.categories]}
        r, pred, _ = evaluar(np.column_stack([tablas["base"][rf.NUEVAS].values, cols]))
        salida["coherencia_y_eco"][m_] = {"que": etiqueta, "solas_mas_alto_mas_abierto": solas, "pares_usados_mediana": float(np.nanmedian(tablas[m_]["n_pares_coh_y_eco"])),
                                          "frente_80m_mas_estas_dos": {"auc": r["auc"], "ic95": r["ic95"], "auc_5_grupos_de_frames": r["auc_5_grupos_de_frames"],
                                                                       "por_tercil": {c: r["por_tercil"][c]["auc"] for c in terc.cat.categories},
                                                                       "diferencia_con_80m": dif(p_base, pred)}}
        print(f"  coh y eco @ {m_:6s} solas {[(k, v_['auc'], v_['ic95']) for k, v_ in solas.items()]}  frente + 2: AUC {r['auc']:.3f}  dif {dif(p_base, pred)['total']}")
    # ---- addendum 4: maturity (BETA and PROVISIONAL) and jump in the ring's mean echo
    mad = tablas["rep80"][MADUREZ].copy()
    mad["frame"] = g
    con = mad["mad_salto_db"].notna()
    salida["madurez"] = {
        "predios_con_las_dos_madureces_en_su_serie_de_eco": int(((mad["mad_n_beta"] > 0) & (mad["mad_n_prov"] > 0)).sum()),
        "predios_con_salto_medible": int(con.sum()),
        "predios_con_fechas_intercaladas": int(mad["mad_intercalado"].fillna(False).astype(bool).sum()),
        "salto_PROVISIONAL_menos_BETA_db": {"mediana": round(float(mad.loc[con, "mad_salto_db"].median()), 2), "mediana_del_valor_absoluto": round(float(mad.loc[con, "mad_salto_db"].abs().median()), 2),
                                            "p10": round(float(mad.loc[con, "mad_salto_db"].quantile(0.1)), 2), "p90": round(float(mad.loc[con, "mad_salto_db"].quantile(0.9)), 2)},
        "salto_en_la_frontera_db": {"mediana": round(float(mad["mad_frontera_db"].median()), 2), "mediana_del_valor_absoluto": round(float(mad["mad_frontera_db"].abs().median()), 2)},
        "paso_tipico_entre_fechas_seguidas_de_la_misma_madurez_db": round(float(mad["mad_paso_tipico_db"].median()), 2),
        "por_frame_mediana_del_salto_db": {k: round(float(v), 2) for k, v in mad[con].groupby("frame")["mad_salto_db"].median().items()},
        "nota": "eco HH medio del anillo (potencia lineal, en dB) por fecha y órbita, vecino más cercano de 80 m. Salto = media de las fechas PROVISIONAL "
                "menos media de las BETA, por órbita con 2 o más fechas de cada una. Frontera = diferencia entre dos fechas seguidas de distinta madurez."}
    print("  madurez:", {k: v for k, v in salida["madurez"].items() if k not in ("nota", "por_frame_mediana_del_salto_db")})
    extras = [c for cols in EXTRA_ECO.values() for c in cols] + COINCIDE
    salida["por_predio"] = [{"id_catalogo": i, "frame": f, "area_ha": round(float(a), 1), "y": int(yy),
                             **{f"{m}:{c}": (None if not np.isfinite(tablas[m].loc[i, c]) else round(float(tablas[m].loc[i, c]), 4))
                                for m in MEDICIONES + ("prom20",) for c in rf.NUEVAS + (extras if m != "prom20" else []) if i in tablas[m].index}}
                            for i, f, a, yy in zip(e["id_catalogo"], e["frame"], e["area_ha"], y)]
    with open(args.salida, "w", encoding="utf-8") as fh:
        json.dump(salida, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print(args.salida)


def main():
    q = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    q.add_argument("orden", choices=["preparar", "leer", "medir", "evaluar"])
    q.add_argument("--frame", nargs="+", help="only these frames (for `leer` and `medir`)")
    q.add_argument("--variables", default=os.path.join(DATOS, "variables.parquet"), help="intermediate table from `medir` (not committed)")
    q.add_argument("--procesos", type=int, default=12)
    q.add_argument("--salida", default=SALIDA_JSON)
    args = q.parse_args()
    {"preparar": cmd_preparar, "leer": cmd_leer, "medir": cmd_medir, "evaluar": cmd_evaluar}[args.orden](args)


if __name__ == "__main__":
    main()
