"""Prompt 4: the model side with real data, frame by frame (stages 5, 6 and 7 of `../docs/modelo.md`).

Stage 4 uploads one folder per frame, `salidas/<FRAME>/`, with `manchas.geojson`, `tabla_radar.parquet` and
`insomnio_catalogo.parquet`. This script goes through the frames in `../data/catalogos/frames.json` that already have it and, for each
one that's missing it (or whose `manchas.geojson` changed), runs:

  1. `cruce_manchas.py`  → `salidas/<FRAME>/cruce_manchas_catalogo.parquet` (seconds; the verdict needs it);
  2. `extraer_optico.py` → `salidas/<FRAME>/tabla_optico.parquet` and `tabla_optico_catalogo.parquet`, with the frame's
     dates (`fecha_inicio` and `fecha_fin` from `frames.json`) spread over the whole period.

Each file is validated with `contratos.py`. `salidas/<FRAME>/modelo_por_frame.json` records what was done and with which
`manchas.geojson` (its hash): if stage 4 uploads the frame again, it's redone.

    python modelo_por_frame.py                       # cross and optical for the missing frames, then `juntar`
    python modelo_por_frame.py --solo-cruce          # only the cross (to upload it right away)
    python modelo_por_frame.py --frame LOS_ANGELES   # only those frames (can be repeated)
    python modelo_por_frame.py --rehacer             # even if they're already done
    python modelo_por_frame.py juntar                # builds the three `salidas/` files with all the frames
    python modelo_por_frame.py tabla                 # radar of all frames → `armar_tabla.py` → `entrenar.py --predecir`
                                                     # (with the OSM negatives; --solo-catalogo gives the run 1 labels)
    python modelo_por_frame.py tabla --final         # same, and predicts the final test (Argentina). Only once, at the end
                                                     # (predicciones.parquet goes to salidas/ only if the model is validated)
    python modelo_por_frame.py variantes             # the run 2 label variants → salidas/metricas_variantes.json
    python modelo_por_frame.py estado                # what each frame has

`juntar` writes `salidas/cruce_manchas_catalogo.parquet`, `tabla_optico.parquet` and `tabla_optico_catalogo.parquet`.
The rows of a frame that doesn't have a folder yet (the AMBA from prompt 3, until `salidas/AMBA/` arrives) are
kept from the existing file.

`tabla` doesn't write `salidas/tabla_radar.parquet` or `salidas/manchas.geojson` (only prompt 1 uploads them): it joins the
radar of all frames in `datos/modelo/tabla_radar.parquet`, which isn't committed. If there's no `salidas/AMBA/`, the AMBA
radar is the provisional one from `tabla_radar_provisional.py` (without the columns that need the series) and it warns.

Sources: NISAR L2 GUNW and GCOV (NASA/ISRO, ASF DAAC) for the blobs; Copernicus Sentinel-2 L2A (ESA) via Microsoft
Planetary Computer; catalogs in `data/` (Overture Maps / © OpenStreetMap contributors, ODbL; EPA LMOP; Climate TRACE).
"""
import argparse
import glob
import hashlib
import json
import os
import subprocess
import sys
import time

import pandas as pd

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import catalogo_poligonos as cp  # noqa: E402
import contratos  # noqa: E402
import cruce_manchas as cm  # noqa: E402

RAIZ = os.path.dirname(AQUI)
SALIDAS = os.path.join(RAIZ, "data", "salidas")
FRAMES_JSON = os.path.join(RAIZ, "data", "catalogos", "frames.json")
DATOS_MODELO = os.path.join(AQUI, "datos", "modelo")
AMBA_PROVISIONAL = os.path.join(AQUI, "datos", "amba_provisional")
ESTADO = "modelo_por_frame.json"
JUNTOS = ("cruce_manchas_catalogo", "tabla_optico", "tabla_optico_catalogo")
NUBES = (20.0, 40.0, 70.0)  # % clouds of the whole scene: relaxed if there aren't enough dates


