"""Predice con el modelo vigente, sin reentrenar, las manchas candidatas de uno o más frames (prompt 7, 15/11).

Carga `salidas/modelo.txt` como Booster de LightGBM y arma las variables igual que `entrenar.py --predecir`:
`tabla_radar.parquet` del frame unida con su `tabla_optico.parquet` por `id_mancha` (left join), con las columnas
de `salidas/metricas.json` en ese orden. Escribe `salidas/<FRAME>/predicciones.parquet` con `contratos.guardar`.

    python predecir_frames.py --frame ARG_ROSARIO ARG_CORDOBA

No toca `modelo.txt`, `metricas.json` ni `salidas/predicciones.parquet` (a diferencia de `modelo_por_frame.py tabla`,
que reentrena). El umbral es el de `metricas.json` (0,5).
"""
import argparse
import json
import os
import sys

import pandas as pd

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import contratos  # noqa: E402

SALIDAS = os.path.join(AQUI, "..", "salidas")


def predecir(frame, booster, cols, base=SALIDAS):
    carpeta = os.path.join(base, frame)
    radar = contratos.leer(os.path.join(carpeta, "tabla_radar.parquet"))
    optico = contratos.leer(os.path.join(carpeta, "tabla_optico.parquet"))
    t = radar.merge(optico.drop(columns=["frame", "n_escenas", "fechas"]), on="id_mancha", how="left")
    faltan = [c for c in cols if c not in t.columns]
    if faltan:
        raise SystemExit(f"{frame}: faltan columnas del modelo: {faltan}")
    X = t[cols].astype(float)
    pred = pd.DataFrame({"id_mancha": t["id_mancha"], "frame": t["frame"], "p_basural": booster.predict(X)})
    return contratos.guardar(pred, "predicciones", carpeta), pred


def main():
    import lightgbm as lgb
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--frame", nargs="+", required=True)
    a.add_argument("--base", default=SALIDAS)
    args = a.parse_args()
    with open(os.path.join(args.base, "metricas.json"), encoding="utf-8") as fh:
        met = json.load(fh)
    booster = lgb.Booster(model_file=os.path.join(args.base, "modelo.txt"))
    cols = met["columnas"]
    if booster.feature_name() != cols:
        raise SystemExit(f"Las columnas de modelo.txt no coinciden con las de metricas.json: {booster.feature_name()} vs {cols}")
    umbral = met.get("umbral", 0.5)
    for f in args.frame:
        ruta, pred = predecir(f, booster, cols, args.base)
        print(f"{f}: {len(pred)} manchas, {int((pred['p_basural'] >= umbral).sum())} con p_basural >= {umbral} -> {os.path.relpath(ruta)}")


if __name__ == "__main__":
    main()
