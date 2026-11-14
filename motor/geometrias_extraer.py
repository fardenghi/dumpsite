"""Baja de Overture Maps los polígonos de los sitios de los catálogos de basurales y de negativos.

Lee los ids de `data/basurales/basurales_mundo.json` (objetos OSM, que se cruzan con el id de
Overture usando `overture_landfill.parquet`) y de `data/negativos/negativos_*.json`
(`poligono.overture_id`). Baja solo esos polígonos, los simplifica a ~10 m y deja un parquet por
archivo de Overture en <dir_descargas>/geom_parts/.

Uso:
    python geometrias_extraer.py <dir_descargas> ../../data
"""

from __future__ import annotations

import json
import os
import re
import sys
import time

import duckdb

RELEASE = "2026-10-21.0"
RAIZ = f"s3://overturemaps-us-west-2/release/{RELEASE}/theme=base"
TOLERANCIA_GRADOS = 0.0001  # ~10 m: muy por debajo de la resolución de NISAR (20-80 m)


def ids_necesarios(dir_in, dir_data):
    """Devuelve filas (overture_id, tipo_overture, catalogo, id_catalogo)."""
    filas = []
    # basurales: OSM -> Overture vía la extracción de landfills
    osm_a_bas = {}
    for s in json.load(open(os.path.join(dir_data, "basurales", "basurales_mundo.json")))["sitios"]:
        for f in s.get("fuentes", []):
            if f["fuente"] == "osm":
                osm_a_bas[f["id_fuente"]] = s["id"]
    tipos = {"w": "way", "r": "relation", "n": "node"}
    for oid, rid in duckdb.sql(f"select id, src_id from '{os.path.join(dir_in, 'overture_landfill.parquet')}'").fetchall():
        m = re.match(r"([nwr])(\d+)", rid or "")
        if m:
            clave = f"{tipos[m.group(1)]}/{m.group(2)}"
            if clave in osm_a_bas:
                filas.append((oid, "land_use", "basurales", osm_a_bas[clave]))
    # negativos: el id de Overture ya está en el registro
    for nombre in ("negativos_mundo.json", "negativos_amba.json"):
        cat = nombre.replace(".json", "")
        for s in json.load(open(os.path.join(dir_data, "negativos", nombre)))["sitios"]:
            p = s["poligono"]
            filas.append((p["overture_id"], p["overture_tipo"], cat, s["id"]))
    return filas


def main(dir_in, dir_data):
    out = os.path.join(dir_in, "geom_parts")
    os.makedirs(out, exist_ok=True)
    filas = ids_necesarios(dir_in, dir_data)
    print("polígonos a bajar:", len(filas), flush=True)

    c = duckdb.connect()
    c.sql("INSTALL httpfs; LOAD httpfs; INSTALL spatial; LOAD spatial; SET geometry_always_xy = true;")
    c.sql("SET memory_limit='5GB'; SET threads=4; SET preserve_insertion_order=false; SET enable_progress_bar=false;")
    c.sql("CREATE SECRET ov (TYPE s3, KEY_ID '', SECRET '', REGION 'us-west-2');")
    c.sql("CREATE TABLE pedidos (oid VARCHAR, tipo VARCHAR, catalogo VARCHAR, id_catalogo VARCHAR)")
    c.executemany("INSERT INTO pedidos VALUES (?, ?, ?, ?)", filas)

    t0 = time.time()
    for tipo in ("land_use", "land", "water", "infrastructure"):
        if not c.sql(f"select count(*) from pedidos where tipo = '{tipo}'").fetchall()[0][0]:
            continue
        archivos = [r[0] for r in c.sql(f"select file from glob('{RAIZ}/type={tipo}/*')").fetchall()]
        for i, f in enumerate(archivos):
            dest = os.path.join(out, f"{tipo}_{i:03d}.parquet")
            if os.path.exists(dest):
                continue
            c.sql(
                f"""
                COPY (
                  SELECT p.catalogo, p.id_catalogo, o.id AS overture_id,
                         ST_AsWKB(ST_SimplifyPreserveTopology(o.geometry, {TOLERANCIA_GRADOS})) AS wkb
                  FROM read_parquet('{f}') o JOIN pedidos p ON p.oid = o.id AND p.tipo = '{tipo}'
                ) TO '{dest}'
                """
            )
            n = c.sql(f"select count(*) from '{dest}'").fetchall()[0][0]
            print(f"{tipo} {i + 1}/{len(archivos)} {n} polígonos {round(time.time() - t0)}s", flush=True)
    print("listo", round(time.time() - t0), "s")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
