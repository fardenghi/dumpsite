"""Stage 7: binary LightGBM (`basural_activo` versus `otro_movil`) with cross-validation by frame.

Reads `tabla_entrenamiento.parquet` and `particiones.json`; writes `modelo.txt` and `metricas.json` and, if given the
tables of all the candidate blobs, `predicciones.parquet` (following `../docs/contratos-datos.md`).

    python entrenar.py                                      # reads and writes in ../data/salidas/
    python entrenar.py --datos datos/mock --salida datos/mock/prueba --predecir
    python entrenar.py --datos datos/amba_provisional --humo   # few rows, a single frame: just check that it runs

- Each partition is predicted by a model trained without it (out of partition). The `prueba_final` frames
  (Argentina) are used neither for training nor for choosing anything: they're predicted with the final model, trained on everything else.
- Class weights (`class_weight="balanced"`), small regularized trees: there are few rows per frame.
- Per frame: AUC with a 95 % bootstrap interval, and precision and recall with a 0.5 threshold and a 95 % Wilson interval.
- Which negative class it gets wrong: fraction of each `clase_negativo` that the model calls a dump site (≥ 0.5).
- Variable importance: gain of the final model.
- `--humo`: if there aren't at least two partitions (for example, only the AMBA), it validates grouping by complex and warns
  in `metricas.json` that **it's not a metric to report**.
- `n_pares` and `n_orbitas` don't go into the model: they're nearly constant per frame (they say how much data there is, not what the
  blob is) and with frames that only have one class they'd be a way of learning the frame. `--con-cantidad-de-datos` adds them.
- `contraste_p10` and `eco_var_p90` (stage 4, `../docs/indice-insomnio.md`) go into the model if the table carries them: they look at the
  most active part of the blob, not the median. They're not in the contract (`RADAR_NUEVAS`). `indice_actividad` doesn't go in: it was
  fitted with labels from an AI. `ha_insomnio_90` doesn't either: it's another size measure.
- `--controles` (prompt 4, part C): with the same partitions, it also trains without the Shape columns, with radar only,
  with optical only and with the amount of data; compares `area_ha` between classes (does it learn "big means dump site"?);
  checks that no column outside the contract goes in; and lists the ten largest errors.
- `validado` in `metricas.json`: true only if the validation is by frame, there are at least `MIN_FRAMES_VALIDOS` frames with
  `MIN_FILAS_CLASE` rows or more of each class, and the lower bound of the 95 % CI of the out-of-partition AUC is above 0.5.
  It's an assumption of this script (prompt 4). **If it's not validated, `p_basural` goes neither to the web nor to the pitch.**
- `--reservar-prueba-final`: doesn't look at the final test (Argentina): neither the metric nor the predictions. It's what's used
  while choosing the model; the final test is predicted only once, at the end, without this option.
"""
import argparse
import json
import math
import os
import sys
import warnings

import numpy as np
import pandas as pd

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import contratos  # noqa: E402

UMBRAL = 0.5
SEMILLA = 0
MIN_FRAMES_VALIDOS = 3  # frames outside the final test with both classes well populated
MIN_FILAS_CLASE = 5     # rows of each class for a frame to count


def validacion(tipo, t_ent, m_global):
    """(validated, criterion, reasons why not). The criterion is an assumption of this script."""
    criterio = (f"validación por frame, al menos {MIN_FRAMES_VALIDOS} frames con {MIN_FILAS_CLASE} filas o más de cada clase, "
                "y límite inferior del IC 95 % del AUC fuera de partición mayor que 0,5")
    motivos = []
    if tipo != "por_frame":
        motivos.append("no hay validación por frame (prueba de humo)")
    buenos = sorted(f for f, g in t_ent.groupby("frame") if g["clase"].value_counts().reindex(["basural_activo", "otro_movil"]).fillna(0).min() >= MIN_FILAS_CLASE)
    if len(buenos) < MIN_FRAMES_VALIDOS:
        motivos.append(f"sólo {len(buenos)} frame(s) con {MIN_FILAS_CLASE} filas o más de cada clase ({', '.join(buenos) or 'ninguno'}); hacen falta {MIN_FRAMES_VALIDOS}")
    ic = (m_global or {}).get("auc_ic95")
    if not ic or ic[0] <= 0.5:
        motivos.append(f"el AUC fuera de partición es {(m_global or {}).get('auc')} con IC 95 % {ic}: no se distingue del azar (0,5)")
    return not motivos, criterio, motivos


