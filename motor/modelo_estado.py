"""Modelo de abierto contra cerrado sobre los basurales de estado conocido, y qué aprende.

Pregunta: con lo que miden el radar (NISAR) y el óptico (Sentinel-2) sobre un predio, ¿se puede decir si el registro
lo da abierto o cerrado? Las etiquetas son las del registro (`estado` del catálogo: EPA LMOP, OSM y casos curados),
**no** salen del insomnio. Se entrena con los basurales de 10 ha o más de los frames procesados, menos el AMBA, que
queda como prueba. Después se predice a los que no tienen estado.

    python modelo_estado.py            # escribe ../salidas/modelo_estado.json y ../salidas/predicciones_estado.parquet

Qué reporta:
- AUC dejando un frame afuera por vez (ningún predio se predice con un modelo que vio su frame), con IC 95 % por
  remuestreo, para cada grupo de variables: radar, óptico, radar + óptico, con y sin el área del predio, y el área sola.
- Líneas de base de una sola variable: insomnio, índice de actividad y `ndvi_contraste`.
- Qué aprende: coeficientes estandarizados de la regresión logística, AUC de cada variable sola con su sentido,
  cuánto baja el AUC al desordenar cada variable, y el AUC adentro de cada tercil de área (control por tamaño).

Entradas: `../salidas/insomnio_catalogo.parquet` (radar), y el óptico de `../salidas/optico_estado_conocido/`
(prompt 7), `../salidas/tabla_optico_catalogo.parquet` (prompt 4) y `../salidas/optico_catalogo_frames.parquet`.
No es una probabilidad calibrada y el estado del registro puede estar desactualizado.
"""
import glob
import json
import os
import sys
import warnings

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import LeaveOneGroupOut
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

AQUI = os.path.dirname(os.path.abspath(__file__))
SALIDAS = os.path.join(AQUI, "..", "salidas")
MIN_HA = 10.0
PRUEBA = ("AMBA",)  # reservado: no entra al entrenamiento ni a la validación
RADAR = ["insomnio", "persistencia", "eco_db", "contraste_p10", "eco_var_p90", "frac_insomnio_90", "hv_hh"]
OPTICO = ["ndvi_contraste", "bsi_contraste", "ndwi_contraste", "swir_b11_contraste", "swir_b12_contraste", "ndvi_media", "ndvi_variacion", "bsi_media"]
AREA = ["log_ha"]
GRUPOS = {"radar": RADAR, "óptico": OPTICO, "radar + óptico": RADAR + OPTICO, "radar + área": RADAR + AREA,
          "óptico + área": OPTICO + AREA, "radar + óptico + área": RADAR + OPTICO + AREA, "sólo área": AREA}
PRINCIPAL = "radar + óptico"  # sin el área: en el registro los abiertos son más grandes, y eso no es actividad
SEMILLA = 0
ZONA_SECA = ("LOS_ANGELES", "USA_CA_SAN_BERNARDINO", "USA_CA_SAN_JOAQUIN", "USA_AZ_MARICOPA", "USA_CA_TULARE", "USA_CA_LOS_ANGELES", "USA_CA_RIVERSIDE")


def cargar():
    """Una fila por basural de 10 ha o más de los frames, con radar, óptico (el primero que haya) y la etiqueta."""
    r = pd.read_parquet(os.path.join(SALIDAS, "insomnio_catalogo.parquet"))
    r = r[(r["catalogo"] == "basurales") & (r["area_ha"] >= MIN_HA)].drop_duplicates("id_catalogo").reset_index(drop=True)
    r["eco_db"] = r["eco_db"].clip(lower=-30)  # hay predios sin eco (−75 dB): se acotan para que no dominen
    r["frac_insomnio_90"] = r["ha_insomnio_90"] / r["area_ha"]
    r["log_ha"] = np.log10(r["area_ha"])
    fuentes = [("prompt 7", a) for a in sorted(glob.glob(os.path.join(SALIDAS, "optico_estado_conocido", "parte_*.parquet")))]
    fuentes += [("prompt 4", os.path.join(SALIDAS, "tabla_optico_catalogo.parquet")), ("optico_catalogo_frames", os.path.join(SALIDAS, "optico_catalogo_frames.parquet"))]
    partes = []
    for nombre, a in fuentes:
        if os.path.exists(a):
            t = pd.read_parquet(a)
            t = t[t["n_escenas"] > 0][["id_catalogo"] + OPTICO].copy()
            t["fuente_optico"] = nombre
            partes.append(t)
    o = pd.concat(partes).drop_duplicates("id_catalogo") if partes else pd.DataFrame(columns=["id_catalogo", "fuente_optico"] + OPTICO)
    d = r.merge(o, on="id_catalogo", how="left")
    d["y"] = np.where(d["estado"] == "abierto", 1.0, np.where(d["estado"] == "cerrado", 0.0, np.nan))
    return d


