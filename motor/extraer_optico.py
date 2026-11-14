"""Etapa 5: variables ópticas de Sentinel-2 L2A por mancha (y por polígono del catálogo), mancha contra anillo.

Escribe `tabla_optico.parquet` (una fila por mancha candidata) y, con `--catalogo`, `tabla_optico_catalogo.parquet`
(una fila por polígono de los catálogos que cae en el frame), según `idea/contratos-datos.md`.

    python extraer_optico.py                                      # el AMBA: ../salidas/manchas.geojson + catálogo
    python extraer_optico.py --manchas ../salidas/DELHI/manchas.geojson --salida ../salidas/DELHI --sin-catalogo
    python extraer_optico.py --desde 2026-06-25 --hasta 2026-10-12 --hilos 24

Cómo:
- Busca escenas L2A en el STAC de Microsoft Planetary Computer (abierto, sin cuenta; como `insomnes-web/scripts/
  s2_fechas.py`) con nubes de escena < `--max-nube` %, en el período de NISAR.
- Agrupa las geometrías en celdas de ~10 km y lee, por celda y escena, **sólo la ventana** de esa celda desde los COG
  (lectura por rango HTTP, a 20 m, usando las overviews de las bandas de 10 m). Celdas y escenas van en paralelo con hilos.
  No se baja ninguna escena entera; con `--cache datos/s2` se guardan las ventanas leídas (no se suben).
- Nubes con la capa SCL: adentro valen vegetación, suelo, agua y sin clasificar (4, 5, 6, 7); en el anillo, sin agua
  (4, 5, 7). Una escena cuenta para una geometría si al menos `--min-valido` de sus píxeles son válidos.
- Anillo de 1,5 km alrededor de la geometría, sin la geometría, sin agua (SCL) y sin los polígonos de los catálogos.
- Por geometría se quedan hasta 8 escenas (las de más píxeles válidos). Reflectancia = (DN − 1000) / 10000 con la
  línea de base de procesamiento ≥ 04.00, y DN / 10000 antes.
- Índices: NDVI = (B08 − B04)/(B08 + B04); NDWI = (B03 − B08)/(B03 + B08);
  BSI = ((B11 + B04) − (B08 + B02)) / ((B11 + B04) + (B08 + B02)).

Datos: Copernicus Sentinel-2 L2A (ESA), vía Microsoft Planetary Computer.
"""
import argparse
import json
import math
import os
import sys
import threading
import time
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
import rasterio
import shapely
from rasterio.features import geometry_mask
from rasterio.transform import from_origin
from rasterio.warp import transform_bounds, transform_geom
from shapely.geometry import box, mapping, shape

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import catalogo_poligonos as cp  # noqa: E402
import contratos  # noqa: E402

STAC = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
TOKEN = "https://planetarycomputer.microsoft.com/api/sas/v1/token/sentinel-2-l2a"
BANDAS = ("B02", "B03", "B04", "B08", "B11", "B12", "SCL")
VALIDO_ADENTRO = (4, 5, 6, 7)
VALIDO_ANILLO = (4, 5, 7)
PASO = 20.0  # m
ANILLO_M = 1500.0
MAX_ESCENAS = 8
GDAL = dict(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
            GDAL_HTTP_MULTIRANGE="YES", GDAL_HTTP_MERGE_CONSECUTIVE_RANGES="YES", GDAL_HTTP_MAX_RETRY="4",
            GDAL_HTTP_RETRY_DELAY="2", VSI_CACHE="TRUE")
INDICES = ("ndvi", "bsi", "ndwi", "b11", "b12")


# ------------------------------------------------------------------ STAC
class Firma:
    """Token SAS de Planetary Computer, renovado cada 40 minutos."""

    def __init__(self):
        self._token, self._t, self._lock = None, 0.0, threading.Lock()

    def __call__(self, href):
        with self._lock:
            if self._token is None or time.time() - self._t > 2400:
                self._token = json.load(urllib.request.urlopen(TOKEN, timeout=60))["token"]
                self._t = time.time()
            return f"{href}?{self._token}"