def parametros(n_filas):
    import lightgbm as lgb  # noqa: F401  (fails early if it's missing)
    return dict(objective="binary", n_estimators=300, learning_rate=0.05, num_leaves=7, max_depth=3,
                min_child_samples=max(2, min(20, n_filas // 10)), subsample=0.8, subsample_freq=1, colsample_bytree=0.8,
                reg_lambda=1.0, class_weight="balanced", n_jobs=-1, random_state=SEMILLA, verbose=-1)


CANTIDAD_DE_DATOS = ("n_pares", "n_orbitas")  # nearly constant per frame: they don't say what the blob is
RADAR_NUEVAS = ("contraste_p10", "eco_var_p90")  # the most active part of the blob (stage 4); outside the contract
GRUPOS = {"movimiento": tuple(c.nombre for c in contratos.MOVIMIENTO), "rugosidad": tuple(c.nombre for c in contratos.RUGOSIDAD),
          "optico": tuple(c.nombre for c in contratos.OPTICO), "forma": tuple(c.nombre for c in contratos.FORMA),
          "contexto": tuple(c.nombre for c in contratos.CONTEXTO)}
# What can never go in: it comes from the label or the registry (data leakage).
PROHIBIDAS = ("clase", "clase_negativo", "id_catalogo", "complejo", "estado", "catalogo", "frame", "ciudad", "pais", "p_basural",
              "actividad_optica", "indice_actividad", "clase_osm", "que")


def columnas(t, con_cantidad=False):
    cols = [c for c in contratos.COLUMNAS_MODELO if c in t.columns and t[c].notna().any()
            and (con_cantidad or c not in CANTIDAD_DE_DATOS)]
    cols += [c for c in RADAR_NUEVAS if c in t.columns and t[c].notna().any()]
    if "cnn_p_basural" in t.columns and t["cnn_p_basural"].notna().any():
        cols.append("cnn_p_basural")
    return cols


def revisar_fuga(cols):
    """Fails if a column outside the contract goes in, or one from EMIT, the registry or the label."""
    permitidas = set(contratos.COLUMNAS_MODELO) | {"cnn_p_basural"} | set(RADAR_NUEVAS)
    malas = [c for c in cols if c not in permitidas or c in PROHIBIDAS or "emit" in c.lower() or "metano" in c.lower()]
    if malas:
        raise SystemExit(f"Fuga de datos: estas columnas no pueden entrar al modelo: {malas}")
    return {"columnas_fuera_del_contrato": [], "emit_o_metano": [], "registro_o_etiqueta": [],
            "nota": "sólo entran columnas de contratos.COLUMNAS_MODELO (radar, óptico, forma y contexto) y RADAR_NUEVAS; "
                    "ni EMIT, ni el estado del catálogo, ni nada que salga de la etiqueta"}


def entrenar_uno(X, y):
    import lightgbm as lgb
    m = lgb.LGBMClassifier(**parametros(len(y)))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        m.fit(X, y)
    return m


def predecir(m, X):
    if m is None or len(X) == 0:
        return np.full(len(X), np.nan)
    return m.predict_proba(X)[:, 1]


# ------------------------------------------------------------------ metrics
def wilson(k, n, z=1.96):
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - r), 3), round(min(1.0, c + r), 3)]


def auc(y, p):
    from sklearn.metrics import roc_auc_score
    return float(roc_auc_score(y, p)) if len(set(y)) == 2 else None


