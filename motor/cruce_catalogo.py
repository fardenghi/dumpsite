"""Cruza un índice de insomnio ya calculado con los catálogos de `data/`: basurales (positivos) y confusores (negativos).

Es una prueba independiente de la calibración: los catálogos no se usaron para elegir los umbrales. Pero no es una
validación fuerte: en la grilla del AMBA hay pocos basurales que se puedan medir a 80 m.

    python cruce_catalogo.py                       # el índice de referencia, ../data/salidas/indice_80m.npz
    python cruce_catalogo.py --indice otra.npz --min-ha 5

- Positivos: los basurales de `basurales/geometrias.geojson` que caen en la grilla, agrupados por complejo
  (`basurales/complejos.json`), así Norte III cuenta una vez. Los complejos cerrados no son positivos: se informan
  aparte, porque se espera que estén quietos (Luján).
- Negativos: los polígonos de `negativos/geometrias_amba.geojson`.
- Por polígono, sobre los píxeles de tierra: la mediana del insomnio relativo y la fracción de píxeles candidatos.
  Polígonos sin agujeros (se usa el anillo exterior); los de menos de `--min-ha` no entran.
- AUC: probabilidad de que un positivo tenga más insomnio mediano que un negativo (empates cuentan 1/2).
"""
import argparse
import json
import os
import sys
from collections import defaultdict

import numpy as np
from scipy.stats import rankdata

AQUI = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(AQUI, "..", "data", "catalogos")
sys.path.insert(0, AQUI)
import geo  # noqa: E402
from geo import CAJA  # noqa: E402


def _anillos(geometria):
    """Anillos exteriores (lon, lat) de un Polygon o MultiPolygon."""
    if geometria["type"] == "Polygon":
        return [geometria["coordinates"][0]]
    if geometria["type"] == "MultiPolygon":
        return [p[0] for p in geometria["coordinates"]]
    return []


def _en_grilla(anillos):
    norte, oeste, sur, este = CAJA
    lon, lat = np.array([q for a in anillos for q in a])[:, :2].T
    return oeste <= lon.mean() <= este and sur <= lat.mean() <= norte


def _medir(mascara, d):
    m = mascara & ~d["agua"] & np.isfinite(d["insomnio"])
    if m.sum() < 3:
        return None
    return {"px": int(m.sum()), "insomnio": float(np.median(d["insomnio"][m])), "candidato": float(d["candidato"][m].mean())}


