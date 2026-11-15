"""The open-versus-closed model (`modelo_estado.py`) next to the flow's verdicts.

It doesn't change any verdict: the insomnia rule stays as is and the model is added as one more fact for each
dump-site polygon. Used by `flujo.py`:

- `anotar(veredictos, salidas)` adds the `modelo_estado` object to each catalog verdict:
  `{"p_abierto": number or null, "lectura": "compatible con abierto" | "compatible con cerrado" | "sin dato", "origen": text}`.
- `bloque_web(salidas)` builds the `estado` key of `web/src/data/seed/modelo.json`.
- `matriz(salidas)` and `lineas_md(salidas)` compare, over the same known-status sites, what the insomnia rule
  says and what the model says (predictions made without the site's frame).

Reads `salidas/predicciones_estado.parquet` and `salidas/modelo_estado.json`. If they're missing, it does nothing.
"compatible with open according to the model" is not a verified status: it's how the model ranks, with registry labels.
"""
import json
import os

import pandas as pd

UMBRAL = 0.5
SIN_MODELO = "el modelo sólo se aplica a polígonos de basural de 10 ha o más con radar medido"
ETIQUETAS = {
    "eco_std_rel_p90": "Variación del eco HH en el tiempo, contra el anillo (percentil 90 del predio)",
    "ecohv_std_rel_p90": "Variación del eco HV en el tiempo, contra el anillo (percentil 90 del predio)",
    "eco_std_rel_max3": "Parche de 3×3 píxeles donde más varía el eco HH, contra el anillo",
    "eco_cambio_rel_p90": "Cambio neto del eco HH entre el principio y el final de la serie, contra el anillo",
    "frente_coh_3x3": "Coherencia del peor parche de 3×3 de cada par, contra el anillo",
    "frente_coh_fijo": "Coherencia del parche de 3×3 que es el peor de forma sostenida, contra el anillo",
    "frente_vs_predio": "Ese parche contra la mediana del predio (bajo = una zona chica mucho menos coherente que el resto)",
    "parche_bajo_ha": "Mayor zona con coherencia persistentemente baja (ha)",
    "parche_bajo_frac": "Esa zona como fracción del predio",
    "parche_se_mueve": "Cuánto se corre el parche menos coherente entre el principio y el final de la serie",
    "ndvi_contraste": "NDVI del predio menos el del anillo (Sentinel-2)",
    "bsi_contraste": "Índice de suelo desnudo del predio menos el del anillo (Sentinel-2)",
    "ndwi_contraste": "NDWI del predio menos el del anillo (Sentinel-2)",
    "swir_b11_contraste": "Infrarrojo de onda corta B11, predio menos anillo (Sentinel-2)",
    "swir_b12_contraste": "Infrarrojo de onda corta B12, predio menos anillo (Sentinel-2)",
    "ndvi_media": "NDVI medio del predio (Sentinel-2)",
    "ndvi_variacion": "Variación del NDVI del predio en el año (Sentinel-2)",
    "bsi_media": "Índice de suelo desnudo medio del predio (Sentinel-2)",
    "insomnio": "Insomnio del predio entero",
    "persistencia": "Persistencia del insomnio del predio entero",
    "eco_db": "Eco medio del predio (dB)",
    "contraste_p10": "Coherencia del 10 % menos coherente del predio, contra el anillo",
    "eco_var_p90": "Variación del eco en el tiempo (percentil 90 del predio)",
    "frac_insomnio_90": "Fracción del predio con insomnio muy alto",
    "hv_hh": "Cociente HV/HH del predio",
}


def cargar(salidas):
    """(predictions by id_catalogo, model) or (None, None) if `modelo_estado.py` hasn't run yet."""
    pred, mod = os.path.join(salidas, "predicciones_estado.parquet"), os.path.join(salidas, "modelo_estado.json")
    if not (os.path.exists(pred) and os.path.exists(mod)):
        return None, None
    with open(mod, encoding="utf-8") as fh:
        modelo = json.load(fh)
    return pd.read_parquet(pred), modelo


def _lectura(p):
    if p is None or pd.isna(p):
        return "sin dato"
    return "compatible con abierto" if p > UMBRAL else "compatible con cerrado"


def anotar(veredictos, salidas):
    """Adds `modelo_estado` to each verdict of a dump-site polygon. Returns how many ended up with data."""
    pred, _ = cargar(salidas)
    if pred is None:
        return 0
    por_id = {(r.id_catalogo, r.frame): r for r in pred.itertuples()}
    n = 0
    for v in veredictos:
        if v.get("tipo") != "catalogo":
            continue
        r = por_id.get((v["id"], v["frame"]))
        if r is None:
            v["modelo_estado"] = {"p_abierto": None, "lectura": "sin dato", "origen": SIN_MODELO}
            continue
        p = None if pd.isna(r.p_abierto) else round(float(r.p_abierto), 3)
        v["modelo_estado"] = {"p_abierto": p, "lectura": _lectura(p), "origen": r.origen}
        n += p is not None
    return n