def auc_ic(y, p, n=1000):
    y, p = np.asarray(y), np.asarray(p)
    if len(set(y)) < 2:
        return None
    rng = np.random.default_rng(SEMILLA)
    vals = []
    for _ in range(n):
        i = rng.integers(0, len(y), len(y))
        if len(set(y[i])) == 2:
            vals.append(auc(y[i], p[i]))
    return [round(float(np.percentile(vals, 2.5)), 3), round(float(np.percentile(vals, 97.5)), 3)] if vals else None


def metricas(y, p):
    y, p = np.asarray(y, dtype=int), np.asarray(p, dtype=float)
    pred = p >= UMBRAL
    vp, fp, fn = int((pred & (y == 1)).sum()), int((pred & (y == 0)).sum()), int((~pred & (y == 1)).sum())
    a = auc(y, p)
    return {
        "n": int(len(y)), "n_basural": int(y.sum()), "n_otro": int((y == 0).sum()),
        "auc": None if a is None else round(a, 3), "auc_ic95": auc_ic(y, p),
        "precision": None if vp + fp == 0 else round(vp / (vp + fp), 3), "precision_ic95": wilson(vp, vp + fp),
        "recall": None if vp + fn == 0 else round(vp / (vp + fn), 3), "recall_ic95": wilson(vp, vp + fn),
    }


def errores_por_clase(t, p):
    neg = t["clase"] == "otro_movil"
    salida = {}
    for c, g in t[neg].groupby(t.loc[neg, "clase_negativo"].fillna("sin_clase")):
        k, n = int((p[g.index] >= UMBRAL).sum()), len(g)
        salida[c] = {"n": n, "dados_como_basural": k, "fraccion": round(k / n, 3), "ic95": wilson(k, n)}
    return dict(sorted(salida.items(), key=lambda x: -x[1]["fraccion"]))


# ------------------------------------------------------------------ flujo
def grupos_validacion(t, partes, humo):
    """{name: test indices} and whether it's validation by frame or a smoke test."""
    por_frame = contratos.particion_por_frame(partes)
    ent = t[t["frame"].map(por_frame) != contratos.PRUEBA_FINAL]
    if len(partes.get("particiones", {})) >= 2:
        return {k: ent.index[ent["frame"].map(por_frame) == k] for k in partes["particiones"]}, ent, "por_frame"
    if not humo:
        raise SystemExit("Hacen falta al menos 2 particiones por frame para validar. Para probar con un solo frame: --humo")
    from sklearn.model_selection import StratifiedGroupKFold
    ent = t  # in a smoke test everything is used, including the final test
    y = (ent["clase"] == "basural_activo").astype(int)
    k = int(max(2, min(5, y.sum(), (1 - y).sum(), ent["complejo"].nunique())))
    if min(y.sum(), (1 - y).sum()) < 2:
        raise SystemExit(f"Muy pocas filas para probar: {y.value_counts().to_dict()}")
    sgk = StratifiedGroupKFold(n_splits=k, shuffle=True, random_state=SEMILLA)
    return {str(i): ent.index[te] for i, (_, te) in enumerate(sgk.split(ent, y, ent["complejo"]))}, ent, "humo_por_complejo"


def validar_fuera(t, y, cols, grupos, ent):
    """Prediction for each row with a model that didn't see it (by partition). Returns (series, models)."""
    oof = pd.Series(np.nan, index=t.index)
    modelos = {}
    for k, idx in grupos.items():
        tr = ent.index.difference(idx)
        if len(set(y[tr])) < 2 or len(idx) == 0:
            modelos[k] = None
            continue
        modelos[k] = entrenar_uno(t.loc[tr, cols], y[tr])
        oof[idx] = predecir(modelos[k], t.loc[idx, cols])
    return oof, modelos


def resumen_validacion(t, y, oof):
    ok = oof.notna()
    por_frame = {f: metricas(y[g.index], oof[g.index]) for f, g in t[ok].groupby("frame")}
    con_auc = [f for f, m in por_frame.items() if m["auc"] is not None]
    return {"global": metricas(y[ok], oof[ok]) if ok.any() else None, "por_frame": por_frame,
            "frames_con_las_dos_clases": con_auc}


