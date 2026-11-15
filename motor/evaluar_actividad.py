"""Etapa 8: ¿el radar coincide con el registro? Matriz de abierto contra cerrado, por país.

Sobre los basurales de estado conocido de cada frame (`salidas/estado_conocido.json`, que arma `frames_elegir.py` desde
la EPA, OSM y los casos curados de Argentina) compara el estado del registro con lo que dice el radar sobre su polígono
(`salidas/insomnio_catalogo.parquet`). Las etiquetas son independientes del insomnio: nunca salen de él.

- Cada complejo cuenta una vez: se usa su sitio de estado conocido más grande.
- Entran los de `--min-ha` (10 ha) o más; los más chicos se cuentan aparte (el radar no alcanza).
- Los frames que todavía no tienen filas en `insomnio_catalogo` se informan como "sin procesar".
- Intervalo de confianza de Wilson al 95 % para las tasas: con pocos sitios, el margen es grande y hay que decirlo.

    python evaluar_actividad.py                                  # ../salidas -> ../salidas/evaluacion_actividad.json
    python evaluar_actividad.py --fuentes epa_lmop curado_manual # sin los cerrados de OSM (etiquetas disused, sin fecha)
"""
import argparse
import datetime as dt
import json
import math
import os
import sys
from collections import defaultdict

import pandas as pd

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
SALIDAS = os.path.join(RAIZ, "data", "salidas")
sys.path.insert(0, AQUI)
import contratos  # noqa: E402

REGISTROS = ("abierto", "cerrado")
RADARES = ("despierto", "quieto", "no_alcanza")


def wilson(k, n, z=1.96):
    """Intervalo de Wilson para k de n. None si n = 0."""
    if n == 0:
        return None
    p = k / n
    c = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    centro = (p + z * z / (2 * n)) / (1 + z * z / n)
    return [round(max(0.0, centro - c), 3), round(min(1.0, centro + c), 3)]


def tasa(k, n):
    return {"k": k, "n": n, "tasa": None if n == 0 else round(k / n, 3), "ic95": wilson(k, n)}


def matriz_vacia():
    return {r: {x: 0 for x in RADARES} for r in REGISTROS}


def metricas(m):
    """Tasas sobre los que el radar pudo decidir (despierto o quieto)."""
    ab_d, ab_q = m["abierto"]["despierto"], m["abierto"]["quieto"]
    ce_d, ce_q = m["cerrado"]["despierto"], m["cerrado"]["quieto"]
    return {
        "abiertos_que_salen_despiertos": tasa(ab_d, ab_d + ab_q),
        "abiertos_que_salen_quietos": tasa(ab_q, ab_d + ab_q),
        "cerrados_que_salen_quietos": tasa(ce_q, ce_d + ce_q),
        "cerrados_que_salen_despiertos": tasa(ce_d, ce_d + ce_q),
        "concordancia": tasa(ab_d + ce_q, ab_d + ab_q + ce_d + ce_q),
        "el_radar_no_alcanza": tasa(m["abierto"]["no_alcanza"] + m["cerrado"]["no_alcanza"],
                                    sum(m[r][x] for r in REGISTROS for x in RADARES)),
    }


def elegir_por_complejo(sitios, fuentes):
    """Un sitio por complejo: el de estado abierto o cerrado (de las fuentes pedidas) más grande."""
    por_cx = {}
    for s in sitios:
        if s["estado"] not in REGISTROS or not set(s["fuentes_estado"]) & set(fuentes):
            continue
        clave = s.get("complejo") or s["id_catalogo"]
        if clave not in por_cx or (s.get("area_ha") or 0) > (por_cx[clave].get("area_ha") or 0):
            por_cx[clave] = s
    return list(por_cx.values())


