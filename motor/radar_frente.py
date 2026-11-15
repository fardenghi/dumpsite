"""Radar variables of a dump site's active front, and whether with them the radar tells open from closed.

Why: the insomnia in `insomnio_catalogo.parquet` is the median of the whole site against its ring, and an open
landfill has a small tipping front (1 % of the polygon) among cells already covered. Here, with the
per-pixel series of the same 80 m crops, we measure the part of the site that changes most.

    python radar_frente.py medir                          # the frames with crops in ../data/salidas/<FRAME>/recortes_80m
    python radar_frente.py medir --recortes /otra/carpeta # also crops read into another folder (AMBA: <carpeta>/recortes_80m)
    python radar_frente.py evaluar                        # compares with the 7 radar variables of `modelo_estado.py`

`medir` writes `../data/salidas/radar_frente.parquet` (one row per dump site of 10 ha or more and frame). `evaluar` writes
`../data/salidas/radar_frente_evaluacion.json`. It modifies nothing existing: it reads the crops with
`pipeline_insomnio.cargar()` and uses `insomnio.anillo()` (the same 1.5 km ring, without water or catalog polygons).

The variables (all against the site's ring, so weather and season cancel out):
  Echo (GCOV, dB), per pixel and within each orbit:
    eco_std_rel_p90     temporal deviation of the HH echo, 90th percentile of the site, minus the ring median
    ecohv_std_rel_p90   the same with the HV cross-polarized echo
    eco_std_rel_max3    the 3×3 pixel patch with the largest temporal deviation of the HH echo, minus the ring median
    eco_cambio_rel_p90  net change of the HH echo between the first and last third of the series, minus the ring's
                        (absolute value, 90th percentile of the site): a surface that ended up different, not one that oscillates
  Coherence (GUNW), ratio to the ring median in each pair:
    frente_coh_3x3      the worst 3×3 patch of each pair (it can be a different one in each pair), median across pairs
    frente_coh_fijo     the 3×3 patch that is consistently the worst (minimum of the median across pairs)
    frente_vs_predio    frente_coh_fijo over the site median: 1 = the site is even; low = there's a small
                        area much less coherent than the rest (what's expected of a front in a covered site)
    parche_bajo_ha      largest connected area with at least 70 % of the pairs below 0.8 × the ring (ha)
    parche_bajo_frac    that area as a fraction of the site
    parche_se_mueve     distance between the worst patch of the first third of the series and that of the last, over the
                        square root of the site's area
  Per-pixel insomnia (fraction of pairs in which the pixel falls below 0.8 × the ring median: the same
  rule as `insomnio.py`, but pixel by pixel instead of with the site median):
    insomnio_px_max3    the 3×3 patch with the most insomnia in the site
    insomnio_px_p95     95th percentile of the site's per-pixel insomnia
    parche_insomnio90_ha  largest connected area with per-pixel insomnia of 0.9 or more (ha)
    insomnio_parche_se_mueve  distance between the patch with the most insomnia in the first third and in the last (over the square root of the area)
    eco_std_en_parche   temporal deviation of the HH echo, minus the ring's, in the patch with the most insomnia: is the place that
                        is never coherent also a place where the echo changes?

The thresholds (0.8 and 70 %) are those of `insomnio.Parametros`, untouched. The variables were decided before looking at the AMBA.

Data: NISAR L2 GUNW and GCOV (NASA/ISRO), via ASF DAAC. Water: JRC Global Surface Water v1.4. Catalog: `../data/README.md`.
"""
import argparse
import glob
import json
import os
import sys
import warnings

import numpy as np
import pandas as pd
from scipy import ndimage

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import extraer_manchas as em  # noqa: E402
import geo  # noqa: E402
import insomnio as ins  # noqa: E402
import pipeline_insomnio as pl  # noqa: E402

