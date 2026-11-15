"""Builds the geometry files from what `geometrias_extraer.py` downloaded.

For each catalog it writes a GeoJSON and, if the GeoJSON is over 50 MB, a GeoParquet instead.
Each feature links to the catalog by `id`. Sites without a polygon (those that come only from the
EPA or Climate TRACE, and the closed OSM ones that Overture doesn't have) go as points, with
`geometria = "punto"`.

Usage:
    python geometrias_armar.py <dir_descargas> ../data/catalogos/
"""

from __future__ import annotations

import glob
import json
import os
import sys

import duckdb

LIMITE_GEOJSON = 50 * 1024 * 1024

SALIDAS = {
    "basurales": ("basurales/basurales_mundo.json", "basurales/geometrias"),
    "negativos_mundo": ("negativos/negativos_mundo.json", "negativos/geometrias_mundo"),
    "negativos_amba": ("negativos/negativos_amba.json", "negativos/geometrias_amba"),
}


def propiedades(catalogo, s):
    if catalogo == "basurales":
        return {"id": s["id"], "nombre": s.get("nombre"), "estado": s["estado"], "tipo": s.get("tipo"),
                "area_ha": s.get("area_ha"), "puntaje_sospecha": s.get("puntaje_sospecha")}
    return {"id": s["id"], "nombre": s.get("nombre"), "clase": s["clase"], "prioridad": s["prioridad"],
            "rol": s["rol"], "area_ha": s.get("area_ha"), "confianza": s.get("confianza")}


def main(dir_in, dir_data):
    partes = sorted(glob.glob(os.path.join(dir_in, "geom_parts", "*.parquet")))
    c = duckdb.connect()
    c.sql("INSTALL spatial; LOAD spatial; SET geometry_always_xy = true;")
    c.sql(f"CREATE TABLE g AS SELECT * FROM read_parquet({partes!r})")
    resumen = {}
    for catalogo, (ruta_cat, base_out) in SALIDAS.items():
        sitios = json.load(open(os.path.join(dir_data, ruta_cat)))["sitios"]
        # A dump site can be made of several OSM objects (or one object split into
        # several Overture features): they are all merged into one geometry. It used to keep only the
        # first one, and the rest of the site fell into the control ring.
        geoms = dict(
            c.sql(
                f"""select id_catalogo,
                           ST_AsGeoJSON(ST_MakeValid(ST_Union_Agg(ST_MakeValid(ST_GeomFromWKB(wkb)))))
                    from g where catalogo = '{catalogo}' group by id_catalogo"""
            ).fetchall()
        )
        feats = []
        for s in sitios:
            props = propiedades(catalogo, s)
            if s["id"] in geoms:
                props["geometria"] = "poligono"
                geom = json.loads(geoms[s["id"]])
            else:
                props["geometria"] = "punto"
                geom = {"type": "Point", "coordinates": [s["lon"], s["lat"]]}
            feats.append({"type": "Feature", "id": s["id"], "properties": props, "geometry": geom})
        fc = {
            "type": "FeatureCollection",
            "name": os.path.basename(base_out),
            "fuente": "Overture Maps 2026-10-21.0 (OSM, ODbL 1.0, © colaboradores de OpenStreetMap); simplificado a ~10 m",
            "catalogo": ruta_cat,
            "features": feats,
        }
        texto = json.dumps(fc, ensure_ascii=False, separators=(",", ":"))
        n_pol = sum(1 for f in feats if f["properties"]["geometria"] == "poligono")
        if len(texto.encode()) <= LIMITE_GEOJSON:
            dest = os.path.join(dir_data, base_out + ".geojson")
            open(dest, "w").write(texto)
        else:
            dest = os.path.join(dir_data, base_out + ".parquet")
            # one feature per line, with the geometry as GeoJSON text
            tmp = os.path.join(dir_in, f"_{catalogo}.ndjson")
            with open(tmp, "w") as fh:
                for f in feats:
                    fh.write(json.dumps({**f["properties"], "geom": json.dumps(f["geometry"])}, ensure_ascii=False) + "\n")
            c.sql(
                f"""COPY (
                      SELECT * EXCLUDE (geom), ST_GeomFromGeoJSON(geom) AS geometry
                      FROM read_json('{tmp}', format='newline_delimited', columns={{
                        'id':'VARCHAR','nombre':'VARCHAR','clase':'VARCHAR','prioridad':'VARCHAR','rol':'VARCHAR',
                        'area_ha':'DOUBLE','confianza':'VARCHAR','geometria':'VARCHAR','geom':'VARCHAR'}})
                    ) TO '{dest}' (FORMAT parquet)"""
            )
            os.remove(tmp)
        resumen[catalogo] = {"archivo": os.path.relpath(dest, dir_data), "sitios": len(feats), "con_poligono": n_pol,
                             "mb": round(os.path.getsize(dest) / 1e6, 1)}
    print(json.dumps(resumen, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
