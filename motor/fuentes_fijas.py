"""Downloads and prepares the fixed sources used by `pipeline_insomnio.py indice`, for any frame. Needs the network.

  python fuentes_fijas.py agua      [--frame X]   JRC Global Surface Water mask over the frame's grid
  python fuentes_fijas.py usos      [--frame X]   polygons of known land uses (airfields, golf, parks, ...) from Overture Maps
  python fuentes_fijas.py catalogo  [--frame X]   polygons of `data/catalogos/basurales/` and `data/catalogos/negativos/` that fall in the frame (offline)
  python fuentes_fijas.py cobertura [--frame X]   urban and cropland fraction from ESA WorldCover (model context, stage 4)
  python fuentes_fijas.py todo      [--frame X]   the four things
  python fuentes_fijas.py sitios                  OpenStreetMap outlines of the sites in sitios_registro.json (AMBA only)

The frame comes from `../data/catalogos/frames.json` or from `--caja lon_west lat_south lon_east lat_north` (with `--frame NAME`).
The results are cached per frame in `fijos/<FRAME>/` (not committed: `indice` rebuilds them only if they're missing).
The AMBA ones are committed, loose in `fijos/`: they're the reference ones of `../docs/indice-insomnio.md` (the land uses, from
Nominatim) and with them `indice` needs no network. To rebuild them pass `--pisar`.

Sources:
- JRC Global Surface Water v1.4 (1984-2021), `occurrence` layer. Pekel, Cottam, Gorelick and Belward (2016),
  Nature 540, 418-422, doi:10.1038/nature20584. Data from EC JRC / Google, free use with citation.
  https://global-surface-water.appspot.com/download
- Overture Maps, release 2026-10-21.0, `base` theme (`land_use`, `land`, `infrastructure`). The data is
  © OpenStreetMap contributors, ODbL 1.0 license. https://docs.overturemaps.org/
- © OpenStreetMap contributors, ODbL 1.0 license. Geometries via the OSM API and Nominatim (AMBA sites and land uses).
- ESA WorldCover 10 m 2021 v200. Zanaga et al. (2022), doi:10.5281/zenodo.7254221. © ESA WorldCover project,
  CC BY 4.0 license. https://esa-worldcover.org/
- Catalogs in `data/` (see `../data/README.md`): Overture/OSM (ODbL), Climate TRACE (CC BY 4.0), EPA LMOP and NASA EMIT.
"""
import argparse
import json
import os
import struct
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import geo  # noqa: E402

RAIZ = os.path.dirname(AQUI)
FIJOS = os.path.join(AQUI, "fijos")
DATA = os.path.join(RAIZ, "data", "catalogos")
AGENTE = {"User-Agent": "insomnes-contornos/0.1"}
JRC = "https://storage.googleapis.com/global-surface-water/downloads2021/occurrence/occurrence_{}v1_4_2021.tif"
JRC_PASO, JRC_LADO = 0.00025, 40000  # pixel size in degrees and pixels per side of a 10° × 10° tile
JRC_NORTE, JRC_OESTE = 80.0, -180.0  # northwest corner of the world mosaic (tiles are named by their northwest corner)
WORLDCOVER = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_{}_Map.tif"
PASOS = {"80m": 80.0, "20m": 20.0}
OVERTURE = "2026-10-21.0"
OVERTURE_RAIZ = f"s3://overturemaps-us-west-2/release/{OVERTURE}/theme=base"
# Known land uses that also give permanently low coherence: (Nominatim search, OSM class, OSM type, label).
USOS = [("aerodrome", "aeroway", "aerodrome", "aeródromo"), ("golf course", "leisure", "golf_course", "golf"),
        ("park", "leisure", "park", "parque"), ("cemetery", "landuse", "cemetery", "cementerio"),
        ("quarry", "landuse", "quarry", "cantera"), ("forest", "landuse", "forest", "forestación"),
        ("nature reserve", "leisure", "nature_reserve", "reserva")]