def controles(t, y, grupos, ent, cols, oof):
    """Part C of prompt 4: size, leakage, contribution of the optical data and what it gets wrong."""
    from sklearn.metrics import roc_auc_score
    variantes = {
        "sin_forma": [c for c in cols if c not in GRUPOS["forma"]],
        "solo_radar": [c for c in cols if c not in GRUPOS["optico"] and c != "cnn_p_basural"],
        "solo_optico": [c for c in cols if c in GRUPOS["optico"]],
        "con_cantidad_de_datos": columnas(t, con_cantidad=True),
        "sin_columnas_nuevas": [c for c in cols if c not in RADAR_NUEVAS],
    }
    res_var = {"completo": {"columnas": len(cols), **{k: v for k, v in resumen_validacion(t, y, oof).items() if k != "por_frame"}}}
    for nombre, cs in variantes.items():
        if not cs or cs == cols:
            continue
        o, _ = validar_fuera(t, y, cs, grupos, ent)
        r = resumen_validacion(t, y, o)
        res_var[nombre] = {"columnas": len(cs), "global": r["global"],
                           "auc_por_frame": {f: m["auc"] for f, m in r["por_frame"].items() if m["auc"] is not None}}
    res_var["completo"]["auc_por_frame"] = {f: m["auc"] for f, m in resumen_validacion(t, y, oof)["por_frame"].items() if m["auc"] is not None}

    # do the variables separate anything? AUC of each one alone (far from 0.5 = it separates), over the training rows
    e = t.loc[ent.index]
    ye = y[ent.index]
    univariado = {}
    if len(set(ye)) == 2:
        for c in cols:
            ok_c = e[c].notna()
            if ok_c.sum() >= 10 and len(set(ye[ok_c])) == 2:
                univariado[c] = round(float(roc_auc_score(ye[ok_c], e.loc[ok_c, c])), 2)
        univariado = dict(sorted(univariado.items(), key=lambda x: -abs(x[1] - 0.5)))
    # Diagnostic, NOT a metric: validating with mixed frames (by complex). If it gives much more than by frame,
    # the model learns each frame's landscape and doesn't transfer.
    mezclado = None
    if min(ye.sum(), (1 - ye).sum()) >= 5:
        from sklearn.model_selection import StratifiedGroupKFold
        aucs = []
        for semilla in range(5):
            o = pd.Series(np.nan, index=e.index)
            for tr, te in StratifiedGroupKFold(5, shuffle=True, random_state=semilla).split(e, ye, e["complejo"]):
                o.iloc[te] = predecir(entrenar_uno(e.iloc[tr][cols], ye.iloc[tr]), e.iloc[te][cols])
            aucs.append(float(roc_auc_score(ye, o)))
        mezclado = {"auc_media": round(float(np.mean(aucs)), 3), "auc_por_semilla": [round(a, 3) for a in aucs],
                    "nota": "DIAGNÓSTICO, NO REPORTAR: validación mezclando frames, agrupando por complejo. Es optimista: el "
                            "modelo ve el paisaje de cada frame al entrenar, y en varios frames hay una sola clase."}
    area = {c: {k: round(float(v), 1) for k, v in g["area_ha"].describe()[["count", "min", "25%", "50%", "75%", "max"]].items()}
            for c, g in e.groupby("clase")}
    auc_area = float(roc_auc_score(ye, e["area_ha"])) if len(set(ye)) == 2 else None
    ok = oof.notna()
    err = (oof[ok] - y[ok]).abs().sort_values(ascending=False).head(10)
    mayores = [{"id_mancha": t.at[i, "id_mancha"], "frame": t.at[i, "frame"], "clase": t.at[i, "clase"],
                "clase_negativo": None if pd.isna(t.at[i, "clase_negativo"]) else t.at[i, "clase_negativo"],
                "id_catalogo": t.at[i, "id_catalogo"], "p_basural": round(float(oof[i]), 3), "area_ha": round(float(t.at[i, "area_ha"]), 1),
                "insomnio": round(float(t.at[i, "insomnio"]), 2)} for i in err.index]
    return {
        "variantes": res_var,
        "tamano": {"area_ha_por_clase": area, "auc_de_area_ha_sola": None if auc_area is None else round(auc_area, 3),
                   "nota": "auc_de_area_ha_sola es lo que separa el tamaño sin modelo: 0,5 quiere decir que no separa. "
                           "Si es alto y `sin_forma` rinde menos que `completo`, el modelo está aprendiendo el tamaño."},
        "fuga": revisar_fuga(cols),
        "auc_de_cada_variable_sola": univariado,
        "diagnostico_mezclando_frames": mezclado,
        "mayores_errores": mayores,
    }