def buscar_escenas(bbox, desde, hasta, max_nube):
    cuerpo = {"collections": ["sentinel-2-l2a"], "bbox": list(bbox), "datetime": f"{desde}/{hasta}",
              "query": {"eo:cloud_cover": {"lt": max_nube}}, "limit": 500}
    feats, url = [], STAC
    while cuerpo is not None and len(feats) < 5000:  # paginado: un frame grande puede pasar de 500 escenas
        pedido = urllib.request.Request(url, json.dumps(cuerpo).encode(), {"content-type": "application/json"})
        r = json.load(urllib.request.urlopen(pedido, timeout=120))
        feats += r["features"]
        sig = next((l for l in r.get("links", []) if l.get("rel") == "next"), None)
        cuerpo, url = (sig.get("body"), sig.get("href", STAC)) if sig and r["features"] else (None, None)
    escenas = []
    for f in feats:
        p = f["properties"]
        epsg = p.get("proj:epsg") or int(str(p.get("proj:code", "EPSG:0")).split(":")[1])
        base = float(p.get("s2:processing_baseline", "0") or 0)
        escenas.append({"id": f["id"], "fecha": p["datetime"][:10], "nube": float(p["eo:cloud_cover"]), "epsg": int(epsg),
                        "huella": shape(f["geometry"]), "offset": 1000 if base >= 4.0 else 0,
                        "hrefs": {b: f["assets"][b]["href"] for b in BANDAS}})
    return escenas


# ------------------------------------------------------------------ geometrías
def objetivos_desde(fc, poligonos_catalogo, con_catalogo):
    """Lista de geometrías a medir: las manchas candidatas y, si se pide, los polígonos del catálogo."""
    obj = [{"tipo": "mancha", "clave": p["id_mancha"], "frame": p["frame"], "geom": g} for p, g in cp.manchas(fc)]
    if con_catalogo:
        frame = obj[0]["frame"] if obj else "AMBA"
        obj += [{"tipo": "catalogo", "clave": p["id_catalogo"], "catalogo": p["catalogo"], "frame": frame, "geom": p["geom"]}
                for p in poligonos_catalogo]
    return obj


def celdas(objetivos, lado_grados=0.1):
    grupos = defaultdict(list)
    for i, o in enumerate(objetivos):
        c = o["geom"].centroid
        grupos[(math.floor(c.x / lado_grados), math.floor(c.y / lado_grados))].append(i)
    return list(grupos.values())


def _margen_grados(lat, m):
    return m / 110540, m / (111320 * math.cos(math.radians(lat)))


def caja_celda(objetivos, idx):
    o, s, e, n = shapely.total_bounds([objetivos[i]["geom"] for i in idx])
    dy, dx = _margen_grados((s + n) / 2, ANILLO_M + 200)
    return (o - dx, s - dy, e + dx, n + dy)


# ------------------------------------------------------------------ lectura
def leer_ventana(escena, caja, firma, cache=None):
    """Lee las bandas de la escena en la caja (grados), a 20 m en la UTM de la escena. Devuelve (dict, transform)."""
    x0, y0, x1, y1 = transform_bounds("EPSG:4326", f"EPSG:{escena['epsg']}", *caja)
    x0, y0 = math.floor(x0 / PASO) * PASO, math.floor(y0 / PASO) * PASO
    x1, y1 = math.ceil(x1 / PASO) * PASO, math.ceil(y1 / PASO) * PASO
    ancho, alto = int((x1 - x0) / PASO), int((y1 - y0) / PASO)
    t = from_origin(x0, y1, PASO, PASO)
    archivo = None
    if cache:
        archivo = os.path.join(cache, f"{escena['id']}_{x0:.0f}_{y1:.0f}_{ancho}x{alto}.npz")
        if os.path.exists(archivo):
            with np.load(archivo) as z:
                return {b: z[b] for b in BANDAS}, t
    bandas = {}
    with rasterio.Env(**GDAL):
        for b in BANDAS:
            with rasterio.open(firma(escena["hrefs"][b])) as src:
                w = rasterio.windows.from_bounds(x0, y0, x1, y1, src.transform)
                bandas[b] = src.read(1, window=w, out_shape=(alto, ancho), boundless=True, fill_value=0,
                                     resampling=rasterio.enums.Resampling.nearest if b == "SCL" else rasterio.enums.Resampling.average)
    if archivo:
        os.makedirs(cache, exist_ok=True)
        np.savez_compressed(archivo, **bandas)
    return bandas, t


