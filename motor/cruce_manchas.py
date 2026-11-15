"""Crosses the blobs with the catalog polygons: writes `cruce_manchas_catalogo.parquet` following the contract.

One row per pair of candidate blob and polygon (dump site or negative) that touch, **without filtering by the 30 %**: the
reader applies `contratos.CRITERIO_CRUCE` on `frac_area_menor`. Areas are measured in the frame's UTM.
Besides the contract it carries `inter_ha` (the area of the intersection), for the minimum in `../docs/model.md`.

    python cruce_manchas.py                                         # ../data/salidas/manchas.geojson (AMBA)
    python cruce_manchas.py --manchas datos/mock/manchas.geojson --catalogo datos/mock/catalogo_mock.geojson \
                            --salida datos/mock/prueba
    python cruce_manchas.py --todas                                 # also the discarded blobs

If `--catalogo` is given, that GeoJSON (with `id`, `catalogo`, `complejo`, `clase` in the properties) is used instead of
`../data/catalogos/`. It's for the mock.
"""
import argparse
import json
import os
import sys
from collections import defaultdict

import pandas as pd
import shapely
from shapely.geometry import shape

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import catalogo_poligonos as cp  # noqa: E402
import contratos  # noqa: E402


def _catalogo_archivo(camino):
    with open(camino, encoding="utf-8") as fh:
        fc = json.load(fh)
    salida = []
    for f in fc["features"]:
        p = f["properties"]
        i = p.get("id") or p.get("id_catalogo")
        cat = p.get("catalogo") or ("basurales" if str(i).startswith("BAS-") else "negativos")
        salida.append({"id_catalogo": i, "catalogo": cat, "complejo": p.get("complejo"), "estado": p.get("estado"),
                       "clase": p.get("clase") or p.get("clase_negativo"), "area_ha": p.get("area_ha"),
                       "nombre": p.get("nombre"), "geom": cp._valida(shape(f["geometry"]))})
    return [s for s in salida if s["geom"] is not None]


def cruzar(lista_manchas, poligonos, epsg_por_frame):
    """DataFrame of the `cruce_manchas_catalogo` contract (plus the computed `frac_area_menor`)."""
    filas = []
    por_frame = defaultdict(list)
    for props, g in lista_manchas:
        por_frame[props["frame"]].append((props, g))
    for frame, ms in por_frame.items():
        epsg = epsg_por_frame(frame, ms)
        geoms = [g for _, g in ms]
        arbol = shapely.STRtree([p["geom"] for p in poligonos])
        pares = arbol.query(geoms, predicate="intersects")
        utm_m, utm_p = {}, {}
        for im, ip in zip(*pares):
            if im not in utm_m:
                utm_m[im] = cp.a_utm(geoms[im], epsg)
            if ip not in utm_p:
                utm_p[ip] = cp.a_utm(poligonos[ip]["geom"], epsg)
            a, b = utm_m[im], utm_p[ip]
            if a is None or b is None:
                continue
            inter = a.intersection(b).area
            if inter <= 0:
                continue
            fm, fp = min(inter / a.area, 1.0), min(inter / b.area, 1.0)
            pol = poligonos[ip]
            filas.append({
                "id_mancha": ms[im][0]["id_mancha"], "id_catalogo": pol["id_catalogo"], "catalogo": pol["catalogo"],
                "frame": frame, "frac_mancha": round(fm, 4), "frac_poligono": round(fp, 4),
                "frac_area_menor": round(max(fm, fp), 4), "inter_ha": round(inter / 1e4, 2),
                "complejo": pol["complejo"] if pol["catalogo"] == "basurales" else None,
                "clase_negativo": pol["clase"] if pol["catalogo"] == "negativos" else None,
            })
    cols = list(contratos.CONTRATOS["cruce_manchas_catalogo"].nombres) + ["inter_ha"]
    df = pd.DataFrame(filas, columns=cols)
    # a polygon can come from both negative sources; we keep the pair with the largest overlap
    return df.sort_values("frac_area_menor", ascending=False).drop_duplicates(["id_mancha", "id_catalogo"]) \
             .sort_values(["id_mancha", "frac_area_menor"], ascending=[True, False]).reset_index(drop=True)


def cruzar_por_frame(ms, fc, cargar):
    """Crosses frame by frame: the catalog is loaded with each frame's box (works for the all-frames geojson
    built by `extraer_manchas.py juntar`). Returns (DataFrame, total polygons loaded)."""
    epsg_meta = (fc.get("meta") or {}).get("epsg") or fc.get("epsg")
    frames = sorted({p["frame"] for p, _ in ms})
    partes, total = [], 0

    def epsg_por_frame(frame, lista):
        if epsg_meta and len(frames) == 1:
            return int(epsg_meta)
        c = shapely.union_all([g for _, g in lista]).centroid
        return cp.epsg_utm(c.x, c.y)

    for f in frames:
        sub = [(p, g) for p, g in ms if p["frame"] == f]
        poligonos = cargar(cp.bbox_de([g for _, g in sub]))
        total += len(poligonos)
        if poligonos:
            partes.append(cruzar(sub, poligonos, epsg_por_frame))
    cols = list(contratos.CONTRATOS["cruce_manchas_catalogo"].nombres) + ["inter_ha"]
    df = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame(columns=cols)
    return df, total


def main():
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--manchas", default=os.path.join(AQUI, "..", "data", "salidas", "manchas.geojson"))
    a.add_argument("--catalogo", help="GeoJSON of polygons instead of ../data/catalogos/ (the mock)")
    a.add_argument("--negativos", default="ambos", choices=("ambos", "amba", "mundo"))
    a.add_argument("--todas", action="store_true", help="also cross the discarded blobs")
    a.add_argument("--salida", default=os.path.join(AQUI, "..", "data", "salidas"))
    args = a.parse_args()

    with open(args.manchas, encoding="utf-8") as fh:
        fc = json.load(fh)
    contratos.leer(args.manchas)
    ms = cp.manchas(fc, solo_candidatas=not args.todas)
    if not ms:
        sys.exit("No hay manchas para cruzar.")
    df, n_pol = cruzar_por_frame(ms, fc, (lambda bbox: _catalogo_archivo(args.catalogo)) if args.catalogo
                                 else (lambda bbox: cp.catalogo(bbox, args.negativos)))
    poligonos = range(n_pol)
    destino = contratos.guardar(df, "cruce_manchas_catalogo", args.salida)
    ok = df[df["frac_area_menor"] >= contratos.CRITERIO_CRUCE]
    print(f"{destino}: {len(df)} pares de {df['id_mancha'].nunique()} manchas (de {len(ms)}) con {len(poligonos)} polígonos "
          f"en la caja; {ok['id_mancha'].nunique()} manchas pasan el {contratos.CRITERIO_CRUCE:.0%} "
          f"({ok[ok.catalogo == 'basurales']['id_mancha'].nunique()} con basurales, "
          f"{ok[ok.catalogo == 'negativos']['id_mancha'].nunique()} con negativos)")


if __name__ == "__main__":
    main()