RAIZ = os.path.dirname(AQUI)
SALIDAS = os.path.join(RAIZ, "data", "salidas")
TABLA = os.path.join(SALIDAS, "radar_frente.parquet")
EVALUACION = os.path.join(SALIDAS, "radar_frente_evaluacion.json")
MIN_HA = 10.0
ECO_SIN_SENAL_DB = -40.0  # below this GCOV carries no signal (some sites have −75 dB on some dates)
NUEVAS = ["eco_std_rel_p90", "ecohv_std_rel_p90", "eco_std_rel_max3", "eco_cambio_rel_p90", "frente_coh_3x3", "frente_coh_fijo",
          "frente_vs_predio", "parche_bajo_ha", "parche_bajo_frac", "parche_se_mueve"]
# Separate request: the maximum insomnia inside the polygon, per pixel, and its two combinations.
MAXIMO = ["insomnio_px_max3", "insomnio_px_p95", "parche_insomnio90_ha"]
COMBINA = ["insomnio_parche_se_mueve", "eco_std_en_parche"]
# Direction each variable would have if it measured activity (+1: higher = more open). Fixed here, before evaluating.
SENTIDO_ACTIVIDAD = {"eco_std_rel_p90": 1, "ecohv_std_rel_p90": 1, "eco_std_rel_max3": 1, "eco_cambio_rel_p90": 1, "frente_coh_3x3": -1,
                     "frente_coh_fijo": -1, "frente_vs_predio": -1, "parche_bajo_ha": 1, "parche_bajo_frac": 1, "parche_se_mueve": 1,
                     "insomnio_px_max3": 1, "insomnio_px_p95": 1, "parche_insomnio90_ha": 1, "insomnio_parche_se_mueve": 1, "eco_std_en_parche": 1}
# Complexes that are also measured as a single unit (the union of their polygons), for the AMBA test: in Norte III
# the "open" status belongs to the complex and got attached to a single polygon (see ../docs/results.md). They go into the table with the
# complex id; they're not catalog rows and don't go into training.
UNIDADES = {"AMBA": {"CPX-015400": ["BAS-053304", "BAS-053307", "BAS-016796"]}}
PRUEBA_AMBA = {"BAS-000007": "Basural de Luján (cerrado el 1/07/2026)", "BAS-053304": "Norte III, polígono con estado abierto",
               "BAS-053307": "Norte III, módulo C (sin estado)", "BAS-000001": "González Catán (sin estado)"}


# ------------------------------------------------------------------ medir
def media3(capa, adentro, min_px=5):
    """3×3 mean of `capa` (2D or a 3D stack) counting only site pixels with data; NaN where there are fewer than `min_px`."""
    ok = np.isfinite(capa) & adentro
    tam = (1, 3, 3) if capa.ndim == 3 else (3, 3)
    suma = ndimage.uniform_filter(np.where(ok, capa, 0.0).astype(np.float64), size=tam, mode="constant") * 9
    n = ndimage.uniform_filter(ok.astype(np.float64), size=tam, mode="constant") * 9
    with np.errstate(invalid="ignore", divide="ignore"):
        m = suma / n
    m[(n < min_px - 0.5) | ~np.broadcast_to(adentro, capa.shape)] = np.nan
    return m


def _std_por_orbita(pila, orbitas):
    """Per-pixel temporal deviation within each orbit (each one looks with another geometry), averaged across orbits."""
    partes = [np.nanstd(pila[orbitas == o], axis=0) for o in np.unique(orbitas) if (orbitas == o).sum() >= 3]
    return np.nanmean(np.stack(partes), axis=0) if partes else None


def _cambio_por_orbita(pila, orbitas):
    """Last third minus first third of the series, per pixel and per orbit (each orbit's dates come in order)."""
    partes = []
    for o in np.unique(orbitas):
        serie = pila[orbitas == o]
        if len(serie) >= 3:
            tercios = np.array_split(np.arange(len(serie)), 3)
            partes.append(np.nanmean(serie[tercios[2]], axis=0) - np.nanmean(serie[tercios[0]], axis=0))
    return partes