def auc(pos, neg):
    v = rankdata(np.r_[pos, neg])
    return float((v[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def main():
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--indice", default=os.path.join(AQUI, "..", "data", "salidas", "indice_80m.npz"))
    a.add_argument("--min-ha", type=float, default=10.0, help="superficie mínima de un polígono (o complejo) para entrar")
    a.add_argument("--json", help="si se da, guarda acá el detalle")
    args = a.parse_args()

    with np.load(args.indice) as z:
        d = {k: z[k] for k in ("insomnio", "candidato", "agua", "xs", "ys")}
    d["insomnio"] = d["insomnio"].astype(np.float32)
    xs, ys = d["xs"], d["ys"]

    with open(os.path.join(DATA, "basurales", "geometrias.geojson"), encoding="utf-8") as fh:
        basurales = [f for f in json.load(fh)["features"] if f["geometry"] and _anillos(f["geometry"]) and _en_grilla(_anillos(f["geometry"]))]
    with open(os.path.join(DATA, "basurales", "complejos.json"), encoding="utf-8") as fh:
        complejos = json.load(fh)
    estado_complejo = {c["id"]: c["estado"] for c in complejos["complejos"]}
    por_complejo = defaultdict(list)
    for f in basurales:
        por_complejo[complejos["complejo_por_sitio"].get(f["properties"]["id"], f["properties"]["id"])].append(f)

    positivos, cerrados = [], []
    for cid, fs in sorted(por_complejo.items()):
        ha = sum(f["properties"].get("area_ha") or 0 for f in fs)
        if ha < args.min_ha:
            continue
        r = _medir(geo.mascara_poligonos([q for f in fs for q in _anillos(f["geometry"])], xs, ys), d)
        if r is None:
            continue
        estado = estado_complejo.get(cid, fs[0]["properties"].get("estado"))
        nombre = next((f["properties"]["nombre"] for f in fs if f["properties"].get("nombre")), "sin nombre")
        fila = {"complejo": cid, "sitios": [f["properties"]["id"] for f in fs], "nombre": nombre, "estado": estado, "ha": round(ha, 1), **r}
        (cerrados if estado == "cerrado" else positivos).append(fila)

    with open(os.path.join(DATA, "negativos", "geometrias_amba.geojson"), encoding="utf-8") as fh:
        negativos_geo = json.load(fh)["features"]
    negativos = []
    for f in negativos_geo:
        p, anillos = f["properties"], _anillos(f["geometry"])
        if not anillos or (p.get("area_ha") or 0) < args.min_ha or not _en_grilla(anillos):
            continue
        r = _medir(geo.mascara_poligonos(anillos, xs, ys), d)
        if r is not None:
            negativos.append({"id": p["id"], "clase": p["clase"], "ha": p.get("area_ha"), **r})

    print(f"Índice: {os.path.relpath(args.indice)}  (polígonos de {args.min_ha:g} ha o más)")
    print("\nBasurales del catálogo (por complejo)")
    for f in positivos + cerrados:
        print(f"  {f['complejo']}  {f['nombre'][:42]:42s} {f['estado']:11s} {f['ha']:7.1f} ha  px {f['px']:4d}  "
              f"insomnio {f['insomnio']:.2f}  candidato {f['candidato']:.0%}")
    print("\nNegativos por clase")
    print(f"  {'clase':28s} {'n':>4s} {'insomnio':>9s} {'>= 0,7':>7s} {'con manchas':>12s}")
    clases = defaultdict(list)
    for n in negativos:
        clases[n["clase"]].append(n)
    for c, v in sorted(clases.items(), key=lambda kv: -np.median([x["insomnio"] for x in kv[1]])):
        i, m = np.array([x["insomnio"] for x in v]), np.array([x["candidato"] for x in v])
        print(f"  {c:28s} {len(v):4d} {np.median(i):9.2f} {np.mean(i >= 0.7):7.0%} {np.mean(m > 0.05):12.0%}")

    pi, pc = np.array([x["insomnio"] for x in positivos]), np.array([x["candidato"] for x in positivos])
    ni, nc = np.array([x["insomnio"] for x in negativos]), np.array([x["candidato"] for x in negativos])
    resumen = {"indice": os.path.basename(args.indice), "min_ha": args.min_ha, "positivos": len(pi), "negativos": len(ni),
               "positivos_insomnio_07": float(np.mean(pi >= 0.7)), "negativos_insomnio_07": float(np.mean(ni >= 0.7)),
               "positivos_con_manchas": float(np.mean(pc > 0.05)), "negativos_con_manchas": float(np.mean(nc > 0.05)),
               "auc": auc(pi, ni), "cerrados": [{k: f[k] for k in ("complejo", "nombre", "insomnio")} for f in cerrados]}
    print(f"\nPositivos (complejos no cerrados): {len(pi)}  insomnio >= 0,7: {resumen['positivos_insomnio_07']:.0%}  "
          f"con manchas (> 5 %): {resumen['positivos_con_manchas']:.0%}")
    print(f"Negativos: {len(ni)}  insomnio >= 0,7: {resumen['negativos_insomnio_07']:.0%}  con manchas (> 5 %): {resumen['negativos_con_manchas']:.0%}")
    print(f"AUC del insomnio mediano: {resumen['auc']:.2f}")
    if cerrados:
        print("Cerrados (se esperan quietos): " + ", ".join(f"{f['nombre']} {f['insomnio']:.2f}" for f in cerrados))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"resumen": resumen, "positivos": positivos, "cerrados": cerrados, "negativos": negativos}, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