def indices(bandas, offset):
    # DN 0 es sin dato; la reflectancia se acota abajo en 1e-4 (con el offset puede dar negativa en agua o sombra)
    r = {b: np.where(bandas[b] > 0, np.maximum((bandas[b].astype(np.float32) - offset) / 10000.0, 1e-4), np.nan)
         for b in BANDAS if b != "SCL"}
    with np.errstate(invalid="ignore", divide="ignore"):
        ndvi = (r["B08"] - r["B04"]) / (r["B08"] + r["B04"])
        ndwi = (r["B03"] - r["B08"]) / (r["B03"] + r["B08"])
        bsi = ((r["B11"] + r["B04"]) - (r["B08"] + r["B02"])) / ((r["B11"] + r["B04"]) + (r["B08"] + r["B02"]))
    return {"ndvi": ndvi, "bsi": bsi, "ndwi": ndwi, "b11": r["B11"], "b12": r["B12"]}


def mascaras(geom_utm, excluir_utm, forma, t):
    """(adentro, anillo) como máscaras booleanas en la ventana."""
    adentro = ~geometry_mask([mapping(geom_utm)], out_shape=forma, transform=t, all_touched=False)
    if adentro.sum() < 3:
        adentro = ~geometry_mask([mapping(geom_utm)], out_shape=forma, transform=t, all_touched=True)
    aro_g = geom_utm.buffer(ANILLO_M).difference(geom_utm)
    if excluir_utm is not None:
        aro_g = aro_g.difference(excluir_utm)
    aro = ~geometry_mask([mapping(aro_g)], out_shape=forma, transform=t, all_touched=False) if not aro_g.is_empty else np.zeros(forma, bool)
    return adentro, aro & ~adentro


def medir_celda(objetivos, idx, escenas_celda, excluir_por_epsg, firma, min_valido, cache):
    """Por cada objetivo de la celda, la lista de mediciones por escena."""
    caja = caja_celda(objetivos, idx)
    salida = defaultdict(list)
    for esc in escenas_celda:
        try:
            bandas, t = leer_ventana(esc, caja, firma, cache)
        except Exception as e:  # noqa: BLE001 - una escena que falla no corta la corrida
            print(f"  aviso: {esc['id']}: {type(e).__name__}: {str(e)[:120]}", file=sys.stderr)
            continue
        scl = bandas["SCL"]
        if not (scl > 0).any():
            continue
        ind = indices(bandas, esc["offset"])
        ok_in, ok_aro = np.isin(scl, VALIDO_ADENTRO), np.isin(scl, VALIDO_ANILLO)
        excl = excluir_por_epsg(esc["epsg"])
        for i in idx:
            g = cp.a_utm(objetivos[i]["geom"], esc["epsg"])
            if g is None:
                continue
            adentro, aro = mascaras(g, excl, scl.shape, t)
            n_in = int(adentro.sum())
            if n_in == 0:
                continue
            v_in = adentro & ok_in & np.isfinite(ind["ndvi"])
            frac = v_in.sum() / n_in
            if frac < min_valido or v_in.sum() < 2:
                continue
            v_aro = aro & ok_aro & np.isfinite(ind["ndvi"])
            m = {"fecha": esc["fecha"], "valido": float(frac)}
            for k in INDICES:
                m[k] = float(np.nanmean(ind[k][v_in]))
                m[k + "_aro"] = float(np.nanmean(ind[k][v_aro])) if v_aro.sum() >= 10 else np.nan
            salida[i].append(m)
    return salida


