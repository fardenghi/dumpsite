"""Manchas de un índice ya calculado como polígonos: escribe `salidas/manchas.geojson` según el contrato.

Lee la capa `candidato` (y las de insomnio, persistencia y eco) de un `indice_80m.npz`, vuelve a agrupar los candidatos
con `insomnio.manchas()` (mismos parámetros que el índice) y vectoriza cada mancha píxel a píxel. Escribe todas las
manchas, también las descartadas (`descartada` dice el motivo), con `id_mancha` = `MAN-<frame>-<n>` en el orden de
`insomnio.manchas()` (de mayor a menor superficie).

    python manchas_vectorizar.py                                    # el AMBA: ../data/salidas/indice_80m.npz
    python manchas_vectorizar.py --indice otro.npz --frame DELHI --epsg 32643 --salida ../data/salidas/DELHI

Es el `manchas.geojson` del AMBA mientras no esté la etapa 4: cuando la VM lo escriba, ese reemplaza a este.
Las geometrías son los bordes de los píxeles de 80 m (en escalera), pasados de UTM a grados.
"""
import argparse
import json
import os
import sys

import numpy as np
from rasterio import features
from rasterio.transform import from_origin
from rasterio.warp import transform_geom

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import contratos  # noqa: E402
import insomnio as ins  # noqa: E402


def _redondear(g, dec=6):
    def r(c):
        return [round(c[0], dec), round(c[1], dec)] if isinstance(c[0], (int, float)) else [r(x) for x in c]
    return {"type": g["type"], "coordinates": r(g["coordinates"])}


def vectorizar(etiquetas, xs, ys, paso, epsg):
    """{etiqueta: geometría GeoJSON en grados} de cada etiqueta > 0 de la capa."""
    t = from_origin(xs[0] - paso / 2, ys[0] + paso / 2, paso, paso)
    partes = {}
    for g, v in features.shapes(etiquetas.astype(np.int32), mask=etiquetas > 0, transform=t, connectivity=4):
        partes.setdefault(int(v), []).append(g["coordinates"])
    salida = {}
    for e, polis in partes.items():
        g = {"type": "Polygon", "coordinates": polis[0]} if len(polis) == 1 else {"type": "MultiPolygon", "coordinates": polis}
        salida[e] = _redondear(transform_geom(f"EPSG:{epsg}", "EPSG:4326", g))
    return salida


def armar(indice, frame, epsg, p=None):
    """Devuelve el FeatureCollection de las manchas del índice."""
    p = p or ins.Parametros()
    with np.load(indice) as z:
        d = {k: z[k] for k in z.files}
    xs, ys = d["xs"], d["ys"]
    paso = float(xs[1] - xs[0])
    capas = {k: d[k].astype(np.float32) for k in ("insomnio", "persistencia")}
    capas["eco_db"] = d["eco_db"].astype(np.float32) if "eco_db" in d and d["eco_db"].shape == d["insomnio"].shape else None
    lista, etiquetas = ins.manchas(d["candidato"], capas, paso, p)
    if "manchas" in d and not np.array_equal(etiquetas, d["manchas"]):
        print("Aviso: las etiquetas no coinciden con la capa `manchas` del índice; se usan las recalculadas.", file=sys.stderr)
    geoms = vectorizar(etiquetas, xs, ys, paso, epsg)
    feats = []
    for n, m in enumerate(lista, start=1):
        lat, lon = transform_geom(f"EPSG:{epsg}", "EPSG:4326", {
            "type": "Point", "coordinates": [xs[0] + m["columna"] * paso, ys[0] - m["fila"] * paso]})["coordinates"][::-1]
        props = {
            "id_mancha": contratos.id_mancha(frame, n), "frame": frame, "ha": m["ha"], "forma": m["forma"],
            "descartada": m["descartada"], "etiqueta": m["etiqueta"], "insomnio": m["insomnio"],
            "persistencia": m["persistencia"], "eco_db": m["eco_db"], "elongacion": max(m["elongacion"], 1.0),
            "nucleo": m["nucleo"], "lat": round(lat, 5), "lon": round(lon, 5),
        }
        props = {k: (None if isinstance(v, float) and not np.isfinite(v) else v) for k, v in props.items()}
        feats.append({"type": "Feature", "properties": props, "geometry": geoms[m["etiqueta"]]})
    return {
        "type": "FeatureCollection",
        "meta": {"generado_por": "motor/manchas_vectorizar.py", "indice": os.path.basename(indice), "frame": frame,
                 "epsg": epsg, "paso_m": paso, "parametros": p.dict(),
                 "fuentes": ["NISAR L2 GUNW y GCOV (NASA/ISRO), ASF DAAC", "JRC Global Surface Water v1.4"]},
        "features": feats,
    }


def main():
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--indice", default=os.path.join(AQUI, "..", "data", "salidas", "indice_80m.npz"))
    a.add_argument("--frame", default="AMBA")
    a.add_argument("--epsg", type=int, default=32721, help="EPSG de la grilla del índice (el AMBA es UTM 21 sur)")
    a.add_argument("--salida", default=os.path.join(AQUI, "..", "data", "salidas"))
    args = a.parse_args()
    fc = armar(args.indice, args.frame, args.epsg)
    os.makedirs(args.salida, exist_ok=True)
    destino = contratos.ruta("manchas", args.salida)
    with open(destino, "w", encoding="utf-8") as fh:
        json.dump(fc, fh, ensure_ascii=False, separators=(",", ":"))
    contratos.leer(destino)  # valida
    cand = sum(1 for f in fc["features"] if f["properties"]["descartada"] is None)
    print(f"{destino}: {len(fc['features'])} manchas, {cand} candidatas ({os.path.getsize(destino) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