# The same land uses in Overture: (layer, SQL condition, label). Order matters: if two overlap, the first wins,
# that's why the most specific go first and the reserves (which can be huge) last. `militar` is new.
USOS_OVERTURE = [
    ("infrastructure", "subtype = 'airport' AND class LIKE '%airport%'", "aeródromo"),
    ("land_use", "class = 'airfield'", "aeródromo"),
    ("land_use", "class = 'golf_course'", "golf"),
    ("land_use", "class = 'park'", "parque"),
    ("land_use", "class = 'cemetery'", "cementerio"),
    ("land_use", "class = 'quarry'", "cantera"),
    ("land", "subtype = 'forest'", "forestación"),
    ("land_use", "subtype = 'military' AND class <> 'airfield'", "militar"),
    ("land_use", "subtype = 'protected'", "reserva"),
]
USO_MIN_HA = 2.0  # less than this doesn't reach 4 pixels of 80 m
MARGEN_CATALOGO = 0.03  # degrees (~3 km): polygons outside the box that enter the ring of a site on the edge


def carpeta(fr, base=None):
    """Where a frame's fixed sources are cached. The AMBA uses plain `fijos/` (the reference files)."""
    base = base or FIJOS
    return base if fr.nombre == "AMBA" else os.path.join(base, fr.nombre)


def pedir(url, pausa=1.2):
    with urllib.request.urlopen(urllib.request.Request(url, headers=AGENTE), timeout=120) as r:
        datos = json.load(r)
    time.sleep(pausa)  # the OSM usage policy asks for at most one request per second
    return datos


def _guardar_json(ruta, datos):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as fh:
        json.dump(datos, fh, ensure_ascii=False, separators=(",", ":"))
        fh.write("\n")


# ------------------------------------------------------------------ agua
def tile_jrc(fila, columna):
    """JRC tile name by its northwest corner: `60W_30S`, `120W_40N`, `70E_30N`, `0E_0N`."""
    lon, lat = int(JRC_OESTE) + 10 * columna, int(JRC_NORTE) - 10 * fila
    return f"{abs(lon)}{'W' if lon < 0 else 'E'}_{abs(lat)}{'S' if lat < 0 else 'N'}"


def _leer_tile(nombre, tif=None):
    """Water occurrence (% of months, uint8; 255 = no data) of a tile, or None if JRC doesn't publish it (open sea)."""
    import tifffile

    ruta = tif or os.path.join(tempfile.gettempdir(), os.path.basename(JRC.format(nombre)))
    if not os.path.exists(ruta):
        print("Bajando", JRC.format(nombre))
        try:
            urllib.request.urlretrieve(JRC.format(nombre), ruta + ".parcial")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise
        os.replace(ruta + ".parcial", ruta)
    return tifffile.imread(ruta)