def correr(t, partes, humo=False, todas=None, reservar=False, con_controles=False, con_cantidad=False):
    t = t.reset_index(drop=True)
    cols = columnas(t, con_cantidad)
    revisar_fuga(cols)
    y = (t["clase"] == "basural_activo").astype(int)
    grupos, ent, tipo = grupos_validacion(t, partes, humo)
    oof, modelos = validar_fuera(t, y, cols, grupos, ent)
    final = entrenar_uno(t.loc[ent.index, cols], y[ent.index])
    por_frame = contratos.particion_por_frame(partes)
    prueba = t.index[t["frame"].map(por_frame) == contratos.PRUEBA_FINAL] if tipo == "por_frame" and not reservar else t.index[:0]
    p_prueba = pd.Series(predecir(final, t.loc[prueba, cols]), index=prueba)

    ok = oof.notna()
    imp = final.booster_.feature_importance(importance_type="gain")
    res = {
        "generado_por": "motor/entrenar.py",
        "validacion": tipo,
        "advertencia": None if tipo == "por_frame" else
        "PRUEBA DE HUMO: un solo frame o sin particiones por frame. Sirve para ver que corre. NO reportar estas métricas.",
        "umbral": UMBRAL, "columnas": cols, "parametros": {k: v for k, v in parametros(len(ent)).items() if k != "n_jobs"},
        "filas": {"entrenamiento": int(len(ent)), "prueba_final": int(len(prueba)),
                  "por_clase": t.loc[ent.index, "clase"].value_counts().to_dict(),
                  "por_frame": {f: g["clase"].value_counts().to_dict() for f, g in t.loc[ent.index].groupby("frame")}},
        "frames_de_entrenamiento": sorted(set(t.loc[ent.index, "frame"])),
        "frames_con_las_dos_clases": sorted(f for f, g in t.loc[ent.index].groupby("frame") if g["clase"].nunique() == 2),
        "fuera_de_particion": {"global": metricas(y[ok], oof[ok]) if ok.any() else None,
                               "por_particion": {k: metricas(y[idx], oof[idx]) for k, idx in grupos.items() if oof[idx].notna().all() and len(idx)},
                               "por_frame": {f: metricas(y[g.index], oof[g.index]) for f, g in t[ok].groupby("frame")}},
        "prueba_final": "reservada: no se mira hasta el final (se predice una sola vez, con el modelo final)" if reservar else
        {f: metricas(y[g.index], p_prueba[g.index]) for f, g in t.loc[prueba].groupby("frame")},
        "errores_por_clase_negativo": errores_por_clase(t[ok], oof) if ok.any() else {},
        "importancia": {c: round(float(v), 2) for c, v in sorted(zip(cols, imp), key=lambda x: -x[1])},
    }
    res["validado"], res["criterio_validacion"], res["por_que_no_esta_validado"] = validacion(
        tipo, t.loc[ent.index], res["fuera_de_particion"]["global"])
    if not res["validado"]:
        res["advertencia"] = ((res["advertencia"] + " ") if res["advertencia"] else "") + \
            "MODELO SIN VALIDAR: p_basural no va a la web ni al pitch. " + "; ".join(res["por_que_no_esta_validado"]) + "."
    if con_controles and ok.any():
        res["controles"] = controles(t, y, grupos, ent, cols, oof)
    pred = None
    if todas is not None:
        if reservar:  # the final test isn't predicted until the end
            todas = todas[todas["frame"].map(por_frame) != contratos.PRUEBA_FINAL]
        todas = todas.reset_index(drop=True)
        for c in cols:
            if c not in todas.columns:
                todas[c] = np.nan
        part = todas["frame"].map(por_frame)
        p = predecir(final, todas[cols])
        if tipo == "por_frame":
            for k, m in modelos.items():
                sel = (part == k).to_numpy()
                if m is not None and sel.any():
                    p[sel] = predecir(m, todas.loc[sel, cols])
        pred = pd.DataFrame({"id_mancha": todas["id_mancha"], "frame": todas["frame"], "p_basural": np.clip(p, 0, 1)})
    return final, res, pred


