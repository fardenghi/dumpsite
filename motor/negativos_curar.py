"""Etapa 2 del catálogo de negativos: clasifica, filtra y muestrea los confusores.

Toma los parquet de `negativos_extraer.py`, asigna a cada polígono una clase de
`idea/negativos-dataset.md`, descarta lo que está a menos de 500 m de un basural del catálogo
y arma dos archivos con el mismo estilo que el catálogo de positivos:
- `negativos_mundo.json`: muestra balanceada por clase y por celda de 1°, cerca de positivos.
- `negativos_amba.json`: todos los confusores del AMBA (con tope por clase).

Uso:
    python negativos_curar.py <dir_descargas> ../../data/basurales/basurales_mundo.json ../../data/negativos
"""

from __future__ import annotations

import glob
import hashlib
import json
import math
import os
import sys
from collections import Counter, defaultdict
from datetime import date

import duckdb

HOY = date(2026, 11, 14)
DIST_MIN_BASURAL_M = 500
AMBA = {"lat_min": -35.2, "lat_max": -34.2, "lon_min": -59.5, "lon_max": -57.8}
TOPE_AMBA_POR_CLASE = 150
CUPO_POR_CELDA = {"A": 6, "B": 3, "C": 2}  # por clase y por celda de 1°

CLASES = {
    # clase: (prioridad, grupo, rol)
    "agua_permanente": ("A", "agua", "mascara"),
    "humedal": ("A", "agua", "negativo"),
    "laguna_chica": ("A", "agua", "negativo"),
    "pileta_efluentes": ("A", "agua", "negativo"),
    "arrozal": ("B", "agua", "negativo"),
    "acuicultura": ("B", "agua", "negativo"),
    "salina": ("C", "agua", "negativo"),
    "cantera": ("A", "suelo", "negativo"),
    "tosquera_arenera": ("A", "suelo", "negativo"),
    "obra": ("A", "suelo", "negativo"),
    "ladrillera": ("B", "suelo", "negativo"),
    "escombrera_acopio": ("B", "suelo", "negativo"),
    "chatarreria_desguace": ("C", "suelo", "negativo"),
    "planta_residuos": ("B", "residuos", "negativo"),
    "cultivo": ("A", "agro", "negativo"),
    "feedlot": ("A", "agro", "negativo"),
    "vegetacion_densa": ("B", "agro", "negativo"),
    "aeropuerto": ("B", "infraestructura", "mascara"),
    "puerto_playa_contenedores": ("B", "infraestructura", "negativo"),
    "estacionamiento_playa": ("B", "infraestructura", "negativo"),
    "acopio_granos": ("C", "infraestructura", "negativo"),
    "parque_solar": ("C", "infraestructura", "mascara"),
    "arena_duna_playa": ("B", "naturaleza", "negativo"),
    "nieve_hielo": ("C", "naturaleza", "mascara"),
}

PENDIENTES = {
    "ruta_via": {"prioridad": "A", "rol": "mascara", "por_que_no_esta": "son líneas, no polígonos: se aplican como buffer", "fuente": "OSM highway=motorway/trunk/primary, railway=rail (Overture transportation/segment)"},
    "agua_permanente_grande": {"prioridad": "A", "rol": "mascara", "por_que_no_esta": "más de 500 ha: va como máscara, no como ejemplo", "fuente": "JRC Global Surface Water (occurrence) y OSM natural=water"},
    "tala_quema": {"prioridad": "C", "rol": "negativo", "por_que_no_esta": "no está en OSM; depende de la fecha", "fuente": "NASA FIRMS (focos de calor) y Global Forest Watch tree cover loss"},
    "asentamiento_en_crecimiento": {"prioridad": "C", "rol": "negativo", "por_que_no_esta": "no está en OSM como polígono de crecimiento", "fuente": "GHSL (Copernicus)"},
    "cauce_movil": {"prioridad": "C", "rol": "negativo", "por_que_no_esta": "se detecta por cambio en el tiempo", "fuente": "JRC GSW transitions"},
    "layover_sombra": {"prioridad": "B", "rol": "mascara", "por_que_no_esta": "depende de la geometría del radar", "fuente": "capa mask del GUNW y Copernicus DEM 30 m"},
    "escombrera_acopio": {"prioridad": "B", "rol": "negativo", "por_que_no_esta": "casi no está etiquetado en OSM (man_made=stockpile); hacen falta detecciones manuales", "fuente": "detección manual"},
}