def medir(mascara, ctx, agua, p):
    """A site's front variables. `ctx` is the one from `pipeline_insomnio.cargar()`."""
    paso = ctx["paso"]
    v = em._ventana(mascara, int(round(p.anillo_m / paso)) + 1)
    m, tierra = mascara[v], ~agua[v]
    adentro = m & tierra
    aro = ins.anillo(m, tierra, paso, p, excluir=ctx["catalogo_px"][v])
    fila = {k: np.nan for k in NUEVAS + MAXIMO + COMBINA}
    std_hh = ref_hh = None
    fila.update(px=int(adentro.sum()), px_anillo=int(aro.sum()), n_pares=0, n_eco=0)
    if adentro.sum() < p.min_px_sitio or not aro.any():
        return fila
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        # ---- eco
        for clave, pila, orbitas in (("eco", ctx["eco"], ctx["orbitas_eco"]), ("ecohv", ctx.get("eco_hv"), ctx.get("orbitas_eco_hv"))):
            if pila is None:
                continue
            pila = pila[(slice(None),) + v]
            pila = np.where(pila < ECO_SIN_SENAL_DB, np.nan, pila)  # no signal: it's not a surface change
            std = _std_por_orbita(pila, np.asarray(orbitas))
            if std is None or not np.isfinite(std[adentro]).any() or not np.isfinite(std[aro]).any():
                continue
            ref = np.nanmedian(std[aro])
            fila[f"{clave}_std_rel_p90"] = float(np.nanpercentile(std[adentro], 90) - ref)
            if clave == "eco":
                fila["n_eco"] = int(len(pila))
                std_hh, ref_hh = std, ref
                fila["eco_std_rel_max3"] = float(np.nanmax(media3(std, adentro)) - ref) if np.isfinite(media3(std, adentro)).any() else np.nan
                cambios = [np.abs(c - np.nanmedian(c[aro])) for c in _cambio_por_orbita(pila, np.asarray(orbitas)) if np.isfinite(c[aro]).any()]
                if cambios:
                    fila["eco_cambio_rel_p90"] = float(np.nanpercentile(np.nanmean(np.stack(cambios), axis=0)[adentro], 90))
        # ---- coherence: ratio to the ring median, pair by pair
        coh = ctx["coh"][(slice(None),) + v]
        m_aro = np.nanmedian(coh[:, aro], axis=1)
        valido = np.isfinite(m_aro) & (m_aro > 0) & (np.isfinite(coh[:, adentro]).mean(axis=1) >= 0.5)
        if valido.sum() < 3:
            return fila
        orden = np.argsort(ctx["fechas"][valido], kind="stable")
        r = (coh[valido] / m_aro[valido, None, None])[orden]
        r[:, ~adentro] = np.nan
        fila["n_pares"] = int(len(r))
        r3 = media3(r, adentro)
        peor = np.nanmin(r3.reshape(len(r3), -1), axis=1)
        fila["frente_coh_3x3"] = float(np.nanmedian(peor))
        mediana = np.nanmedian(r, axis=0)
        fijo = media3(mediana, adentro)
        if np.isfinite(fijo).any():
            fila["frente_coh_fijo"] = float(np.nanmin(fijo))
            fila["frente_vs_predio"] = float(np.nanmin(fijo) / np.nanmedian(mediana[adentro]))
        bajo = np.nanmean(np.where(np.isfinite(r), r < p.razon, np.nan), axis=0)
        etq, _ = ndimage.label(adentro & (np.nan_to_num(bajo) >= p.min_insomnio))
        mayor = max(np.bincount(etq.ravel())[1:], default=0)
        fila["parche_bajo_ha"] = float(mayor * paso * paso / 1e4)
        fila["parche_bajo_frac"] = float(mayor / adentro.sum())
        # The maximum insomnia inside the polygon, per pixel.
        bajo3 = media3(bajo, adentro)
        if np.isfinite(bajo3).any():
            fila["insomnio_px_max3"] = float(np.nanmax(bajo3))
            fila["insomnio_px_p95"] = float(np.nanpercentile(bajo[adentro], 95))
            etq90, _ = ndimage.label(adentro & (np.nan_to_num(bajo) >= 0.9))
            fila["parche_insomnio90_ha"] = float(max(np.bincount(etq90.ravel())[1:], default=0) * paso * paso / 1e4)
            if std_hh is not None:
                std3 = media3(std_hh, adentro)
                en_parche = std3[np.unravel_index(np.nanargmax(bajo3), bajo3.shape)]
                fila["eco_std_en_parche"] = float(en_parche - ref_hh) if np.isfinite(en_parche) else np.nan
        tercios = np.array_split(np.arange(len(r)), 3)
        donde = []
        for t in (tercios[0], tercios[2]):
            mapa = media3(np.nanmean(np.where(np.isfinite(r[t]), r[t] < p.razon, np.nan), axis=0), adentro)
            donde.append(np.unravel_index(np.nanargmax(mapa), mapa.shape) if np.isfinite(mapa).any() else None)
        if donde[0] is not None and donde[1] is not None:
            fila["insomnio_parche_se_mueve"] = float(np.hypot(donde[0][0] - donde[1][0], donde[0][1] - donde[1][1]) / np.sqrt(adentro.sum()))
        lugares = []
        for t in (tercios[0], tercios[2]):
            mapa = media3(np.nanmean(r[t], axis=0), adentro)
            lugares.append(np.unravel_index(np.nanargmin(mapa), mapa.shape) if np.isfinite(mapa).any() else None)
        if lugares[0] is not None and lugares[1] is not None:
            fila["parche_se_mueve"] = float(np.hypot(lugares[0][0] - lugares[1][0], lugares[0][1] - lugares[1][1]) / np.sqrt(adentro.sum()))
    return fila


