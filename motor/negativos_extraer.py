"""Stage 1 of the negatives catalog: extracts the confuser polygons from Overture Maps.

Reads `base/land_use`, `base/land`, `base/water` and `base/infrastructure` from the given release,
keeps the classes of `../docs/datos.md` with an area between 2 and 500 ha, and
only in the 0.25° cells near dump sites with known status (a proxy for "the same NISAR frames
as the positives"). Saves one parquet per file in <dir_descargas>/neg_parts/.

Usage:
    python negativos_extraer.py <dir_descargas> ../data/catalogos/basurales/basurales_mundo.json
Requires duckdb and anonymous access to s3://overturemaps-us-west-2.
"""

from __future__ import annotations

import json
import os
import sys
import time

import duckdb

RELEASE = "2026-10-21.0"
RAIZ = f"s3://overturemaps-us-west-2/release/{RELEASE}/theme=base"
CELDA = 0.25  # grados
VECINDAD = 1  # cells around each positive (~28 km on each side at the equator)
AREA_MIN_M2, AREA_MAX_M2 = 2e4, 5e6

# (Overture type, SQL condition on subtype/class)
FILTROS = {
    "land_use": """class in ('quarry','salt_pond','construction','greenfield','farmland','farmyard','animal_keeping',
                   'aquaculture','railway','works','industrial','brownfield','airfield','greenhouse_horticulture')""",
    "land": "class in ('wetland','wood','forest','beach','sand','dune','glacier')",
    "water": """class in ('pond','fishpond','reservoir','basin','water_storage','lake','lagoon','oxbow','wastewater',
                'sewage','salt_pond','river','canal')""",
    "infrastructure": "class in ('runway','apron','taxiway','airport','parking','plant','recycling','waste_disposal','silo')",
}
# source_tags (OSM) columns that help refine the class
TAGS = ["resource", "industrial", "product", "plant:source", "generator:source", "man_made", "basin", "wetland",
        "crop", "animal_keeping", "landuse", "natural", "water", "amenity", "recycling_type", "parking", "aeroway",
        "power", "craft", "building", "access", "disused"]


def celdas_positivas(ruta_catalogo):
    d = json.load(open(ruta_catalogo))
    cel = set()
    for s in d["sitios"]:
        if s["estado"] in ("abierto", "cerrado", "contradictorio") or any(
            f["fuente"] == "curado_manual" for f in s.get("fuentes", [])
        ):
            cy, cx = int(s["lat"] // CELDA), int(s["lon"] // CELDA)
            for dy in range(-VECINDAD, VECINDAD + 1):
                for dx in range(-VECINDAD, VECINDAD + 1):
                    cel.add((cy + dy, cx + dx))
    return cel


def main(dir_in, ruta_catalogo):
    out = os.path.join(dir_in, "neg_parts")
    os.makedirs(out, exist_ok=True)
    cel = celdas_positivas(ruta_catalogo)
    print(f"celdas de {CELDA}° cerca de positivos: {len(cel)}", flush=True)

    c = duckdb.connect()
    c.sql("INSTALL httpfs; LOAD httpfs; INSTALL spatial; LOAD spatial; SET geometry_always_xy = true;")
    c.sql("SET memory_limit='5GB'; SET threads=4; SET preserve_insertion_order=false; SET enable_progress_bar=false;")
    c.sql("CREATE SECRET ov (TYPE s3, KEY_ID '', SECRET '', REGION 'us-west-2');")
    c.sql("CREATE TABLE celdas (cy INTEGER, cx INTEGER)")
    c.executemany("INSERT INTO celdas VALUES (?, ?)", sorted(cel))

    t0 = time.time()
    for tipo, cond in FILTROS.items():
        archivos = [r[0] for r in c.sql(f"select file from glob('{RAIZ}/type={tipo}/*')").fetchall()]
        cols = {r[0] for r in c.sql(f"describe select * from read_parquet('{archivos[0]}')").fetchall()}
        tags = (
            "map_from_entries([" + ",".join(f"('{t}', source_tags['{t}'])" for t in TAGS) + "])"
            if "source_tags" in cols
            else "NULL"
        )
        for i, f in enumerate(archivos):
            dest = os.path.join(out, f"{tipo}_{i:03d}.parquet")
            if os.path.exists(dest):
                continue
            c.sql(
                f"""
                COPY (
                  WITH base AS (
                    SELECT id, names.primary AS nombre, subtype, class, geometry,
                           sources[1].record_id AS src_id, sources[1].dataset AS src_dataset, {tags} AS tags,
                           ST_Y(ST_Centroid(geometry)) AS lat, ST_X(ST_Centroid(geometry)) AS lon
                    FROM read_parquet('{f}')
                    WHERE {cond} AND ST_GeometryType(geometry) IN ('POLYGON','MULTIPOLYGON')
                  )
                  SELECT b.id, b.nombre, '{tipo}' AS tipo_overture, b.subtype, b.class, b.src_id, b.src_dataset, b.tags,
                         b.lat, b.lon, ST_Area_Spheroid(b.geometry) AS area_m2,
                         ST_XMin(b.geometry) xmin, ST_YMin(b.geometry) ymin, ST_XMax(b.geometry) xmax, ST_YMax(b.geometry) ymax
                  FROM base b JOIN celdas c ON c.cy = floor(b.lat / {CELDA}) AND c.cx = floor(b.lon / {CELDA})
                  WHERE ST_Area_Spheroid(b.geometry) BETWEEN {AREA_MIN_M2} AND {AREA_MAX_M2}
                ) TO '{dest}'
                """
            )
            n = c.sql(f"select count(*) from '{dest}'").fetchall()[0][0]
            print(f"{tipo} {i + 1}/{len(archivos)} {n} filas {round(time.time() - t0)}s", flush=True)
    print("listo", round(time.time() - t0), "s")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