FUENTES = {
    "overture": {
        "nombre": "Overture Maps Foundation, release 2026-10-21.0, tema base (land_use, land, water, infrastructure)",
        "url": "https://docs.overturemaps.org",
        "licencia": "ODbL 1.0 (datos derivados de OpenStreetMap)",
        "cita": "Overture Maps Foundation; © colaboradores de OpenStreetMap",
    },
    "catalogo_basurales": {
        "nombre": "Catálogo curado de basurales del equipo",
        "url": "data/basurales/basurales_mundo.json",
        "uso": "excluir negativos a menos de 500 m de un basural e inferir el país",
    },
}

ARENAS = {"sand", "gravel", "clay", "soil", "earth", "aggregate", "tosca", "loam", "sand;gravel", "gravel;sand"}


def clasificar(tipo, clase, tags):
    t = {k: (v or "").lower() for k, v in (tags or {}).items() if v}
    if tipo == "land_use":
        if clase == "quarry":
            return ("tosquera_arenera" if t.get("resource") in ARENAS else "cantera"), "alta"
        if clase == "salt_pond":
            return "salina", "media"
        if clase in ("construction", "greenfield"):
            return "obra", "media"
        if clase == "farmland":
            return ("arrozal" if "rice" in t.get("crop", "") else "cultivo"), "media"
        if clase in ("farmyard", "animal_keeping"):
            # un farmyard no siempre es un feedlot: confianza baja salvo que diga el animal
            return "feedlot", "media" if t.get("animal_keeping") or "cow" in t.get("building", "") else "baja"
        if clase == "aquaculture":
            return "acuicultura", "media"
        if clase == "railway":
            return "estacionamiento_playa", "media"
        if clase == "airfield":
            return "aeropuerto", "media"
        if clase == "works":
            if "compost" in t.get("product", ""):
                return "planta_residuos", "media"
            if t.get("man_made") == "wastewater_plant":
                return "pileta_efluentes", "media"
            if "brick" in t.get("product", ""):
                return "ladrillera", "media"
            return None, None
        if clase == "industrial":
            ind = t.get("industrial", "")
            if ind in ("scrap_yard", "scrapyard", "car_scrapyard"):
                return "chatarreria_desguace", "media"
            if "brick" in ind or t.get("craft") == "brickmaker":
                return "ladrillera", "media"
            if ind in ("port", "container_terminal", "harbour"):
                return "puerto_playa_contenedores", "media"
            if ind in ("depot", "stockpile", "aggregate"):
                return "escombrera_acopio", "baja"
            if t.get("man_made") == "wastewater_plant" or ind == "wastewater_plant":
                return "pileta_efluentes", "media"
            return None, None
        return None, None
    if tipo == "land":
        if clase == "wetland":
            return "humedal", "media"
        if clase in ("wood", "forest"):
            return "vegetacion_densa", "media"
        if clase in ("beach", "sand", "dune"):
            return "arena_duna_playa", "media"
        if clase == "glacier":
            return "nieve_hielo", "media"
        return None, None
    if tipo == "water":
        if clase in ("wastewater", "sewage") or t.get("water") == "wastewater" or t.get("basin") in ("sewage", "wastewater", "settling"):
            return "pileta_efluentes", "media"
        if clase == "fishpond":
            return "acuicultura", "media"
        if clase == "salt_pond":
            return "salina", "media"
        if clase in ("river", "canal"):
            return "agua_permanente", "media"
        if clase in ("pond", "reservoir", "basin", "water_storage", "lake", "lagoon", "oxbow"):
            return "laguna_chica", "media"
        return None, None
    if tipo == "infrastructure":
        if clase in ("runway", "apron", "taxiway", "airport"):
            return "aeropuerto", "media"
        if clase == "parking":
            return "estacionamiento_playa", "media"
        if clase == "plant":
            if "solar" in (t.get("plant:source", "") + t.get("generator:source", "")):
                return "parque_solar", "media"
            return None, None
        if clase in ("recycling", "waste_disposal"):
            return "planta_residuos", "media"
        if clase == "silo":
            return "acopio_granos", "baja"
    return None, None


