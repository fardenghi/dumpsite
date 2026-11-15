"""Óptico de Sentinel-2 de TODOS los basurales de estado conocido del catálogo, estén o no en un frame de NISAR.

Pregunta: ¿"menos verde que el entorno" separa los basurales abiertos de los cerrados? En los 10 frames procesados
separó 19 de 24 abiertos y 4 de 35 cerrados (umbral de −0,15 en `ndvi_contraste`, elegido con 5 frames). Acá se mide
con todos los del catálogo: los de estado `abierto` o `cerrado`, de 10 ha o más y con polígono (unos 1.000).

No usa NISAR ni la VM: lee ventanas de Sentinel-2 L2A con `extraer_optico.py` (sin modificarlo). Se puede partir
entre varias compus y cortar y seguir: cada celda de 1° se guarda en `datos/optico_estado/celdas/` (no se sube).

    python optico_estado_conocido.py correr --parte 1/3     # un tercio de las celdas; las otras compus, 2/3 y 3/3
    python optico_estado_conocido.py juntar                 # arma ../data/salidas/optico_estado_conocido.parquet con lo que haya
    python optico_estado_conocido.py resumen                # abiertos contra cerrados, en total y por país

`correr` deja al final su parte en `../data/salidas/optico_estado_conocido/parte_<i>de<n>.parquet` (chico: se sube).
`juntar` lee todas las partes subidas más las celdas locales.

- Período: del 21/10/2025 al 21/10/2026 (el año de NISAR de los frames), hasta 10 fechas repartidas en el año.
- Anillo de 1,5 km sin agua y sin los demás polígonos de los catálogos, igual que en `extraer_optico.py`.
- El estado es el del registro (`data/catalogos/basurales/`: EPA LMOP, OSM y casos curados). Puede estar desactualizado.
- **El umbral no se toca acá:** `resumen` reporta el de −0,15 ya fijado, y además el AUC, que no depende del umbral.

Datos: Copernicus Sentinel-2 L2A (ESA), vía Microsoft Planetary Computer. Catálogo: ver `../data/README.md`.
"""
import argparse
import glob
import json
import math
import os
import sys
import time

import numpy as np
import pandas as pd
import shapely
from shapely.geometry import shape

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import catalogo_poligonos as cp  # noqa: E402
import extraer_optico as eo  # noqa: E402

DATA = os.path.join(AQUI, "..", "data", "catalogos")
CELDAS = os.path.join(AQUI, "datos", "optico_estado", "celdas")
PARTES = os.path.join(AQUI, "..", "data", "salidas", "optico_estado_conocido")
SALIDA = os.path.join(AQUI, "..", "data", "salidas", "optico_estado_conocido.parquet")
PERIODO = ("2025-10-21", "2026-10-21")
ESTADOS = ("abierto", "cerrado")
MIN_HA = 10.0
UMBRAL_NDVI = -0.15  # fijado antes de esta corrida (ver el encabezado); acá no se ajusta
# Los 10 frames que existían cuando se fijó el umbral. Lo que cae fuera de ellos es la prueba independiente.
FRAMES_DEL_UMBRAL = ("AMBA", "LOS_ANGELES", "USA_OH_LAKE", "USA_MD_HOWARD", "CDMX", "PRI_PONCE", "USA_NH_HILLSBOROUGH",
                     "USA_NY_RICHMOND", "DELHI", "YAKARTA")

# `extraer_optico.py` pide un permiso de lectura (token) nuevo en cada llamada y, si una lectura falla, la saltea con
# un aviso. Con muchas celdas a la vez el servicio de permisos contesta "429 Too Many Requests" y las escenas se
# pierden en silencio: el basural queda con menos escenas o con ninguna. Por eso acá, sin tocar ese archivo:
#   - se usa UN solo permiso para toda la corrida;
#   - cada lectura se reintenta antes de darla por perdida, y las perdidas se cuentan;
#   - una celda con algún basural sin escenas no se guarda (queda pendiente), salvo con `--aceptar-vacias`.
LECTURAS_PERDIDAS = []