def main():
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--datos", default=os.path.join(AQUI, "..", "data", "salidas"))
    a.add_argument("--tabla")
    a.add_argument("--particiones")
    a.add_argument("--salida", default=os.path.join(AQUI, "..", "data", "salidas"))
    a.add_argument("--humo", action="store_true", help="allow a single frame (test that it runs; don't report)")
    a.add_argument("--predecir", action="store_true",
                   help="write predicciones.parquet for all the candidate blobs (tabla_radar + tabla_optico from --datos)")
    a.add_argument("--radar", help="tabla_radar.parquet for --predecir (default: the one in --datos)")
    a.add_argument("--optico", help="tabla_optico.parquet for --predecir (default: the one in --datos)")
    a.add_argument("--controles", action="store_true", help="size, leakage, optical contribution and largest errors (see above)")
    a.add_argument("--reservar-prueba-final", action="store_true", help="don't look at or predict the final test (Argentina)")
    a.add_argument("--con-cantidad-de-datos", action="store_true", help="add n_pares and n_orbitas to the model")
    a.add_argument("--aviso", action="append", default=[], help="text noted in metricas.json (can be repeated)")
    args = a.parse_args()

    t = contratos.leer(args.tabla or contratos.ruta("tabla_entrenamiento", args.datos))
    with open(args.particiones or contratos.ruta("particiones", args.datos), encoding="utf-8") as fh:
        partes = json.load(fh)
    if len(partes.get("particiones", {})) >= 2:
        contratos.validar_particiones(partes, frames=sorted(set(t["frame"])))
    todas = None
    if args.predecir:
        radar = contratos.leer(args.radar or contratos.ruta("tabla_radar", args.datos))
        optico = contratos.leer(args.optico or contratos.ruta("tabla_optico", args.datos))
        todas = radar.merge(optico.drop(columns=["frame", "n_escenas", "fechas"]), on="id_mancha", how="left")

    if todas is not None:  # a frame in the predictions that's not in the partitions (no labeled rows) goes with the final model
        reservados = set(partes.get("prueba_final", []))
        frames_json = os.path.join(AQUI, "..", "data", "catalogos", "frames.json")
        if os.path.exists(frames_json):
            with open(frames_json, encoding="utf-8") as fh:
                reservados |= {f["frame"] for f in json.load(fh)["frames"] if f.get("reservado_prueba")}
        if args.reservar_prueba_final:
            todas = todas[~todas["frame"].isin(reservados)]
    final, res, pred = correr(t, partes, args.humo, todas, reservar=args.reservar_prueba_final,
                              con_controles=args.controles, con_cantidad=args.con_cantidad_de_datos)
    res["avisos"] = args.aviso
    os.makedirs(args.salida, exist_ok=True)
    final.booster_.save_model(os.path.join(args.salida, "modelo.txt"))
    with open(os.path.join(args.salida, "metricas.json"), "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1)
    if pred is not None:
        print(contratos.guardar(pred, "predicciones", args.salida))
    g = res["fuera_de_particion"]["global"] or {}
    if res["advertencia"]:
        print("AVISO:", res["advertencia"])
    print(f"Validación {res['validacion']}: {res['filas']} · AUC fuera de partición {g.get('auc')} {g.get('auc_ic95')} · "
          f"precisión {g.get('precision')} · recall {g.get('recall')}")
    print("Importancia:", list(res["importancia"])[:8])
    print(f"Escrito: {os.path.join(args.salida, 'modelo.txt')} y metricas.json")


if __name__ == "__main__":
    main()