def logistica():
    return make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(C=0.5, max_iter=2000))


def arboles():
    return HistGradientBoostingClassifier(max_depth=3, max_iter=80, learning_rate=0.05, min_samples_leaf=8, random_state=SEMILLA)


def fuera_de_frame(modelo, X, y, g):
    """Predicción de cada fila con un modelo entrenado sin su frame."""
    p = np.full(len(y), np.nan)
    for tr, te in LeaveOneGroupOut().split(X, y, g):
        m = modelo()
        m.fit(X[tr], y[tr])
        p[te] = m.predict_proba(X[te])[:, 1]
    return p


def auc_ic(y, p, n=2000):
    ok = np.isfinite(p)
    y, p = y[ok], p[ok]
    rng, vals = np.random.default_rng(SEMILLA), []
    for _ in range(n):
        i = rng.integers(0, len(y), len(y))
        if 0 < y[i].sum() < len(i):
            vals.append(roc_auc_score(y[i], p[i]))
    lo, hi = np.percentile(vals, [2.5, 97.5])
    return {"auc": round(float(roc_auc_score(y, p)), 3), "ic95": [round(float(lo), 3), round(float(hi), 3)], "n": int(len(y)), "abiertos": int(y.sum())}


def que_aprende(e, cols, p_base):
    """Coeficientes, AUC por variable, importancia por desorden (dejando un frame afuera) y control por área."""
    X, y, g = e[cols].values, e["y"].values, e["frame"].values
    m = logistica().fit(X, y)
    coef = dict(zip(cols, m[-1].coef_[0]))
    base = roc_auc_score(y, p_base)
    rng, filas = np.random.default_rng(SEMILLA), []
    for j, c in enumerate(cols):
        v = e[c].values
        ok = np.isfinite(v)
        sola = roc_auc_score(y[ok], v[ok]) if 0 < y[ok].sum() < ok.sum() else np.nan
        caidas = []
        for _ in range(20):  # se desordena la variable sólo en el frame que se predice
            p = np.full(len(y), np.nan)
            for tr, te in LeaveOneGroupOut().split(X, y, g):
                Xt = X[te].copy()
                Xt[:, j] = rng.permutation(Xt[:, j])
                p[te] = logistica().fit(X[tr], y[tr]).predict_proba(Xt)[:, 1]
            caidas.append(base - roc_auc_score(y, p))
        filas.append({"variable": c, "coeficiente": round(float(coef[c]), 2),
                      "sentido": "más alto = más abierto" if coef[c] > 0 else "más alto = más cerrado",
                      "auc_sola": round(float(sola), 3), "caida_auc_al_desordenar": round(float(np.mean(caidas)), 3),
                      "faltantes": int((~ok).sum())})
    filas.sort(key=lambda f: -f["caida_auc_al_desordenar"])
    terciles = pd.qcut(e["area_ha"], 3, labels=["chicos", "medianos", "grandes"])
    por_area = []
    for t in terciles.cat.categories:
        s = (terciles == t).values
        por_area.append({"tercil": t, "ha": [round(float(e.loc[s, "area_ha"].min()), 1), round(float(e.loc[s, "area_ha"].max()), 1)],
                         "n": int(s.sum()), "abiertos": int(y[s].sum()),
                         "auc": round(float(roc_auc_score(y[s], p_base[s])), 3) if 0 < y[s].sum() < s.sum() else None})
    return filas, por_area