class _Firma(eo.Firma):
    def __call__(self, href):
        for i in range(6):
            try:
                return super().__call__(href)
            except Exception:
                if i == 5:
                    raise
                time.sleep(3 * (i + 1))


_FIRMA = _Firma()
eo.Firma = lambda: _FIRMA
_leer_ventana = eo.leer_ventana


def _leer_con_reintento(*a, **k):
    for i in range(4):
        try:
            return _leer_ventana(*a, **k)
        except Exception:
            if i == 3:
                LECTURAS_PERDIDAS.append(1)
                raise
            time.sleep(2 * (i + 1))


eo.leer_ventana = _leer_con_reintento


def sitios():
    """Los basurales a medir (DataFrame con geom) y todas las geometrías de los catálogos, para sacarlas del anillo."""
    with open(os.path.join(DATA, "basurales", "basurales_mundo.json"), encoding="utf-8") as fh:
        ficha = {s["id"]: s for s in json.load(fh)["sitios"]}
    with open(os.path.join(DATA, "basurales", "geometrias.geojson"), encoding="utf-8") as fh:
        feats = json.load(fh)["features"]
    filas, todas = [], []
    for f in feats:
        if not f.get("geometry") or f["geometry"]["type"] not in ("Polygon", "MultiPolygon"):
            continue
        g = cp._valida(shape(f["geometry"]))
        if g is None:
            continue
        todas.append(g)
        s = ficha.get(f["properties"]["id"])
        if s and s["estado"] in ESTADOS and (s.get("area_ha") or 0) >= MIN_HA:
            c = g.centroid
            filas.append({"id_catalogo": s["id"], "nombre": s.get("nombre"), "pais": s.get("pais"), "estado": s["estado"],
                          "area_ha": s["area_ha"], "fecha_cierre": None if s.get("fecha_cierre") is None else str(s["fecha_cierre"]), "lon": round(c.x, 5), "lat": round(c.y, 5),
                          "fuentes_estado": ",".join(sorted({str(e.get("fuente") if isinstance(e, dict) else e)
                                                             for e in (s.get("estados_por_fuente") or [])})) or None,
                          "celda": f"{math.floor(c.x):+04d}_{math.floor(c.y):+03d}", "geom": g})
    todas += [g for g in (cp._valida(shapely.from_wkb(w)) for _, w in cp._mundo() if w is not None) if g is not None]
    return pd.DataFrame(filas), todas


def buscar(caja, intentos=4):
    for i in range(intentos):
        try:
            return eo.buscar_escenas(caja, *PERIODO, 20.0)
        except Exception as e:  # el buscador de Planetary Computer a veces se cuelga: se reintenta
            if i == intentos - 1:
                raise
            print(f"    el buscador falló ({type(e).__name__}); reintento {i + 1}", flush=True)
            time.sleep(5 * (i + 1))