def ocurrencia_jrc(fr, tif=None):
    """Crop of the JRC `occurrence` layer covering the frame's box, with a margin. Returns (crop, row0, column0)
    in world mosaic indices. If the box crosses tiles, it joins them. A tile JRC doesn't publish counts as water."""
    norte, oeste, sur, este = fr.caja
    f0, f1 = int((JRC_NORTE - norte) / JRC_PASO) - 800, int((JRC_NORTE - sur) / JRC_PASO) + 800
    c0, c1 = int((oeste - JRC_OESTE) / JRC_PASO) - 800, int((este - JRC_OESTE) / JRC_PASO) + 800
    rec = np.zeros((f1 - f0, c1 - c0), dtype=np.uint8)
    tiles = [(tf, tc) for tf in range(f0 // JRC_LADO, (f1 - 1) // JRC_LADO + 1) for tc in range(c0 // JRC_LADO, (c1 - 1) // JRC_LADO + 1)]
    if tif and len(tiles) > 1:
        sys.exit(f"La caja de {fr.nombre} cruza {len(tiles)} tiles de JRC: no se puede usar --tif.")
    for tf, tc in tiles:
        nombre = tile_jrc(tf, tc)
        tile = _leer_tile(nombre, tif)
        a0, a1 = max(f0, tf * JRC_LADO), min(f1, (tf + 1) * JRC_LADO)
        b0, b1 = max(c0, tc * JRC_LADO), min(c1, (tc + 1) * JRC_LADO)
        if tile is None:
            print(f"  JRC no publica el tile {nombre} (mar abierto): cuenta como agua")
            rec[a0 - f0:a1 - f0, b0 - c0:b1 - c0] = 100
        else:
            rec[a0 - f0:a1 - f0, b0 - c0:b1 - c0] = tile[a0 - tf * JRC_LADO:a1 - tf * JRC_LADO, b0 - tc * JRC_LADO:b1 - tc * JRC_LADO]
        del tile
    return np.where(rec == 255, 0, rec).astype(np.float32), f0, c0, [tile_jrc(*t) for t in tiles]


def agua(fr, capas=("80m", "20m"), destino=None, tif=None):
    """JRC water mask over the frame's grid: `agua_jrc_<capa>.npz` with the % occurrence per cell."""
    destino = destino or carpeta(fr)
    os.makedirs(destino, exist_ok=True)
    rec, f0, c0, tiles = ocurrencia_jrc(fr, tif)
    for capa in capas:
        paso = PASOS[capa]
        xs, ys = fr.grilla(paso)
        k = max(1, int(round(paso / 20)))  # subsampling: the JRC cell is about 25 m
        desvios = (np.arange(k) + 0.5) / k * paso - paso / 2
        suma = np.zeros((len(ys), len(xs)), dtype=np.float32)
        for dy in desvios:
            for dx in desvios:
                lat, lon = fr.latlon(xs[None, :] + dx, ys[:, None] + dy)
                f = np.clip(np.floor((JRC_NORTE - lat) / JRC_PASO).astype(int) - f0, 0, rec.shape[0] - 1)
                c = np.clip(np.floor((lon - JRC_OESTE) / JRC_PASO).astype(int) - c0, 0, rec.shape[1] - 1)
                suma += rec[f, c]
        media = np.rint(suma / (k * k)).astype(np.uint8)
        ruta = os.path.join(destino, f"agua_jrc_{capa}.npz")
        np.savez_compressed(ruta, ocurrencia=media, fuente=f"JRC Global Surface Water v1.4, occurrence 1984-2021, tile {', '.join(tiles)}")
        print(f"{ruta}: {media.shape}, {os.path.getsize(ruta) / 1e3:.0f} kB, celdas con ocurrencia >= 10 %: {(media >= 10).mean():.1%}")


# ------------------------------------------------------------------ contornos de OSM
def anillos_osm(objeto):
    """Exterior rings (lon, lat) of a way or a multipolygon relation, via the OSM API."""
    datos = pedir(f"https://api.openstreetmap.org/api/0.6/{objeto}/full.json")["elements"]
    nodos = {e["id"]: (round(e["lon"], 6), round(e["lat"], 6)) for e in datos if e["type"] == "node"}
    ways = {e["id"]: e["nodes"] for e in datos if e["type"] == "way"}
    tipo, ident = objeto.split("/")
    principal = next(e for e in datos if e["type"] == tipo and e["id"] == int(ident))
    if tipo == "way":
        tramos = [ways[int(ident)]]
    else:
        tramos = [ways[m["ref"]] for m in principal["members"] if m["type"] == "way" and m.get("role") in ("outer", "")]
    anillos, tramos = [], [list(t) for t in tramos]
    while tramos:  # joins the segments end to end until each ring closes
        actual = tramos.pop(0)
        while actual[0] != actual[-1]:
            for i, t in enumerate(tramos):
                if t[0] == actual[-1]:
                    actual += tramos.pop(i)[1:]
                    break
                if t[-1] == actual[-1]:
                    actual += tramos.pop(i)[-2::-1]
                    break
            else:
                break
        if actual[0] == actual[-1] and len(actual) >= 4:
            anillos.append([list(nodos[n]) for n in actual])
    return anillos, principal.get("tags", {})


def sitios(args):
    with open(os.path.join(AQUI, "sitios_registro.json"), encoding="utf-8") as fh:
        registro = json.load(fh)["sitios"]
    salida = {}
    for s in registro:
        if "osm" not in s:
            continue
        anillos, etiquetas = [], {}
        for objeto in s["osm"]:
            a, t = anillos_osm(objeto)
            anillos += a
            etiquetas = etiquetas or t
        ha = sum(geo.area_y_centro(a)[0] for a in anillos)
        lat, lon = geo.area_y_centro(max(anillos, key=lambda a: geo.area_y_centro(a)[0]))[1]
        lugar = pedir(f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=jsonv2&zoom=12&accept-language=es")
        d = lugar.get("address", {})
        salida[s["id"]] = {"osm": s["osm"], "etiquetas": etiquetas, "anillos": anillos,
                           "lugar_osm": d.get("city") or d.get("town") or d.get("village") or d.get("suburb") or d.get("county") or ""}
        print(f"{s['id']:24s} {len(anillos)} anillo(s), {ha:6.1f} ha, {salida[s['id']]['lugar_osm']}")
    with open(os.path.join(FIJOS, "contornos_osm.json"), "w", encoding="utf-8") as fh:
        json.dump({"fuente": "© colaboradores de OpenStreetMap, ODbL 1.0 (API de OSM y Nominatim)", "bajado": time.strftime("%Y-%m-%d"), "sitios": salida},
                  fh, ensure_ascii=False, separators=(",", ":"))


# ------------------------------------------------------------------ usos conocidos
def _exteriores(geometria):
    """Exterior rings (lon, lat) of a GeoJSON Polygon or MultiPolygon, with 5 decimals (~1 m)."""
    partes = [geometria["coordinates"]] if geometria.get("type") == "Polygon" else geometria.get("coordinates", []) if geometria.get("type") == "MultiPolygon" else []
    return [[[round(p[0], 5), round(p[1], 5)] for p in parte[0]] for parte in partes if parte and len(parte[0]) >= 4]


def usos(fr, destino=None):
    """The frame's known land uses, from Overture Maps (OSM data), exhaustive within the box. Needs `duckdb` and the network.

    Same format as the AMBA Nominatim file: `{"usos": [{"osm", "uso", "nombre", "anillos"}]}`.
    """
    import duckdb

    destino = destino or carpeta(fr)
    norte, oeste, sur, este = fr.caja
    c = duckdb.connect()
    c.sql("INSTALL httpfs; LOAD httpfs; INSTALL spatial; LOAD spatial; SET geometry_always_xy = true; SET enable_progress_bar = false;")
    c.sql("CREATE SECRET ov (TYPE s3, KEY_ID '', SECRET '', REGION 'us-west-2');")
    tipos = {"w": "way", "r": "relation", "n": "node"}
    salida, vistos, cuenta = [], set(), {}
    for capa, condicion, etiqueta in USOS_OVERTURE:
        filas = c.sql(f"""
            SELECT id, names.primary, sources[1].record_id, ST_AsGeoJSON(ST_SimplifyPreserveTopology(geometry, 0.0001))
            FROM read_parquet('{OVERTURE_RAIZ}/type={capa}/*', hive_partitioning = 1)
            WHERE bbox.xmin <= {este} AND bbox.xmax >= {oeste} AND bbox.ymin <= {norte} AND bbox.ymax >= {sur}
              AND ({condicion}) AND ST_GeometryType(geometry) IN ('POLYGON', 'MULTIPOLYGON')
              AND ST_Area_Spheroid(geometry) >= {USO_MIN_HA * 1e4}
            ORDER BY id""").fetchall()
        for ident, nombre, registro, gj in filas:
            if ident in vistos:
                continue
            vistos.add(ident)
            anillos = _exteriores(json.loads(gj))
            if not anillos:
                continue
            m = (registro or "")[:1], (registro or "")[1:].split("@")[0]
            osm = f"{tipos[m[0]]}/{m[1]}" if m[0] in tipos and m[1].isdigit() else f"overture/{ident}"
            salida.append({"osm": osm, "uso": etiqueta, "nombre": nombre or "", "anillos": anillos})
            cuenta[etiqueta] = cuenta.get(etiqueta, 0) + 1
    for etiqueta, n in cuenta.items():
        print(f"{etiqueta:12s} {n} polígonos")
    ruta = os.path.join(destino, "usos_osm.json")
    _guardar_json(ruta, {"fuente": f"Overture Maps {OVERTURE}, tema base (© colaboradores de OpenStreetMap, ODbL 1.0)",
                         "bajado": time.strftime("%Y-%m-%d"), "frame": fr.nombre, "min_ha": USO_MIN_HA,
                         "advertencia": "Todos los polígonos de esas clases que tocan la caja del frame y miden 2 ha o más. "
                                        "OSM puede estar incompleto o desactualizado.",
                         "usos": salida})
    print(f"{ruta}: {len(salida)} polígonos, {os.path.getsize(ruta) / 1e3:.0f} kB")


# ------------------------------------------------------------------ catalog polygons
def _wkb_exteriores(b):
    """Exterior rings (lon, lat) of a Polygon or MultiPolygon in WKB (the negatives GeoParquet)."""
    def poligono(pos):
        orden = "<" if b[pos] == 1 else ">"
        tipo, = struct.unpack_from(orden + "I", b, pos + 1)
        pos += 5
        if tipo % 1000 == 6:  # MultiPolygon
            n, = struct.unpack_from(orden + "I", b, pos)
            pos += 4
            salida = []
            for _ in range(n):
                anillos, pos = poligono(pos)
                salida += anillos
            return salida, pos
        if tipo % 1000 != 3:
            raise ValueError(f"WKB de tipo {tipo}: se esperaba Polygon o MultiPolygon")
        dim = 2 + (tipo // 1000 in (1, 2)) + 2 * (tipo // 1000 == 3)
        n_anillos, = struct.unpack_from(orden + "I", b, pos)
        pos += 4
        exterior = None
        for i in range(n_anillos):
            n, = struct.unpack_from(orden + "I", b, pos)
            pos += 4
            if i == 0:
                exterior = np.frombuffer(b, dtype=orden + "f8", count=n * dim, offset=pos).reshape(n, dim)[:, :2]
            pos += 8 * n * dim
        return ([exterior] if exterior is not None and len(exterior) >= 4 else []), pos

    return [np.round(a, 5).tolist() for a in poligono(0)[0]]


def catalogo(fr, destino=None, data=DATA):
    """The polygons of the catalogs in `data/` that fall in the frame (with a ~3 km margin), in a small file.

    It's used for two things: each site's ring excludes all these polygons (`insomnio.anillo`), and the VM can
    run without the 100 MB of `data/`. It needs no network. It includes the dump sites with a polygon (those with only a
    point can't be rasterized) and the negatives from `geometrias_amba.geojson` and `geometrias_mundo.parquet`.
    """
    destino = destino or carpeta(fr)
    norte, oeste, sur, este = fr.caja
    norte, sur, oeste, este = norte + MARGEN_CATALOGO, sur - MARGEN_CATALOGO, oeste - MARGEN_CATALOGO, este + MARGEN_CATALOGO

    def toca(anillos):
        lon, lat = np.array([q[:2] for a in anillos for q in a]).T
        return lon.min() <= este and lon.max() >= oeste and lat.min() <= norte and lat.max() >= sur

    salida = []
    with open(os.path.join(data, "basurales", "geometrias.geojson"), encoding="utf-8") as fh:
        basurales = json.load(fh)["features"]
    with open(os.path.join(data, "basurales", "complejos.json"), encoding="utf-8") as fh:
        complejos = json.load(fh)
    complejo = complejos["complejo_por_sitio"]
    estado_complejo = {c["id"]: c.get("estado") for c in complejos.get("complejos", [])}
    del complejos
    for f in basurales:
        anillos = _exteriores(f["geometry"] or {})
        if anillos and toca(anillos):
            p = f["properties"]
            salida.append({"id": p["id"], "catalogo": "basurales", "nombre": p.get("nombre") or "", "estado": p.get("estado"),
                           "complejo": complejo.get(p["id"]), "estado_complejo": estado_complejo.get(complejo.get(p["id"])),
                           "area_ha": p.get("area_ha"), "anillos": anillos})
    del basurales
    vistos = set()
    ruta_amba = os.path.join(data, "negativos", "geometrias_amba.geojson")
    if os.path.exists(ruta_amba):
        with open(ruta_amba, encoding="utf-8") as fh:
            for f in json.load(fh)["features"]:
                anillos = _exteriores(f["geometry"] or {})
                if anillos and toca(anillos):
                    p = f["properties"]
                    vistos.add(p["id"])
                    salida.append({"id": p["id"], "catalogo": "negativos", "nombre": p.get("nombre") or "", "clase": p.get("clase"),
                                   "prioridad": p.get("prioridad"), "rol": p.get("rol"), "area_ha": p.get("area_ha"), "anillos": anillos})
    ruta_mundo = os.path.join(data, "negativos", "geometrias_mundo.parquet")
    if os.path.exists(ruta_mundo):
        import pyarrow.parquet as pq

        for p in pq.read_table(ruta_mundo).to_pylist():
            if p["id"] in vistos or not p.get("geometry"):
                continue
            anillos = _wkb_exteriores(p["geometry"])
            if anillos and toca(anillos):
                salida.append({"id": p["id"], "catalogo": "negativos", "nombre": p.get("nombre") or "", "clase": p.get("clase"),
                               "prioridad": p.get("prioridad"), "rol": p.get("rol"), "area_ha": p.get("area_ha"), "anillos": anillos})
    ruta = os.path.join(destino, "catalogo.json")
    n = {c: sum(1 for x in salida if x["catalogo"] == c) for c in ("basurales", "negativos")}
    _guardar_json(ruta, {"fuente": "data/catalogos/basurales/geometrias.geojson, data/catalogos/negativos/geometrias_amba.geojson y geometrias_mundo.parquet "
                                   "(Overture Maps 2026-10-21.0: © colaboradores de OpenStreetMap, ODbL 1.0; ver data/README.md)",
                         "armado": time.strftime("%Y-%m-%d"), "frame": fr.nombre, "bbox": fr.bbox, "margen_grados": MARGEN_CATALOGO,
                         "conteo": n, "poligonos": salida})
    print(f"{ruta}: {n['basurales']} basurales y {n['negativos']} negativos, {os.path.getsize(ruta) / 1e3:.0f} kB")


# ------------------------------------------------------------------ land cover
def tile_worldcover(lat, lon):
    """Name of the 3° × 3° ESA WorldCover tile containing a point, by its southwest corner: `N33W120`, `S36W060`."""
    la, lo = int(np.floor(lat / 3) * 3), int(np.floor(lon / 3) * 3)
    return f"{'S' if la < 0 else 'N'}{abs(la):02d}{'W' if lo < 0 else 'E'}{abs(lo):03d}"


def cobertura(fr, destino=None, capa="80m"):
    """Urban (class 50) and cropland (class 40) fraction of each grid cell, according to ESA WorldCover 2021 (10 m).

    Writes `worldcover_<capa>.npz` with `urbano` and `cultivo` in % (uint8). They're the model's context columns
    (`urbano_anillo`, `cultivo_anillo`). Downloads one or more ~100 MB tiles to the temp folder.
    """
    import tifffile

    destino = destino or carpeta(fr)
    os.makedirs(destino, exist_ok=True)
    paso = PASOS[capa]
    xs, ys = fr.grilla(paso)
    k = 4  # 4 × 4 points per 80 m cell: one every 20 m
    desvios = (np.arange(k) + 0.5) / k * paso - paso / 2
    urbano = np.zeros((len(ys), len(xs)), dtype=np.float32)
    cultivo = np.zeros_like(urbano)
    visto = np.zeros_like(urbano)
    norte, oeste, sur, este = fr.caja
    tiles = sorted({tile_worldcover(la, lo) for la in (norte + 0.05, sur - 0.05) for lo in (oeste - 0.05, este + 0.05)})
    for nombre in tiles:
        ruta = os.path.join(tempfile.gettempdir(), WORLDCOVER.format(nombre).rsplit("/", 1)[1])
        if not os.path.exists(ruta):
            print("Bajando", WORLDCOVER.format(nombre))
            try:
                urllib.request.urlretrieve(WORLDCOVER.format(nombre), ruta + ".parcial")
            except urllib.error.HTTPError as e:
                if e.code in (403, 404):  # WorldCover doesn't publish open-sea tiles
                    print(f"  WorldCover no publica el tile {nombre}")
                    continue
                raise
            os.replace(ruta + ".parcial", ruta)
        tile = tifffile.imread(ruta)  # 36000 × 36000, uint8: the class of each 10 m pixel
        lat0 = (-1 if nombre[0] == "S" else 1) * int(nombre[1:3]) + 3  # borde norte
        lon0 = (-1 if nombre[3] == "W" else 1) * int(nombre[4:7])  # borde oeste
        for dy in desvios:
            for dx in desvios:
                lat, lon = fr.latlon(xs[None, :] + dx, ys[:, None] + dy)
                f = np.floor((lat0 - lat) * 12000).astype(int)
                c = np.floor((lon - lon0) * 12000).astype(int)
                ok = (f >= 0) & (f < tile.shape[0]) & (c >= 0) & (c < tile.shape[1])
                clase = tile[f[ok], c[ok]]
                urbano[ok] += clase == 50
                cultivo[ok] += clase == 40
                visto[ok] += 1
        del tile
    with np.errstate(invalid="ignore", divide="ignore"):
        urbano = np.where(visto > 0, np.rint(100 * urbano / visto), 255).astype(np.uint8)
        cultivo = np.where(visto > 0, np.rint(100 * cultivo / visto), 255).astype(np.uint8)
    ruta = os.path.join(destino, f"worldcover_{capa}.npz")
    np.savez_compressed(ruta, urbano=urbano, cultivo=cultivo, sin_dato=np.uint8(255),
                        fuente=f"ESA WorldCover 10 m 2021 v200 (CC BY 4.0), tiles {', '.join(tiles)}; clase 50 = urbano, clase 40 = cultivo")
    print(f"{ruta}: urbano {urbano[urbano < 255].mean():.0f} %, cultivo {cultivo[cultivo < 255].mean():.0f} %, {os.path.getsize(ruta) / 1e3:.0f} kB")


def usos_nominatim(args):
    """The original version, AMBA only: what the Nominatim search returns. It isn't exhaustive."""
    norte, oeste, sur, este = geo.CAJA
    salida, vistos = [], set()
    for consulta, clase, tipo, etiqueta in USOS:
        hallados, excluir = [], []
        for _ in range(8):  # the search returns 50 at a time
            q = {"q": consulta, "viewbox": f"{oeste},{norte},{este},{sur}", "bounded": 1, "format": "jsonv2", "limit": 50}
            if excluir:
                q["exclude_place_ids"] = ",".join(map(str, excluir))
            r = pedir("https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(q))
            nuevos = [x for x in r if x["place_id"] not in excluir]
            if not nuevos:
                break
            excluir += [x["place_id"] for x in nuevos]
            hallados += [x for x in nuevos if x["category"] == clase and x["type"] == tipo and x["osm_type"] in ("way", "relation")]
        ids = sorted({x["osm_type"][0].upper() + str(x["osm_id"]) for x in hallados} - vistos)
        vistos |= set(ids)
        n = 0
        for i in range(0, len(ids), 50):
            r = pedir("https://nominatim.openstreetmap.org/lookup?" + urllib.parse.urlencode(
                {"osm_ids": ",".join(ids[i:i + 50]), "format": "json", "polygon_geojson": 1, "accept-language": "es"}))
            for x in r:
                g = x.get("geojson", {})
                partes = [g["coordinates"]] if g.get("type") == "Polygon" else g.get("coordinates", []) if g.get("type") == "MultiPolygon" else []
                anillos = [[[round(lon, 5), round(lat, 5)] for lon, lat in p[0]] for p in partes]
                if anillos:
                    salida.append({"osm": f"{x['osm_type']}/{x['osm_id']}", "uso": etiqueta, "nombre": x.get("name") or "", "anillos": anillos})
                    n += 1
        print(f"{etiqueta:12s} {n} polígonos")
    with open(os.path.join(FIJOS, "usos_osm.json"), "w", encoding="utf-8") as fh:
        json.dump({"fuente": "© colaboradores de OpenStreetMap, ODbL 1.0 (Nominatim)", "bajado": time.strftime("%Y-%m-%d"),
                   "advertencia": "No es exhaustivo: es lo que devuelve la búsqueda de Nominatim dentro de la caja del AMBA.",
                   "usos": salida}, fh, ensure_ascii=False, separators=(",", ":"))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("paso", choices=["agua", "sitios", "usos", "catalogo", "cobertura", "todo", "usos_nominatim"])
    p.add_argument("--frame", nargs="+", default=["AMBA"], help="one or more frames from data/catalogos/frames.json, or `todos`")
    p.add_argument("--caja", type=float, nargs=4, metavar=("LON_O", "LAT_S", "LON_E", "LAT_N"), help="box of a frame that isn't in frames.json (goes with a single --frame NAME)")
    p.add_argument("--epsg", type=int, help="EPSG of the grid, with --caja (otherwise, the one in the pipeline's frame.json or that of the center's UTM zone)")
    p.add_argument("--salida", default=os.path.join(RAIZ, "data", "salidas"), help="pipeline output folder: it looks for <FRAME>/frame.json there")
    p.add_argument("--capas", nargs="+", choices=list(PASOS), default=["80m"], help="layers of the water mask (default: 80 m only)")
    p.add_argument("--destino", help="folder to write to (default: fijos/<FRAME>/)")
    p.add_argument("--pisar", action="store_true", help="allows rebuilding the AMBA reference files")
    p.add_argument("--tif", help="JRC tile already downloaded (otherwise it downloads it to the temp folder)")
    args = p.parse_args()
    os.makedirs(FIJOS, exist_ok=True)
    if args.paso in ("sitios", "usos_nominatim"):
        globals()[args.paso](args)
        return
    nombres = list(geo.frames_conocidos()) if args.frame == ["todos"] else args.frame
    for nombre in nombres:
        if args.caja:
            guardado = os.path.join(args.salida, nombre.upper(), "frame.json")
            fr = geo.frame(nombre, os.path.dirname(guardado)) if os.path.exists(guardado) and not args.epsg else geo.frame_de_caja(nombre, args.caja, args.epsg)
        else:
            fr = geo.frame(nombre, os.path.join(args.salida, nombre.upper()))
        if fr.nombre == "AMBA" and not args.destino and not args.pisar and args.paso not in ("catalogo", "cobertura"):
            sys.exit("Los archivos de fijos/ del AMBA son los de referencia de ../docs/indice-insomnio.md. Pasá --destino para "
                     "escribir en otro lado, o --pisar para rehacerlos (los usos pasan de Nominatim a Overture).")
        print(f"== {fr.nombre}: caja {fr.bbox}, EPSG {fr.epsg}")
        if args.paso in ("agua", "todo"):
            agua(fr, tuple(args.capas), args.destino, args.tif)
        if args.paso in ("usos", "todo"):
            usos(fr, args.destino)
        if args.paso in ("catalogo", "todo"):
            catalogo(fr, args.destino)
        if args.paso in ("cobertura", "todo"):
            cobertura(fr, args.destino)


if __name__ == "__main__":
    main()
