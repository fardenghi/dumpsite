"""Open-versus-closed model over the known-status dump sites, and what it learns.

Question: with what the radar (NISAR) and the optical data (Sentinel-2) measure over a site, can we tell whether the
registry lists it as open or closed? The labels are the registry's (`estado` in the catalog: EPA LMOP, OSM and curated
cases), they do **not** come from the insomnia. It trains on the dump sites of 10 ha or more in the processed frames,
except the AMBA, which is kept as a test. Then it predicts the ones without a status.

    python modelo_estado.py            # writes ../data/salidas/modelo_estado.json and ../data/salidas/predicciones_estado.parquet

Three families of variables per site:
- **front** (10): those of `radar_frente.py`, which look at the part of the site that changes most (per-pixel echo
  variation, the worst coherence patch). They come from `../data/salidas/radar_frente.parquet`.
- **optical** (8): Sentinel-2, site versus ring.
- **previous radar** (7): those of the whole site (insomnia, persistence, echo…), from `../data/salidas/insomnio_catalogo.parquet`.

**How the main model is chosen (fixed here, before looking at the AMBA):** from `CANDIDATOS`, which go from the simplest
to the most complex, the first one whose AUC (logistic regression, leaving one frame out at a time) is within `TOLERANCIA`
of the best of the three. None uses the site's area: in the registry the open ones are larger and that isn't activity.

What it reports:
- AUC leaving one frame out at a time (no site is predicted by a model that saw its frame), with a 95 % CI by
  resampling, and a control with 5 groups of frames (leaving out a single frame, the share of open sites in
  training moves opposite to that of the predicted frame, and that takes AUC away from weak models).
- Single-variable baselines.
- What the main model learns: standardized coefficients, AUC of each variable alone, how much the AUC drops when
  shuffling each variable, and the AUC within each area tercile (size control).
- The reserved AMBA test, with each candidate.

Inputs: `../data/salidas/insomnio_catalogo.parquet`, `../data/salidas/radar_frente.parquet` and the optical data from
`../data/salidas/optico_estado_conocido/` (prompt 7), `../data/salidas/tabla_optico_catalogo.parquet` (prompt 4) and
`../data/salidas/optico_catalogo_frames.parquet`. It's not a calibrated probability and the registry status may be
outdated.
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
from sklearn.model_selection import GroupKFold, LeaveOneGroupOut
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

AQUI = os.path.dirname(os.path.abspath(__file__))
SALIDAS = os.path.join(AQUI, "..", "data", "salidas")
MIN_HA = 10.0
PRUEBA = ("AMBA",)  # reserved: it goes into neither training nor validation
RADAR = ["insomnio", "persistencia", "eco_db", "contraste_p10", "eco_var_p90", "frac_insomnio_90", "hv_hh"]
OPTICO = ["ndvi_contraste", "bsi_contraste", "ndwi_contraste", "swir_b11_contraste", "swir_b12_contraste", "ndvi_media", "ndvi_variacion", "bsi_media"]
# The same as `radar_frente.NUEVAS` (repeated here to avoid loading the whole pipeline when training).
FRENTE = ["eco_std_rel_p90", "ecohv_std_rel_p90", "eco_std_rel_max3", "eco_cambio_rel_p90", "frente_coh_3x3", "frente_coh_fijo",
          "frente_vs_predio", "parche_bajo_ha", "parche_bajo_frac", "parche_se_mueve"]
AREA = ["log_ha"]
GRUPOS = {"frente": FRENTE, "óptico": OPTICO, "frente + óptico": FRENTE + OPTICO,
          "radar de antes": RADAR, "frente + radar de antes": FRENTE + RADAR, "óptico + radar de antes": OPTICO + RADAR,
          "frente + óptico + radar de antes": FRENTE + OPTICO + RADAR,
          "sólo área": AREA, "frente + área": FRENTE + AREA, "frente + óptico + área": FRENTE + OPTICO + AREA}
CANDIDATOS = ("frente", "frente + óptico", "frente + óptico + radar de antes")  # from the simplest to the most complex
TOLERANCIA = 0.02
# The "open" status of Norte III belongs to the complex (curated case, with an approximate coordinate) and in the catalog it got
# attached to `BAS-053304`, a vegetated sector (see ../docs/results.md). That's why the test includes, besides the
# individual polygons, the complex `CPX-015400` measured as a single unit (measured by `radar_frente.py`, `UNIDADES`).
PRUEBA_IDS = {"BAS-000007": "Basural de Luján",
              "CPX-015400": "Norte III, el complejo como una sola unidad (BAS-053304 + módulo C + BAS-016796)",
              "BAS-053304": "Norte III, polígono BAS-053304 (lleva el estado «abierto», que es del complejo)",
              "BAS-053307": "Norte III, módulo C (BAS-053307)", "BAS-016796": "Norte III, sector oeste sin nombre (BAS-016796)",
              "BAS-000001": "González Catán"}
ESTADO_UNIDADES = {"CPX-015400": "abierto"}  # the complex's, from the curated case AR-NORTE-III
UMBRAL = 0.5
SEMILLA = 0
ZONA_SECA = ("LOS_ANGELES", "USA_CA_SAN_BERNARDINO", "USA_CA_SAN_JOAQUIN", "USA_AZ_MARICOPA", "USA_CA_TULARE", "USA_CA_LOS_ANGELES", "USA_CA_RIVERSIDE")


def cargar():
    """One row per dump site of 10 ha or more in the frames, with radar, front, optical (the first available) and the label."""
    r = pd.read_parquet(os.path.join(SALIDAS, "insomnio_catalogo.parquet"))
    r = r[(r["catalogo"] == "basurales") & (r["area_ha"] >= MIN_HA)].drop_duplicates("id_catalogo").reset_index(drop=True)
    r["eco_db"] = r["eco_db"].clip(lower=-30)  # some sites have no echo (−75 dB): they're clipped so they don't dominate
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
    frente = os.path.join(SALIDAS, "radar_frente.parquet")
    if os.path.exists(frente):
        f = pd.read_parquet(frente)[["id_catalogo", "frame"] + FRENTE]
        d = d.merge(f.drop_duplicates(["id_catalogo", "frame"]), on=["id_catalogo", "frame"], how="left")
    else:
        d = d.assign(**{c: np.nan for c in FRENTE})
    d["y"] = np.where(d["estado"] == "abierto", 1.0, np.where(d["estado"] == "cerrado", 0.0, np.nan))
    return d


def logistica():
    return make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(C=0.5, max_iter=2000))


def arboles():
    return HistGradientBoostingClassifier(max_depth=3, max_iter=80, learning_rate=0.05, min_samples_leaf=8, random_state=SEMILLA)


def fuera_de_frame(modelo, X, y, g):
    """Prediction for each row with a model trained without its frame."""
    p = np.full(len(y), np.nan)
    for tr, te in LeaveOneGroupOut().split(X, y, g):
        m = modelo()
        m.fit(X[tr], y[tr])
        p[te] = m.predict_proba(X[te])[:, 1]
    return p


def en_5_grupos(modelo, X, y, g):
    """Control: 5 groups of frames instead of one frame at a time."""
    p = np.full(len(y), np.nan)
    for tr, te in GroupKFold(n_splits=5).split(X, y, g):
        p[te] = modelo().fit(X[tr], y[tr]).predict_proba(X[te])[:, 1]
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


def elegir_principal(auc):
    """The first candidate (from the simplest to the most complex) within `TOLERANCIA` of the best candidate."""
    mejor = max(auc[c]["auc"] for c in CANDIDATOS)
    return next(c for c in CANDIDATOS if auc[c]["auc"] >= mejor - TOLERANCIA)


def que_aprende(e, cols, p_base):
    """Coefficients, AUC per variable, permutation importance (leaving one frame out) and area control."""
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
        for _ in range(20):  # the variable is shuffled only in the frame being predicted
            p = np.full(len(y), np.nan)
            for tr, te in LeaveOneGroupOut().split(X, y, g):
                Xt = X[te].copy()
                Xt[:, j] = rng.permutation(Xt[:, j])
                p[te] = logistica().fit(X[tr], y[tr]).predict_proba(Xt)[:, 1]
            caidas.append(base - roc_auc_score(y, p))
        filas.append({"variable": c, "familia": "frente" if c in FRENTE else "óptico" if c in OPTICO else "radar de antes",
                      "coeficiente": round(float(coef[c]), 2),
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


def lectura(p):
    if p is None or not np.isfinite(p):
        return "sin dato"
    return "compatible con abierto" if p > UMBRAL else "compatible con cerrado"


def main():
    warnings.filterwarnings("ignore")
    d = cargar()
    e = d[d["y"].notna() & ~d["frame"].isin(PRUEBA)].reset_index(drop=True)  # training and validation
    sin_frente = e[FRENTE].isna().all(axis=1)
    if sin_frente.any():
        print(f"OJO: {int(sin_frente.sum())} predios con estado no tienen variables del frente (frames sin recortes medidos: "
              f"{sorted(e.loc[sin_frente, 'frame'].unique())}). Quedan afuera.")
        e = e[~sin_frente].reset_index(drop=True)
    y, g = e["y"].values, e["frame"].values
    print(f"{len(e)} basurales de estado conocido en {e['frame'].nunique()} frames ({int(y.sum())} abiertos y {int((1 - y).sum())} cerrados); "
          f"con óptico: {int(e['ndvi_contraste'].notna().sum())}")
    res, preds = {"logística": {}, "árboles": {}}, {}
    for nombre, cols in GRUPOS.items():
        X = e[cols].values
        p = fuera_de_frame(logistica, X, y, g)
        preds[nombre] = p
        res["logística"][nombre] = {**auc_ic(y, p), "auc_5_grupos_de_frames": round(float(roc_auc_score(y, en_5_grupos(logistica, X, y, g))), 3),
                                    "n_variables": len(cols)}
        res["árboles"][nombre] = auc_ic(y, fuera_de_frame(arboles, X, y, g))
        r = res["logística"][nombre]
        print(f"  {nombre:34s} logística {r['auc']:.3f} {r['ic95']} (5 grupos: {r['auc_5_grupos_de_frames']:.3f})   árboles {res['árboles'][nombre]['auc']:.3f}")
    principal = elegir_principal(res["logística"])
    print(f"\nModelo principal (criterio fijado de antemano, tolerancia {TOLERANCIA}): {principal}")
    bases = {}
    for c, signo in (("insomnio", 1), ("indice_actividad", 1), ("ndvi_contraste", -1), ("eco_std_rel_p90", 1)):
        bases[c] = {**auc_ic(y, signo * e[c].values), "sentido": "más alto = más abierto" if signo > 0 else "más bajo = más abierto"}
        print(f"  {c} sola: {bases[c]['auc']:.2f} {bases[c]['ic95']} ({bases[c]['sentido']}, n={bases[c]['n']})")
    p_base = preds[principal]
    variables, por_area = que_aprende(e, GRUPOS[principal], p_base)
    print(f"\nQué aprende ({principal}, logística):")
    for f in variables:
        print(f"  {f['variable']:20s} [{f['familia']}] coef {f['coeficiente']:+.2f} ({f['sentido']}); sola {f['auc_sola']:.2f}; al desordenarla el AUC baja {f['caida_auc_al_desordenar']:+.3f}")
    print("Por tercil de área:", [(t["tercil"], t["n"], t["abiertos"], t["auc"]) for t in por_area])
    acierta = {"abiertos": [int(((p_base > UMBRAL) & (y == 1)).sum()), int(y.sum())], "cerrados": [int(((p_base <= UMBRAL) & (y == 0)).sum()), int((y == 0).sum())]}
    seca = e["frame"].isin(ZONA_SECA).values
    por_zona = [{"zona": z, "n": int(m.sum()), "auc": round(float(roc_auc_score(y[m], p_base[m])), 3)} for z, m in (("California y Arizona", seca), ("resto", ~seca))]
    with open(os.path.join(AQUI, "..", "data", "catalogos", "frames.json"), encoding="utf-8") as fh:
        agregados = {f["frame"] for f in json.load(fh)["frames"] if f.get("criterio") == "abiertos"}
    viejos = ~e["frame"].isin(agregados)
    por_tanda = [{"frames": z, "n": int(m.sum()), "abiertos": int(y[m].sum()), "auc": round(float(roc_auc_score(y[m], p_base[m])), 3)}
                 for z, m in (("los 10 de antes", viejos.values), ("los 20 agregados", ~viejos.values)) if 0 < y[m].sum() < m.sum()]
    print(f"Con umbral {UMBRAL}: abiertos {acierta['abiertos']}, cerrados {acierta['cerrados']}; por zona: {por_zona}; por tanda: {por_tanda}")

    # Final model with all the known-status sites: it predicts the ones without status and the AMBA ones.
    cols = GRUPOS[principal]
    final = logistica().fit(e[cols].values, y)
    con_dato = ~d[FRENTE].isna().all(axis=1) if set(FRENTE) <= set(cols) else pd.Series(True, index=d.index)
    d["p_abierto"] = np.where(con_dato, final.predict_proba(d[cols].values)[:, 1], np.nan)
    d["origen"] = np.where(con_dato, "modelo final (no entró al entrenamiento)", "sin recortes de radar medidos")
    en = d["id_catalogo"].isin(e["id_catalogo"])
    d.loc[en, "p_abierto"] = d.loc[en, "id_catalogo"].map(dict(zip(e["id_catalogo"], p_base)))
    d.loc[en, "origen"] = "validación: modelo entrenado sin su frame"
    d["lectura"] = [lectura(p) for p in d["p_abierto"]]
    d["sin_optico"] = d["ndvi_contraste"].isna()
    salida_cols = ["id_catalogo", "frame", "nombre", "estado", "area_ha", "p_abierto", "lectura", "origen", "sin_optico", "radar", "insomnio",
                   "indice_actividad", "ndvi_contraste", "eco_std_rel_p90", "frente_vs_predio", "parche_bajo_frac"]
    d[salida_cols].sort_values(["frame", "p_abierto"], ascending=[True, False]).to_parquet(os.path.join(SALIDAS, "predicciones_estado.parquet"), index=False)

    # The reserved test (AMBA), with each candidate: it shows which part of the model gets it right or wrong there.
    prueba = d[d["id_catalogo"].isin(PRUEBA_IDS) & d["frame"].isin(PRUEBA)]
    # Complexes measured as a unit: they only have front variables (there's no optical or previous radar for the union).
    ruta_frente = os.path.join(SALIDAS, "radar_frente.parquet")
    if os.path.exists(ruta_frente):
        u = pd.read_parquet(ruta_frente)
        u = u[u["id_catalogo"].isin(ESTADO_UNIDADES)].copy()
        if len(u):
            u["estado"] = u["id_catalogo"].map(ESTADO_UNIDADES)
            u["p_abierto"] = final.predict_proba(u[cols].values)[:, 1] if set(cols) <= set(FRENTE) else np.nan
            prueba = pd.concat([prueba, u.reindex(columns=prueba.columns)], ignore_index=True)
    prueba = prueba.set_index("id_catalogo").reindex([i for i in PRUEBA_IDS if i in set(prueba["id_catalogo"])]).reset_index()
    prueba_por_grupo = []
    for nombre in dict.fromkeys(CANDIDATOS + ("óptico", "óptico + radar de antes")):
        m = logistica().fit(e[GRUPOS[nombre]].values, y)
        sueltos = prueba[~prueba["id_catalogo"].isin(ESTADO_UNIDADES) | (set(GRUPOS[nombre]) <= set(FRENTE))]
        for (_, f), pa in zip(sueltos.iterrows(), m.predict_proba(sueltos[GRUPOS[nombre]].values)[:, 1]):
            prueba_por_grupo.append({"variables": nombre, "id_catalogo": f["id_catalogo"], "nombre": PRUEBA_IDS[f["id_catalogo"]],
                                     "estado": f["estado"], "p_abierto": round(float(pa), 3)})
    medidas_prueba = prueba[["id_catalogo", "estado", "insomnio", "eco_std_rel_p90", "eco_std_rel_max3", "frente_vs_predio", "parche_bajo_frac",
                             "ndvi_contraste", "swir_b12_contraste"]].round(3).to_dict("records")
    sin = d[d["y"].isna()]
    salida = {
        "generado_por": "motor/modelo_estado.py",
        "pregunta": "con el radar y el óptico de un predio, ¿el registro lo da abierto o cerrado?",
        "etiquetas": "estado del registro (EPA LMOP, OSM, casos curados); no salen del insomnio y pueden estar desactualizadas",
        "muestras": {"n": int(len(e)), "abiertos": int(y.sum()), "cerrados": int((1 - y).sum()), "frames": int(e["frame"].nunique()),
                     "con_optico": int(e["ndvi_contraste"].notna().sum()), "prueba_reservada": list(PRUEBA)},
        "validacion": "un frame afuera por vez; IC 95 % por remuestreo de predios; control con 5 grupos de frames",
        "criterio_del_principal": (f"de {list(CANDIDATOS)}, del más simple al más complejo, el primero cuyo AUC (logística, un frame afuera) "
                                   f"no queda a más de {TOLERANCIA} del mejor de los tres; fijado antes de mirar el AMBA"),
        "modelo_principal": {"variables": principal, "lista": GRUPOS[principal], "tipo": "regresión logística (C = 0,5), faltantes con la mediana",
                             **res["logística"][principal]},
        "auc": res, "aciertos_con_umbral_0.5": acierta, "auc_por_zona": por_zona, "auc_por_tanda_de_frames": por_tanda,
        "lineas_de_base": bases, "variables": variables, "auc_por_tercil_de_area": por_area,
        "sin_estado": {"n": int(len(sin)), "con_p_abierto": int(sin["p_abierto"].notna().sum()), "p_abierto_mayor_0.5": int((sin["p_abierto"] > UMBRAL).sum())},
        "prueba": [{"id_catalogo": r["id_catalogo"], "nombre": PRUEBA_IDS[r["id_catalogo"]], "estado": r["estado"],
                    "p_abierto": None if pd.isna(r["p_abierto"]) else round(float(r["p_abierto"]), 3)} for _, r in prueba.iterrows()],
        "prueba_por_grupo_de_variables": prueba_por_grupo, "prueba_mediciones": medidas_prueba,
        "medianas_entrenamiento": {c: [round(float(e.loc[e["y"] == 1, c].median()), 3), round(float(e.loc[e["y"] == 0, c].median()), 3)]
                                   for c in ("insomnio", "eco_std_rel_p90", "eco_std_rel_max3", "frente_vs_predio", "parche_bajo_frac", "ndvi_contraste", "swir_b12_contraste")},
        "limites": ["casi todo EE. UU. (registro de la EPA)", "el estado es el del registro, no una observación de actividad",
                    "p_abierto no es una probabilidad calibrada", "en el registro los abiertos son más grandes: por eso el modelo no usa el área",
                    "en el AMBA la serie de radar es de cuatro meses y en EE. UU. de un año: la variación del eco no es del todo comparable"],
    }
    with open(os.path.join(SALIDAS, "modelo_estado.json"), "w", encoding="utf-8") as fh:
        json.dump(salida, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print(f"\nSin estado: {len(sin)} predios; con p_abierto: {salida['sin_estado']['con_p_abierto']}; mayor que {UMBRAL}: {salida['sin_estado']['p_abierto_mayor_0.5']}")
    print("Prueba reservada (modelo principal):", salida["prueba"])
    for f in prueba_por_grupo:
        print(f"  {f['variables']:34s} {f['nombre'][:40]:40s} registro: {f['estado']:12s} p_abierto {f['p_abierto']:.2f}")
    print("  mediciones:", medidas_prueba)
    print("  medianas en el entrenamiento [abiertos, cerrados]:", salida["medianas_entrenamiento"])


if __name__ == "__main__":
    sys.exit(main())
