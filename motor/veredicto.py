"""Stage 9: joins the cross in both directions and gives a verdict per site (table in `../docs/modelo.md`).

From the catalog to the blobs (`insomnio_catalogo.parquet`, one row per catalog polygon) and from the blobs to the
catalog (`cruce_manchas_catalogo.parquet`, written by prompt 3). The dump-site probability comes from
`predicciones.parquet` (the model, or the mock while there isn't one) or from a `p_basural` column in the cross or in
`manchas.geojson`.

| Registry            | Radar and model                                  | Verdict                        |
|---------------------|--------------------------------------------------|--------------------------------|
| open or no status   | awake blob (or awake polygon)                    | activo_conocido                |
| closed              | awake blob (or awake polygon)                    | cerrado_despierto              |
| closed              | no blob; the polygon comes out quiet             | cerrado_quieto                 |
| open or no status   | no blob; the polygon comes out quiet             | quieto_radar                   |
| not listed          | awake blob, p_basural >= threshold               | posible_nuevo                  |
| not listed          | awake blob, p_basural < threshold                | descartada                     |
| not listed          | awake blob, no model                             | sin_clasificar                 |
| any                 | under 10 ha, or the radar can't decide           | no_alcanza                     |

Decisions (they weren't in the plan):
- A dump-site catalog polygon with a blob on top is a dump site because of the catalog, not the model: the
  model answers "what is it?" and the registry already says that. If the model hesitates, it is noted in `motivo`.
- If the polygon didn't end up in any blob but its record comes out `despierto`, it counts as awake (the blob may have
  been cut by the 10 ha threshold or by its shape).
- The registry status of a polygon without a status takes its complex's, if it has one (Norte III C has no status of its
  own; the Norte III complex is listed as open).

    python veredicto.py                                   # reads and writes in ../data/salidas
    python veredicto.py --carpeta datos/mock --salida /tmp/v.json
    python veredicto.py --frame AMBA --umbral 0.5
"""
import argparse
import datetime as dt
import json
import os
import sys

import numpy as np
import pandas as pd

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
DATA = os.path.join(RAIZ, "data", "catalogos")
SALIDAS = os.path.join(RAIZ, "data", "salidas")
sys.path.insert(0, AQUI)
import contratos  # noqa: E402

TEXTOS = {
    "activo_conocido": "Activo, ya conocido",
    "cerrado_despierto": "Cerrado pero despierto",
    "cerrado_quieto": "Cerrado y quieto",
    "quieto_radar": "Quieto según el radar",
    "posible_nuevo": "Posible basural activo nuevo",
    "descartada": "Descartada",
    "sin_clasificar": "Mancha despierta sin clasificar (sin modelo)",
    "no_alcanza": "El radar no alcanza",
}


# ---------------------------------------------------------------- lectura
def _opcional(carpeta, nombre, ruta=None):
    """Reads and validates a contract; None if it's not there. An explicit path must have the contract's name."""
    camino = ruta or contratos.ruta(nombre, carpeta)
    return contratos.leer(camino) if os.path.exists(camino) else None


def _estados_catalogo():
    """site id -> (site status, complex status), from complejos.json."""
    camino = os.path.join(DATA, "basurales", "complejos.json")
    if not os.path.exists(camino):
        return {}, {}
    with open(camino, encoding="utf-8") as fh:
        cx = json.load(fh)
    sitio, complejo = {}, {}
    for c in cx["complejos"]:
        for s, e in c.get("estados_sitios", {}).items():
            sitio[s] = e
            complejo[s] = c["estado"]
    return sitio, complejo


def registro(fila, est_sitio, est_cx):
    """Registry status of a dump-site polygon: its own; if it has none, its complex's."""
    e = fila.get("estado") if isinstance(fila.get("estado"), str) else est_sitio.get(fila["id_catalogo"], "desconocido")
    if e == "desconocido":
        c = fila.get("estado_complejo") if isinstance(fila.get("estado_complejo"), str) else est_cx.get(fila["id_catalogo"])
        if c in ("abierto", "cerrado"):
            return c, "complejo"
    return e, "sitio"


def probabilidades(pred, cruce, manchas):
    """id_mancha -> p_basural. Priority: predicciones.parquet, p_basural column of the cross, blob property."""
    p = {}
    if manchas is not None and "p_basural" in manchas:
        p.update({m: v for m, v in zip(manchas["id_mancha"], manchas["p_basural"]) if pd.notna(v)})
    if cruce is not None and "p_basural" in cruce:
        p.update({m: v for m, v in zip(cruce["id_mancha"], cruce["p_basural"]) if pd.notna(v)})
    if pred is not None:
        p.update(dict(zip(pred["id_mancha"], pred["p_basural"])))
    return {k: float(v) for k, v in p.items()}