def medir_frame(a, p):
    ctx = pl.cargar(a)
    fr, xs, ys = ctx["fr"], ctx["xs"], ctx["ys"]
    agua = ins.mascara_agua(ctx["ocurrencia"], ctx["paso"], p)
    filas = []
    for s in ctx["catalogo"]:
        if s["catalogo"] != "basurales" or (s.get("area_ha") or 0) < MIN_HA:
            continue
        lon, lat = np.array([q for an in s["anillos"] for q in an], dtype=float)[:, :2].T
        if not fr.contiene(lat.mean(), lon.mean()):
            continue
        mascara = fr.mascara_poligonos(s["anillos"], xs, ys)
        if not mascara.any():
            continue
        filas.append({"id_catalogo": s["id"], "frame": fr.nombre, "area_ha": float(s["area_ha"]), **medir(mascara, ctx, agua, p)})
    for unidad, ids in UNIDADES.get(fr.nombre, {}).items():
        partes = [s for s in ctx["catalogo"] if s["id"] in ids]
        if len(partes) == len(ids):
            mascara = fr.mascara_poligonos([an for s in partes for an in s["anillos"]], xs, ys)
            filas.append({"id_catalogo": unidad, "frame": fr.nombre, "area_ha": float(sum(s["area_ha"] for s in partes)), **medir(mascara, ctx, agua, p)})
    return filas


def cmd_medir(args):
    p = ins.Parametros()
    bases = [SALIDAS] + (args.recortes or [])
    nombres = [n.upper() for n in args.frame] if args.frame else list(geo.frames_conocidos())
    filas = []
    for nombre in nombres:
        for base in bases:
            ns = argparse.Namespace(frame=[nombre], caja=None, epsg=None, datos="", salida=base, fijos=pl.FIJOS, web="", orbitas=None,
                                    desde=None, hasta=None, capa="80m", sin_catalogos=False)
            a = pl.preparar(ns, nombre)
            if glob.glob(os.path.join(a.salida, "recortes_80m", "gunw_*.npz")):
                f = medir_frame(a, p)
                filas += f
                print(f"{nombre}: {len(f)} basurales de {MIN_HA:g} ha o más ({os.path.relpath(a.salida)})", flush=True)
                break
        else:
            print(f"{nombre}: sin recortes en disco, no se mide")
    t = pd.DataFrame(filas)
    t.to_parquet(args.tabla, index=False)
    print(f"{args.tabla}: {len(t)} basurales de {t['frame'].nunique()} frames")


