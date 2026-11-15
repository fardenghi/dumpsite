"""Stage 2: picks the NISAR frames where the model is trained and evaluated, and builds `data/catalogos/frames.json`.

For each candidate area (fixed cities + the 1° cells with the most known-status dump sites):
  1. queries the public ASF API (no login) for the `PR` GUNWs that touch it;
  2. groups by NISAR track and frame and keeps those that cover the area (up to 2 tracks, preferably one
     ascending and one descending, like the AMBA);
  3. counts, within the area and the footprint of those frames:
     - dump sites of 10 ha or more by status, grouped by complex (`basurales/complejos.json`);
     - negatives by class (`rol = negativo`), and separately the class A ones of 10 ha or more;
     - GUNW pairs and date range.
Then it sorts by priority (see `puntaje`) and picks ~10 frames without staying only in the USA.

    python frames_elegir.py                     # queries ASF, writes ../data/catalogos/frames.json and datos/frames-elegidos.md
    python frames_elegir.py --cache /tmp/asf    # saves/reuses the ASF responses
    python frames_elegir.py --n 10 --max-usa 5
    python frames_elegir.py --agregar 20        # leaves the already chosen frames as they are and adds 20 by number of open sites

`--agregar N` (prompt 6) doesn't choose again: it reads `frames.json`, keeps its frames with the same name, the same box and
the same priority, and adds N more, with priority from there on. The candidates are the 1° cells with the most
**open** dump sites of 10 ha or more with a polygon (per site, not per complex; score 2 × open + closed),
without counting those that already fall in a chosen box. Each one's box is shrunk to its dump sites plus 5 km. Those
with at least 15 `PR` GUNW pairs that don't touch an already chosen box get in. There's no USA cap.

Assumptions (noted in `meta`): an area is a box of ~1° around the city (the AMBA's is `geo.CAJA`);
a frame "covers" the area if its footprint contains at least `--min-cobertura` of the box; the EPSG comes from the UTM zone
of the area's center (the GUNW grid uses the frame's; it has to be confirmed with the `projection` dataset).
"""
import argparse
import collections
import datetime as dt
import json
import math
import os
import re
import sys
import time
import urllib.parse
import urllib.request

import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
DATA = os.path.join(RAIZ, "data", "catalogos")
sys.path.insert(0, AQUI)
import geo  # noqa: E402

API_ASF = "https://api.daac.asf.alaska.edu/services/search/param"
EEUU = {"USA", "PRI", "VIR", "GUM", "ASM", "MNP"}  # USA and territories: the status comes from the EPA in all of them

# frame, city, country, box [west, south, east, north]. The AMBA uses the pipeline's box (geo.CAJA, another order).
_N, _O, _S, _E = geo.CAJA
CIUDADES = [
    ("AMBA", "Buenos Aires", "ARG", [_O, _S, _E, _N]),
    ("DELHI", "Delhi", "IND", [76.85, 28.35, 77.55, 28.95]),
    ("CDMX", "Ciudad de México", "MEX", [-99.40, 19.15, -98.80, 19.75]),
    ("LAGOS", "Lagos", "NGA", [3.05, 6.35, 3.75, 6.80]),
    ("NAIROBI", "Nairobi", "KEN", [36.60, -1.50, 37.15, -1.05]),
    ("YAKARTA", "Yakarta", "IDN", [106.55, -6.55, 107.20, -5.95]),
    ("LOS_ANGELES", "Los Ángeles", "USA", [-118.70, 33.70, -117.60, 34.40]),
    ("NUEVA_YORK", "Nueva York", "USA", [-74.40, 40.45, -73.60, 41.05]),
]


# ---------------------------------------------------------------- geometry
def wkt_anillo(wkt):
    """Primer anillo (lon, lat) de un POLYGON en WKT."""
    nums = re.findall(r"(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)", wkt)
    return np.array([[float(a), float(b)] for a, b in nums])


def dentro_poligono(lon, lat, anillo):
    """Even-odd rule, vectorized over points."""
    lon, lat = np.asarray(lon, float), np.asarray(lat, float)
    adentro = np.zeros(lon.shape, dtype=bool)
    for (x1, y1), (x2, y2) in zip(anillo, np.roll(anillo, -1, axis=0)):
        if y1 == y2:
            continue
        cruza = (y1 > lat) != (y2 > lat)
        with np.errstate(divide="ignore", invalid="ignore"):
            adentro ^= cruza & (lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1)
    return adentro


def en_caja(lon, lat, caja):
    o, s, e, n = caja
    lon, lat = np.asarray(lon, float), np.asarray(lat, float)
    return (lon >= o) & (lon <= e) & (lat >= s) & (lat <= n)


def cobertura(caja, anillo, n=15):
    """Fraction of an n×n grid of points of the box that falls inside the footprint."""
    o, s, e, nn = caja
    lon, lat = np.meshgrid(np.linspace(o, e, n), np.linspace(s, nn, n))
    return float(dentro_poligono(lon.ravel(), lat.ravel(), anillo).mean())


