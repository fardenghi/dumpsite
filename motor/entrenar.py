"""Etapa 7: LightGBM binario (`basural_activo` contra `otro_movil`) con validación cruzada por frame.

Lee `tabla_entrenamiento.parquet` y `particiones.json`; escribe `modelo.txt` y `metricas.json` y, si se le pasan las
tablas de todas las manchas candidatas, `predicciones.parquet` (según `idea/contratos-datos.md`).

    python entrenar.py                                      # lee y escribe en ../salidas/
    python entrenar.py --datos ../datos/mock --salida ../datos/mock/prueba --predecir
    python entrenar.py --datos ../datos/amba_provisional --humo   # pocas filas, un solo frame: sólo ver que corre

- Cada partición se predice con un modelo entrenado sin ella (fuera de la partición). Los frames de `prueba_final`
  (Argentina) no se usan para entrenar ni para elegir nada: se predicen con el modelo final, entrenado con todo lo demás.
- Peso por clase (`class_weight="balanced"`), árboles chicos y regularizados: hay pocas filas por frame.
- Por frame: AUC con intervalo bootstrap del 95 %, y precisión y recall con umbral 0,5 e intervalo de Wilson del 95 %.
- En qué clase de negativo se equivoca: fracción de cada `clase_negativo` que el modelo da como basural (≥ 0,5).
- Importancia de variables: ganancia del modelo final.
- `--humo`: si no hay al menos dos particiones (por ejemplo, sólo el AMBA), valida agrupando por complejo y avisa
  en `metricas.json` que **no es una métrica para reportar**.
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


def parametros(n_filas):
    import lightgbm as lgb  # noqa: F401  (falla temprano si no está)
    return dict(objective="binary", n_estimators=300, learning_rate=0.05, num_leaves=7, max_depth=3,
                min_child_samples=max(2, min(20, n_filas // 10)), subsample=0.8, subsample_freq=1, colsample_bytree=0.8,
                reg_lambda=1.0, class_weight="balanced", n_jobs=-1, random_state=SEMILLA, verbose=-1)


def columnas(t):
    cols = [c for c in contratos.COLUMNAS_MODELO if c in t.columns and t[c].notna().any()]
    if "cnn_p_basural" in t.columns and t["cnn_p_basural"].notna().any():
        cols.append("cnn_p_basural")
    return cols


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


# ------------------------------------------------------------------ métricas
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
    """{nombre: índices de prueba} y si es validación por frame o de humo."""
    por_frame = contratos.particion_por_frame(partes)
    ent = t[t["frame"].map(por_frame) != contratos.PRUEBA_FINAL]
    if len(partes.get("particiones", {})) >= 2:
        return {k: ent.index[ent["frame"].map(por_frame) == k] for k in partes["particiones"]}, ent, "por_frame"
    if not humo:
        raise SystemExit("Hacen falta al menos 2 particiones por frame para validar. Para probar con un solo frame: --humo")
    from sklearn.model_selection import StratifiedGroupKFold
    ent = t  # en humo se usa todo, también la prueba final
    y = (ent["clase"] == "basural_activo").astype(int)
    k = int(max(2, min(5, y.sum(), (1 - y).sum(), ent["complejo"].nunique())))
    if min(y.sum(), (1 - y).sum()) < 2:
        raise SystemExit(f"Muy pocas filas para probar: {y.value_counts().to_dict()}")
    sgk = StratifiedGroupKFold(n_splits=k, shuffle=True, random_state=SEMILLA)
    return {str(i): ent.index[te] for i, (_, te) in enumerate(sgk.split(ent, y, ent["complejo"]))}, ent, "humo_por_complejo"


def correr(t, partes, humo=False, todas=None):
    t = t.reset_index(drop=True)
    cols = columnas(t)
    y = (t["clase"] == "basural_activo").astype(int)
    grupos, ent, tipo = grupos_validacion(t, partes, humo)
    oof = pd.Series(np.nan, index=t.index)
    modelos = {}
    for k, idx in grupos.items():
        tr = ent.index.difference(idx)
        if len(set(y[tr])) < 2 or len(idx) == 0:
            modelos[k] = None
            continue
        modelos[k] = entrenar_uno(t.loc[tr, cols], y[tr])
        oof[idx] = predecir(modelos[k], t.loc[idx, cols])
    final = entrenar_uno(t.loc[ent.index, cols], y[ent.index])
    por_frame = contratos.particion_por_frame(partes)
    prueba = t.index[t["frame"].map(por_frame) == contratos.PRUEBA_FINAL] if tipo == "por_frame" else t.index[:0]
    p_prueba = pd.Series(predecir(final, t.loc[prueba, cols]), index=prueba)

    ok = oof.notna()
    imp = final.booster_.feature_importance(importance_type="gain")
    res = {
        "generado_por": "herramientas/entrenar.py",
        "validacion": tipo,
        "advertencia": None if tipo == "por_frame" else
        "PRUEBA DE HUMO: un solo frame o sin particiones por frame. Sirve para ver que corre. NO reportar estas métricas.",
        "umbral": UMBRAL, "columnas": cols, "parametros": {k: v for k, v in parametros(len(ent)).items() if k != "n_jobs"},
        "filas": {"entrenamiento": int(len(ent)), "prueba_final": int(len(prueba)),
                  "por_clase": t["clase"].value_counts().to_dict()},
        "fuera_de_particion": {"global": metricas(y[ok], oof[ok]) if ok.any() else None,
                               "por_particion": {k: metricas(y[idx], oof[idx]) for k, idx in grupos.items() if oof[idx].notna().all() and len(idx)},
                               "por_frame": {f: metricas(y[g.index], oof[g.index]) for f, g in t[ok].groupby("frame")}},
        "prueba_final": {f: metricas(y[g.index], p_prueba[g.index]) for f, g in t.loc[prueba].groupby("frame")},
        "errores_por_clase_negativo": errores_por_clase(t[ok], oof) if ok.any() else {},
        "importancia": {c: round(float(v), 2) for c, v in sorted(zip(cols, imp), key=lambda x: -x[1])},
    }
    pred = None
    if todas is not None:
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
    a.add_argument("--datos", default=os.path.join(AQUI, "..", "salidas"))
    a.add_argument("--tabla")
    a.add_argument("--particiones")
    a.add_argument("--salida", default=os.path.join(AQUI, "..", "salidas"))
    a.add_argument("--humo", action="store_true", help="permitir un solo frame (prueba de que corre; no reportar)")
    a.add_argument("--predecir", action="store_true",
                   help="escribir predicciones.parquet para todas las manchas candidatas (tabla_radar + tabla_optico de --datos)")
    args = a.parse_args()

    t = contratos.leer(args.tabla or contratos.ruta("tabla_entrenamiento", args.datos))
    with open(args.particiones or contratos.ruta("particiones", args.datos), encoding="utf-8") as fh:
        partes = json.load(fh)
    if len(partes.get("particiones", {})) >= 2:
        contratos.validar_particiones(partes, frames=sorted(set(t["frame"])))
    todas = None
    if args.predecir:
        radar = contratos.leer(contratos.ruta("tabla_radar", args.datos))
        optico = contratos.leer(contratos.ruta("tabla_optico", args.datos))
        todas = radar.merge(optico.drop(columns=["frame", "n_escenas", "fechas"]), on="id_mancha", how="left")

    final, res, pred = correr(t, partes, args.humo, todas)
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