def evaluar(estado_conocido, ic, fuentes=("epa_lmop", "curado_manual", "osm"), min_ha=contratos.MIN_HA):
    radar = {(f, i): r for f, i, r in zip(ic["frame"], ic["id_catalogo"], ic["radar"])}
    insom = {(f, i): v for f, i, v in zip(ic["frame"], ic["id_catalogo"], ic["insomnio"])}
    procesados = set(ic["frame"])
    por_pais, total = defaultdict(matriz_vacia), matriz_vacia()
    sitios, chicos, sin_poligono, sin_procesar = [], defaultdict(int), defaultdict(int), {}
    for frame, lista in estado_conocido["frames"].items():
        elegidos = elegir_por_complejo(lista, fuentes)
        if frame not in procesados:
            sin_procesar[frame] = len([s for s in elegidos if (s.get("area_ha") or 0) >= min_ha])
            continue
        for s in elegidos:
            pais = s.get("pais") or "?"
            if (s.get("area_ha") or 0) < min_ha:
                chicos[pais] += 1
                continue
            r = radar.get((frame, s["id_catalogo"]))
            if r is None:  # sin polígono en el catálogo (sitios de la EPA que son un punto) o fuera de la grilla
                sin_poligono[pais] += 1
                continue
            por_pais[pais][s["estado"]][r] += 1
            total[s["estado"]][r] += 1
            ins = insom.get((frame, s["id_catalogo"]))
            sitios.append({"frame": frame, "pais": pais, "id_catalogo": s["id_catalogo"], "nombre": s.get("nombre"),
                           "complejo": s.get("complejo"), "area_ha": s.get("area_ha"), "registro": s["estado"],
                           "fuentes_estado": s["fuentes_estado"], "fecha_cierre": s.get("fecha_cierre"), "radar": r,
                           "insomnio": None if pd.isna(ins) else float(ins),
                           "coincide": None if r == "no_alcanza" else (s["estado"] == "abierto") == (r == "despierto")})
    discordantes = [s for s in sitios if s["coincide"] is False]
    return {
        "total": {"matriz": total, "metricas": metricas(total)},
        "por_pais": {p: {"matriz": m, "metricas": metricas(m)} for p, m in sorted(por_pais.items())},
        "chicos_menos_de_min_ha": dict(chicos), "sin_poligono_o_fuera_de_grilla": dict(sin_poligono),
        "frames_sin_procesar": sin_procesar,
        "discordantes": {"cerrados_pero_despiertos": [s for s in discordantes if s["registro"] == "cerrado"],
                         "abiertos_pero_quietos": [s for s in discordantes if s["registro"] == "abierto"]},
        "sitios": sitios,
    }


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--estado-conocido", default=os.path.join(SALIDAS, "estado_conocido.json"))
    a.add_argument("--insomnio-catalogo", default=os.path.join(SALIDAS, "insomnio_catalogo.parquet"))
    a.add_argument("--fuentes", nargs="+", default=["epa_lmop", "curado_manual", "osm"],
                   help="fuentes del estado que valen como etiqueta")
    a.add_argument("--min-ha", type=float, default=contratos.MIN_HA)
    a.add_argument("--salida", default=os.path.join(SALIDAS, "evaluacion_actividad.json"))
    args = a.parse_args(argv)

    with open(args.estado_conocido, encoding="utf-8") as fh:
        ec = json.load(fh)
    ic = contratos.leer(args.insomnio_catalogo)
    r = evaluar(ec, ic, args.fuentes, args.min_ha)
    modo = sorted(ic["modo"].unique().tolist()) if "modo" in ic else None
    meta = {
        "generado": dt.datetime.now().isoformat(timespec="seconds"), "generado_por": "herramientas/evaluar_actividad.py",
        "entradas": [os.path.relpath(args.estado_conocido, RAIZ), os.path.relpath(args.insomnio_catalogo, RAIZ)],
        "fuentes_del_estado": args.fuentes, "min_ha": args.min_ha, "modo_insomnio": modo,
        "lectura": ("Filas: estado del registro. Columnas: lo que dice el radar sobre el polígono (insomnio.ficha). "
                    "Las tasas se calculan sobre los que el radar pudo decidir; ic95 es el intervalo de Wilson."),
        "advertencias": ["El estado conocido es casi todo de la EPA (EE. UU.): por eso la matriz va por país.",
                         "Un relleno 'abierto' puede tener el frente de descarga más chico que el píxel de 80 m y salir quieto.",
                         "Los cerrados de OSM salen de etiquetas disused/abandoned, sin fecha de cierre."],
    }
    with open(args.salida, "w", encoding="utf-8") as fh:
        json.dump({"meta": meta, **r}, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    for pais, d in list(r["por_pais"].items()) + [("TOTAL", r["total"])]:
        m = d["matriz"]
        print(f"{pais:6s} abierto: {m['abierto']}  cerrado: {m['cerrado']}  concordancia: {d['metricas']['concordancia']['tasa']}"
              f" (n={d['metricas']['concordancia']['n']})")
    if r["frames_sin_procesar"]:
        print("Sin procesar (sitios grandes de estado conocido esperando):", r["frames_sin_procesar"])
    print(f"-> {os.path.relpath(args.salida)}")
    return r


if __name__ == "__main__":
    main()