# ------------------------------------------------------------------ frames y estado
def leer_frames(camino=FRAMES_JSON):
    with open(camino, encoding="utf-8") as fh:
        return {f["frame"]: f for f in json.load(fh)["frames"]}


def hash_archivo(camino):
    h = hashlib.sha1()
    with open(camino, "rb") as fh:
        for bloque in iter(lambda: fh.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def carpeta_de(frame, base=SALIDAS):
    return os.path.join(base, frame)


def con_manchas(frames, base=SALIDAS):
    """Frames in `frames.json` that already have `<base>/<FRAME>/manchas.geojson`, in `frames.json` order."""
    return [f for f in frames if os.path.exists(os.path.join(carpeta_de(f, base), "manchas.geojson"))]


def leer_estado(carpeta):
    try:
        with open(os.path.join(carpeta, ESTADO), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def guardar_estado(carpeta, estado):
    with open(os.path.join(carpeta, ESTADO), "w", encoding="utf-8") as fh:
        json.dump(estado, fh, ensure_ascii=False, indent=1)


def falta(carpeta, paso, archivos, rehacer=False):
    """True if `paso` has to run: it wasn't done, `manchas.geojson` changed or one of its files is missing."""
    e = leer_estado(carpeta)
    hecho = e.get(paso) or {}
    if rehacer or hecho.get("manchas_sha1") != hash_archivo(os.path.join(carpeta, "manchas.geojson")):
        return True
    return any(not os.path.exists(os.path.join(carpeta, a)) for a in hecho.get("archivos", archivos))


def anotar(carpeta, paso, datos):
    e = leer_estado(carpeta)
    e["generado_por"] = "motor/modelo_por_frame.py"
    e[paso] = {"manchas_sha1": hash_archivo(os.path.join(carpeta, "manchas.geojson")), **datos}
    guardar_estado(carpeta, e)


def leer_manchas(carpeta):
    camino = os.path.join(carpeta, "manchas.geojson")
    contratos.leer(camino)  # valida
    with open(camino, encoding="utf-8") as fh:
        return json.load(fh)


# ------------------------------------------------------------------ steps per frame
def paso_cruce(frame, carpeta, avisar=print):
    fc = leer_manchas(carpeta)
    ms = cp.manchas(fc)
    if ms:
        df, n_pol = cm.cruzar_por_frame(ms, fc, cp.catalogo)
    else:
        df, n_pol = pd.DataFrame(columns=list(contratos.CONTRATOS["cruce_manchas_catalogo"].nombres) + ["inter_ha"]), 0
    destino = contratos.guardar(df, "cruce_manchas_catalogo", carpeta)
    ok = df[df["frac_area_menor"] >= contratos.CRITERIO_CRUCE]
    resumen = {"archivos": [os.path.basename(destino)], "manchas_candidatas": len(ms), "poligonos_en_la_caja": n_pol,
               "pares": int(len(df)), "manchas_que_pasan_el_criterio": int(ok["id_mancha"].nunique()),
               "con_basurales": int(ok[ok.catalogo == "basurales"]["id_mancha"].nunique()),
               "con_negativos": int(ok[ok.catalogo == "negativos"]["id_mancha"].nunique())}
    anotar(carpeta, "cruce", resumen)
    avisar(f"{frame}: cruce: {len(df)} pares de {df['id_mancha'].nunique()} manchas (de {len(ms)}) con {n_pol} polígonos; "
           f"pasan el {contratos.CRITERIO_CRUCE:.0%}: {resumen['con_basurales']} con basurales y {resumen['con_negativos']} con negativos")
    return df


def paso_optico(frame, info, carpeta, hilos=24, max_fechas=10, min_valido=0.6, cache=None, limite=None, avisar=print):
    import extraer_optico as eo  # here, so the cross doesn't need rasterio open or the network

    fc = leer_manchas(carpeta)
    o, s, e, n = info["bbox"]
    bbox = (o - 0.03, s - 0.03, e + 0.03, n + 0.03)
    poligonos = cp.catalogo(bbox)
    objetivos = [{"tipo": "mancha", "clave": p["id_mancha"], "frame": frame, "geom": g} for p, g in cp.manchas(fc)]
    objetivos += [{"tipo": "catalogo", "clave": p["id_catalogo"], "catalogo": p["catalogo"], "frame": frame, "geom": p["geom"]}
                  for p in poligonos]
    if limite:
        objetivos = objetivos[:limite]
    desde, hasta = info["fecha_inicio"], info["fecha_fin"]
    escenas, max_nube = [], NUBES[0]
    for max_nube in NUBES:
        escenas = eo.buscar_escenas(bbox, desde, hasta, max_nube)
        if len({x["fecha"] for x in escenas}) >= 2 * max_fechas:
            break
    fechas = sorted({x["fecha"] for x in escenas})
    avisar(f"{frame}: {len(escenas)} escenas L2A con menos de {max_nube:.0f} % de nubes entre {desde} y {hasta} ({len(fechas)} fechas)")
    t0 = time.time()
    res = eo.extraer(objetivos, escenas, [p["geom"] for p in poligonos], hilos=hilos, min_valido=min_valido,
                     max_fechas=max_fechas, cache=cache, avisar=avisar, periodo=(desde, hasta))
    filas_m = [{"id_mancha": x["clave"], "frame": frame, **r} for x, r in zip(objetivos, res) if x["tipo"] == "mancha"]
    filas_c = [{"id_catalogo": x["clave"], "catalogo": x["catalogo"], "frame": frame, **r}
               for x, r in zip(objetivos, res) if x["tipo"] == "catalogo"]
    resumen = {"archivos": [], "desde": desde, "hasta": hasta, "max_nube": max_nube, "escenas": len(escenas),
               "fechas_disponibles": len(fechas), "segundos": None, "fuente": "Copernicus Sentinel-2 L2A (ESA), vía Microsoft Planetary Computer"}
    for filas, nombre in ((filas_m, "tabla_optico"), (filas_c, "tabla_optico_catalogo")):
        if not filas:
            continue
        df = pd.DataFrame(filas)
        df["n_escenas"] = df["n_escenas"].astype("int64")
        destino = contratos.guardar(df, nombre, carpeta)
        resumen["archivos"].append(os.path.basename(destino))
        resumen[nombre] = {"filas": int(len(df)), "con_escenas": int((df.n_escenas > 0).sum()),
                           "escenas_mediana": float(df.n_escenas.median())}
        avisar(f"{frame}: {os.path.basename(destino)}: {len(df)} filas; con escenas: {(df.n_escenas > 0).sum()}; "
               f"escenas por fila: mediana {df.n_escenas.median():.0f}")
    resumen["segundos"] = round(time.time() - t0)
    if not limite:
        anotar(carpeta, "optico", resumen)
    return resumen


# ------------------------------------------------------------------ juntar
def juntar(base=SALIDAS, frames=None, avisar=print):
    """Builds the `base` files from each `<base>/<FRAME>/`. The rows of frames without a folder
    are kept from the previous file (the AMBA from prompt 3, until `salidas/AMBA/` arrives)."""
    escritos = {}
    for nombre in JUNTOS:
        archivo = os.path.basename(contratos.ruta(nombre, base))
        partes = []
        for camino in sorted(glob.glob(os.path.join(base, "*", archivo))):
            frame = os.path.basename(os.path.dirname(camino))
            if frames is None or frame in frames:
                partes.append(pd.read_parquet(camino))
        propios = {f for p in partes for f in p["frame"].unique()}
        anterior = contratos.ruta(nombre, base)
        if os.path.exists(anterior):
            viejo = pd.read_parquet(anterior)
            viejo = viejo[~viejo["frame"].isin(propios)]
            # a frame is kept only if it has no folder of its own with blobs (if it has one, the new data wins)
            viejo = viejo[[not os.path.exists(os.path.join(base, f, "manchas.geojson")) for f in viejo["frame"]]]
            if len(viejo):
                partes.append(viejo)
        partes = [p for p in partes if len(p)]
        if not partes:
            continue
        df = pd.concat(partes, ignore_index=True)
        destino = contratos.guardar(df, nombre, base)
        escritos[nombre] = df
        avisar(f"{os.path.relpath(destino, RAIZ)}: {len(df)} filas de {df['frame'].nunique()} frames "
               f"({', '.join(f'{f} {n}' for f, n in df['frame'].value_counts().sort_index().items())})")
    return escritos


# ------------------------------------------------------------------ tabla y entrenamiento
def radar_de_todos(base=SALIDAS, destino=DATOS_MODELO, avisar=print):
    """Joins the radar of all frames in `datos/modelo/tabla_radar.parquet` (not committed). Returns (path, warnings)."""
    partes = [pd.read_parquet(c) for c in sorted(glob.glob(os.path.join(base, "*", "tabla_radar.parquet")))]
    avisos = []
    if not os.path.exists(os.path.join(base, "AMBA", "tabla_radar.parquet")):
        prov = os.path.join(AMBA_PROVISIONAL, "tabla_radar.parquet")
        if not os.path.exists(prov):
            manchas = os.path.join(AMBA_PROVISIONAL, "manchas.geojson")
            subprocess.run([sys.executable, os.path.join(AQUI, "manchas_vectorizar.py"), "--salida", AMBA_PROVISIONAL], check=True)
            subprocess.run([sys.executable, os.path.join(AQUI, "tabla_radar_provisional.py"), "--manchas", manchas,
                            "--salida", AMBA_PROVISIONAL], check=True)
        partes.append(pd.read_parquet(prov))
        avisos.append("El radar del AMBA es el provisional de tabla_radar_provisional.py (sale del índice resumido: faltan "
                      "contraste_mediana, contraste_desvio, tendencia, eco_variacion, hv_hh, urbano_anillo y cultivo_anillo). "
                      "Se reemplaza cuando la etapa 4 suba salidas/AMBA/.")
    df = pd.concat(partes, ignore_index=True)
    os.makedirs(destino, exist_ok=True)
    ruta = contratos.guardar(df, "tabla_radar", destino)
    avisar(f"{os.path.relpath(ruta, RAIZ)}: {len(df)} manchas candidatas de {df['frame'].nunique()} frames (no se sube)")
    for a in avisos:
        avisar("AVISO: " + a)
    return ruta, avisos


def tabla_y_entrenar(base=SALIDAS, final=False, umbral_insomnio=None, publicar_sin_validar=False, extra_entrenar=(), avisar=print,
                     negativos_osm=True, positivos="todos"):
    """`armar_tabla.py` and `entrenar.py --predecir --controles` over all frames. The table, the partitions, the
    model and the metrics go to `base`. **`predicciones.parquet` goes to `base` only if the model is validated**
    (`validado` in `metricas.json`); otherwise it stays in `datos/modelo/` and the one in `base` is removed, so the verdict
    (prompt 5) leaves the blobs as `sin_clasificar` instead of classifying them with a model no better than chance."""
    import shutil
    radar, avisos = radar_de_todos(base, avisar=avisar)
    # one partition per frame (leave one frame out at a time): the validation is truly by frame
    armar = [sys.executable, os.path.join(AQUI, "armar_tabla.py"), "--datos", base, "--radar", radar, "--salida", base,
             "--particiones", "50"]
    if negativos_osm:  # since run 2: the OSM `uso_conocido` blobs go in as otro_movil
        armar.append("--negativos-osm")
    ia = os.path.join(base, "etiquetas_optico_ia.json")
    if os.path.exists(ia):
        armar += ["--etiquetas-optico", ia, "--positivos", positivos]
    if umbral_insomnio is not None:
        armar += ["--umbral-insomnio", str(umbral_insomnio)]
    subprocess.run(armar, check=True)
    entrenar = [sys.executable, os.path.join(AQUI, "entrenar.py"), "--datos", base, "--radar", radar, "--salida", DATOS_MODELO,
                "--predecir", "--controles"]
    if not final:
        entrenar.append("--reservar-prueba-final")
    for a in avisos:
        entrenar += ["--aviso", a]
    subprocess.run(entrenar + list(extra_entrenar), check=True)
    for archivo in ("modelo.txt", "metricas.json"):
        shutil.copyfile(os.path.join(DATOS_MODELO, archivo), os.path.join(base, archivo))
    with open(os.path.join(base, "metricas.json"), encoding="utf-8") as fh:
        validado = json.load(fh).get("validado", False)
    pred = contratos.ruta("predicciones", base)
    if validado or publicar_sin_validar:
        shutil.copyfile(contratos.ruta("predicciones", DATOS_MODELO), pred)
        avisar(f"{os.path.relpath(pred, RAIZ)}: publicado" + ("" if validado else " SIN VALIDAR (--publicar-sin-validar)"))
    else:
        if os.path.exists(pred):
            os.remove(pred)
        avisar(f"MODELO SIN VALIDAR: predicciones.parquet queda en {os.path.relpath(DATOS_MODELO, RAIZ)}/ y no en salidas/ "
               "(el veredicto deja las manchas sin catálogo como `sin_clasificar`). Ver metricas.json.")
    return validado


# ------------------------------------------------------------------ variantes de etiquetas (corrida 2)
# name: (options of `armar_tabla.armar`, what changes). All with the same partitions (one per frame).
VARIANTES = {
    "catalogo": (dict(), "La de la corrida 1: positivos y negativos de los catálogos."),
    "catalogo_y_osm": (dict(con_negativos_osm=True),
                       "Suma como otro_movil las manchas `uso_conocido` de OSM que no tocan ningún basural."),
    "osm_sin_los_sin": (dict(con_negativos_osm=True, positivos="sin_sin"),
                        "Ídem, y saca de basural_activo los basurales donde la IA no ve actividad en Sentinel-2 (`sin`)."),
    "osm_solo_act": (dict(con_negativos_osm=True, positivos="solo_act"),
                     "Ídem, y deja como basural_activo sólo los basurales donde la IA ve actividad (`act`)."),
}


def variantes(base=SALIDAS, avisar=print):
    """Trains and validates by frame each label variant. Each one stays whole in `datos/modelo/variantes/<nombre>/`
    (not committed) and the summary of all of them, in `<base>/metricas_variantes.json`. It doesn't touch the final test."""
    import armar_tabla as at
    import entrenar

    radar_ruta, avisos = radar_de_todos(base, avisar=avisar)
    radar = pd.read_parquet(radar_ruta)
    optico = contratos.leer(contratos.ruta("tabla_optico", base))
    cruce = contratos.leer(contratos.ruta("cruce_manchas_catalogo", base))
    frames = at.leer_frames(FRAMES_JSON)
    ia_ruta = os.path.join(base, "etiquetas_optico_ia.json")
    ia = at.leer_etiquetas_optico(ia_ruta) if os.path.exists(ia_ruta) else None
    todas = radar.drop(columns=[c for c in ("clase_osm", "que") if c in radar.columns]) \
                 .merge(optico.drop(columns=["frame", "n_escenas", "fechas"]), on="id_mancha", how="left")
    resumen = {"generado_por": "motor/modelo_por_frame.py variantes", "validacion": "una partición por frame (se deja un frame afuera por vez)",
               "prueba_final": "reservada: ninguna variante miró ni predijo la prueba final (Argentina)", "avisos": avisos,
               "etiquetas_optico": "salidas/etiquetas_optico_ia.json: las puso una IA en dos pasadas a ciegas y NO las revisó una persona",
               "negativos_osm": "manchas con clase_osm = uso_conocido (OSM vía Overture, etapa 4) que no tocan ningún basural del catálogo",
               "variantes": {}}
    for nombre, (opciones, que) in VARIANTES.items():
        if ia is None and opciones.get("positivos"):
            continue
        t, partes = at.armar(radar, optico, cruce, frames, k=50, optico_ia=ia, **opciones)
        destino = os.path.join(DATOS_MODELO, "variantes", nombre)
        os.makedirs(destino, exist_ok=True)
        contratos.guardar(t, "tabla_entrenamiento", destino)
        with open(contratos.ruta("particiones", destino), "w", encoding="utf-8") as fh:
            json.dump(partes, fh, ensure_ascii=False, indent=1)
        final, res, pred = entrenar.correr(t, partes, todas=todas.copy(), reservar=True, con_controles=True)
        final.booster_.save_model(os.path.join(destino, "modelo.txt"))
        with open(os.path.join(destino, "metricas.json"), "w", encoding="utf-8") as fh:
            json.dump(res, fh, ensure_ascii=False, indent=1)
        contratos.guardar(pred, "predicciones", destino)
        g, c = res["fuera_de_particion"]["global"], res.get("controles", {})
        resumen["variantes"][nombre] = {
            "que": que, "filas": res["filas"]["por_clase"], "filas_por_frame": res["filas"]["por_frame"],
            "positivos_sacados_por_el_optico": partes["meta"]["positivos_sacados_por_el_optico"],
            "validado": res["validado"], "por_que_no_esta_validado": res["por_que_no_esta_validado"],
            "global": g, "por_frame": res["fuera_de_particion"]["por_frame"],
            "auc_de_las_variantes_de_columnas": {k: {"auc": v["global"]["auc"], "auc_ic95": v["global"]["auc_ic95"]}
                                                 for k, v in (c.get("variantes") or {}).items()},
            "auc_de_area_ha_sola": (c.get("tamano") or {}).get("auc_de_area_ha_sola"),
            "diagnostico_mezclando_frames_no_reportar": (c.get("diagnostico_mezclando_frames") or {}).get("auc_media"),
            "errores_por_clase_negativo": res["errores_por_clase_negativo"], "mayores_errores": c.get("mayores_errores"),
            "importancia": dict(list(res["importancia"].items())[:10]),
            "manchas_sin_etiqueta_dadas_como_basural": None,
        }
        etiquetadas = set(t["id_mancha"])
        resto = pred[~pred["id_mancha"].isin(etiquetadas)]
        resumen["variantes"][nombre]["manchas_sin_etiqueta_dadas_como_basural"] = {
            "n": int(len(resto)), "p_basural_0_5_o_mas": int((resto["p_basural"] >= 0.5).sum())}
        avisar(f"{nombre}: {res['filas']['por_clase']} · AUC {g['auc']} {g['auc_ic95']} · precisión {g['precision']} {g['precision_ic95']} · "
               f"recall {g['recall']} {g['recall_ic95']} · validado: {res['validado']}")
    with open(os.path.join(base, "metricas_variantes.json"), "w", encoding="utf-8") as fh:
        json.dump(resumen, fh, ensure_ascii=False, indent=1)
    return resumen


# ------------------------------------------------------------------ estado
def estado(frames, base=SALIDAS):
    filas = []
    for f, info in frames.items():
        c = carpeta_de(f, base)
        if not os.path.exists(os.path.join(c, "manchas.geojson")):
            filas.append({"frame": f, "manchas": "falta (etapa 4)"})
            continue
        e = leer_estado(c)
        cr, op = e.get("cruce") or {}, e.get("optico") or {}
        filas.append({"frame": f, "manchas": cr.get("manchas_candidatas", "?"),
                      "cruce": "falta" if falta(c, "cruce", ["cruce_manchas_catalogo.parquet"]) else f"{cr.get('con_basurales')} bas / {cr.get('con_negativos')} neg",
                      "optico": "falta" if falta(c, "optico", ["tabla_optico.parquet"]) else
                      f"{(op.get('tabla_optico') or {}).get('con_escenas')} manchas con escenas, nubes < {op.get('max_nube'):.0f} %"})
    return pd.DataFrame(filas).fillna("")


def main():
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("paso", nargs="?", choices=["frames", "juntar", "tabla", "variantes", "estado"], default="frames")
    a.add_argument("--frame", action="append", help="only these frames (can be repeated); by default, all those with blobs")
    a.add_argument("--base", default=SALIDAS, help="folder with one subfolder per frame (default ../data/salidas)")
    a.add_argument("--solo-cruce", action="store_true", help="don't run the optical step")
    a.add_argument("--rehacer", action="store_true", help="run even if it's already done")
    a.add_argument("--sin-juntar", action="store_true")
    a.add_argument("--hilos", type=int, default=24)
    a.add_argument("--max-fechas", type=int, default=10, help="dates to read per cell, spread over the period (up to 8 are kept per geometry)")
    a.add_argument("--cache", help="folder to save the Sentinel-2 windows read (for example datos/s2); not committed")
    a.add_argument("--limite", type=int, help="measure only the first N geometries of each frame (for testing; not recorded)")
    a.add_argument("--final", action="store_true", help="`tabla`: also predict the final test (Argentina). Only once, at the end")
    a.add_argument("--umbral-insomnio", type=float, help="`tabla`: minimum blob insomnia to train (default 0.70)")
    a.add_argument("--solo-catalogo", action="store_true",
                   help="`tabla`: without the OSM negatives (the run 1 labels: catalogs only)")
    a.add_argument("--positivos", choices=("todos", "sin_sin", "solo_act"), default="todos",
                   help="`tabla`: which dump sites count as basural_activo according to the AI optical labels (see armar_tabla.py)")
    a.add_argument("--publicar-sin-validar", action="store_true",
                   help="`tabla`: write salidas/predicciones.parquet even if the model isn't validated (team decision)")
    args = a.parse_args()

    frames = leer_frames()
    if args.paso == "estado":
        print(estado(frames, args.base).to_string(index=False))
        return
    if args.paso == "juntar":
        juntar(args.base)
        return
    if args.paso == "variantes":
        variantes(args.base)
        return
    if args.paso == "tabla":
        tabla_y_entrenar(args.base, final=args.final, umbral_insomnio=args.umbral_insomnio, publicar_sin_validar=args.publicar_sin_validar,
                         negativos_osm=not args.solo_catalogo, positivos=args.positivos)
        return

    elegidos = [f for f in con_manchas(frames, args.base) if not args.frame or f in set(args.frame)]
    if not elegidos:
        sys.exit("No hay frames con manchas.geojson para procesar.")
    for f in elegidos:  # the cross for all of them first: it takes seconds and the verdict waits for it
        c = carpeta_de(f, args.base)
        if falta(c, "cruce", ["cruce_manchas_catalogo.parquet"], args.rehacer):
            paso_cruce(f, c)
    if not args.sin_juntar:
        juntar(args.base)
    if args.solo_cruce:
        return
    for f in elegidos:
        c = carpeta_de(f, args.base)
        if falta(c, "optico", ["tabla_optico.parquet"], args.rehacer) or args.limite:
            paso_optico(f, frames[f], c, hilos=args.hilos, max_fechas=args.max_fechas, cache=args.cache, limite=args.limite)
            if not args.sin_juntar and not args.limite:
                juntar(args.base)


if __name__ == "__main__":
    main()