def epsg(caja):
    lon, lat = (caja[0] + caja[2]) / 2, (caja[1] + caja[3]) / 2
    zona = int((lon + 180) // 6) + 1
    return (32600 if lat >= 0 else 32700) + zona, "N" if lat >= 0 else "S"


# ---------------------------------------------------------------- ASF
def consultar_asf(caja, cache=None, reintentos=3):
    o, s, e, n = caja
    wkt = f"POLYGON(({o} {s},{e} {s},{e} {n},{o} {n},{o} {s}))"
    params = {"dataset": "NISAR", "processingLevel": "GUNW", "intersectsWith": wkt, "output": "jsonlite", "maxResults": "5000"}
    url = API_ASF + "?" + urllib.parse.urlencode(params)
    archivo = None
    if cache:
        os.makedirs(cache, exist_ok=True)
        archivo = os.path.join(cache, "asf_" + "_".join(f"{v:.2f}" for v in caja) + ".json")
        if os.path.exists(archivo):
            with open(archivo, encoding="utf-8") as fh:
                return json.load(fh)
    for i in range(reintentos):
        try:
            with urllib.request.urlopen(url, timeout=180) as r:
                res = json.load(r)["results"]
            break
        except Exception as ex:  # noqa: BLE001 (the API sometimes cuts off; we retry)
            if i == reintentos - 1:
                raise
            print(f"  ASF falló ({ex}); reintento", file=sys.stderr)
            time.sleep(5 * (i + 1))
    if archivo:
        with open(archivo, "w", encoding="utf-8") as fh:
            json.dump(res, fh)
    return res


def pares_por_frame(resultados):
    """Groups the PR GUNWs by (track, direction, frame): unique pairs, dates and footprint."""
    grupos = {}
    for g in resultados:
        nombre = g.get("granuleName", "")
        if g.get("productType") != "GUNW" or "_PR_GUNW_" not in nombre or not g.get("wkt"):
            continue
        fechas = re.findall(r"_(\d{8})T\d{6}", nombre)
        if len(fechas) < 3:
            continue
        ref, sec = fechas[0], fechas[2]
        direccion = (g.get("flightDirection") or "?")[0]
        clave = (int(g["path"]), direccion, int(g["frame"]))
        gr = grupos.setdefault(clave, {"pares": {}, "huella": None, "cobertura_frame": set()})
        rango = ("_F_" in nombre, nombre[-3:])
        par = (ref, sec)
        if par not in gr["pares"] or rango > gr["pares"][par]:
            gr["pares"][par] = rango
        if gr["huella"] is None or "_F_" in nombre:
            gr["huella"] = wkt_anillo(g["wkt"])
    return grupos


def elegir_tracks(caja, grupos, min_cob, max_tracks=2):
    """The (track, dir, frame) that cover the box, sorted by pairs; up to max_tracks, preferably from different directions."""
    ok = []
    for clave, g in grupos.items():
        c = cobertura(caja, g["huella"])
        if c >= min_cob:
            ok.append((len(g["pares"]), c, clave))
    ok.sort(reverse=True)
    elegidos = []
    for n, c, clave in ok:  # first one per direction
        if clave[0] not in [e[0] for e in elegidos] and clave[1] not in [e[1] for e in elegidos]:
            elegidos.append(clave)
        if len(elegidos) == max_tracks:
            break
    for n, c, clave in ok:  # if one is missing, any other track
        if len(elegidos) < max_tracks and clave not in elegidos and clave[0] not in [e[0] for e in elegidos]:
            elegidos.append(clave)
    return elegidos, {clave: c for n, c, clave in ok}


# ---------------------------------------------------------------- catalogs
def cargar_catalogos():
    with open(os.path.join(DATA, "basurales", "complejos.json"), encoding="utf-8") as fh:
        cx = json.load(fh)
    complejos = [c for c in cx["complejos"] if c.get("lat") is not None]
    negs = {}
    for nombre in ("negativos_mundo.json", "negativos_amba.json"):
        with open(os.path.join(DATA, "negativos", nombre), encoding="utf-8") as fh:
            d = json.load(fh)
        for s in d.get("sitios") or d.get("negativos") or []:
            if s.get("rol") == "negativo" and s.get("lat") is not None:
                negs[s["id"]] = s
    return complejos, list(negs.values())


def celdas_conocidas(complejos, n, lado=0.9):
    """The n 1° cells with the most complexes of 10 ha or more with known status (open or closed).

    Each cell becomes a box of `lado` degrees centered on the center of those complexes (a box smaller
    than the cell is more often covered by a single NISAR frame).
    """
    por_celda = collections.defaultdict(list)
    for c in complejos:
        if c["estado"] in ("abierto", "cerrado") and (c.get("area_ha_suma") or 0) >= 10:
            por_celda[(math.floor(c["lon"]), math.floor(c["lat"]))].append(c)
    salida = []
    for (lo, la), cs in sorted(por_celda.items(), key=lambda kv: -len(kv[1]))[:n]:
        clon, clat = np.mean([c["lon"] for c in cs]), np.mean([c["lat"] for c in cs])
        caja = [clon - lado / 2, clat - lado / 2, clon + lado / 2, clat + lado / 2]
        salida.append((lo, la, len(cs), [round(v, 3) for v in caja], max(cs, key=lambda c: c.get("area_ha_suma") or 0)))
    return salida


def se_tocan(a, b):
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def contar(caja, huellas, complejos, negativos):
    def adentro(lon, lat):
        m = en_caja(lon, lat, caja)
        cubre = np.zeros_like(m)
        for h in huellas:
            cubre |= dentro_poligono(lon, lat, h)
        return m & cubre

    clon = np.array([c["lon"] for c in complejos])
    clat = np.array([c["lat"] for c in complejos])
    sel = adentro(clon, clat)
    por_estado = {"abierto": 0, "cerrado": 0, "desconocido": 0, "contradictorio": 0}
    paises = collections.Counter()
    for c, s in zip(complejos, sel):
        if s and (c.get("area_ha_suma") or 0) >= 10:
            por_estado[c["estado"]] += 1
    nlon = np.array([x["lon"] for x in negativos])
    nlat = np.array([x["lat"] for x in negativos])
    seln = adentro(nlon, nlat)
    por_clase, a10 = collections.Counter(), 0
    for x, s in zip(negativos, seln):
        if s:
            por_clase[x["clase"]] += 1
            a10 += x.get("prioridad") == "A" and (x.get("area_ha") or 0) >= 10
            paises[x.get("pais")] += 1
    if not por_estado["contradictorio"]:
        del por_estado["contradictorio"]
    return por_estado, dict(sorted(por_clase.items())), int(a10)


def puntaje(f):
    """Priority: large dump sites (known-status ones count double), class A negatives of 10 ha or more, and pairs.

    (2 × known + unknown + 0.25 × min(A negatives ≥ 10 ha, 60)) × min(1, pairs / 15). Fewer than 4 pairs is worth 0.
    - Known-status ones count double because they serve for the model and for the activity matrix (stage 8);
      unknown ones only for the model (`basural_activo` if they're awake).
    - The 15 pairs are the AMBA's; with fewer, the insomnia by thirds is weak.
    """
    b = f["n_basurales_10ha"]
    if f["n_gunw"] < 4:
        return 0.0
    base = 2 * (b["abierto"] + b["cerrado"]) + b["desconocido"] + b.get("contradictorio", 0) + 0.25 * min(f["n_negativos_a_10ha"], 60)
    return round(base * min(1.0, f["n_gunw"] / 15), 2)


# ---------------------------------------------------------------- add frames by number of open sites (prompt 6)
MARGEN_KM = 5.0
MIN_PARES_AGREGAR = 15
MARCA_MD = ("<!-- agregados: inicio (lo escribe `frames_elegir.py --agregar`) -->", "<!-- agregados: fin -->")


def sitios_con_poligono():
    """The open or closed dump sites of 10 ha or more with a polygon (the 1,008 of `optico_estado_conocido.py`).

    Returns a list of dicts with `id`, `estado`, `lon`, `lat`, `area_ha`, `nombre`, `pais` and `caja` (the polygon's).
    """
    with open(os.path.join(DATA, "basurales", "basurales_mundo.json"), encoding="utf-8") as fh:
        ficha = {s["id"]: s for s in json.load(fh)["sitios"]}
    with open(os.path.join(DATA, "basurales", "geometrias.geojson"), encoding="utf-8") as fh:
        feats = json.load(fh)["features"]
    salida = []
    for f in feats:
        g = f.get("geometry")
        s = ficha.get(f["properties"]["id"])
        if not g or g["type"] not in ("Polygon", "MultiPolygon") or not s:
            continue
        if s["estado"] not in ("abierto", "cerrado") or (s.get("area_ha") or 0) < 10 or s.get("lat") is None:
            continue
        anillos = g["coordinates"] if g["type"] == "Polygon" else [a for pol in g["coordinates"] for a in pol]
        xy = np.array([p[:2] for a in anillos for p in a], dtype=float)
        salida.append({"id": s["id"], "estado": s["estado"], "lon": s["lon"], "lat": s["lat"], "area_ha": s["area_ha"],
                       "nombre": s.get("nombre"), "pais": s.get("pais"),
                       "caja": [xy[:, 0].min(), xy[:, 1].min(), xy[:, 0].max(), xy[:, 1].max()]})
    return salida


def caja_con_margen(cajas, km=MARGEN_KM):
    """The box containing all of them, plus `km` of margin, rounded to 4 decimals."""
    c = np.array(cajas, dtype=float)
    o, s, e, n = c[:, 0].min(), c[:, 1].min(), c[:, 2].max(), c[:, 3].max()
    dlat = km / 111.32
    dlon = km / (111.32 * math.cos(math.radians((s + n) / 2)))
    return [round(float(v), 4) for v in (o - dlon, s - dlat, e + dlon, n + dlat)]


def _clave_area(lo, la, loc):
    """Frame name of a cell: "Sun Valley, Los Angeles, CA" -> USA_CA_LOS_ANGELES; without a locality, CELDA_N34_W119."""
    if not loc:
        return "CELDA_" + ("N" if la >= 0 else "S") + f"{abs(la):02d}_" + ("E" if lo >= 0 else "W") + f"{abs(lo):03d}"
    partes = [p.strip() for p in loc.split(",")]
    lugar = partes[1] if len(partes) > 2 else partes[0]
    return "_".join((["PRI"] if partes[-1].upper() == "PR" else ["USA", partes[-1].upper()])
                    + [re.sub(r"[^A-Z0-9]+", "_", _ascii(lugar).upper()).strip("_")])


def _puntaje_abiertos(sitios):
    return 2 * sum(s["estado"] == "abierto" for s in sitios) + sum(s["estado"] == "cerrado" for s in sitios)


def agregar(args):
    """Adds `args.agregar` frames to `frames.json` without touching the existing ones (see the header)."""
    with open(args.salida, encoding="utf-8") as fh:
        actual = json.load(fh)
    viejos = actual["frames"]
    if any(f.get("criterio") == "abiertos" for f in viejos):
        sys.exit("frames.json ya tiene frames agregados por abiertos. Para rehacerlos, sacalos a mano y volvé a correr.")
    complejos, negativos = cargar_catalogos()
    localidades = _localidades_epa()
    sitios = sitios_con_poligono()
    total = collections.Counter(s["estado"] for s in sitios)
    ya = [s for s in sitios if any(en_caja([s["lon"]], [s["lat"]], f["bbox"])[0] for f in viejos)]
    libres = [s for s in sitios if s not in ya]
    por_celda = collections.defaultdict(list)
    for s in libres:
        por_celda[(math.floor(s["lon"]), math.floor(s["lat"]))].append(s)
    print(f"{len(sitios)} basurales de estado conocido de 10 ha o más con polígono ({total['abierto']} abiertos, {total['cerrado']} cerrados); "
          f"{len(ya)} ya caen en una caja elegida; quedan {len(libres)} en {len(por_celda)} celdas")

    elegidos, descartadas, nombres = [], [], {f["frame"] for f in viejos}
    pendientes = dict(por_celda)

    def descartar(lo, la, clave, ss, motivo):
        print(f"   no entra: {motivo}")
        descartadas.append({"celda": [lo, la], "frame": clave, "abiertos": sum(s["estado"] == "abierto" for s in ss),
                            "cerrados": sum(s["estado"] == "cerrado" for s in ss), "motivo": motivo})

    while len(elegidos) < args.agregar:
        cajas = [f["bbox"] for f in viejos + elegidos]
        # Of each cell, the dump sites whose polygon with margin doesn't touch an already chosen box are kept.
        utiles = {k: [s for s in v if not any(se_tocan(caja_con_margen([s["caja"]]), c) for c in cajas)] for k, v in pendientes.items()}
        utiles = {k: v for k, v in utiles.items() if any(s["estado"] == "abierto" for s in v)}
        if not utiles:
            break  # no cells with free open sites are left
        (lo, la), ss = max(utiles.items(), key=lambda kv: (_puntaje_abiertos(kv[1]), sum(s["estado"] == "abierto" for s in kv[1]), -kv[0][0], -kv[0][1]))
        del pendientes[(lo, la)]
        resto = []
        # Each dump site separately doesn't touch a chosen box, but the box joining them can:
        # then the cell is split and the side (west, east, south or north of that box) with the highest score is kept.
        while True:
            caja = caja_con_margen([s["caja"] for s in ss])
            toca = next((c for c in cajas if se_tocan(caja, c)), None)
            if toca is None:
                break
            m = {s["id"]: caja_con_margen([s["caja"]]) for s in ss}
            lados = [[s for s in ss if m[s["id"]][2] <= toca[0]], [s for s in ss if m[s["id"]][0] >= toca[2]],
                     [s for s in ss if m[s["id"]][3] <= toca[1]], [s for s in ss if m[s["id"]][1] >= toca[3]]]
            lado = max(lados, key=_puntaje_abiertos)
            resto += [s for s in ss if s not in lado]
            ss = lado
        ref = max(ss, key=lambda s: s["area_ha"])
        loc = localidades.get(ref["id"])
        clave, i = _clave_area(lo, la, loc), 2
        base = clave
        while clave in nombres:
            clave, i = f"{base}_{i}", i + 1
        ciudad = f"{loc or 'celda ' + str(la) + ', ' + str(lo)} (alrededor de {ref['nombre'] or ref['id']})"
        pais = collections.Counter(s["pais"] for s in ss if s.get("pais")).most_common(1)
        pais = pais[0][0] if pais else "USA"
        print(f"celda ({lo}, {la}) {clave}: {sum(s['estado'] == 'abierto' for s in ss)} abiertos y {sum(s['estado'] == 'cerrado' for s in ss)} cerrados"
              + (f" (aparte quedan {len(resto)} por la caja de otro frame)" if resto else "") + f"; caja {caja}; consultando ASF…", flush=True)
        f = evaluar_area(clave, ciudad, pais, caja, args, complejos, negativos)
        if f.get("sin_cobertura"):
            # No NISAR frame covers the whole box: the footprint with the highest score is kept and the box shrinks to its dump sites.
            lon, lat = np.array([s["lon"] for s in ss]), np.array([s["lat"] for s in ss])
            grupos = pares_por_frame(consultar_asf(caja, args.cache))
            mejor = max(([s for s, d in zip(ss, dentro_poligono(lon, lat, g["huella"])) if d] for g in grupos.values() if len(g["pares"]) >= 4),
                        key=_puntaje_abiertos, default=[])
            if not any(s["estado"] == "abierto" for s in mejor) or len(mejor) == len(ss):
                descartar(lo, la, clave, ss, f"sin frame GUNW PR que cubra el {args.min_cobertura:.0%} de la caja (mejor cobertura {f['mejor_cobertura']:.0%})")
                continue
            print(f"   sin un frame que cubra la caja (mejor {f['mejor_cobertura']:.0%}): se achica a los {len(mejor)} basurales de la huella con más puntaje")
            resto += [s for s in ss if s not in mejor]
            ss = mejor
            caja = caja_con_margen([s["caja"] for s in ss])
            f = evaluar_area(clave, ciudad, pais, caja, args, complejos, negativos)
            if f.get("sin_cobertura"):
                descartar(lo, la, clave, ss, f"sin frame GUNW PR que cubra el {args.min_cobertura:.0%} de la caja, ni achicándola a una huella (mejor cobertura {f['mejor_cobertura']:.0%})")
                continue
        if resto:
            pendientes[(lo, la)] = resto  # what was left out can form another frame later
        if f["n_gunw"] < MIN_PARES_AGREGAR:
            descartar(lo, la, clave, ss, f"sólo {f['n_gunw']} pares GUNW PR (hacen falta {MIN_PARES_AGREGAR})")
            continue
        # Those inside the footprint of the chosen tracks (the box may not be fully covered).
        lon, lat = np.array([s["lon"] for s in ss]), np.array([s["lat"] for s in ss])
        cubre = np.zeros(len(ss), dtype=bool)
        for h in f["_huellas"]:
            cubre |= dentro_poligono(lon, lat, h)
        f["n_sitios_10ha"] = {e: int(sum(c and s["estado"] == e for s, c in zip(ss, cubre))) for e in ("abierto", "cerrado")}
        if not f["n_sitios_10ha"]["abierto"]:
            descartar(lo, la, clave, ss, "ningún abierto cae en la huella de los tracks elegidos")
            continue
        f["puntaje"] = float(2 * f["n_sitios_10ha"]["abierto"] + f["n_sitios_10ha"]["cerrado"])
        f["criterio"], f["celda"] = "abiertos", [lo, la]
        f["prioridad"] = max(g["prioridad"] for g in viejos) + 1 + len(elegidos)
        print(f"   entra con prioridad {f['prioridad']}: {f['frames_nisar']}, {f['n_gunw']} pares, {f['fecha_inicio']} a {f['fecha_fin']}; "
              f"en la huella {f['n_sitios_10ha']}")
        elegidos.append(f)
        nombres.add(clave)
    # The processing order goes from most to fewest open sites.
    elegidos.sort(key=lambda f: (-f["n_sitios_10ha"]["abierto"], -f["puntaje"], f["prioridad"]))
    for i, f in enumerate(elegidos):
        f["prioridad"] = max(g["prioridad"] for g in viejos) + 1 + i

    claves = ["frame", "orbita", "ciudad", "pais", "hemisferio", "epsg", "bbox", "n_gunw", "fecha_inicio", "fecha_fin",
              "n_basurales_10ha", "n_negativos", "reservado_prueba", "frames_nisar",
              "prioridad", "puntaje", "n_negativos_a_10ha", "n_gunw_por_track", "cobertura", "criterio", "celda", "n_sitios_10ha"]
    actual["frames"] = viejos + [{k: f[k] for k in claves} for f in elegidos]
    actual["meta"]["agregados"] = {
        "generado": dt.date.today().isoformat(), "generado_por": "motor/frames_elegir.py --agregar",
        "n": len(elegidos), "prioridad_desde": max(g["prioridad"] for g in viejos) + 1,
        "criterio": ("celdas de 1° con más basurales abiertos de 10 ha o más con polígono, por sitio (puntaje 2 × abiertos + cerrados), "
                     "sin contar los que ya caen en una caja elegida; caja achicada a esos basurales más "
                     f"{MARGEN_KM:g} km; al menos {MIN_PARES_AGREGAR} pares GUNW PR; sin tocar una caja ya elegida; sin tope de EE. UU"),
        "n_sitios_10ha": "abiertos y cerrados de 10 ha o más con polígono, por sitio, dentro de la caja y de la huella (lo que definió el frame)",
        "sesgo": "todos los frames agregados salen del registro de la EPA (EE. UU.): el modelo queda entrenado ahí y probado en Argentina",
        "celdas_descartadas": descartadas,
    }
    import pandas as pd

    import contratos
    contratos.validar(pd.DataFrame(actual["frames"]), "frames")
    with open(args.salida, "w", encoding="utf-8") as fh:
        json.dump(actual, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    if args.estado_conocido:  # the earlier frames stay as they are; the new ones are added
        with open(args.estado_conocido, encoding="utf-8") as fh:
            ec = json.load(fh)
        ec["frames"].update(estado_conocido(elegidos)["frames"])
        ec["meta"]["agregados"] = f"{dt.date.today().isoformat()}: {len(elegidos)} frames de `frames_elegir.py --agregar`"
        with open(args.estado_conocido, "w", encoding="utf-8") as fh:
            json.dump(ec, fh, ensure_ascii=False, indent=1)
            fh.write("\n")
    if args.md:
        _escribir_md_agregados(args.md, elegidos, descartadas, actual["meta"]["agregados"], len(sitios), total, len(ya))
    ab, ce = (sum(f["n_sitios_10ha"][e] for f in elegidos) for e in ("abierto", "cerrado"))
    print(f"\n{len(elegidos)} frames agregados -> {os.path.relpath(args.salida)}: {ab} abiertos y {ce} cerrados de 10 ha o más con polígono, "
          f"{sum(f['n_gunw'] for f in elegidos)} pares GUNW")


def _escribir_md_agregados(ruta, elegidos, descartadas, meta, n_sitios, total, n_ya):
    """Adds (or replaces) in the .md the section of the added frames; the rest of the document isn't touched."""
    filas = ["| Prioridad | Frame | Ciudad | Celda (lon, lat) | Tracks (NISAR) | Pares | Fechas | Abiertos | Cerrados | Caja (lon O, lat S, lon E, lat N) | Puntaje |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for f in elegidos:
        n = f["n_sitios_10ha"]
        filas.append(f"| {f['prioridad']} | `{f['frame']}` | {f['ciudad']} | ({f['celda'][0]}, {f['celda'][1]}) | {', '.join(f['frames_nisar'])} | {f['n_gunw']} | "
                     f"{f['fecha_inicio']} a {f['fecha_fin']} | {n['abierto']} | {n['cerrado']} | {', '.join(str(v) for v in f['bbox'])} | {f['puntaje']:g} |")
    ab, ce = (sum(f["n_sitios_10ha"][e] for f in elegidos) for e in ("abierto", "cerrado"))
    filas.append(f"| **Total** | {len(elegidos)} frames | | | | {sum(f['n_gunw'] for f in elegidos)} | | **{ab}** | **{ce}** | | |")
    desc = ["| Celda (lon, lat) | Nombre | Abiertos | Cerrados | Por qué no entra |", "|---|---|---|---|---|"]
    desc += [f"| ({d['celda'][0]}, {d['celda'][1]}) | `{d['frame']}` | {d['abiertos']} | {d['cerrados']} | {d['motivo']} |" for d in descartadas]
    seccion = f"""{MARCA_MD[0]}
## Frames agregados por cantidad de abiertos (prompt 6, {meta['generado']})

Generado por `python frames_elegir.py --agregar {len(elegidos)}`. **Los frames de arriba no cambian** (mismo nombre, misma caja, misma prioridad); estos siguen con prioridad de {meta['prioridad_desde']} en adelante, que es el orden de procesamiento.

**Por qué:** los 10 frames de arriba se eligieron por diversidad y cubren pocos basurales de estado conocido. El catálogo tiene {f'{n_sitios:,}'.replace(',', '.')} basurales abiertos o cerrados de 10 ha o más con polígono ({total['abierto']} abiertos y {total['cerrado']} cerrados); {n_ya} ya caen en una caja de arriba.

{chr(10).join(filas)}

- **Abiertos y cerrados acá se cuentan por sitio** (polígono de 10 ha o más con estado en el registro), no por complejo como en la tabla de arriba, y sólo los que caen en la huella de los tracks elegidos. `frames.json` trae los dos conteos: `n_sitios_10ha` (este) y `n_basurales_10ha` (por complejo, el del contrato).
- Criterio: {meta['criterio']}.
- Puntaje: 2 × abiertos + cerrados. Las celdas se eligen de a una: después de cada elección se descuentan los basurales que quedaron a menos de {MARGEN_KM:g} km de una caja elegida.
- **Sesgo:** {meta['sesgo']}.

### Celdas que no entraron
{chr(10).join(desc) if descartadas else 'Ninguna.'}
{MARCA_MD[1]}
"""
    with open(ruta, encoding="utf-8") as fh:
        texto = fh.read()
    if MARCA_MD[0] in texto:
        texto = texto.split(MARCA_MD[0])[0].rstrip("\n") + "\n\n" + seccion + texto.split(MARCA_MD[1], 1)[1].lstrip("\n")
    else:
        texto = texto.rstrip("\n") + "\n\n" + seccion
    with open(ruta, "w", encoding="utf-8") as fh:
        fh.write(texto)


# ---------------------------------------------------------------- principal
def evaluar_area(clave, ciudad, pais, caja, args, complejos, negativos):
    res = consultar_asf(caja, args.cache)
    grupos = pares_por_frame(res)
    tracks, cobs = elegir_tracks(caja, grupos, args.min_cobertura)
    if not tracks:
        mejor = max(cobs.values(), default=0.0) if cobs else max((cobertura(caja, g["huella"]) for g in grupos.values()), default=0.0)
        return {"frame": clave, "ciudad": ciudad, "pais": pais, "bbox": caja, "n_gunw": 0, "sin_cobertura": True,
                "productos_asf": len(res), "mejor_cobertura": round(mejor, 2)}
    pares = [(t, p) for t in tracks for p in grupos[t]["pares"]]
    fechas = sorted(d for _, (a, b) in pares for d in (a, b))
    iso = lambda s: f"{s[:4]}-{s[4:6]}-{s[6:]}"  # noqa: E731
    por_estado, por_clase, a10 = contar(caja, [grupos[t]["huella"] for t in tracks], complejos, negativos)
    cod, hem = epsg(caja)
    f = {
        "frame": clave, "orbita": sorted({t[0] for t in tracks}), "ciudad": ciudad, "pais": pais, "hemisferio": hem,
        "epsg": cod, "bbox": [round(v, 4) for v in caja], "n_gunw": len(pares),
        "fecha_inicio": iso(fechas[0]), "fecha_fin": iso(fechas[-1]),
        "n_basurales_10ha": por_estado, "n_negativos": por_clase, "reservado_prueba": pais == "ARG",
        "frames_nisar": [f"{t[0]:03d}_{t[1]}_{t[2]:03d}" for t in tracks],
        "n_gunw_por_track": {f"{t[0]:03d}_{t[1]}_{t[2]:03d}": len(grupos[t]["pares"]) for t in tracks},
        "cobertura": {f"{t[0]:03d}_{t[1]}_{t[2]:03d}": round(cobs[t], 2) for t in tracks},
        "n_negativos_a_10ha": a10,
        "_huellas": [grupos[t]["huella"] for t in tracks],
    }
    f["puntaje"] = puntaje(f)
    return f


def elegir(evaluados, n, max_usa, min_fuera_top=1, top=4):
    """Argentina (reserved) first; then by score, without overlapping areas and with a USA cap.

    - Two areas that touch can't both get in (a complex has to fall in a single partition).
    - Among the first `top` (those processed if time runs short) at least `min_fuera_top` from outside the USA get in.
    """
    con_datos = [f for f in evaluados if f.get("n_gunw", 0) >= 4 and f.get("puntaje", 0) > 0 or f.get("pais") == "ARG" and f.get("n_gunw", 0)]
    reservados = [f for f in con_datos if f["reservado_prueba"]]
    resto = sorted((f for f in con_datos if not f["reservado_prueba"]), key=lambda f: -f["puntaje"])
    elegidos, n_usa = [], 0
    for f in resto:
        if len(elegidos) + len(reservados) >= n:
            break
        if any(se_tocan(f["bbox"], g["bbox"]) for g in elegidos + reservados):
            continue
        if f["pais"] in EEUU:
            if n_usa >= max_usa:
                continue
            n_usa += 1
        elegidos.append(f)
    # so the cut of the first `top` doesn't stay only in the USA
    fuera = [f for f in elegidos if f["pais"] not in EEUU]
    if fuera and sum(f["pais"] not in EEUU for f in elegidos[:top]) < min_fuera_top:
        mejor = fuera[0]
        elegidos.remove(mejor)
        elegidos.insert(top - 1, mejor)
    for i, f in enumerate(elegidos, start=1):
        f["prioridad"] = i
    for f in reservados:
        f["prioridad"] = 0
    return reservados + elegidos


def tabla_md(frames, descartados, meta):
    filas = ["| Prioridad | Frame | Ciudad | País | Tracks (NISAR) | Pares | Fechas | Abiertos | Cerrados | Desconocidos | Negativos A ≥ 10 ha | Negativos (todos) | Puntaje |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for f in frames:
        b = f["n_basurales_10ha"]
        pr = "reservado (prueba final)" if f["reservado_prueba"] else str(f["prioridad"])
        filas.append(f"| {pr} | `{f['frame']}` | {f['ciudad']} | {f['pais']} | {', '.join(f['frames_nisar'])} | {f['n_gunw']} | "
                     f"{f['fecha_inicio']} a {f['fecha_fin']} | {b['abierto']} | {b['cerrado']} | {b['desconocido']} | "
                     f"{f['n_negativos_a_10ha']} | {sum(f['n_negativos'].values())} | {f['puntaje']} |")
    desc = ["| Área | País | Por qué no entra |", "|---|---|---|"]
    for f in descartados:
        if f.get("sin_cobertura"):
            motivo = f"sin frame GUNW PR que cubra el {meta['min_cobertura']:.0%} de la caja ({f['productos_asf']} productos tocan la caja; mejor cobertura {f['mejor_cobertura']:.0%})"
        elif f["n_gunw"] < 4:
            motivo = f"sólo {f['n_gunw']} pares"
        else:
            b = f["n_basurales_10ha"]
            motivo = f"puntaje {f['puntaje']} ({b['abierto']} abiertos, {b['cerrado']} cerrados, {f['n_negativos_a_10ha']} negativos A ≥ 10 ha, {f['n_gunw']} pares)"
            tocan = [g["frame"] for g in frames if se_tocan(f["bbox"], g["bbox"])]
            if tocan:
                motivo += f"; se superpone con `{tocan[0]}`"
            elif f["pais"] in EEUU:
                motivo += "; tope de frames de EE. UU. o menos puntaje que los elegidos"
        desc.append(f"| `{f['frame']}` ({f['ciudad']}) | {f['pais']} | {motivo} |")
    return "\n".join(filas), "\n".join(desc)


def main():
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--n", type=int, default=10, help="how many frames to choose (counting the AMBA)")
    a.add_argument("--max-usa", type=int, default=6, help="tope de frames de EE. UU. y sus territorios")
    a.add_argument("--celdas", type=int, default=25, help="1° cells with the most known-status dump sites to try")
    a.add_argument("--min-cobertura", type=float, default=0.75, help="fraction of the box a frame's footprint has to cover")
    a.add_argument("--cache", help="folder to save the ASF responses")
    a.add_argument("--agregar", type=int, metavar="N",
                   help="doesn't choose again: leaves the frames in frames.json as they are and adds N by number of open sites (see the header)")
    a.add_argument("--salida", default=os.path.join(DATA, "frames.json"))
    a.add_argument("--md", default=os.path.join(AQUI, "datos", "frames-elegidos.md"))
    a.add_argument("--todos", help="if given, saves here all the evaluated areas (JSON)")
    a.add_argument("--estado-conocido", default=os.path.join(RAIZ, "data", "salidas", "estado_conocido.json"),
                   help="known-status dump sites of each chosen frame (read by stages 8 and 9)")
    args = a.parse_args()
    if args.agregar:
        return agregar(args)

    complejos, negativos = cargar_catalogos()
    areas = list(CIUDADES)
    localidades = _localidades_epa()
    for lo, la, k, caja, ref in celdas_conocidas(complejos, args.celdas):
        loc = next((localidades[i] for i in ref["sitios"] if i in localidades), None)
        clave = "CELDA_" + ("N" if la >= 0 else "S") + f"{abs(la):02d}_" + ("E" if lo >= 0 else "W") + f"{abs(lo):03d}"
        if loc:  # "Sun Valley, Los Angeles, CA" -> USA_CA_LOS_ANGELES
            partes = [p.strip() for p in loc.split(",")]
            lugar = partes[1] if len(partes) > 2 else partes[0]
            clave = "_".join((["PRI"] if partes[-1].upper() == "PR" else ["USA", partes[-1].upper()]) + [ re.sub(r"[^A-Z0-9]+", "_", _ascii(lugar).upper()).strip("_")])
        nombre = (ref.get("nombres") or [ref["id"]])[0]
        areas.append((clave, f"{loc or 'celda ' + str(la) + ', ' + str(lo)} (alrededor de {nombre})", None, caja))
    paises_sitio = _paises_por_complejo()
    evaluados = []
    for clave, ciudad, pais, caja in areas:
        if pais is None:  # cells: the most common country among the dump sites in the box
            ids = [c["id"] for c in complejos if en_caja([c["lon"]], [c["lat"]], caja)[0]]
            pais = collections.Counter(paises_sitio.get(i) for i in ids if paises_sitio.get(i)).most_common(1)
            pais = pais[0][0] if pais else "USA"
        print(f"{clave:28s} {pais}  consultando ASF…", flush=True)
        f = evaluar_area(clave, ciudad, pais, caja, args, complejos, negativos)
        if f.get("sin_cobertura"):
            print(f"   sin cobertura suficiente ({f['productos_asf']} productos; mejor {f['mejor_cobertura']:.0%})")
        else:
            print(f"   {f['frames_nisar']}  pares {f['n_gunw']}  {f['fecha_inicio']}..{f['fecha_fin']}  "
                  f"basurales {f['n_basurales_10ha']}  neg A≥10ha {f['n_negativos_a_10ha']}  puntaje {f['puntaje']}")
        evaluados.append(f)

    frames = elegir(evaluados, args.n, args.max_usa)
    elegidos = {f["frame"] for f in frames}
    descartados = [f for f in evaluados if f["frame"] not in elegidos]
    meta = {
        "generado": dt.date.today().isoformat(), "generado_por": "motor/frames_elegir.py",
        "fuente": "ASF Search API (api.daac.asf.alaska.edu), productos NISAR L2 GUNW PR (provisional V1)",
        "catalogos": ["data/catalogos/basurales/complejos.json", "data/catalogos/negativos/negativos_mundo.json", "data/catalogos/negativos/negativos_amba.json"],
        "criterio": ("~10 frames que maximizan complejos de 10 ha o más con estado conocido, negativos de clase A de 10 ha o más "
                     "y pares GUNW (ver `puntaje` en el script); tope de frames de EE. UU.; Argentina reservada para la prueba final"),
        "min_cobertura": args.min_cobertura, "max_usa": args.max_usa,
        "supuestos": ["caja de ~1° por ciudad (el AMBA usa geo.CAJA)", "EPSG por la zona UTM del centro de la caja: confirmar con el dataset `projection` del GUNW",
                      "conteos dentro de la caja y de la huella de los frames elegidos", "n_basurales_10ha cuenta complejos (área sumada ≥ 10 ha) por el estado del complejo"],
        "prioridad": "0 = reservado (Argentina, ya procesado); 1 en adelante = orden de procesamiento",
    }
    claves_contrato = ["frame", "orbita", "ciudad", "pais", "hemisferio", "epsg", "bbox", "n_gunw", "fecha_inicio", "fecha_fin",
                       "n_basurales_10ha", "n_negativos", "reservado_prueba", "frames_nisar"]
    extra = ["prioridad", "puntaje", "n_negativos_a_10ha", "n_gunw_por_track", "cobertura"]
    salida = {"meta": meta, "frames": [{k: f[k] for k in claves_contrato + extra} for f in frames]}
    with open(args.salida, "w", encoding="utf-8") as fh:
        json.dump(salida, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    if args.todos:
        with open(args.todos, "w", encoding="utf-8") as fh:
            json.dump([{k: v for k, v in f.items() if k != "_huellas"} for f in evaluados], fh, ensure_ascii=False, indent=1)
    if args.estado_conocido:
        ec = estado_conocido(frames)
        with open(args.estado_conocido, "w", encoding="utf-8") as fh:
            json.dump(ec, fh, ensure_ascii=False, indent=1)
            fh.write("\n")
        print(f"estado conocido -> {os.path.relpath(args.estado_conocido)}: "
              + ", ".join(f"{k} {len(v)}" for k, v in ec["frames"].items()))
    tabla, desc = tabla_md(frames, descartados, meta)
    if args.md:
        _escribir_md(args.md, tabla, desc, meta, frames)
    print(f"\n{len(frames)} frames -> {os.path.relpath(args.salida)}")
    print(tabla)


FUENTES_ESTADO = ("epa_lmop", "curado_manual", "osm")


def estado_conocido(frames):
    """Per chosen frame, the catalog dump sites with known status (open, closed or contradictory).

    They come from `basurales_mundo.json` (which already joins EPA LMOP, OSM and the curated Argentine cases; the closed
    ones are those of `basurales_cerrados.json`). They're matched with `casos_curados_argentina.json` by `id_fuente`.
    Each site says which source gives the status: stage 8 can keep only EPA and curated cases.
    """
    with open(os.path.join(DATA, "basurales", "basurales_mundo.json"), encoding="utf-8") as fh:
        sitios = json.load(fh)["sitios"]
    with open(os.path.join(DATA, "basurales", "complejos.json"), encoding="utf-8") as fh:
        cx = json.load(fh)
    with open(os.path.join(DATA, "basurales", "basurales_cerrados.json"), encoding="utf-8") as fh:
        cerrados = {s["id"] for s in json.load(fh)["sitios"]}
    with open(os.path.join(DATA, "basurales", "casos_curados_argentina.json"), encoding="utf-8") as fh:
        curados = {c["id"]: c for c in json.load(fh)["sitios"]}
    estado_cx = {c["id"]: c["estado"] for c in cx["complejos"]}
    conocidos = [s for s in sitios if s["estado"] in ("abierto", "cerrado", "contradictorio") and s.get("lat") is not None]
    lon = np.array([s["lon"] for s in conocidos])
    lat = np.array([s["lat"] for s in conocidos])
    salida = {}
    for f in frames:
        m = en_caja(lon, lat, f["bbox"])
        cubre = np.zeros_like(m)
        for h in f["_huellas"]:
            cubre |= dentro_poligono(lon, lat, h)
        lista = []
        for s in (conocidos[i] for i in np.nonzero(m & cubre)[0]):
            fuentes = [e for e in s["estados_por_fuente"] if e["estado"] != "sin_dato"]
            curado = next((curados[e["id_fuente"]] for e in fuentes if e["fuente"] == "curado_manual" and e["id_fuente"] in curados), None)
            cpx = cx["complejo_por_sitio"].get(s["id"])
            lista.append({
                "id_catalogo": s["id"], "nombre": s.get("nombre"), "pais": s.get("pais") or f["pais"], "lat": s["lat"], "lon": s["lon"],
                "area_ha": s.get("area_ha"), "grande": (s.get("area_ha") or 0) >= 10, "estado": s["estado"],
                "fuentes_estado": sorted({e["fuente"] for e in fuentes}),
                "estados_por_fuente": fuentes, "fecha_cierre": s.get("fecha_cierre"),
                "complejo": cpx, "estado_complejo": estado_cx.get(cpx), "en_basurales_cerrados": s["id"] in cerrados,
                "caso_curado": curado["id"] if curado else None,
            })
        lista.sort(key=lambda x: (-(x["area_ha"] or 0)))
        salida[f["frame"]] = lista
    return {
        "meta": {
            "generado": dt.date.today().isoformat(), "generado_por": "motor/frames_elegir.py",
            "fuentes": ["data/catalogos/basurales/basurales_mundo.json (EPA LMOP, OSM vía Overture, casos curados)",
                        "data/catalogos/basurales/basurales_cerrados.json", "data/catalogos/basurales/casos_curados_argentina.json"],
            "criterio": "sitios con estado abierto, cerrado o contradictorio dentro de la caja y de la huella de los frames elegidos",
            "uso": "etiquetas independientes del insomnio para la etapa 8 (evaluar_actividad.py). `grande` = 10 ha o más.",
            "advertencia": "el estado de OSM sale de etiquetas disused/abandoned, sin fecha; el de la EPA es de 2024-09",
        },
        "frames": salida,
    }


def _ascii(t):
    import unicodedata
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()


def _localidades_epa():
    """site -> "locality, county, state" from the EPA (to name the USA cells)."""
    with open(os.path.join(DATA, "basurales", "basurales_mundo.json"), encoding="utf-8") as fh:
        sitios = json.load(fh)["sitios"]
    salida = {}
    for s in sitios:
        for f in s.get("fuentes", []):
            loc = f.get("datos", {}).get("localidad") if f.get("fuente") == "epa_lmop" else None
            if loc:
                salida[s["id"]] = loc
                break
    return salida


def _paises_por_complejo():
    """complex -> country, from basurales_mundo.json (complexes don't carry a country)."""
    with open(os.path.join(DATA, "basurales", "complejos.json"), encoding="utf-8") as fh:
        por_sitio = json.load(fh)["complejo_por_sitio"]
    with open(os.path.join(DATA, "basurales", "basurales_mundo.json"), encoding="utf-8") as fh:
        sitios = json.load(fh)["sitios"]
    salida = {}
    for s in sitios:
        if s.get("pais"):
            salida.setdefault(por_sitio.get(s["id"], s["id"]), s["pais"])
    return salida


def _escribir_md(ruta, tabla, desc, meta, frames):
    usa = sum(f["pais"] in EEUU for f in frames)
    conocidos = sum(f["n_basurales_10ha"]["abierto"] + f["n_basurales_10ha"]["cerrado"] for f in frames)
    conocidos_no_usa = sum(f["n_basurales_10ha"]["abierto"] + f["n_basurales_10ha"]["cerrado"] for f in frames if f["pais"] not in EEUU)
    texto = f"""# Frames elegidos para el modelo (etapa 2, {meta['generado']})

Generado por `motor/frames_elegir.py` (se regenera con `python frames_elegir.py`). Datos: `../data/catalogos/frames.json`, validado con `contratos.py`.
Fuente: {meta['fuente']}. Catálogos: `data/catalogos/basurales/complejos.json` y `data/catalogos/negativos/`.

**Orden de procesamiento:** la columna Prioridad. Si no da el tiempo, se procesan los primeros 3 o 4. El AMBA ya está procesado y queda **reservado para la prueba final** (Argentina no entra al entrenamiento).

{tabla}

- Abiertos, cerrados y desconocidos: **complejos** de 10 ha o más (área sumada) dentro de la caja y de la huella de los frames, por el estado del complejo.
- Pares: GUNW `PR` únicos (fecha de referencia y secundaria) sumando los tracks elegidos.
- Puntaje: (2 × (abiertos + cerrados) + desconocidos + 0,25 × min(negativos A ≥ 10 ha, 60)) × min(1, pares / 15). Entre los primeros 4 entra al menos un frame de fuera de EE. UU.
- Las áreas no se superponen: un complejo cae en un solo frame (y en una sola partición).
- En total hay {conocidos} complejos grandes de estado conocido en los frames elegidos; **{conocidos_no_usa} fuera de EE. UU.** Los frames de fuera de EE. UU. ({len(frames) - usa}) aportan sobre todo basurales sin estado (sirven como `basural_activo` si están despiertos, no para la matriz de actividad) y diversidad de paisaje para la validación por frame.

## Áreas evaluadas que no entraron
{desc}

## Supuestos
""" + "\n".join(f"- {s}" for s in meta["supuestos"]) + """

## Costo de procesamiento
- Cada GUNW pesa unos 2,2 GB. Los frames con un año de datos (Los Ángeles, Ciudad de México, Delhi, Staten Island) tienen 50 o más pares: más de 100 GB si se bajan enteros. Usar `procesar --remoto` (sólo la coherencia de 80 m) o, si no da el tiempo, **los últimos 15 pares de cada frame** (de junio a octubre de 2026, como el AMBA), así los frames quedan comparables.
- Antes de procesar un frame, la etapa 1 tiene que generalizar `geo.py` (zona UTM y hemisferio por frame): todos menos el AMBA y Yakarta son del hemisferio norte.

## Limitaciones
- El estado conocido es casi todo de la EPA (EE. UU.): de los complejos de 10 ha o más con estado abierto o cerrado del catálogo, la gran mayoría está en EE. UU. La matriz de actividad (etapa 8) se reporta por país por eso.
- Los negativos se muestrearon cerca de basurales con estado conocido (`../docs/data.md`): fuera de EE. UU. hay pocos, salvo en el AMBA.
- `frame_nisar` de los catálogos todavía no se completó: lo hace la etapa 4 al leer cada frame.
"""
    with open(ruta, "w", encoding="utf-8") as fh:
        fh.write(texto)


if __name__ == "__main__":
    main()
