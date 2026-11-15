"""Tablas de `idea/etapa4-manchas.md`, en Markdown, a partir de `salidas/<FRAME>/` (no calcula nada nuevo).

    python resumen_etapa4.py            # manchas por frame, y despierto / quieto / no alcanza por estado

Lee de cada frame `manchas.geojson` (encabezado), `tabla_radar.parquet` e `insomnio_catalogo.parquet`. Separa los
frames de `data/frames.json` en dos grupos: los de antes y los agregados por cantidad de abiertos (`criterio` =
`abiertos`, prompt 6). Cuenta polígonos de `data/basurales/` de 10 ha o más por el estado del registro.
"""
import json
import os
import sys

import pandas as pd

AQUI = os.path.dirname(os.path.abspath(__file__))
SALIDAS = os.path.join(AQUI, "..", "salidas")
FRAMES = os.path.join(AQUI, "..", "..", "data", "frames.json")
RADAR = ("despierto", "quieto", "no_alcanza")
ESTADOS = (("abierto", ("abierto",)), ("cerrado", ("cerrado",)), ("sin estado", ("desconocido", "contradictorio")))


def cargar():
    with open(FRAMES, encoding="utf-8") as fh:
        frames = json.load(fh)["frames"]
    filas = []
    for f in frames:
        carpeta = os.path.join(SALIDAS, f["frame"])
        if not os.path.exists(os.path.join(carpeta, "insomnio_catalogo.parquet")):
            continue
        with open(os.path.join(carpeta, "manchas.geojson"), encoding="utf-8") as fh:
            g = json.load(fh)
        filas.append({"f": f, "meta": {k: v for k, v in g.items() if k != "features"},
                      "radar": pd.read_parquet(os.path.join(carpeta, "tabla_radar.parquet")),
                      "cat": pd.read_parquet(os.path.join(carpeta, "insomnio_catalogo.parquet"))})
    return filas, [f["frame"] for f in frames if not os.path.exists(os.path.join(SALIDAS, f["frame"], "insomnio_catalogo.parquet"))]


def tabla_manchas(filas):
    out = ["| Frame | Órbitas | Período de los pares | Pares | Manchas | Candidatas | En un basural del catálogo | Uso conocido (OSM) | Sin explicar | ha candidatas |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    tot = [0] * 7
    for x in filas:
        m, r = x["meta"], x["radar"]
        clases = r["clase_osm"].value_counts()
        v = [m["pares"], m["manchas_en_total"], len(r), int(clases.get("relleno_osm", 0)), int(clases.get("uso_conocido", 0)),
             int(clases.get("sin_explicar", 0)), round(r["area_ha"].sum())]
        tot = [a + b for a, b in zip(tot, v)]
        out.append(f"| `{x['f']['frame']}` | {', '.join(str(o) for o in m['orbitas'])} | {m['desde']} a {m['hasta']} | " + " | ".join(f"{n:,}".replace(",", ".") for n in v) + " |")
    out.append("| **Total** | | | " + " | ".join(f"{n:,}".replace(",", ".") for n in tot) + " |")
    return "\n".join(out)


def conteo(cat, estados):
    b = cat[(cat["catalogo"] == "basurales") & (cat["area_ha"] >= 10) & cat["estado"].isin(estados)]
    return [int((b["radar"] == r).sum()) for r in RADAR]


def tabla_estado(filas):
    out = ["| Frame | Abiertos | Cerrados | Sin estado |", "|---|---|---|---|"]
    tot = {e: [0, 0, 0] for e, _ in ESTADOS}
    for x in filas:
        celdas = []
        for e, vals in ESTADOS:
            c = conteo(x["cat"], vals)
            tot[e] = [a + b for a, b in zip(tot[e], c)]
            celdas.append(" / ".join(map(str, c)) if sum(c) else "—")
        out.append(f"| `{x['f']['frame']}` | " + " | ".join(celdas) + " |")
    out.append("| **Total** | " + " | ".join(f"**{' / '.join(map(str, tot[e]))}** ({sum(tot[e])})" for e, _ in ESTADOS) + " |")
    return "\n".join(out), tot


def main():
    filas, faltan = cargar()
    grupos = (("Frames de antes (10)", [x for x in filas if x["f"].get("criterio") != "abiertos"]),
              ("Frames agregados por abiertos (prompt 6)", [x for x in filas if x["f"].get("criterio") == "abiertos"]))
    totales = {}
    for titulo, g in grupos:
        if not g:
            continue
        print(f"\n## {titulo}: manchas\n\n{tabla_manchas(g)}")
        t, totales[titulo] = tabla_estado(g)
        print(f"\n## {titulo}: despierto / quieto / no alcanza, polígonos de 10 ha o más\n\n{t}")
    print("\n## Resumen")
    for titulo, tot in totales.items():
        for e in ("abierto", "cerrado"):
            d, q, n = tot[e]
            juzga = d + q
            print(f"- {titulo}, {e}s: {sum(tot[e])} polígonos; despiertos {d}, quietos {q}, no alcanza {n}"
                  + (f"; entre los que el radar juzga, despierto el {d / juzga:.0%} ({d} de {juzga})" if juzga else ""))
    if faltan:
        print(f"\nFrames de frames.json sin salidas: {', '.join(faltan)}", file=sys.stderr)


if __name__ == "__main__":
    main()
