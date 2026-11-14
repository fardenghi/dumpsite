"""Etapa 2: elige los frames de NISAR donde se entrena y evalúa el modelo, y arma `data/frames.json`.

Por cada área candidata (ciudades fijas + las celdas de 1° con más basurales de estado conocido):
  1. consulta la API pública de ASF (sin login) por los GUNW `PR` que la tocan;
  2. agrupa por track y frame de NISAR y se queda con los que cubren el área (hasta 2 tracks, mejor uno
     ascendente y uno descendente, como el AMBA);
  3. cuenta, dentro del área y de la huella de esos frames:
     - basurales de 10 ha o más por estado, agrupados por complejo (`basurales/complejos.json`);
     - negativos por clase (`rol = negativo`), y aparte los de clase A de 10 ha o más;
     - pares GUNW y rango de fechas.
Después ordena por prioridad (ver `puntaje`) y elige ~10 frames sin quedarse sólo en EE. UU.

    python frames_elegir.py                     # consulta ASF, escribe ../../data/frames.json y ../idea/frames-elegidos.md
    python frames_elegir.py --cache /tmp/asf    # guarda/reusa las respuestas de ASF
    python frames_elegir.py --n 10 --max-usa 5

Supuestos (se anotan en `meta`): un área es una caja de ~1° alrededor de la ciudad (la del AMBA es `geo.CAJA`);
un frame "cubre" el área si su huella contiene al menos `--min-cobertura` de la caja; la EPSG sale de la zona UTM
del centro del área (la grilla de los GUNW usa la del frame; hay que confirmarla con el dataset `projection`).
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
IDEA = os.path.dirname(AQUI)
DATA = os.path.join(os.path.dirname(IDEA), "data")
sys.path.insert(0, AQUI)
import geo  # noqa: E402

API_ASF = "https://api.daac.asf.alaska.edu/services/search/param"
EEUU = {"USA", "PRI", "VIR", "GUM", "ASM", "MNP"}  # EE. UU. y territorios: el estado sale de la EPA en todos

# frame, ciudad, país, caja [oeste, sur, este, norte]. El AMBA usa la caja del pipeline (geo.CAJA, otro orden).
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


# ---------------------------------------------------------------- geometría
def wkt_anillo(wkt):
    """Primer anillo (lon, lat) de un POLYGON en WKT."""
    nums = re.findall(r"(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)", wkt)
    return np.array([[float(a), float(b)] for a, b in nums])


def dentro_poligono(lon, lat, anillo):
    """Regla par-impar, vectorizada sobre puntos."""
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
    """Fracción de una grilla n×n de puntos de la caja que cae adentro de la huella."""
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
        except Exception as ex:  # noqa: BLE001 (la API a veces corta; reintentamos)
            if i == reintentos - 1:
                raise
            print(f"  ASF falló ({ex}); reintento", file=sys.stderr)
            time.sleep(5 * (i + 1))
    if archivo:
        with open(archivo, "w", encoding="utf-8") as fh:
            json.dump(res, fh)
    return res


def pares_por_frame(resultados):
    """Agrupa los GUNW PR por (track, dirección, frame): pares únicos, fechas y huella."""
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
    """Los (track, dir, frame) que cubren la caja, ordenados por pares; hasta max_tracks, mejor de direcciones distintas."""
    ok = []
    for clave, g in grupos.items():
        c = cobertura(caja, g["huella"])
        if c >= min_cob:
            ok.append((len(g["pares"]), c, clave))
    ok.sort(reverse=True)
    elegidos = []
    for n, c, clave in ok:  # primero uno por dirección
        if clave[0] not in [e[0] for e in elegidos] and clave[1] not in [e[1] for e in elegidos]:
            elegidos.append(clave)
        if len(elegidos) == max_tracks:
            break
    for n, c, clave in ok:  # si falta, otro track cualquiera
        if len(elegidos) < max_tracks and clave not in elegidos and clave[0] not in [e[0] for e in elegidos]:
            elegidos.append(clave)
    return elegidos, {clave: c for n, c, clave in ok}


# ---------------------------------------------------------------- catálogos
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
    """Las n celdas de 1° con más complejos de 10 ha o más con estado conocido (abierto o cerrado).

    Cada celda se convierte en una caja de `lado` grados centrada en el centro de esos complejos (una caja más
    chica que la celda queda cubierta por un solo frame de NISAR más seguido).
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
    """Prioridad: basurales grandes (los de estado conocido pesan doble), negativos A de 10 ha o más, y pares.

    (2 × conocidos + desconocidos + 0,25 × min(negativos A ≥ 10 ha, 60)) × min(1, pares / 15). Menos de 4 pares vale 0.
    - Los de estado conocido pesan doble porque sirven para el modelo y para la matriz de actividad (etapa 8);
      los desconocidos sólo para el modelo (`basural_activo` si están despiertos).
    - Los 15 pares son los del AMBA; con menos, el insomnio por tercios queda flojo.
    """
    b = f["n_basurales_10ha"]
    if f["n_gunw"] < 4:
        return 0.0
    base = 2 * (b["abierto"] + b["cerrado"]) + b["desconocido"] + b.get("contradictorio", 0) + 0.25 * min(f["n_negativos_a_10ha"], 60)
    return round(base * min(1.0, f["n_gunw"] / 15), 2)


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
    """Argentina (reservada) primero; después por puntaje, sin áreas superpuestas y con tope de EE. UU.

    - Dos áreas que se tocan no pueden entrar las dos (un complejo tiene que caer en una sola partición).
    - Entre los primeros `top` (los que se procesan si no da el tiempo) entra al menos `min_fuera_top` de fuera de EE. UU.
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
    # que el corte de los primeros `top` no quede sólo en EE. UU.
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
    a.add_argument("--n", type=int, default=10, help="cuántos frames elegir (contando el AMBA)")
    a.add_argument("--max-usa", type=int, default=6, help="tope de frames de EE. UU. y sus territorios")
    a.add_argument("--celdas", type=int, default=25, help="celdas de 1° con más basurales de estado conocido para probar")
    a.add_argument("--min-cobertura", type=float, default=0.75, help="fracción de la caja que tiene que cubrir la huella de un frame")
    a.add_argument("--cache", help="carpeta para guardar las respuestas de ASF")
    a.add_argument("--salida", default=os.path.join(DATA, "frames.json"))
    a.add_argument("--md", default=os.path.join(IDEA, "idea", "frames-elegidos.md"))
    a.add_argument("--todos", help="si se da, guarda acá todas las áreas evaluadas (JSON)")
    a.add_argument("--estado-conocido", default=os.path.join(IDEA, "salidas", "estado_conocido.json"),
                   help="basurales de estado conocido de cada frame elegido (lo leen las etapas 8 y 9)")
    args = a.parse_args()

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
        if pais is None:  # celdas: el país más común entre los basurales de la caja
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
        "generado": dt.date.today().isoformat(), "generado_por": "herramientas/frames_elegir.py",
        "fuente": "ASF Search API (api.daac.asf.alaska.edu), productos NISAR L2 GUNW PR (provisional V1)",
        "catalogos": ["data/basurales/complejos.json", "data/negativos/negativos_mundo.json", "data/negativos/negativos_amba.json"],
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
    """Por frame elegido, los basurales del catálogo con estado conocido (abierto, cerrado o contradictorio).

    Salen de `basurales_mundo.json` (que ya junta EPA LMOP, OSM y los casos curados de Argentina; los cerrados
    son los de `basurales_cerrados.json`). Se cruzan con `casos_curados_argentina.json` por `id_fuente`.
    Cada sitio dice qué fuente da el estado: la etapa 8 puede quedarse sólo con EPA y casos curados.
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
            "generado": dt.date.today().isoformat(), "generado_por": "herramientas/frames_elegir.py",
            "fuentes": ["data/basurales/basurales_mundo.json (EPA LMOP, OSM vía Overture, casos curados)",
                        "data/basurales/basurales_cerrados.json", "data/basurales/casos_curados_argentina.json"],
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
    """sitio -> "localidad, condado, estado" de la EPA (para nombrar las celdas de EE. UU.)."""
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
    """complejo -> país, desde basurales_mundo.json (los complejos no traen país)."""
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

Generado por `herramientas/frames_elegir.py` (se regenera con `python frames_elegir.py`). Datos: `../../data/frames.json`, validado con `contratos.py`.
Fuente: {meta['fuente']}. Catálogos: `data/basurales/complejos.json` y `data/negativos/`.

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
- Los negativos se muestrearon cerca de basurales con estado conocido (`idea/negativos-dataset.md`): fuera de EE. UU. hay pocos, salvo en el AMBA.
- `frame_nisar` de los catálogos todavía no se completó: lo hace la etapa 4 al leer cada frame.
"""
    with open(ruta, "w", encoding="utf-8") as fh:
        fh.write(texto)


if __name__ == "__main__":
    main()