# ------------------------------------------------------------------ resumen
def resumir(medidas):
    """Columnas ópticas del contrato a partir de las mediciones por escena de una geometría."""
    vacio = {c: np.nan for c in ("ndvi_media", "ndvi_variacion", "bsi_media", "ndwi_media", "swir_b11", "swir_b12",
                                 "ndvi_contraste", "bsi_contraste", "ndwi_contraste", "swir_b11_contraste", "swir_b12_contraste")}
    # una medición por fecha (la de más píxeles válidos) y como mucho MAX_ESCENAS
    por_fecha = {}
    for m in sorted(medidas, key=lambda m: -m["valido"]):
        por_fecha.setdefault(m["fecha"], m)
    ms = sorted(por_fecha.values(), key=lambda m: -m["valido"])[:MAX_ESCENAS]
    ms.sort(key=lambda m: m["fecha"])
    if not ms:
        return {**vacio, "n_escenas": 0, "fechas": None}
    v = lambda k: np.array([m[k] for m in ms], dtype=float)  # noqa: E731

    def contraste(k):
        d = v(k) - v(k + "_aro")
        return float(np.nanmean(d)) if np.isfinite(d).any() else np.nan

    return {
        "ndvi_media": float(np.mean(v("ndvi"))), "ndvi_variacion": float(np.std(v("ndvi"))),
        "bsi_media": float(np.mean(v("bsi"))), "ndwi_media": float(np.mean(v("ndwi"))),
        "swir_b11": float(np.mean(v("b11"))), "swir_b12": float(np.mean(v("b12"))),
        "ndvi_contraste": contraste("ndvi"), "bsi_contraste": contraste("bsi"), "ndwi_contraste": contraste("ndwi"),
        "swir_b11_contraste": contraste("b11"), "swir_b12_contraste": contraste("b12"),
        "n_escenas": len(ms), "fechas": ",".join(m["fecha"] for m in ms),
    }


def escenas_para(caja, escenas, max_fechas):
    """Una escena por fecha (la que más cubre la celda), hasta `max_fechas` fechas de menos nubes, en orden."""
    b = box(*caja)
    por_fecha = {}
    for e in escenas:
        cubre = e["huella"].intersection(b).area / b.area
        if cubre <= 0.05:
            continue
        actual = por_fecha.get(e["fecha"])
        if actual is None or (cubre, -e["nube"]) > (actual[0], -actual[1]["nube"]):
            por_fecha[e["fecha"]] = (cubre, e)
    elegidas = sorted(por_fecha.values(), key=lambda x: x[1]["nube"])[:max_fechas]
    return sorted([e for _, e in elegidas], key=lambda e: e["fecha"])


def extraer(objetivos, escenas, excluir_deg, hilos=16, min_valido=0.6, max_fechas=10, cache=None, avisar=print):
    firma = Firma()
    excl_cache, lock = {}, threading.Lock()

    def excluir_por_epsg(epsg):
        with lock:
            if epsg not in excl_cache:
                gs = [cp.a_utm(g, epsg) for g in excluir_deg]
                gs = [g for g in gs if g is not None]
                excl_cache[epsg] = shapely.union_all(gs) if gs else None
            return excl_cache[epsg]

    grupos = celdas(objetivos)
    tareas = [(idx, escenas_para(caja_celda(objetivos, idx), escenas, max_fechas)) for idx in grupos]
    avisar(f"{len(objetivos)} geometrías en {len(grupos)} celdas; {sum(len(e) for _, e in tareas)} ventanas de escena a leer")
    medidas = defaultdict(list)
    t0 = time.time()
    # se paraleliza por (celda, escena): es lo que va por la red
    trabajos = [(idx, [e]) for idx, es in tareas for e in es]
    with ThreadPoolExecutor(max_workers=hilos) as ex:
        futuros = [ex.submit(medir_celda, objetivos, idx, es, excluir_por_epsg, firma, min_valido, cache) for idx, es in trabajos]
        for n, f in enumerate(as_completed(futuros), 1):
            for i, ms in f.result().items():
                medidas[i].extend(ms)
            if n % 50 == 0 or n == len(futuros):
                avisar(f"  {n}/{len(futuros)} ventanas ({time.time() - t0:.0f} s)")
    return [resumir(medidas[i]) for i in range(len(objetivos))]