def main():
    warnings.filterwarnings("ignore")
    d = cargar()
    e = d[d["y"].notna() & ~d["frame"].isin(PRUEBA)].reset_index(drop=True)  # entrenamiento y validación
    y, g = e["y"].values, e["frame"].values
    print(f"{len(e)} basurales de estado conocido en {e['frame'].nunique()} frames ({int(y.sum())} abiertos y {int((1 - y).sum())} cerrados); "
          f"con óptico: {int(e['ndvi_contraste'].notna().sum())}")
    res, preds = {"logística": {}, "árboles": {}}, {}
    for nombre, cols in GRUPOS.items():
        for tipo, modelo in (("logística", logistica), ("árboles", arboles)):
            p = fuera_de_frame(modelo, e[cols].values, y, g)
            res[tipo][nombre] = auc_ic(y, p)
            preds[(tipo, nombre)] = p
        print(f"  {nombre:24s} logística {res['logística'][nombre]['auc']:.2f} {res['logística'][nombre]['ic95']}   árboles {res['árboles'][nombre]['auc']:.2f} {res['árboles'][nombre]['ic95']}")
    bases = {}
    for c, signo in (("insomnio", 1), ("indice_actividad", 1), ("ndvi_contraste", -1)):
        bases[c] = {**auc_ic(y, signo * e[c].values), "sentido": "más alto = más abierto" if signo > 0 else "más bajo = más abierto"}
        print(f"  {c} sola: {bases[c]['auc']:.2f} {bases[c]['ic95']} ({bases[c]['sentido']}, n={bases[c]['n']})")
    p_base = preds[("logística", PRINCIPAL)]
    variables, por_area = que_aprende(e, GRUPOS[PRINCIPAL], p_base)
    print(f"\nQué aprende ({PRINCIPAL}, logística):")
    for f in variables:
        print(f"  {f['variable']:20s} coef {f['coeficiente']:+.2f} ({f['sentido']}); sola {f['auc_sola']:.2f}; al desordenarla el AUC baja {f['caida_auc_al_desordenar']:+.3f}")
    print("Por tercil de área:", [(t["tercil"], t["n"], t["abiertos"], t["auc"]) for t in por_area])

    # Con el umbral de 0,5 y por zona (California y Arizona, secas, contra el resto), con las predicciones de la validación.
    acierta = {"abiertos": [int(((p_base > 0.5) & (y == 1)).sum()), int(y.sum())], "cerrados": [int(((p_base <= 0.5) & (y == 0)).sum()), int((y == 0).sum())]}
    seca = e["frame"].isin(ZONA_SECA).values
    por_zona = [{"zona": z, "n": int(m.sum()), "auc": round(float(roc_auc_score(y[m], p_base[m])), 3)} for z, m in (("California y Arizona", seca), ("resto", ~seca))]
    print(f"Con umbral 0,5: abiertos {acierta['abiertos']}, cerrados {acierta['cerrados']}; por zona: {por_zona}")

    # Modelo final con todos los de estado conocido: predice a los que no tienen estado y a los del AMBA.
    final = logistica().fit(e[GRUPOS[PRINCIPAL]].values, y)
    d["p_abierto"] = final.predict_proba(d[GRUPOS[PRINCIPAL]].values)[:, 1]
    d["origen"] = "modelo final (no entró al entrenamiento)"
    en = d["id_catalogo"].isin(e["id_catalogo"])
    d.loc[en, "p_abierto"] = d.loc[en, "id_catalogo"].map(dict(zip(e["id_catalogo"], p_base)))
    d.loc[en, "origen"] = "validación: modelo entrenado sin su frame"
    d["sin_optico"] = d["ndvi_contraste"].isna()
    cols = ["id_catalogo", "frame", "nombre", "estado", "area_ha", "p_abierto", "origen", "sin_optico", "radar", "insomnio", "indice_actividad", "ndvi_contraste"]
    d[cols].sort_values(["frame", "p_abierto"], ascending=[True, False]).to_parquet(os.path.join(SALIDAS, "predicciones_estado.parquet"), index=False)
    # La prueba reservada (AMBA), con cada grupo de variables por separado: muestra qué parte del modelo acierta o falla ahí.
    prueba = d[d["frame"].isin(PRUEBA) & d["y"].notna()]
    prueba_por_grupo = []
    for nombre in ("radar", "óptico", PRINCIPAL):
        m = logistica().fit(e[GRUPOS[nombre]].values, y)
        for (_, f), pa in zip(prueba.iterrows(), m.predict_proba(prueba[GRUPOS[nombre]].values)[:, 1]):
            prueba_por_grupo.append({"variables": nombre, "nombre": f["nombre"], "estado": f["estado"], "p_abierto": round(float(pa), 3)})
    medidas_prueba = prueba[["nombre", "estado", "insomnio", "contraste_p10", "eco_var_p90", "ndvi_contraste", "swir_b12_contraste"]].round(3).to_dict("records")
    sin = d[d["y"].isna()]
    salida = {
        "generado_por": "herramientas/modelo_estado.py",
        "pregunta": "con el radar y el óptico de un predio, ¿el registro lo da abierto o cerrado?",
        "etiquetas": "estado del registro (EPA LMOP, OSM, casos curados); no salen del insomnio y pueden estar desactualizadas",
        "muestras": {"n": int(len(e)), "abiertos": int(y.sum()), "cerrados": int((1 - y).sum()), "frames": int(e["frame"].nunique()),
                     "con_optico": int(e["ndvi_contraste"].notna().sum()), "prueba_reservada": list(PRUEBA)},
        "validacion": "un frame afuera por vez; IC 95 % por remuestreo de predios",
        "modelo_principal": {"variables": PRINCIPAL, "tipo": "regresión logística (C = 0,5), faltantes con la mediana"},
        "auc": res, "aciertos_con_umbral_0.5": acierta, "auc_por_zona": por_zona, "lineas_de_base": bases, "variables": variables, "auc_por_tercil_de_area": por_area,
        "sin_estado": {"n": int(len(sin)), "p_abierto_mayor_0.5": int((sin["p_abierto"] > 0.5).sum())},
        "prueba": d[d["frame"].isin(PRUEBA) & d["y"].notna()][["id_catalogo", "nombre", "estado", "p_abierto"]].round(3).to_dict("records"),
        "prueba_por_grupo_de_variables": prueba_por_grupo, "prueba_mediciones": medidas_prueba,
        "medianas_entrenamiento": {c: [round(float(e.loc[e["y"] == 1, c].median()), 3), round(float(e.loc[e["y"] == 0, c].median()), 3)]
                                   for c in ("insomnio", "contraste_p10", "eco_var_p90", "ndvi_contraste", "swir_b12_contraste")},
        "limites": ["casi todo EE. UU. (registro de la EPA)", "el estado es el del registro, no una observación de actividad",
                    "p_abierto no es una probabilidad calibrada", "en el registro los abiertos son más grandes: por eso el modelo principal no usa el área"],
    }
    with open(os.path.join(SALIDAS, "modelo_estado.json"), "w", encoding="utf-8") as fh:
        json.dump(salida, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print(f"\nSin estado: {len(sin)} predios; con p_abierto > 0,5: {int((sin['p_abierto'] > 0.5).sum())}")
    print("Prueba reservada:", salida["prueba"])
    for f in prueba_por_grupo:
        print(f"  {f['variables']:16s} {f['nombre'][:40]:40s} registro: {f['estado']:8s} p_abierto {f['p_abierto']:.2f}")
    print("  mediciones:", medidas_prueba)
    print("  medianas en el entrenamiento [abiertos, cerrados]:", salida["medianas_entrenamiento"])


if __name__ == "__main__":
    sys.exit(main())
