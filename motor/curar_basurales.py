"""Builds the curated world dump-site catalog in JSON.

Joins four open sources, matches sites by proximity and flags the ones that
are "closed in theory" but show some sign of activity.

Input sources (downloaded to a folder, see `bajar_fuentes()`):
- OpenStreetMap via Overpass: `osm_landuse.json` and `osm_closed.json` (optional `osm_geom.json`).
- Climate TRACE, solid-waste-disposal subsector: `ct_*.json`.
- EPA LMOP (USA): `lmop.xlsx`.
- NASA EMIT L2B CH4PLM v002 (CMR metadata): `emit_p*.json`.

Usage:
    python curar_basurales.py <dir_descargas> ../data/catalogos/basurales
"""

from __future__ import annotations

import glob
import json
import math
import os
import re
import sys
from collections import defaultdict
from datetime import date

HOY = date(2026, 11, 14)
RADIO_CRUCE_M = 1000  # two records closer than this are considered the same site
RADIO_EMIT_M = 1500  # EMIT plume closer than this to the site

FUENTES = {
    "osm": {
        "nombre": "OpenStreetMap (Overpass API)",
        "url": "https://www.openstreetmap.org",
        "licencia": "ODbL 1.0",
        "cita": "© colaboradores de OpenStreetMap",
    },
    "overture": {
        "nombre": "Overture Maps Foundation, release 2026-10-21.0, base/land_use class=landfill",
        "url": "https://docs.overturemaps.org",
        "licencia": "ODbL 1.0 (datos derivados de OpenStreetMap)",
        "cita": "Overture Maps Foundation; © colaboradores de OpenStreetMap",
        "uso": "polígonos y áreas de los sitios OSM",
    },
    "curado_manual": {
        "nombre": "Casos curados a mano por el equipo (data/catalogos/basurales/casos_curados_argentina.json)",
        "url": "ver 'fuentes_documentales' de cada sitio",
        "licencia": "cada nota o documento citado conserva la suya",
        "cita": "fuentes periodísticas y oficiales listadas por sitio",
    },
    "climate_trace": {
        "nombre": "Climate TRACE, subsector solid-waste-disposal (API v6)",
        "url": "https://climatetrace.org/data",
        "licencia": "CC BY 4.0",
        "cita": "Climate TRACE Emissions Inventory, https://climatetrace.org",
    },
    "epa_lmop": {
        "nombre": "EPA Landfill Methane Outreach Program (LMOP) Database",
        "url": "https://www.epa.gov/lmop/lmop-landfill-and-project-database",
        "licencia": "Dominio público (gobierno de EE. UU.)",
        "cita": "U.S. EPA LMOP Landfill and Project Database, lmopcompositedata.xlsx (2024-09)",
    },
    "nasa_emit": {
        "nombre": "NASA EMIT L2B Estimated Methane Plume Complexes 60 m V002",
        "url": "https://doi.org/10.5067/EMIT/EMITL2BCH4PLM.002",
        "licencia": "Sin restricciones de uso (NASA LP DAAC)",
        "cita": "Green, R. et al., EMIT L2B CH4PLM V002, NASA LP DAAC, doi:10.5067/EMIT/EMITL2BCH4PLM.002",
    },
}

ACRE_M2 = 4046.8564224