def correr(parte, total, hilos, a_la_vez, aceptar_vacias=False):
    from concurrent.futures import ThreadPoolExecutor, as_completed
    df, todas = sitios()
    arbol = shapely.STRtree(todas)
    celdas = sorted(df["celda"].unique())
    mias = [c for i, c in enumerate(celdas) if i % total == parte - 1]
    os.makedirs(CELDAS, exist_ok=True)
    camino = lambda c: os.path.join(CELDAS, f"{c}.parquet")  # noqa: E731
    faltan = [c for c in mias if not os.path.exists(camino(c))]
    print(f"{len(df)} basurales de estado conocido en {len(celdas)} celdas; esta parte ({parte}/{total}): {len(mias)} celdas, "
          f"{df['celda'].isin(mias).sum()} basurales; faltan {len(faltan)} celdas", flush=True)

    def una(celda):
        d = df[df["celda"] == celda]
        obj = [{"tipo": "catalogo", "clave": r.id_catalogo, "catalogo": "basurales", "frame": celda, "geom": r.geom} for r in d.itertuples()]
        caja = cp.bbox_de([o["geom"] for o in obj], margen=0.03)
        escenas = buscar(caja)
        excluir = [todas[i] for i in arbol.query(shapely.box(*caja))]
        res = eo.extraer(obj, escenas, excluir, hilos=hilos, max_fechas=10, periodo=PERIODO, avisar=lambda m: None)
        vacios = sum(r["n_escenas"] == 0 for r in res)
        if vacios and not aceptar_vacias:
            raise RuntimeError(f"{vacios} de {len(obj)} basurales quedaron sin escenas")
        pd.DataFrame([{"id_catalogo": o["clave"], **r} for o, r in zip(obj, res)]).to_parquet(camino(celda), index=False)
        return len(obj), len(escenas)

    t0, fallas = time.time(), []
    with ThreadPoolExecutor(max_workers=a_la_vez) as ex:  # varias celdas a la vez: lo lento es la red
        futuros = {ex.submit(una, c): c for c in faltan}
        for n, f in enumerate(as_completed(futuros), 1):
            celda = futuros[f]
            try:
                k, e = f.result()
                print(f"  [{n}/{len(faltan)}] {celda}: {k} basurales, {e} escenas ({time.time() - t0:.0f} s)", flush=True)
            except Exception as err:
                fallas.append(celda)
                print(f"  [{n}/{len(faltan)}] {celda}: FALLÓ ({type(err).__name__}: {err}); queda pendiente", flush=True)
    hechas = [pd.read_parquet(camino(c)) for c in mias if os.path.exists(camino(c))]
    if hechas:
        os.makedirs(PARTES, exist_ok=True)
        destino = os.path.join(PARTES, f"parte_{parte}de{total}.parquet")
        pd.concat(hechas).to_parquet(destino, index=False)
        print(f"{destino}: {sum(len(h) for h in hechas)} basurales")
    if LECTURAS_PERDIDAS:
        print(f"OJO: {len(LECTURAS_PERDIDAS)} lecturas de escena se perdieron después de 4 intentos: hay basurales con menos escenas.")
    if fallas:
        print(f"Quedaron {len(fallas)} celdas sin medir: volvé a correr el mismo comando. Si siguen quedando las mismas, es que no "
              f"tienen escenas sin nubes: corré una última vez con --aceptar-vacias. {fallas}")
    return 1 if fallas else 0


def juntar():
    df, _ = sitios()
    archivos = glob.glob(os.path.join(PARTES, "parte_*.parquet")) + glob.glob(os.path.join(CELDAS, "*.parquet"))
    if not archivos:
        raise SystemExit("No hay nada medido todavía: corré `correr` primero.")
    med = pd.concat([pd.read_parquet(a) for a in archivos]).drop_duplicates("id_catalogo")
    t = df.drop(columns=["geom"]).merge(med, on="id_catalogo", how="inner").sort_values("id_catalogo").reset_index(drop=True)
    t["n_escenas"] = t["n_escenas"].astype("int64")
    t.to_parquet(SALIDA, index=False)
    print(f"{SALIDA}: {len(t)} de {len(df)} basurales de estado conocido; con escenas: {(t.n_escenas > 0).sum()}")
    return t