def main():
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--manchas", default=os.path.join(AQUI, "..", "salidas", "manchas.geojson"))
    a.add_argument("--salida", default=os.path.join(AQUI, "..", "salidas"))
    a.add_argument("--desde", default="2026-06-25")
    a.add_argument("--hasta", default="2026-10-12")
    a.add_argument("--max-nube", type=float, default=20.0, help="%% de nubes de la escena entera, para buscar")
    a.add_argument("--max-fechas", type=int, default=10, help="fechas a leer por celda (después quedan hasta 8 por geometría)")
    a.add_argument("--min-valido", type=float, default=0.6, help="fracción de píxeles sin nubes para que una escena cuente")
    a.add_argument("--hilos", type=int, default=16)
    cat = a.add_mutually_exclusive_group()
    cat.add_argument("--catalogo", dest="catalogo", action="store_true", default=None, help="medir también los polígonos del catálogo")
    cat.add_argument("--sin-catalogo", dest="catalogo", action="store_false")
    a.add_argument("--negativos", default="ambos", choices=("ambos", "amba", "mundo"))
    a.add_argument("--frame", action="append", help="sólo estos frames (se puede repetir); por defecto todos los del geojson")
    a.add_argument("--cache", help="carpeta para guardar las ventanas leídas (por ejemplo ../datos/s2); no se sube")
    a.add_argument("--limite", type=int, help="medir sólo las primeras N geometrías (para probar)")
    args = a.parse_args()

    contratos.leer(args.manchas)
    with open(args.manchas, encoding="utf-8") as fh:
        fc = json.load(fh)
    frames = sorted({f["properties"]["frame"] for f in fc["features"] if not f["properties"].get("descartada")})
    if args.frame:
        frames = [f for f in frames if f in set(args.frame)]
    objetivos, res = [], []
    for frame in frames:  # cada frame con su caja: el geojson de `extraer_manchas.py juntar` trae todos
        sub = {"type": "FeatureCollection", "features": [f for f in fc["features"] if f["properties"]["frame"] == frame]}
        ms = cp.manchas(sub)
        con_catalogo = args.catalogo if args.catalogo is not None else frame == "AMBA"
        bbox = cp.bbox_de([g for _, g in ms], margen=0.03)
        poligonos = cp.catalogo(bbox, args.negativos)
        obj = objetivos_desde(sub, poligonos, con_catalogo)
        if args.limite:
            obj = obj[:args.limite]
        escenas = buscar_escenas(bbox, args.desde, args.hasta, args.max_nube)
        print(f"{frame}: {len(escenas)} escenas L2A con menos de {args.max_nube:.0f} % de nubes entre {args.desde} y "
              f"{args.hasta} ({len({e['fecha'] for e in escenas})} fechas)")
        res += extraer(obj, escenas, [p["geom"] for p in poligonos], hilos=args.hilos, min_valido=args.min_valido,
                       max_fechas=args.max_fechas, cache=args.cache)
        objetivos += obj

    filas_m = [{"id_mancha": o["clave"], "frame": o["frame"], **r} for o, r in zip(objetivos, res) if o["tipo"] == "mancha"]
    filas_c = [{"id_catalogo": o["clave"], "catalogo": o["catalogo"], "frame": o["frame"], **r}
               for o, r in zip(objetivos, res) if o["tipo"] == "catalogo"]
    for filas, nombre in ((filas_m, "tabla_optico"), (filas_c, "tabla_optico_catalogo")):
        if not filas:
            continue
        df = pd.DataFrame(filas)
        df["n_escenas"] = df["n_escenas"].astype("int64")
        destino = contratos.guardar(df, nombre, args.salida)
        print(f"{destino}: {len(df)} filas; con escenas: {(df.n_escenas > 0).sum()}; "
              f"escenas por fila: mediana {df.n_escenas.median():.0f}")


if __name__ == "__main__":
    main()
