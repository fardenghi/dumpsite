"""Etapa 4, segunda dirección del cruce: el insomnio sobre CADA polígono del catálogo de un frame.

Lee el insomnio sobre cada basural (`data/catalogos/basurales/geometrias.geojson`) y cada negativo (`data/catalogos/negativos/`) que cae
en el frame, haya quedado o no en una mancha, y escribe `salidas/insomnio_catalogo.parquet` con el contrato de
`../docs/contratos-datos.md` (sección 3). Sin esto no hay "cerrado y quieto" para un basural que no formó mancha (Luján).

Dos modos:
  exacto      con los recortes por par (`salidas/recortes_80m/`): `insomnio.ficha()` por polígono, la misma serie
              par a par contra el anillo que usa el pipeline. Reproduce `salidas/fichas_80m.json`.
  aproximado  sólo con `salidas/indice_80m.npz` (como `cruce_catalogo.py`): mediana del insomnio y de la persistencia
              por píxel adentro del polígono. Sirve para probar sin los recortes; `motivo` lo dice.

    python insomnio_catalogo.py                     # exacto si están los recortes; si no, aproximado
    python insomnio_catalogo.py --modo aproximado
    python insomnio_catalogo.py --salida /tmp/x     # carpeta de salida (por defecto ../data/salidas)

Por ahora sólo el AMBA: `geo.py` tiene fija la grilla y la zona UTM 21 sur hasta que la etapa 1 la generalice.
Los recortes: `gs://basurales-514714-salidas/salidas-v3.tgz` (ver README).
"""
import argparse
import json
import os
import sys
import types
import warnings

import numpy as np
import pandas as pd

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
DATA = os.path.join(RAIZ, "data", "catalogos")
SALIDAS = os.path.join(RAIZ, "data", "salidas")
sys.path.insert(0, AQUI)
import contratos  # noqa: E402
import geo  # noqa: E402
import insomnio as ins  # noqa: E402

PASO = 80.0
MIN_HA = 10.0


# ---------------------------------------------------------------- polígonos
def anillos_exteriores(geometria):
    """Anillos exteriores (lon, lat) de un Polygon o MultiPolygon (como `cruce_catalogo.py`: sin agujeros)."""
    if not geometria:
        return []
    if geometria["type"] == "Polygon":
        return [geometria["coordinates"][0]]
    if geometria["type"] == "MultiPolygon":
        return [p[0] for p in geometria["coordinates"]]
    return []


def _en_grilla(anillos, xs, ys):
    lon, lat = np.array([q for a in anillos for q in a])[:, :2].T
    x, y = geo.utm(lat.mean(), lon.mean())
    return xs[0] <= x <= xs[-1] and ys[-1] <= y <= ys[0]


def poligonos_del_frame(xs, ys, frame="AMBA"):
    """Basurales y negativos con polígono cuyo centro cae en la grilla. Una entrada por polígono del catálogo."""
    with open(os.path.join(DATA, "basurales", "complejos.json"), encoding="utf-8") as fh:
        cx = json.load(fh)
    estado_cx = {c["id"]: c["estado"] for c in cx["complejos"]}
    salida = []
    with open(os.path.join(DATA, "basurales", "geometrias.geojson"), encoding="utf-8") as fh:
        for f in json.load(fh)["features"]:
            a = anillos_exteriores(f["geometry"])
            if not a or not _en_grilla(a, xs, ys):
                continue
            p = f["properties"]
            cpx = cx["complejo_por_sitio"].get(p["id"])
            salida.append({"id_catalogo": p["id"], "catalogo": "basurales", "complejo": cpx, "nombre": p.get("nombre"),
                           "area_ha": p.get("area_ha"), "estado": p.get("estado"), "estado_complejo": estado_cx.get(cpx),
                           "clase": None, "anillos": a})
    if frame != "AMBA":
        raise SystemExit("Fuera del AMBA hace falta la etapa 1 (geo.py por frame) y los negativos de geometrias_mundo.parquet.")
    with open(os.path.join(DATA, "negativos", "geometrias_amba.geojson"), encoding="utf-8") as fh:
        for f in json.load(fh)["features"]:
            a = anillos_exteriores(f["geometry"])
            if not a or not _en_grilla(a, xs, ys):
                continue
            p = f["properties"]
            salida.append({"id_catalogo": p["id"], "catalogo": "negativos", "complejo": None, "nombre": p.get("nombre"),
                           "area_ha": p.get("area_ha"), "estado": None, "estado_complejo": None, "clase": p.get("clase"),
                           "anillos": a})
    return salida


# ---------------------------------------------------------------- modos
def cargar_recortes(carpeta_salidas, orbitas=(10, 161)):
    """Los recortes por par con el mismo lector del pipeline (no se duplica la lógica)."""
    import pipeline_insomnio as pipe

    args = types.SimpleNamespace(salida=carpeta_salidas, capa="80m", orbitas=list(orbitas))
    ctx = pipe.cargar(args)
    p = ins.Parametros()
    agua = ins.mascara_agua(ctx["ocurrencia"], PASO, p)
    eco_db = ins.eco_medio(ctx["eco"], ctx["orbitas_eco"])
    return {"xs": ctx["xs"], "ys": ctx["ys"], "coh": ctx["coh"], "orbitas": ctx["orbitas"], "fechas": ctx["fechas"],
            "agua": agua, "eco_db": eco_db}


def medir_exacto(mascara, d, p):
    f = ins.ficha(mascara, d["coh"], d["orbitas"], d["fechas"], ~d["agua"], PASO, p, eco_db=d["eco_db"])
    return {"insomnio": f["insomnio"], "persistencia": f["persistencia"], "eco_db": f["eco_db"], "n_pares": len(f["pares"]),
            "radar": f["radar"], "motivo": f["motivo"], "px": f["px"], "px_anillo": f["px_anillo"]}


