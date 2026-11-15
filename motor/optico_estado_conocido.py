"""Sentinel-2 optical data for ALL the known-status dump sites in the catalog, whether or not they are in a NISAR frame.

Question: does "less green than its surroundings" separate open dump sites from closed ones? In the 10 processed frames
it separated 19 of 24 open and 4 of 35 closed (threshold of −0.15 on `ndvi_contraste`, picked with 5 frames). Here it is measured
with every one in the catalog: those with status `abierto` or `cerrado`, of 10 ha or more and with a polygon (about 1,000).

It uses neither NISAR nor the VM: it reads Sentinel-2 L2A windows with `extraer_optico.py` (unmodified). It can be split
across several computers and stopped and resumed: each 1° cell is saved in `datos/optico_estado/celdas/` (not committed).

    python optico_estado_conocido.py correr --parte 1/3     # a third of the cells; the other computers, 2/3 and 3/3
    python optico_estado_conocido.py juntar                 # builds ../data/salidas/optico_estado_conocido.parquet with whatever is there
    python optico_estado_conocido.py resumen                # open versus closed, in total and by country

At the end `correr` leaves its part in `../data/salidas/optico_estado_conocido/parte_<i>de<n>.parquet` (small: committed).
`juntar` reads all the committed parts plus the local cells.

- Period: from 21/10/2025 to 21/10/2026 (the NISAR year of the frames), up to 10 dates spread over the year.
- 1.5 km ring without water and without the other catalog polygons, same as in `extraer_optico.py`.
- The status is the registry's (`data/catalogos/basurales/`: EPA LMOP, OSM and curated cases). It may be outdated.
- **The threshold isn't touched here:** `resumen` reports the already fixed −0.15, plus the AUC, which doesn't depend on the threshold.

Data: Copernicus Sentinel-2 L2A (ESA), via Microsoft Planetary Computer. Catalog: see `../data/README.md`.
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
UMBRAL_NDVI = -0.15  # fixed before this run (see the header); not adjusted here
# The 10 frames that existed when the threshold was fixed. What falls outside them is the independent test.
FRAMES_DEL_UMBRAL = ("AMBA", "LOS_ANGELES", "USA_OH_LAKE", "USA_MD_HOWARD", "CDMX", "PRI_PONCE", "USA_NH_HILLSBOROUGH",
                     "USA_NY_RICHMOND", "DELHI", "YAKARTA")

# `extraer_optico.py` requests a new read permission (token) on every call and, if a read fails, skips it with
# a warning. With many cells at once the permission service answers "429 Too Many Requests" and the scenes get
# lost silently: the dump site ends up with fewer scenes or none. That's why here, without touching that file:
#   - ONE single permission is used for the whole run;
#   - each read is retried before giving it up, and the lost ones are counted;
#   - a cell with some dump site without scenes isn't saved (stays pending), unless `--aceptar-vacias` is given.
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
    """The dump sites to measure (DataFrame with geom) and all the catalog geometries, to remove them from the ring."""
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
        except Exception as e:  # the Planetary Computer search sometimes hangs: it's retried
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
    with ThreadPoolExecutor(max_workers=a_la_vez) as ex:  # several cells at once: the slow part is the network
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
    """Probability that a value of `pos` is LOWER than one of `neg` (ties count 1/2)."""
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
    c.add_argument("--parte", default="1/1", help="i/n: this computer does part i of n (default: everything)")
    c.add_argument("--hilos", type=int, default=8, help="parallel reads per cell")
    c.add_argument("--celdas-a-la-vez", type=int, default=6)
    c.add_argument("--aceptar-vacias", action="store_true", help="also save cells with dump sites that have no scenes")
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