def dist_m(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def osm_url(src_id):
    if not src_id:
        return None, None
    tipo = {"w": "way", "r": "relation", "n": "node"}.get(src_id[0])
    num = src_id[1:].split("@")[0]
    if not tipo or not num.isdigit():
        return None, None
    return f"{tipo}/{num}", f"https://www.openstreetmap.org/{tipo}/{num}"


def hash_orden(s):
    return hashlib.sha1(s.encode()).hexdigest()


def main(dir_in, ruta_catalogo, dir_out):
    cat = json.load(open(ruta_catalogo))["sitios"]
    # índice de basurales (todos, con o sin estado) para la distancia mínima
    celda_b = 0.05
    idx = defaultdict(list)
    for s in cat:
        r = math.sqrt((s.get("area_m2") or 0) / math.pi)
        idx[(int(s["lat"] // celda_b), int(s["lon"] // celda_b))].append((s["lat"], s["lon"], r, s["id"], s.get("nombre"), s.get("pais")))

    def basural_cercano(lat, lon):
        mejor = None
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                for la, lo, r, i, n, p in idx.get((int(lat // celda_b) + dy, int(lon // celda_b) + dx), []):
                    d = dist_m(lat, lon, la, lo) - r
                    if mejor is None or d < mejor[0]:
                        mejor = (d, i, n, p)
        return mejor

    # país inferido: el del positivo con país más cercano (celda de 1°)
    paises = defaultdict(list)
    for s in cat:
        if s.get("pais"):
            paises[(int(s["lat"] // 1), int(s["lon"] // 1))].append((s["lat"], s["lon"], s["pais"]))

    def pais_inferido(lat, lon):
        mejor = None
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                for la, lo, p in paises.get((int(lat // 1) + dy, int(lon // 1) + dx), []):
                    d = (la - lat) ** 2 + (lo - lon) ** 2
                    if mejor is None or d < mejor[0]:
                        mejor = (d, p)
        return mejor[1] if mejor else None

    partes = sorted(glob.glob(os.path.join(dir_in, "neg_parts", "*.parquet")))
    filas = duckdb.sql(
        f"select id, nombre, tipo_overture, subtype, class, src_id, src_dataset, tags, lat, lon, area_m2, xmin, ymin, xmax, ymax "
        f"from read_parquet({partes!r})"
    ).fetchall()
    print("polígonos extraídos:", len(filas))

    disponibles, excluidos = Counter(), Counter()
    pool = []
    vistos = set()
    for (oid, nombre, tipo, sub, clase, src_id, src_ds, tags, lat, lon, area, xmin, ymin, xmax, ymax) in filas:
        if oid in vistos:
            continue
        vistos.add(oid)
        cl, conf = clasificar(tipo, clase, tags)
        if not cl:
            continue
        disponibles[cl] += 1
        rn = math.sqrt(area / math.pi)
        bc = basural_cercano(lat, lon)
        if bc and bc[0] - rn < DIST_MIN_BASURAL_M:
            excluidos[cl] += 1
            continue
        pool.append((cl, conf, oid, nombre, tipo, clase, src_id, src_ds, tags, lat, lon, area, (xmin, ymin, xmax, ymax), bc))

    def registro(p):
        cl, conf, oid, nombre, tipo, clase, src_id, src_ds, tags, lat, lon, area, bb, bc = p
        prio, grupo, rol = CLASES[cl]
        id_osm, url = osm_url(src_id) if src_ds == "OpenStreetMap" else (None, None)
        t = {k: v for k, v in (tags or {}).items() if v}
        return {
            "clase": cl,
            "grupo": grupo,
            "prioridad": prio,
            "rol": rol,
            "nombre": nombre,
            "pais": pais_inferido(lat, lon),
            "pais_origen": "inferido del basural con país más cercano",
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "area_ha": round(area / 1e4, 2),
            "bbox": [round(v, 6) for v in bb],
            "poligono": {"overture_id": oid, "overture_tipo": tipo, "overture_clase": clase, "osm": id_osm},
            "frame_nisar": None,
            "fuente": "overture",
            "id_fuente": id_osm or oid,
            "url": url,
            "licencia": "ODbL 1.0",
            "confianza": conf,
            "basural_mas_cercano": {"id": bc[1], "nombre": bc[2], "distancia_borde_m": round(max(0, bc[0] - math.sqrt(area / math.pi)))} if bc else None,
            "etiquetas_osm": t or None,
            "notas": None,
        }

    def en_amba(p):
        return AMBA["lat_min"] <= p[9] <= AMBA["lat_max"] and AMBA["lon_min"] <= p[10] <= AMBA["lon_max"]

    # AMBA: todo, con tope por clase
    amba, por_clase = [], Counter()
    for p in sorted((p for p in pool if en_amba(p)), key=lambda p: hash_orden(p[2])):
        if por_clase[p[0]] < TOPE_AMBA_POR_CLASE:
            por_clase[p[0]] += 1
            amba.append(registro(p))

    # mundo: cupo por clase y celda de 1°, orden reproducible por hash
    mundo, cupo = [], Counter()
    for p in sorted(pool, key=lambda p: hash_orden(p[2])):
        k = (p[0], int(p[9] // 1), int(p[10] // 1))
        if cupo[k] < CUPO_POR_CELDA[CLASES[p[0]][0]]:
            cupo[k] += 1
            mundo.append(registro(p))

    for lista, pref in ((mundo, "NEG"), (amba, "NEG-AMBA")):
        lista.sort(key=lambda r: (r["prioridad"], r["clase"], r["pais"] or "", r["lat"]))
        for i, r in enumerate(lista, 1):
            r_id = f"{pref}-{i:06d}"
            lista[i - 1] = {"id": r_id, **r}

    meta = {
        "titulo": "Catálogo de negativos: lo que el radar puede confundir con un basural",
        "generado": HOY.isoformat(),
        "documento": "idea-basurales-nisar/idea/negativos-dataset.md",
        "scripts": ["idea-basurales-nisar/herramientas/negativos_extraer.py", "idea-basurales-nisar/herramientas/negativos_curar.py"],
        "fuentes": FUENTES,
        "clases": {k: {"prioridad": v[0], "grupo": v[1], "rol": v[2]} for k, v in CLASES.items()},
        "clases_pendientes": PENDIENTES,
        "criterios": {
            "area": "entre 2 y 500 ha",
            "distancia": f"borde a borde a más de {DIST_MIN_BASURAL_M} m de cualquier sitio del catálogo de basurales (radio equivalente al área)",
            "zona": "celdas de 0,25° vecinas a un basural con estado conocido o curado (proxy de los mismos frames de NISAR)",
            "muestra_mundo": f"cupo por clase y celda de 1°: A={CUPO_POR_CELDA['A']}, B={CUPO_POR_CELDA['B']}, C={CUPO_POR_CELDA['C']}; orden reproducible por hash del id",
            "amba": f"bbox {AMBA}; hasta {TOPE_AMBA_POR_CLASE} por clase",
            "rol": "negativo = ejemplo de entrenamiento; mascara = se filtra antes del modelo, se incluye para validar la máscara",
            "confianza": "alta: etiqueta OSM específica (p. ej. quarry con resource); media: etiqueta OSM directa; baja: la clase es una aproximación (farmyard como feedlot, silo como acopio)",
        },
        "advertencias": [
            "frame_nisar queda vacío: se asigna cuando se bajan los frames.",
            "El país se infiere del basural más cercano con país; puede fallar en fronteras.",
            "OSM puede tener polígonos desactualizados: una obra terminada sigue como construction.",
            "farmyard no es siempre feedlot: revisar los de confianza baja antes de entrenar.",
            "Validar separando por ciudad o frame, no por sitio, para evitar fuga de datos.",
        ],
        "conteos": {
            "poligonos_clasificados": dict(sorted(disponibles.items())),
            "excluidos_por_cercania_a_basural": dict(sorted(excluidos.items())),
            "mundo_por_clase": dict(sorted(Counter(r["clase"] for r in mundo).items())),
            "amba_por_clase": dict(sorted(Counter(r["clase"] for r in amba).items())),
            "mundo": len(mundo),
            "amba": len(amba),
        },
    }
    os.makedirs(dir_out, exist_ok=True)
    json.dump({"meta": meta, "sitios": mundo}, open(os.path.join(dir_out, "negativos_mundo.json"), "w"), ensure_ascii=False, separators=(",", ":"))
    json.dump(
        {"meta": {**meta, "titulo": meta["titulo"] + " (AMBA)"}, "sitios": amba},
        open(os.path.join(dir_out, "negativos_amba.json"), "w"),
        ensure_ascii=False,
        indent=1,
    )
    print(json.dumps(meta["conteos"], indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