# ------------------------------------------------------------------ evaluar
def cmd_evaluar(args):
    import modelo_estado as me
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import GroupKFold

    warnings.filterwarnings("ignore")
    f = pd.read_parquet(args.tabla)
    d = me.cargar().merge(f[["id_catalogo"] + NUEVAS + MAXIMO + COMBINA + ["n_pares", "n_eco"]], on="id_catalogo", how="inner", suffixes=("", "_frente"))
    e = d[d["y"].notna() & ~d["frame"].isin(me.PRUEBA)].reset_index(drop=True)
    y, g = e["y"].values, e["frame"].values
    print(f"{len(e)} basurales de estado conocido con las variables nuevas, en {e['frame'].nunique()} frames "
          f"({int(y.sum())} abiertos y {int((1 - y).sum())} cerrados)")
    grupos = {"(a) radar actual (7)": me.RADAR, "(b) frente (10)": NUEVAS, "(c) radar actual + frente": me.RADAR + NUEVAS,
              "óptico (8)": me.OPTICO, "óptico + radar actual": me.OPTICO + me.RADAR, "óptico + frente": me.OPTICO + NUEVAS,
              "sólo área": me.AREA, "radar actual + área": me.RADAR + me.AREA, "frente + área": NUEVAS + me.AREA}
    auc, preds = {}, {}
    for nombre, cols in grupos.items():
        preds[nombre] = me.fuera_de_frame(me.logistica, e[cols].values, y, g)
        auc[nombre] = me.auc_ic(y, preds[nombre])
        # Control: 5 groups of frames instead of one frame at a time. Leaving one frame out, the share of open sites
        # in training moves opposite to that of the predicted frame, and that takes AUC away from weak models.
        p5 = np.full(len(y), np.nan)
        for tr, te in GroupKFold(n_splits=5).split(e[cols].values, y, g):
            p5[te] = me.logistica().fit(e[cols].values[tr], y[tr]).predict_proba(e[cols].values[te])[:, 1]
        auc[nombre]["auc_5_grupos_de_frames"] = round(float(roc_auc_score(y, p5)), 3)
        print(f"  {nombre:28s} AUC {auc[nombre]['auc']:.3f} {auc[nombre]['ic95']}   (con 5 grupos de frames: {auc[nombre]['auc_5_grupos_de_frames']:.3f})")
    # (d) each new variable alone, in the direction it would have if it measured activity
    solas = []
    for c in NUEVAS:
        ok = e[c].notna().values
        a = roc_auc_score(y[ok], SENTIDO_ACTIVIDAD[c] * e.loc[ok, c].values)
        solas.append({"variable": c, "si_midiera_actividad": "más alto = más abierto" if SENTIDO_ACTIVIDAD[c] > 0 else "más bajo = más abierto",
                      "auc_en_ese_sentido": round(float(a), 3), "n": int(ok.sum()),
                      "mediana_abiertos": round(float(e.loc[e["y"] == 1, c].median()), 3), "mediana_cerrados": round(float(e.loc[e["y"] == 0, c].median()), 3)})
    # Size control for each variable: a maximum or minimum over more pixels comes out more extreme just by chance, and in
    # the registry the open ones are larger. Correlation with the log of the area and AUC within each area tercile.
    terc = pd.qcut(e["area_ha"], 3, labels=False).values
    for s_ in solas:
        c = s_["variable"]
        ok = e[c].notna().values
        s_["correlacion_con_log_area"] = round(float(np.corrcoef(e.loc[ok, c], e.loc[ok, "log_ha"])[0, 1]), 2)
        s_["auc_por_tercil_de_area"] = [round(float(roc_auc_score(y[ok & (terc == t)], SENTIDO_ACTIVIDAD[c] * e.loc[ok & (terc == t), c].values)), 2)
                                        if 0 < y[ok & (terc == t)].sum() < (ok & (terc == t)).sum() else None for t in range(3)]
    # what model (b) learns: standardized coefficient and whether it matches the direction of activity
    m = me.logistica().fit(e[NUEVAS].values, y)
    for s, coef in zip(solas, m[-1].coef_[0]):
        s["coeficiente_b"] = round(float(coef), 2)
        s["coincide_con_actividad"] = bool(np.sign(coef) == SENTIDO_ACTIVIDAD[s["variable"]])
    solas.sort(key=lambda s: -abs(s["auc_en_ese_sentido"] - 0.5))
    print("\nCada variable nueva sola (AUC en el sentido de la actividad; menos de 0,5 = ordena al revés):")
    for s in solas:
        print(f"  {s['variable']:20s} {s['auc_en_ese_sentido']:.3f}  medianas abiertos/cerrados {s['mediana_abiertos']:.3f} / {s['mediana_cerrados']:.3f}  "
              f"coef en (b) {s['coeficiente_b']:+.2f} ({'actividad' if s['coincide_con_actividad'] else 'al revés'}); "
              f"r con log área {s['correlacion_con_log_area']:+.2f}; por tercil {s['auc_por_tercil_de_area']}")
    # The maximum insomnia inside the polygon: each variable alone and combined with "the patch moves" and with the echo.
    maximo = []
    for c in MAXIMO + COMBINA:
        ok = e[c].notna().values
        maximo.append({"variable": c, **me.auc_ic(y[ok], e.loc[ok, c].values), "sentido": "AUC de más alto = más abierto",
                       "mediana_abiertos": round(float(e.loc[e["y"] == 1, c].median()), 3), "mediana_cerrados": round(float(e.loc[e["y"] == 0, c].median()), 3)})
    alto = e["insomnio_px_max3"] >= 0.9
    con_maximo_alto = {"abiertos": [int((alto & (e["y"] == 1)).sum()), int(y.sum())], "cerrados": [int((alto & (e["y"] == 0)).sum()), int((1 - y).sum())]}
    e["max_x_mueve"] = e["insomnio_px_max3"] * e["insomnio_parche_se_mueve"]
    e["max_x_eco"] = e["insomnio_px_max3"] * e["eco_std_en_parche"]
    combos = {"máximo + se mueve + producto": ["insomnio_px_max3", "insomnio_parche_se_mueve", "max_x_mueve"],
              "máximo + eco en el parche + producto": ["insomnio_px_max3", "eco_std_en_parche", "max_x_eco"],
              "las tres del máximo": MAXIMO, "frente + máximo + combinaciones": NUEVAS + MAXIMO + COMBINA}
    auc_combos = {}
    for nombre, cols in combos.items():
        preds[nombre] = me.fuera_de_frame(me.logistica, e[cols].values, y, g)
        auc_combos[nombre] = me.auc_ic(y, preds[nombre])
    # Only among the sites with a high maximum: do the patch movement or the echo separate there?
    entre_altos = {}
    for c in COMBINA:
        ok = (alto & e[c].notna()).values
        if 0 < y[ok].sum() < ok.sum():
            entre_altos[c] = {**me.auc_ic(y[ok], e.loc[ok, c].values), "sentido": "AUC de más alto = más abierto, sólo predios con insomnio_px_max3 >= 0,9"}
    print("\nInsomnio máximo adentro del polígono (AUC de más alto = más abierto):")
    for f_ in maximo:
        print(f"  {f_['variable']:26s} {f_['auc']:.3f} {f_['ic95']}  medianas abiertos/cerrados {f_['mediana_abiertos']:.3f} / {f_['mediana_cerrados']:.3f}")
    print(f"  con máximo de 3×3 >= 0,9: abiertos {con_maximo_alto['abiertos']}, cerrados {con_maximo_alto['cerrados']}")
    for nombre, v_ in auc_combos.items():
        print(f"  {nombre:40s} AUC {v_['auc']:.3f} {v_['ic95']}")
    print("  entre los de máximo alto:", {k: (v_["auc"], v_["ic95"], v_["n"], v_["abiertos"]) for k, v_ in entre_altos.items()})
    # size control
    terciles = pd.qcut(e["area_ha"], 3, labels=["chicos", "medianos", "grandes"])
    por_area = []
    for t in terciles.cat.categories:
        s = (terciles == t).values
        por_area.append({"tercil": t, "n": int(s.sum()), "abiertos": int(y[s].sum()),
                         **{k: (round(float(roc_auc_score(y[s], preds[k][s])), 3) if 0 < y[s].sum() < s.sum() else None)
                            for k in ("(a) radar actual (7)", "(b) frente (10)")}})
    print("Por tercil de área:", por_area)
    # AMBA test with model (b) and with (a), trained with all the known-status sites
    prueba = []
    amba = d[d["id_catalogo"].isin(PRUEBA_AMBA)]
    if len(amba):
        pa = me.logistica().fit(e[me.RADAR].values, y).predict_proba(amba[me.RADAR].values)[:, 1]
        pb = m.predict_proba(amba[NUEVAS].values)[:, 1]
        pc = me.logistica().fit(e[me.RADAR + NUEVAS].values, y).predict_proba(amba[me.RADAR + NUEVAS].values)[:, 1]
        for (_, fila), a, b, c in zip(amba.iterrows(), pa, pb, pc):
            prueba.append({"id_catalogo": fila["id_catalogo"], "predio": PRUEBA_AMBA[fila["id_catalogo"]], "estado": fila["estado"],
                           "p_abierto_radar_actual": round(float(a), 3), "p_abierto_frente": round(float(b), 3), "p_abierto_los_dos": round(float(c), 3),
                           **{k: round(float(fila[k]), 3) for k in NUEVAS + MAXIMO + COMBINA}})
            print(f"  AMBA {PRUEBA_AMBA[fila['id_catalogo']]:42s} radar actual {a:.2f} | frente {b:.2f} | los dos {c:.2f}")
    else:
        print("  AMBA: sin recortes medidos (pasá --recortes a `medir`)")
    salida = {"generado_por": "motor/radar_frente.py evaluar",
              "muestras": {"n": int(len(e)), "abiertos": int(y.sum()), "cerrados": int((1 - y).sum()), "frames": sorted(set(g))},
              "validacion": "regresión logística como en modelo_estado.py; un frame afuera por vez; IC 95 % por remuestreo",
              "auc": auc, "variables_nuevas": solas, "auc_por_tercil_de_area": por_area, "prueba_amba": prueba,
              "insomnio_maximo": {"solas": maximo, "predios_con_maximo_3x3_mayor_0.9": con_maximo_alto, "combinaciones": auc_combos,
                                  "entre_los_de_maximo_alto": entre_altos}}
    with open(args.evaluacion, "w", encoding="utf-8") as fh:
        json.dump(salida, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print(args.evaluacion)


def main():
    q = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    q.add_argument("orden", choices=["medir", "evaluar"])
    q.add_argument("--frame", nargs="+", help="frames to measure (default: all those in data/catalogos/frames.json that have crops)")
    q.add_argument("--recortes", nargs="+", help="other pipeline output folders to look for crops in, besides ../data/salidas")
    q.add_argument("--tabla", default=TABLA)
    q.add_argument("--evaluacion", default=EVALUACION)
    args = q.parse_args()
    (cmd_medir if args.orden == "medir" else cmd_evaluar)(args)


if __name__ == "__main__":
    main()