# ---------------------------------------------------------------- utilidades
def dist_m(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def area_poligono_m2(coords):
    """Approximate geodesic area (local equirectangular projection) of a ring [(lat, lon)]."""
    if len(coords) < 3:
        return None
    lat0 = math.radians(sum(c[0] for c in coords) / len(coords))
    k = 6371000.0
    pts = [(math.radians(lon) * k * math.cos(lat0), math.radians(lat) * k) for lat, lon in coords]
    s = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        s += x1 * y2 - x2 * y1
    return abs(s) / 2


def anio(texto):
    if texto is None:
        return None
    m = re.search(r"(1[89]\d\d|20\d\d)", str(texto))
    return int(m.group(1)) if m else None


def limpio(d):
    return {k: v for k, v in d.items() if v not in (None, "", [], {})}


# ---------------------------------------------------------------- lectores
def leer_osm(dir_in):
    vistos = {}
    geom = {}
    p = os.path.join(dir_in, "osm_geom.json")
    if os.path.exists(p):
        for e in json.load(open(p))["elements"]:
            if e["type"] == "way" and "geometry" in e:
                geom[("way", e["id"])] = area_poligono_m2([(g["lat"], g["lon"]) for g in e["geometry"]])
            elif e["type"] == "relation" and "members" in e:
                tot = 0.0
                for m in e["members"]:
                    if m.get("role") == "outer" and "geometry" in m:
                        tot += area_poligono_m2([(g["lat"], g["lon"]) for g in m["geometry"]]) or 0
                geom[("relation", e["id"])] = tot or None
    rutas = [os.path.join(dir_in, n) for n in ("osm_landuse.json", "osm_closed.json")]
    rutas += sorted(glob.glob(os.path.join(dir_in, "osm_tiles", "t_*.json")))
    for p in rutas:
        if not os.path.exists(p):
            continue
        try:
            elementos = json.load(open(p))["elements"]
        except (json.JSONDecodeError, KeyError):
            print(f"aviso: {p} no es JSON válido, se saltea")
            continue
        for e in elementos:
            vistos[(e["type"], e["id"])] = e
    # Overture Maps (base/land_use, class=landfill): the same OSM objects, already with a polygon.
    p = os.path.join(dir_in, "overture_landfill.parquet")
    if os.path.exists(p):
        import duckdb

        tipos = {"w": "way", "r": "relation", "n": "node"}
        for nombre, lat, lon, area, ds, rid in duckdb.sql(
            f"select nombre, lat, lon, area_m2, src_dataset, src_id from '{p}'"
        ).fetchall():
            m = re.match(r"([nwr])(\d+)", rid or "")
            if ds != "OpenStreetMap" or not m:
                continue
            clave = (tipos[m.group(1)], int(m.group(2)))
            if area:
                geom.setdefault(clave, area)
            if clave not in vistos:
                vistos[clave] = {"type": clave[0], "id": clave[1], "center": {"lat": lat, "lon": lon}, "tags": {"landuse": "landfill", **({"name": nombre} if nombre else {})}, "_overture": True}

    sitios = []
    for (tipo, oid), e in vistos.items():
        t = e.get("tags", {})
        c = e.get("center") or {"lat": e.get("lat"), "lon": e.get("lon")}
        if c.get("lat") is None:
            continue
        fin = t.get("end_date") or t.get("disused:end_date")
        a_fin = anio(fin)
        if any(k in t for k in ("disused:landuse", "abandoned:landuse", "was:landuse")) or t.get("historic") == "landfill":
            estado, motivo = "cerrado", "etiqueta disused/abandoned/was/historic"
        elif t.get("disused") == "yes" or t.get("abandoned") == "yes":
            estado, motivo = "cerrado", "disused=yes / abandoned=yes"
        elif a_fin and a_fin <= HOY.year:
            estado, motivo = "cerrado", f"end_date={fin}"
        elif str(t.get("landfill:status", "")).lower() in ("closed", "inactive", "disused", "capped", "restored"):
            estado, motivo = "cerrado", f"landfill:status={t['landfill:status']}"
        elif str(t.get("landfill:status", "")).lower() in ("active", "operational", "open"):
            estado, motivo = "abierto", f"landfill:status={t['landfill:status']}"
        else:
            estado, motivo = "sin_dato", "landuse=landfill sin etiqueta de estado (OSM no distingue activo de cerrado)"
        sitios.append(
            {
                "fuente": "osm",
                "id_fuente": f"{tipo}/{oid}",
                "url": f"https://www.openstreetmap.org/{tipo}/{oid}",
                "lat": round(c["lat"], 6),
                "lon": round(c["lon"], 6),
                "nombre": t.get("name") or t.get("name:es") or t.get("name:en"),
                "pais": t.get("addr:country") or t.get("is_in:country"),
                "tipo": "informal" if t.get("informal") == "yes" else t.get("landfill:type") or None,
                "estado": estado,
                "estado_motivo": motivo,
                "fecha_apertura": t.get("start_date"),
                "fecha_cierre": fin,
                "operador": t.get("operator"),
                "residuos": t.get("landfill:waste") or t.get("waste"),
                "area_m2": round(geom[(tipo, oid)]) if geom.get((tipo, oid)) else None,
                "area_origen": "polígono OSM (vía Overture Maps)" if geom.get((tipo, oid)) else None,
                "via": "Overture Maps 2026-10-21.0 (solo nombre y geometría, sin etiquetas OSM)" if e.get("_overture") else None,
                "etiquetas": {k: v for k, v in t.items() if not k.startswith(("name:", "source", "wikipedia:", "alt_name:"))},
            }
        )
    return sitios


def leer_climate_trace(dir_in):
    sitios = []
    for p in sorted(glob.glob(os.path.join(dir_in, "ct_*.json"))):
        for a in json.load(open(p))["assets"] or []:
            lon, lat = a["Centroid"]["Geometry"]
            em = (a.get("EmissionsSummary") or [{}])[0]
            tipo = {"Dumpsite": "basural", "Controlled Dumpsite": "basural controlado", "Sanitary Landfill": "relleno sanitario"}.get(
                a.get("AssetType"), a.get("AssetType")
            )
            sitios.append(
                {
                    "fuente": "climate_trace",
                    "id_fuente": str(a["Id"]),
                    "url": f"https://climatetrace.org/explore#asset={a['Id']}",
                    "lat": round(lat, 6),
                    "lon": round(lon, 6),
                    "nombre": a.get("Name"),
                    "pais": a.get("Country"),
                    "tipo": tipo,
                    "estado": "sin_dato",
                    "estado_motivo": "Climate TRACE no publica estado operativo",
                    "area_m2": round(em["Capacity"]) if em.get("CapacityUnits") == "m2" and em.get("Capacity") else None,
                    "area_origen": "Climate TRACE 'Capacity' (m2)" if em.get("Capacity") else None,
                    "emisiones": limpio(
                        {
                            "co2e_100yr_t": round(em["EmissionsQuantity"], 1) if em.get("EmissionsQuantity") is not None else None,
                            "residuos_t": round(em["Activity"]) if em.get("Activity") else None,
                            "ranking_sector": a.get("SectorRanks"),
                            "fuente": "climate_trace",
                        }
                    ),
                }
            )
    return sitios


def leer_lmop(dir_in):
    import openpyxl

    p = os.path.join(dir_in, "lmop.xlsx")
    if not os.path.exists(p):
        return []
    ws = openpyxl.load_workbook(p, read_only=True)["LMOP Database"]
    filas = list(ws.iter_rows(values_only=True))
    H = filas[0]
    por_id = {}
    for f in filas[1:]:
        r = dict(zip(H, f))
        por_id.setdefault(r["Landfill ID"], r)
    sitios = []
    for lid, r in por_id.items():
        if r["Latitude"] is None:
            continue
        est = {"Open": "abierto", "Closed": "cerrado"}.get(r["Current Landfill Status"], "sin_dato")
        area_ac = r["Current Landfill Area (acres)"] or r["Design Landfill Area (acres)"]
        cierre = r["Landfill Closure Year"]
        sitios.append(
            {
                "fuente": "epa_lmop",
                "id_fuente": str(lid),
                "url": "https://www.epa.gov/lmop/lmop-landfill-and-project-database",
                "lat": round(float(r["Latitude"]), 6),
                "lon": round(float(r["Longitude"]), 6),
                "nombre": r["Landfill Name"],
                "pais": "USA",
                "tipo": "relleno sanitario municipal",
                "estado": est,
                "estado_motivo": f"LMOP 'Current Landfill Status'={r['Current Landfill Status']}",
                "fecha_apertura": r["Year Landfill Opened"],
                # LMOP also gives the planned closure year to open ones
                "fecha_cierre": cierre if est == "cerrado" else None,
                "fecha_cierre_prevista": cierre if est == "abierto" else None,
                "operador": r["Landfill Operator Organization"] or r["Landfill Owner Organization(s)"],
                "area_m2": round(area_ac * ACRE_M2) if area_ac else None,
                "area_origen": ("LMOP Current Landfill Area" if r["Current Landfill Area (acres)"] else "LMOP Design Landfill Area") if area_ac else None,
                "residuos_en_sitio_t": r["Waste in Place (tons)"],
                "residuos_anuales_t": r["Annual Waste Acceptance Rate (tons per year)"],
                "residuos_anuales_anio": r["Annual Waste Acceptance Year"],
                "profundidad_actual_ft": r["Current Landfill Depth (feet)"],
                "captura_biogas": r["LFG Collection System In Place?"],
                "localidad": ", ".join(x for x in (r["City"], r["County"], r["State"]) if x),
            }
        )
    return sitios


def leer_curados(ruta):
    """Cases curated by hand (data/catalogos/basurales/casos_curados_argentina.json) with coordinates."""
    if not os.path.exists(ruta):
        return []
    sitios = []
    for c in json.load(open(ruta))["sitios"]:
        if c.get("lat") is None:
            continue
        est = {"cerrado": "cerrado", "abierto": "abierto"}.get(c.get("estado_oficial"), "sin_dato")
        sitios.append(
            {
                "fuente": "curado_manual",
                "id_fuente": c["id"],
                "url": (c.get("fuentes") or [{}])[0].get("url"),
                "lat": c["lat"],
                "lon": c["lon"],
                "nombre": c["nombre"],
                "pais": c.get("pais"),
                "tipo": c.get("tipo"),
                "estado": est,
                "estado_motivo": f"estado oficial documentado: {c.get('estado_oficial')}",
                "fecha_cierre": c.get("fecha_cierre"),
                "area_segun_notas": c.get("area"),
                "senales_documentadas": c.get("senales_cerrado_pero_activo"),
                "fuentes_documentales": c.get("fuentes"),
            }
        )
    return sitios


def leer_emit(dir_in):
    plumas = []
    for p in sorted(glob.glob(os.path.join(dir_in, "emit_p*.json"))):
        for it in json.load(open(p))["items"]:
            u = it["umm"]
            pts = []
            for g in u["SpatialExtent"]["HorizontalSpatialDomain"]["Geometry"].get("GPolygons", []):
                pts += [(q["Latitude"], q["Longitude"]) for q in g["Boundary"]["Points"]]
            if not pts:
                continue
            attrs = {a["Name"]: a["Values"][0] for a in u.get("AdditionalAttributes", [])}
            fecha = u["TemporalExtent"].get("SingleDateTime") or u["TemporalExtent"].get("RangeDateTime", {}).get("BeginningDateTime")
            plumas.append(
                {
                    "granulo": u["GranuleUR"],
                    "plume_id": attrs.get("PLUME_ID"),
                    "fecha": fecha[:10] if fecha else None,
                    "lat": round(sum(q[0] for q in pts) / len(pts), 5),
                    "lon": round(sum(q[1] for q in pts) / len(pts), 5),
                    "_pts": pts,
                }
            )
    return plumas


# ---------------------------------------------------------------- cruce
def agrupar(registros):
    """Joins records from different sources within RADIO_CRUCE_M (single linkage with a grid)."""
    celda = RADIO_CRUCE_M / 111000.0
    grilla = defaultdict(list)
    for i, r in enumerate(registros):
        grilla[(int(r["lat"] // celda), int(r["lon"] // celda))].append(i)
    padre = list(range(len(registros)))

    def raiz(i):
        while padre[i] != i:
            padre[i] = padre[padre[i]]
            i = padre[i]
        return i

    for (gy, gx), idx in grilla.items():
        vecinos = [j for dy in (-1, 0, 1) for dx in (-1, 0, 1) for j in grilla.get((gy + dy, gx + dx), [])]
        for i in idx:
            for j in vecinos:
                if j <= i:
                    continue
                a, b = registros[i], registros[j]
                if dist_m(a["lat"], a["lon"], b["lat"], b["lon"]) <= RADIO_CRUCE_M:
                    # two different OSM objects are different sites even if they are close
                    if a["fuente"] == b["fuente"] == "osm":
                        continue
                    padre[raiz(i)] = raiz(j)
    grupos = defaultdict(list)
    for i in range(len(registros)):
        grupos[raiz(i)].append(registros[i])
    return list(grupos.values())


def plumas_cercanas(lat, lon, plumas, indice):
    celda = 0.05
    res = []
    candidatas = set()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            candidatas.update(indice.get((int(lat // celda) + dy, int(lon // celda) + dx), []))
    for k in sorted(candidatas):
        p = plumas[k]
        d = min(dist_m(lat, lon, q[0], q[1]) for q in p["_pts"])
        if d <= RADIO_EMIT_M:
            res.append({"granulo": p["granulo"], "plume_id": p["plume_id"], "fecha": p["fecha"], "distancia_m": round(d)})
    return sorted(res, key=lambda x: x["fecha"] or "")


PRIORIDAD_NOMBRE = ["curado_manual", "epa_lmop", "osm", "climate_trace"]


def consolidar(grupo, plumas, indice):
    por_f = defaultdict(list)
    for r in grupo:
        por_f[r["fuente"]].append(r)
    lat = sum(r["lat"] for r in grupo) / len(grupo)
    lon = sum(r["lon"] for r in grupo) / len(grupo)

    def primero(campo, orden=PRIORIDAD_NOMBRE):
        for f in orden:
            for r in por_f.get(f, []):
                if r.get(campo):
                    return r[campo], f
        return None, None

    nombre, _ = primero("nombre")
    pais, _ = primero("pais", ["curado_manual", "climate_trace", "epa_lmop", "osm"])
    tipo, tipo_f = primero("tipo", ["climate_trace", "epa_lmop", "osm"])
    area, area_f = primero("area_m2", ["osm", "epa_lmop", "climate_trace"])
    area_origen = next((r.get("area_origen") for r in por_f.get(area_f, []) if r.get("area_m2") == area), None)

    estados = [{"fuente": r["fuente"], "id_fuente": r["id_fuente"], "estado": r["estado"], "motivo": r["estado_motivo"]} for r in grupo]
    dichos = {e["estado"] for e in estados if e["estado"] != "sin_dato"}
    if dichos == {"cerrado"}:
        estado = "cerrado"
    elif dichos == {"abierto"}:
        estado = "abierto"
    elif dichos == {"abierto", "cerrado"}:
        estado = "contradictorio"
    else:
        estado = "desconocido"

    cierre, _ = primero("fecha_cierre", ["curado_manual", "epa_lmop", "osm"])
    a_cierre = anio(cierre)
    pl = plumas_cercanas(lat, lon, plumas, indice)

    senales = []
    if estado == "contradictorio":
        fa = {e["fuente"] for e in estados if e["estado"] == "abierto"}
        fc = {e["fuente"] for e in estados if e["estado"] == "cerrado"}
        if fa != fc or len(fa) > 1:
            senales.append(
                {"tipo": "fuentes_en_desacuerdo", "detalle": f"abierto según {sorted(fa)}, cerrado según {sorted(fc)}", "peso": 2}
            )
        else:
            # same source with neighboring records: typical of an old closed cell next to a new active one
            senales.append(
                {"tipo": "celda_cerrada_junto_a_celda_activa", "detalle": f"{sorted(fa)[0]} lista registros vecinos abiertos y cerrados (probable ampliación del mismo complejo)", "peso": 0}
            )
    if estado == "cerrado" and pl:
        post = [p for p in pl if a_cierre and p["fecha"] and int(p["fecha"][:4]) > a_cierre]
        if post:
            senales.append(
                {
                    "tipo": "metano_emit_despues_del_cierre",
                    "detalle": f"{len(post)} pluma(s) de EMIT posteriores al cierre ({a_cierre}); la última el {post[-1]['fecha']}. "
                    "Ojo: un relleno cerrado sigue emitiendo metano por años, no prueba que reciba residuos.",
                    "peso": 1,
                }
            )
        elif not a_cierre:
            senales.append({"tipo": "metano_emit_en_sitio_cerrado", "detalle": f"{len(pl)} pluma(s) de EMIT; fecha de cierre desconocida", "peso": 1})
    if estado == "cerrado" and "climate_trace" in por_f:
        ct = por_f["climate_trace"][0]
        if ct.get("tipo") in ("basural", "basural controlado"):
            senales.append(
                {
                    "tipo": "climate_trace_lo_modela_como_basural",
                    "detalle": f"Climate TRACE lo lista como '{ct['tipo']}' con residuos estimados de {ct.get('emisiones', {}).get('residuos_t')} t",
                    "peso": 1,
                }
            )
    for r in por_f.get("curado_manual", []):
        for s in r.get("senales_documentadas") or []:
            senales.append({"tipo": s["tipo"], "detalle": s["detalle"], "fuente": s.get("fuente"), "peso": 1 if s.get("evidencia") == "debil" else 2})
    for r in por_f.get("epa_lmop", []):
        # compared within the same record: a group can join several neighboring LMOP landfills
        c = anio(r.get("fecha_cierre"))
        if r["estado"] == "cerrado" and r.get("residuos_anuales_anio") and c and r["residuos_anuales_anio"] > c:
            senales.append(
                {
                    "tipo": "recibe_residuos_despues_del_cierre",
                    "detalle": f"LMOP {r['id_fuente']}: cerrado en {c} pero reporta ingreso de residuos en {r['residuos_anuales_anio']}",
                    "peso": 3,
                }
            )

    fuentes = []
    for r in grupo:
        fuentes.append(
            limpio(
                {
                    "fuente": r["fuente"],
                    "id_fuente": r["id_fuente"],
                    "url": r["url"],
                    "lat": r["lat"],
                    "lon": r["lon"],
                    "distancia_al_centro_m": round(dist_m(lat, lon, r["lat"], r["lon"])),
                    "datos": limpio({k: v for k, v in r.items() if k not in ("fuente", "id_fuente", "url", "lat", "lon", "estado", "estado_motivo")}),
                }
            )
        )
    if pl:
        fuentes.append({"fuente": "nasa_emit", "plumas": pl})

    return limpio(
        {
            "nombre": nombre,
            "pais": pais,
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "tipo": tipo,
            "estado": estado,
            "estados_por_fuente": estados,
            "fecha_apertura": primero("fecha_apertura", ["epa_lmop", "osm"])[0],
            "fecha_cierre": cierre,
            "area_m2": area,
            "area_ha": round(area / 10000, 2) if area else None,
            "area_origen": area_origen,
            "operador": primero("operador", ["epa_lmop", "osm"])[0],
            "residuos": primero("residuos", ["osm"])[0],
            "emisiones_climate_trace": por_f["climate_trace"][0].get("emisiones") if "climate_trace" in por_f else None,
            "plumas_metano_emit": len(pl) or None,
            "ultima_pluma_emit": pl[-1]["fecha"] if pl else None,
            "senales_cerrado_pero_activo": senales,
            "puntaje_sospecha": sum(s["peso"] for s in senales) or None,
            "fuentes": fuentes,
        }
    )


def main(dir_in, dir_out):
    osm = leer_osm(dir_in)
    ct = leer_climate_trace(dir_in)
    lmop = leer_lmop(dir_in)
    plumas = leer_emit(dir_in)
    print(f"OSM {len(osm)}  Climate TRACE {len(ct)}  LMOP {len(lmop)}  plumas EMIT {len(plumas)}")

    indice = defaultdict(list)
    for k, p in enumerate(plumas):
        for q in p["_pts"][:: max(1, len(p["_pts"]) // 20)]:
            indice[(int(q[0] // 0.05), int(q[1] // 0.05))].append(k)
    for v in indice.values():
        v[:] = sorted(set(v))

    curados = leer_curados(os.path.join(dir_out, "casos_curados_argentina.json"))
    grupos = agrupar(osm + ct + lmop + curados)
    sitios = [consolidar(g, plumas, indice) for g in grupos]
    sitios.sort(key=lambda s: (-(s.get("puntaje_sospecha") or 0), s.get("pais") or "", s.get("nombre") or ""))
    for i, s in enumerate(sitios, 1):
        s["id"] = f"BAS-{i:06d}"
        sitios[i - 1] = {"id": s.pop("id"), **s}

    meta = {
        "titulo": "Catálogo curado de basurales y rellenos del mundo",
        "generado": HOY.isoformat(),
        "script": "motor/curar_basurales.py (salida en data/catalogos/basurales/)",
        "fuentes": FUENTES,
        "criterios": {
            "cruce": f"registros de distintas fuentes a menos de {RADIO_CRUCE_M} m se unen en un sitio; dos objetos OSM nunca se unen entre sí",
            "emit": f"pluma de EMIT cuyo contorno pasa a menos de {RADIO_EMIT_M} m del centro del sitio",
            "estado": "cerrado/abierto si todas las fuentes que opinan coinciden; contradictorio si discrepan; desconocido si ninguna opina",
            "puntaje_sospecha": "suma de pesos de las señales 'cerrado pero activo'. Es una priorización para mirar con NISAR, no una acusación",
        },
        "advertencias": [
            "OSM landuse=landfill no distingue activos de cerrados: la mayoría queda en 'desconocido'.",
            "El metano no prueba actividad: un relleno cerrado emite durante décadas.",
            "Las coordenadas son centroides; el área sale de la primera fuente disponible (polígono OSM > LMOP > Climate TRACE).",
            "Ningún sitio se califica de 'ilegal': hablar de 'señal compatible con actividad' hasta verificar.",
        ],
        "conteos": {
            "sitios": len(sitios),
            "por_estado": {e: sum(1 for s in sitios if s["estado"] == e) for e in ("abierto", "cerrado", "contradictorio", "desconocido")},
            "con_senales": sum(1 for s in sitios if s.get("puntaje_sospecha")),
            "registros_por_fuente": {"osm": len(osm), "climate_trace": len(ct), "epa_lmop": len(lmop), "nasa_emit_plumas": len(plumas)},
        },
    }
    os.makedirs(dir_out, exist_ok=True)
    with open(os.path.join(dir_out, "basurales_mundo.json"), "w") as f:
        json.dump({"meta": meta, "sitios": sitios}, f, ensure_ascii=False, separators=(",", ":"))
    cand = [s for s in sitios if s["estado"] in ("cerrado", "contradictorio")]
    with open(os.path.join(dir_out, "basurales_cerrados.json"), "w") as f:
        json.dump(
            {"meta": {**meta, "titulo": "Basurales cerrados o en disputa, ordenados por señales de actividad", "conteos": {"sitios": len(cand)}}, "sitios": cand},
            f,
            ensure_ascii=False,
            indent=1,
        )
    print(json.dumps(meta["conteos"], indent=1))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