def bloque_web(salidas):
    """The `estado` key of the web's `modelo.json`, or None if there is no model."""
    _, m = cargar(salidas)
    if m is None:
        return None
    p = m["modelo_principal"]
    return {
        "auc": p["auc"], "ic95": p["ic95"], "n": m["muestras"]["n"], "abiertos": m["muestras"]["abiertos"],
        "cerrados": m["muestras"]["cerrados"], "frames": m["muestras"]["frames"],
        "variables": [ETIQUETAS.get(c, c) for c in p["lista"]],
        "validacion": ("Se deja un frame afuera por vez: ningún predio se predice con un modelo que vio su frame. "
                       "Intervalo del 95 % por remuestreo. Etiquetas: el estado del registro, no el insomnio."),
        "limites": m["limites"],
        "prueba_amba": [{"nombre": x["nombre"], "estado_registro": x["estado"], "p_abierto": x["p_abierto"]} for x in m["prueba"]],
    }


def matriz(salidas):
    """Insomnia rule versus model, over the same known-status sites with a validation prediction."""
    pred, m = cargar(salidas)
    if pred is None:
        return None
    d = pred[pred["estado"].isin(["abierto", "cerrado"]) & pred["origen"].str.startswith("validación")]
    filas = {}
    for est in ("abierto", "cerrado"):
        s = d[d["estado"] == est]
        filas[est] = {
            "n": int(len(s)),
            "regla": {k: int((s["radar"] == k).sum()) for k in ("despierto", "quieto", "no_alcanza")},
            "modelo": {k: int((s["lectura"] == k).sum()) for k in ("compatible con abierto", "compatible con cerrado", "sin dato")},
        }
    a, c = filas["abierto"], filas["cerrado"]
    decide = a["regla"]["despierto"] + a["regla"]["quieto"] + c["regla"]["despierto"] + c["regla"]["quieto"]
    return {
        "predios": int(len(d)), "frames": int(d["frame"].nunique()), "filas": filas,
        "regla_decide": decide, "regla_acierta": a["regla"]["despierto"] + c["regla"]["quieto"],
        "modelo_decide": int((d["lectura"] != "sin dato").sum()),
        "modelo_acierta": a["modelo"]["compatible con abierto"] + c["modelo"]["compatible con cerrado"],
        "auc": m["modelo_principal"]["auc"], "ic95": m["modelo_principal"]["ic95"], "variables": m["modelo_principal"]["variables"],
    }


def lineas_md(salidas):
    """The section of `resultados-flujo.md` that compares the rule with the model."""
    x = matriz(salidas)
    if x is None:
        return []
    _, m = cargar(salidas)
    a, c = x["filas"]["abierto"], x["filas"]["cerrado"]
    pct = lambda k, n: f"{k} de {n} ({k / n:.0%})".replace("%", " %") if n else "—"  # noqa: E731
    num = lambda v, dec=2: "sin dato" if v is None else f"{v:.{dec}f}".replace(".", ",")  # noqa: E731
    L = ["## Regla del insomnio contra el modelo de abierto contra cerrado", "",
         f"Sobre los mismos {x['predios']} basurales de 10 ha o más con estado en el registro, de {x['frames']} frames (sin el AMBA, "
         "que es la prueba). La regla es el veredicto del radar con los umbrales del AMBA. El modelo es el de "
         f"`motor/modelo_estado.py` (variables: {x['variables']}; AUC {num(x['auc'])}, IC 95 % {num(x['ic95'][0])} a {num(x['ic95'][1])}), "
         "y cada predio se predice con un modelo entrenado sin su frame. Las etiquetas son el estado del registro, no el insomnio.", "",
         "| Registro | Predios | Regla: despierto | Regla: quieto | Regla: no alcanza | Modelo: compatible con abierto | Modelo: compatible con cerrado | Modelo: sin dato |",
         "|---|---|---|---|---|---|---|---|"]
    for nombre, f in (("Abierto", a), ("Cerrado", c)):
        L.append(f"| {nombre} | {f['n']} | {f['regla']['despierto']} | {f['regla']['quieto']} | {f['regla']['no_alcanza']} | "
                 f"{f['modelo']['compatible con abierto']} | {f['modelo']['compatible con cerrado']} | {f['modelo']['sin dato']} |")
    L += ["",
          f"- **Regla:** decide en {pct(x['regla_decide'], x['predios'])} de los predios y, de esos, coincide con el registro en "
          f"{pct(x['regla_acierta'], x['regla_decide'])} (abierto y despierto, o cerrado y quieto).",
          f"- **Modelo (umbral 0,5):** da una lectura en {pct(x['modelo_decide'], x['predios'])} y coincide con el registro en "
          f"{pct(x['modelo_acierta'], x['modelo_decide'])}.",
          "- \"Compatible con abierto según el modelo\" no es un estado verificado, y `p_abierto` no es una probabilidad calibrada.",
          "- **Prueba reservada (AMBA), modelo entrenado sólo con EE. UU.** (`p_abierto`): "
          + "; ".join(f"{p['nombre']}, registro {p['estado']}: {num(p['p_abierto'])}" for p in m["prueba"]) + ".",
          "- **Ojo con la frase del pitch de arriba:** los \"nuevos\" salen de otro modelo, el de \"basural contra otra cosa que se "
          "mueve\" (`../docs/results.md`: AUC 0,79 con 39 basurales, \"no alcanza como veredicto\"), y sólo en los frames que "
          "tienen `predicciones.parquet`. En los 20 frames agregados las manchas sin catálogo quedan sin clasificar: falta su "
          "óptico y reentrenar ese modelo.",
          "- Detalle, límites y qué aprende el modelo de abierto contra cerrado: `../docs/model.md`.", ""]
    return L