def cargar_indice(ruta):
    with np.load(ruta) as z:
        d = {k: z[k] for k in z.files if k in ("insomnio", "persistencia", "eco_db", "agua", "pares", "coherencia_media", "xs", "ys")}
    for k in ("insomnio", "persistencia", "eco_db", "coherencia_media"):
        d[k] = d[k].astype(np.float32)
    return d


def medir_aproximado(mascara, d, p):
    """Mediana por píxel (como cruce_catalogo.py) y los mismos umbrales que `insomnio.ficha()`."""
    adentro = mascara & ~d["agua"] & np.isfinite(d["insomnio"])
    n = int(adentro.sum())
    base = {"insomnio": None, "persistencia": None, "eco_db": None, "n_pares": 0, "px": n, "px_anillo": None}
    if n == 0:
        return {**base, "radar": "no_alcanza", "motivo": "aproximado: el predio es agua o queda fuera de la grilla"}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        i = float(np.median(d["insomnio"][adentro]))
        per = float(np.nanmedian(d["persistencia"][adentro]))
        e = d["eco_db"][adentro]
        eco = float(np.nanmedian(e)) if np.isfinite(e).any() else None
        aro = ins.anillo(mascara, ~d["agua"], PASO, p)
        coh_aro = float(np.nanmedian(d["coherencia_media"][aro])) if aro.any() else np.nan
    base.update(insomnio=round(i, 2), persistencia=round(per, 2), eco_db=None if eco is None else round(eco, 1),
                n_pares=int(np.median(d["pares"][adentro])), px_anillo=int(aro.sum()))
    if n < p.min_px_sitio:
        r, m = "no_alcanza", f"el predio ocupa {n} píxeles de {PASO:.0f} m: menos de {p.min_px_sitio}"
    elif eco is not None and eco < p.eco_min_db:
        r, m = "no_alcanza", f"superficie lisa (eco {eco:.1f} dB)"
    elif np.isfinite(coh_aro) and coh_aro < p.min_coh_anillo:
        r, m = "no_alcanza", "el entorno tampoco es coherente"
    elif i >= p.min_insomnio and per >= p.min_persistencia:
        r, m = "despierto", "insomnio y persistencia altos en el polígono"
    elif i >= p.min_insomnio:
        r, m = "no_alcanza", "despierto sólo en una parte de la serie"
    elif i <= p.max_quieto:
        r, m = "quieto", "insomnio bajo en el polígono"
    else:
        r, m = "no_alcanza", "señal intermedia: ni quieto ni despierto"
    return {**base, "radar": r, "motivo": "aproximado (mediana por píxel, sin recortes): " + m}


# ---------------------------------------------------------------- principal
def calcular(poligonos, d, medir, frame, p=None, min_ha=MIN_HA):
    p = p or ins.Parametros()
    filas = []
    for s in poligonos:
        mascara = geo.mascara_poligonos(s["anillos"], d["xs"], d["ys"])
        ha = s["area_ha"]
        if ha is None:
            ha = sum(geo.area_y_centro(a)[0] for a in s["anillos"])
        r = medir(mascara, d, p)
        if ha < min_ha:
            r = {**r, "radar": "no_alcanza", "motivo": f"el polígono mide {ha:.1f} ha: menos de {min_ha:g} ha"}
        filas.append({"id_catalogo": s["id_catalogo"], "catalogo": s["catalogo"], "complejo": s["complejo"], "frame": frame,
                      **r, "area_ha": float(ha), "estado": s["estado"], "clase": s["clase"], "nombre": s["nombre"],
                      "estado_complejo": s["estado_complejo"]})
    df = pd.DataFrame(filas)
    df["n_pares"] = df["n_pares"].astype("int64")
    for c in ("insomnio", "persistencia", "eco_db", "area_ha"):
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("float64")
    df["px"] = df["px"].astype("int64")
    df["px_anillo"] = pd.to_numeric(df["px_anillo"], errors="coerce").astype("Int64")
    return df


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--frame", default="AMBA")
    a.add_argument("--modo", choices=("auto", "exacto", "aproximado"), default="auto")
    a.add_argument("--recortes", default=SALIDAS, help="carpeta que tiene recortes_80m/ (la del pipeline)")
    a.add_argument("--indice", default=os.path.join(SALIDAS, "indice_80m.npz"))
    a.add_argument("--salida", default=SALIDAS)
    a.add_argument("--min-ha", type=float, default=MIN_HA)
    args = a.parse_args(argv)

    hay_recortes = os.path.isdir(os.path.join(args.recortes, "recortes_80m"))
    modo = args.modo if args.modo != "auto" else ("exacto" if hay_recortes else "aproximado")
    if modo == "exacto":
        d, medir = cargar_recortes(args.recortes), medir_exacto
    else:
        if args.modo == "auto":
            print("Sin recortes por par: modo aproximado (no reproduce fichas_80m.json; ver --help).", file=sys.stderr)
        d, medir = cargar_indice(args.indice), medir_aproximado
    poligonos = poligonos_del_frame(d["xs"], d["ys"], args.frame)
    df = calcular(poligonos, d, medir, args.frame, min_ha=args.min_ha)
    df["modo"] = modo
    ruta = contratos.guardar(df, "insomnio_catalogo", args.salida)
    cuenta = df.groupby(["catalogo", "radar"]).size().unstack(fill_value=0)
    print(f"{len(df)} polígonos ({modo}) -> {os.path.relpath(ruta)}\n{cuenta}")
    return df


if __name__ == "__main__":
    main()