# ---------------------------------------------------------------- veredicto
def veredicto_catalogo(fila, reg, manchas_sitio, p, umbral, min_ha):
    """Verdict for a polygon of the dump-site catalog."""
    ps = [p[m] for m in manchas_sitio if m in p]
    p_max = max(ps) if ps else None
    if (fila["area_ha"] if pd.notna(fila.get("area_ha")) else 0) < min_ha:
        return "no_alcanza", f"el polígono mide menos de {min_ha:g} ha", p_max
    despierto_por = None
    if manchas_sitio:
        despierto_por = f"mancha despierta encima ({', '.join(manchas_sitio)})"
    elif fila["radar"] == "despierto":
        despierto_por = "el polígono sale despierto aunque no formó mancha"
    if despierto_por:
        duda = f"; el modelo duda (p_basural {p_max:.2f})" if p_max is not None and p_max < umbral else ""
        return ("cerrado_despierto" if reg == "cerrado" else "activo_conocido"), despierto_por + duda, p_max
    if fila["radar"] == "quieto":
        return ("cerrado_quieto" if reg == "cerrado" else "quieto_radar"), "sin mancha y el polígono sale quieto", p_max
    motivo = fila.get("motivo") if isinstance(fila.get("motivo"), str) else "el radar no decide"
    return "no_alcanza", motivo, p_max


def veredicto_mancha(p_basural, umbral, negativos):
    neg = f" (toca un negativo del catálogo: {', '.join(negativos)})" if negativos else ""
    if p_basural is None:
        return "sin_clasificar", "no está en el catálogo de basurales y no hay modelo" + neg
    if p_basural >= umbral:
        return "posible_nuevo", f"no está en el catálogo de basurales; p_basural {p_basural:.2f}" + neg
    return "descartada", f"el modelo dice otra cosa (p_basural {p_basural:.2f})" + neg


def calcular(ic, cruce=None, manchas=None, pred=None, umbral=0.5, criterio=contratos.CRITERIO_CRUCE, min_ha=contratos.MIN_HA,
             frame=None):
    """Returns the list of verdicts (dicts). `ic` is insomnio_catalogo; the rest may be missing."""
    if frame:
        ic = ic[ic["frame"] == frame]
        cruce = None if cruce is None else cruce[cruce["frame"] == frame]
        manchas = None if manchas is None else manchas[manchas["frame"] == frame]
    est_sitio, est_cx = _estados_catalogo()
    p = probabilidades(pred, cruce, manchas)

    candidatas = None
    if manchas is not None:
        candidatas = set(manchas.loc[manchas["descartada"].isna(), "id_mancha"])
    cruces = pd.DataFrame(columns=["id_mancha", "id_catalogo", "catalogo", "frame", "frac_area_menor"]) if cruce is None else cruce
    cruces = cruces[cruces["frac_area_menor"] >= criterio]
    if candidatas is not None:
        cruces = cruces[cruces["id_mancha"].isin(candidatas)]
    manchas_de = cruces[cruces["catalogo"] == "basurales"].groupby(["frame", "id_catalogo"])["id_mancha"].apply(sorted).to_dict()

    salida = []
    for _, f in ic[ic["catalogo"] == "basurales"].iterrows():
        reg, de = registro(f, est_sitio, est_cx)
        ms = manchas_de.get((f["frame"], f["id_catalogo"]), [])
        v, motivo, p_max = veredicto_catalogo(f, reg, ms, p, umbral, min_ha)
        salida.append({
            "tipo": "catalogo", "id": f["id_catalogo"], "frame": f["frame"],
            "complejo": f["complejo"] if isinstance(f.get("complejo"), str) else None,
            "nombre": f["nombre"] if isinstance(f.get("nombre"), str) else None,
            "area_ha": None if pd.isna(f.get("area_ha")) else round(float(f["area_ha"]), 1),
            "registro": reg, "registro_de": de, "radar": f["radar"],
            "insomnio": None if pd.isna(f["insomnio"]) else float(f["insomnio"]),
            "persistencia": None if pd.isna(f["persistencia"]) else float(f["persistencia"]),
            "manchas": ms, "p_basural": p_max, "veredicto": v, "veredicto_texto": TEXTOS[v], "motivo": motivo,
        })

    # blobs that don't cross any dump site
    todas = set(candidatas) if candidatas is not None else set(cruces["id_mancha"]) | set(p)
    con_basural = set(cruces.loc[cruces["catalogo"] == "basurales", "id_mancha"])
    neg_de = cruces[cruces["catalogo"] == "negativos"]
    info = manchas.set_index("id_mancha") if manchas is not None else None
    for m in sorted(todas - con_basural):
        negs = neg_de.loc[neg_de["id_mancha"] == m]
        etiquetas = [f"{r.id_catalogo} {getattr(r, 'clase_negativo', '') or ''}".strip() for r in negs.itertuples()]
        v, motivo = veredicto_mancha(p.get(m), umbral, etiquetas)
        fila = {"tipo": "mancha", "id": m, "frame": m.split("-")[1] if frame is None else frame, "complejo": None, "nombre": None,
                "area_ha": None, "registro": "no_figura", "registro_de": None, "radar": "despierto", "insomnio": None,
                "persistencia": None, "manchas": [m], "p_basural": p.get(m), "veredicto": v, "veredicto_texto": TEXTOS[v], "motivo": motivo}
        if info is not None and m in info.index:
            r = info.loc[m]
            fila.update(frame=r["frame"], area_ha=float(r["ha"]), insomnio=None if pd.isna(r["insomnio"]) else float(r["insomnio"]),
                        persistencia=None if pd.isna(r["persistencia"]) else float(r["persistencia"]))
            if "lat" in info.columns and pd.notna(r.get("lat")):
                fila.update(lat=float(r["lat"]), lon=float(r["lon"]))
        salida.append(fila)
    return salida