def auc(pos, neg):
    """Probabilidad de que un valor de `pos` sea MENOR que uno de `neg` (empates cuentan 1/2)."""
    from scipy.stats import rankdata
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    pos, neg = pos[np.isfinite(pos)], neg[np.isfinite(neg)]
    if len(pos) == 0 or len(neg) == 0:
        return None
    v = rankdata(np.r_[pos, neg])
    return 1 - float((v[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def wilson(k, n, z=1.96):
    if n == 0:
        return None
    p, d = k / n, 1 + z * z / n
    c, r = (p + z * z / (2 * n)) / d, z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(c - r, 0), 3), round(min(c + r, 1), 3)]


def resumen():
    if not os.path.exists(SALIDA):
        juntar()
    t = pd.read_parquet(SALIDA)
    t = t[(t.n_escenas > 0) & t.ndvi_contraste.notna()]
    with open(os.path.join(DATA, "frames.json"), encoding="utf-8") as fh:
        cajas = [f["bbox"] for f in json.load(fh)["frames"] if f["frame"] in FRAMES_DEL_UMBRAL]
    t["en_frame"] = [any(b[0] <= x <= b[2] and b[1] <= y <= b[3] for b in cajas) for x, y in zip(t.lon, t.lat)]

    def fila(nombre, d):
        a, c = d[d.estado == "abierto"], d[d.estado == "cerrado"]
        ka, kc = int((a.ndvi_contraste < UMBRAL_NDVI).sum()), int((c.ndvi_contraste < UMBRAL_NDVI).sum())
        v = auc(a.ndvi_contraste, c.ndvi_contraste)
        return {"grupo": nombre, "abiertos": len(a), "cerrados": len(c),
                "abiertos_pelados": ka, "abiertos_pelados_ic95": wilson(ka, len(a)),
                "cerrados_pelados": kc, "cerrados_pelados_ic95": wilson(kc, len(c)),
                "ndvi_contraste_mediana": [round(float(x.ndvi_contraste.median()), 3) if len(x) else None for x in (a, c)],
                "auc": None if v is None else round(v, 3)}

    filas = [fila("todos", t), fila("fuera de los 10 frames con que se fijó el umbral (prueba independiente)", t[~t.en_frame]),
             fila("en los 10 frames con que se fijó el umbral", t[t.en_frame])]
    filas += [fila(f"país {p}", d) for p, d in t.groupby(t.pais.fillna("sin país")) if len(d) >= 10]
    filas += [fila(f"cerrados con fecha de cierre {txt}", pd.concat([t[t.estado == "abierto"], t[(t.estado == "cerrado") & m]]))
              for txt, m in (("hasta 2015", t.fecha_cierre.astype(str).str[:4].str.isdigit() & (t.fecha_cierre.astype(str).str[:4] <= "2015")),
                             ("desde 2016", t.fecha_cierre.astype(str).str[:4].str.isdigit() & (t.fecha_cierre.astype(str).str[:4] >= "2016")))]
    salida = {"generado_por": "motor/optico_estado_conocido.py resumen", "periodo": PERIODO, "umbral_ndvi_contraste": UMBRAL_NDVI,
              "nota": "pelado = ndvi_contraste < umbral. AUC = probabilidad de que un abierto sea menos verde, contra su entorno, "
                      "que un cerrado. El estado es el del registro y puede estar desactualizado.", "grupos": filas}
    destino = SALIDA.replace(".parquet", "_resumen.json")
    with open(destino, "w", encoding="utf-8") as fh:
        json.dump(salida, fh, ensure_ascii=False, indent=1)
    print(f"| Grupo | Abiertos pelados | Cerrados pelados | AUC |\n|---|---|---|---|")
    for f in filas:
        print(f"| {f['grupo']} | {f['abiertos_pelados']} de {f['abiertos']} | {f['cerrados_pelados']} de {f['cerrados']} | {f['auc']} |")
    print(destino)


def main():
    a = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = a.add_subparsers(dest="orden", required=True)
    c = sub.add_parser("correr")
    c.add_argument("--parte", default="1/1", help="i/n: esta compu hace la parte i de n (por defecto, todo)")
    c.add_argument("--hilos", type=int, default=8, help="lecturas en paralelo por celda")
    c.add_argument("--celdas-a-la-vez", type=int, default=6)
    c.add_argument("--aceptar-vacias", action="store_true", help="guardar también las celdas con basurales sin ninguna escena")
    sub.add_parser("juntar")
    sub.add_parser("resumen")
    args = a.parse_args()
    if args.orden == "correr":
        i, n = (int(x) for x in args.parte.split("/"))
        if not 1 <= i <= n:
            raise SystemExit("--parte va como i/n, con 1 <= i <= n")
        return correr(i, n, args.hilos, args.celdas_a_la_vez, args.aceptar_vacias)
    if args.orden == "juntar":
        juntar()
    else:
        resumen()
    return 0


if __name__ == "__main__":
    sys.exit(main())
