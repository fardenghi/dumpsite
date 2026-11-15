"""Sentinel-2 optical data for the dump sites of 10 ha or more in the frames that don't have it measured yet.

Fills in what the open-versus-closed model (`modelo_estado.py`) is missing: the dump sites of the frames
that are neither in `salidas/optico_estado_conocido/` (prompt 7, only the known-status ones) nor in
`salidas/tabla_optico_catalogo.parquet` (prompt 4, the original 10 frames). It measures the same thing in the same way as
`optico_estado_conocido.py`: it uses `extraer_optico.extraer()` unmodified, with the same period and ring.

    python optico_catalogo_frames.py preparar                      # builds datos/optico_frames/trabajo.json (offline)
    python optico_catalogo_frames.py correr                        # reads Sentinel-2 and writes ../data/salidas/optico_catalogo_frames.parquet
    python optico_catalogo_frames.py correr --trabajo t.json --salida s.parquet --hilos 16

`preparar` and `correr` are separate so the reading can run on another machine (the VM) without the catalogs:
the job carries each polygon to measure and the nearby catalog polygons (to remove them from the ring).

Data: Copernicus Sentinel-2 L2A (ESA), via Microsoft Planetary Computer. Catalog: see `../data/README.md`.
"""
import argparse
import glob
import json
import os
import sys
import time

import pandas as pd
import shapely

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
RAIZ = os.path.dirname(AQUI)
SALIDAS = os.path.join(RAIZ, "data", "salidas")
TRABAJO = os.path.join(AQUI, "datos", "optico_frames", "trabajo.json")
SALIDA = os.path.join(SALIDAS, "optico_catalogo_frames.parquet")
PERIODO = ("2025-10-21", "2026-10-21")  # the one from `optico_estado_conocido.py`
MIN_HA = 10.0
CERCA = 0.03  # degrees: what is kept around each polygon to remove it from its ring (1.5 km)


def ya_medidos():
    ids = set()
    for a in glob.glob(os.path.join(SALIDAS, "optico_estado_conocido", "parte_*.parquet")) + [os.path.join(SALIDAS, "tabla_optico_catalogo.parquet")]:
        if os.path.exists(a):
            ids |= set(pd.read_parquet(a, columns=["id_catalogo"])["id_catalogo"])
    return ids


def preparar(destino):
    import catalogo_poligonos as cp

    with open(os.path.join(RAIZ, "data", "catalogos", "frames.json"), encoding="utf-8") as fh:
        frames = json.load(fh)["frames"]
    hechos, trabajo = ya_medidos(), {}
    for f in frames:
        tabla = os.path.join(SALIDAS, f["frame"], "insomnio_catalogo.parquet")
        if not os.path.exists(tabla):
            continue
        t = pd.read_parquet(tabla)
        faltan = set(t[(t["catalogo"] == "basurales") & (t["area_ha"] >= MIN_HA) & ~t["id_catalogo"].isin(hechos)]["id_catalogo"])
        if not faltan:
            continue
        cat = cp.catalogo(f["bbox"])
        objetivos = [p for p in cat if p["id_catalogo"] in faltan]
        zona = shapely.union_all([shapely.box(*p["geom"].bounds).buffer(CERCA) for p in objetivos])
        cerca = [p["geom"] for p in cat if p["geom"].intersects(zona)]
        trabajo[f["frame"]] = {"objetivos": [{"id_catalogo": p["id_catalogo"], "wkt": shapely.to_wkt(p["geom"], rounding_precision=5)} for p in objetivos],
                               "excluir": [shapely.to_wkt(g, rounding_precision=5) for g in cerca]}
        print(f"{f['frame']}: {len(objetivos)} basurales a medir, {len(cerca)} polígonos de los catálogos cerca")
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    with open(destino, "w", encoding="utf-8") as fh:
        json.dump({"periodo": PERIODO, "min_ha": MIN_HA, "frames": trabajo}, fh)
    print(f"{destino}: {sum(len(v['objetivos']) for v in trabajo.values())} basurales en {len(trabajo)} frames, {os.path.getsize(destino) / 1e3:.0f} kB")


def correr(trabajo, salida, hilos):
    import catalogo_poligonos as cp
    import extraer_optico as eo

    with open(trabajo, encoding="utf-8") as fh:
        d = json.load(fh)
    periodo, filas, t0 = tuple(d["periodo"]), [], time.time()
    for frame, w in d["frames"].items():
        t1 = time.time()
        obj = [{"tipo": "catalogo", "clave": o["id_catalogo"], "catalogo": "basurales", "frame": frame, "geom": shapely.from_wkt(o["wkt"])} for o in w["objetivos"]]
        excluir = [shapely.from_wkt(x) for x in w["excluir"]]
        caja = cp.bbox_de([o["geom"] for o in obj], margen=CERCA)
        for i in range(4):  # the Planetary Computer search sometimes hangs
            try:
                escenas = eo.buscar_escenas(caja, *periodo, 20.0)
                break
            except Exception as e:  # noqa: BLE001
                if i == 3:
                    raise
                print(f"  {frame}: el buscador falló ({type(e).__name__}); reintento", flush=True)
                time.sleep(5 * (i + 1))
        res = eo.extraer(obj, escenas, excluir, hilos=hilos, max_fechas=10, periodo=periodo, avisar=lambda m: None)
        filas += [{"id_catalogo": o["clave"], "frame": frame, **r} for o, r in zip(obj, res)]
        print(f"OPTICO {frame}: {len(obj)} basurales, {len(escenas)} escenas, {time.time() - t1:.0f} s", flush=True)
    t = pd.DataFrame(filas)
    t.to_parquet(salida, index=False)
    print(f"OPTICO fin: {len(t)} basurales, {int((t['n_escenas'] > 0).sum())} con escenas, {time.time() - t0:.0f} s en total -> {salida}", flush=True)


def main():
    a = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    a.add_argument("orden", choices=["preparar", "correr"])
    a.add_argument("--trabajo", default=TRABAJO)
    a.add_argument("--salida", default=SALIDA)
    a.add_argument("--hilos", type=int, default=16, help="lecturas en paralelo")
    args = a.parse_args()
    if args.orden == "preparar":
        preparar(args.trabajo)
    else:
        correr(args.trabajo, args.salida, args.hilos)


if __name__ == "__main__":
    main()