def resumen(veredictos):
    """Counts for the pitch, with each complex only once (it keeps its most 'active' verdict)."""
    orden = ["cerrado_despierto", "activo_conocido", "cerrado_quieto", "quieto_radar", "no_alcanza"]
    por_cx = {}
    for v in veredictos:
        if v["tipo"] != "catalogo":
            continue
        clave = (v["frame"], v["complejo"] or v["id"])
        if clave not in por_cx or orden.index(v["veredicto"]) < orden.index(por_cx[clave]):
            por_cx[clave] = v["veredicto"]
    cuenta_cx = pd.Series(list(por_cx.values()), dtype=object).value_counts().to_dict()
    cuenta_m = pd.Series([v["veredicto"] for v in veredictos if v["tipo"] == "mancha"], dtype=object).value_counts().to_dict()
    conocidos = cuenta_cx.get("activo_conocido", 0) + cuenta_cx.get("cerrado_despierto", 0)
    nuevos = cuenta_m.get("posible_nuevo", 0)
    return {
        "complejos_por_veredicto": {k: int(v) for k, v in cuenta_cx.items()},
        "manchas_por_veredicto": {k: int(v) for k, v in cuenta_m.items()},
        "activos": int(conocidos + nuevos), "activos_ya_conocidos": int(conocidos), "posibles_nuevos": int(nuevos),
        "cerrados_pero_despiertos": int(cuenta_cx.get("cerrado_despierto", 0)),
        "cerrados_y_quietos": int(cuenta_cx.get("cerrado_quieto", 0)),
        "frase": (f"En los frames procesados, el radar ve {conocidos + nuevos} basurales activos: {conocidos} ya estaban en los "
                  f"catálogos y {nuevos} son posibles nuevos; de los conocidos, {cuenta_cx.get('cerrado_despierto', 0)} figuran "
                  f"cerrados pero siguen despiertos."),
    }


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--carpeta", default=SALIDAS, help="where to read the contracts from (salidas/ or datos/mock/)")
    a.add_argument("--insomnio-catalogo")
    a.add_argument("--cruce", help="cruce_manchas_catalogo.parquet (optional; written by prompt 3)")
    a.add_argument("--manchas", help="manchas.geojson (opcional)")
    a.add_argument("--predicciones", help="predicciones.parquet (optional; without a model, the mock)")
    a.add_argument("--frame", help="only this frame")
    a.add_argument("--umbral", type=float, default=0.5, help="p_basural from which the model says dump site")
    a.add_argument("--salida", default=os.path.join(SALIDAS, "veredictos.json"))
    args = a.parse_args(argv)

    ic = _opcional(args.carpeta, "insomnio_catalogo", args.insomnio_catalogo)
    if ic is None:
        sys.exit("Falta insomnio_catalogo.parquet: corré insomnio_catalogo.py.")
    cruce = _opcional(args.carpeta, "cruce_manchas_catalogo", args.cruce)
    manchas = _opcional(args.carpeta, "manchas", args.manchas)
    pred = _opcional(args.carpeta, "predicciones", args.predicciones)
    vs = calcular(ic, cruce, manchas, pred, umbral=args.umbral, frame=args.frame)
    r = resumen(vs)
    meta = {
        "generado": dt.datetime.now().isoformat(timespec="seconds"), "generado_por": "motor/veredicto.py",
        "entradas": {"insomnio_catalogo": True, "cruce_manchas_catalogo": cruce is not None, "manchas": manchas is not None,
                     "predicciones": pred is not None},
        "carpeta": os.path.relpath(args.carpeta, RAIZ), "umbral_p_basural": args.umbral, "criterio_cruce": contratos.CRITERIO_CRUCE,
        "modo_insomnio": sorted(ic["modo"].unique().tolist()) if "modo" in ic else None,
        "advertencia": "Señal compatible con actividad, no prueba. Lo quieto es 'quieto según el radar'.",
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.salida)), exist_ok=True)
    with open(args.salida, "w", encoding="utf-8") as fh:
        json.dump({"meta": meta, "resumen": r, "veredictos": vs}, fh, ensure_ascii=False, indent=1,
                  default=lambda o: o.item() if isinstance(o, np.generic) else str(o))
        fh.write("\n")
    for v in vs:
        if v["tipo"] == "catalogo" and v["veredicto"] != "no_alcanza" or v["tipo"] == "mancha":
            print(f"  {v['frame']:6s} {v['id']:16s} {(v['nombre'] or '')[:40]:40s} {v['registro']:11s} {v['radar']:10s} -> {v['veredicto_texto']}")
    print(r["frase"])
    print(f"-> {os.path.relpath(args.salida)}")
    return vs, r


if __name__ == "__main__":
    main()
