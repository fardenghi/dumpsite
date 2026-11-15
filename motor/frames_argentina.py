"""Frames de Argentina fuera del AMBA: dónde el catálogo tiene más basurales de 10 ha o más (15/11, prompt 7).

Sólo para predecir con el modelo vigente: estos frames no entran al entrenamiento (`reservado_prueba = true`).

    python frames_argentina.py contar                  # tabla por celda de 1° (no escribe nada)
    python frames_argentina.py agregar --celdas 61O,33S 65O,32S ...   # suma esas celdas a data/frames.json

Cómo cuenta:
- Un sitio es de Argentina si su punto cae en el contorno de Natural Earth 1:10m (`fijos/argentina_ne10m.geojson`).
  No se usa el campo `pais`: los sitios que sólo vienen de OSM no lo traen.
- Se sacan los que caen en la caja de un frame que ya está en `data/frames.json` (el AMBA).
- Celda = (piso de lon, piso de lat). Se cuentan los sitios de 10 ha o más (el piso del índice) y el total.

`agregar` hace lo mismo que `frames_elegir.py --agregar`, pero con todos los estados (en Argentina fuera del AMBA
ningún sitio tiene estado conocido, así que `--agregar`, que elige por abiertos, no sirve):
- la caja es la de los polígonos (o el punto, si no hay polígono) de los sitios de 10 ha o más de la celda, más 5 km;
- consulta la API pública de ASF y elige hasta 2 tracks que cubran el 75 % de la caja;
- entra si tiene al menos 15 pares GUNW `PR` y la caja no se toca con la de otro frame;
- deja los frames que ya están con el mismo nombre, caja y prioridad, y suma los nuevos con prioridad de ahí en adelante.
"""
import argparse
import collections
import datetime as dt
import json
import math
import os
import sys

import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import frames_elegir as fe  # noqa: E402

CONTORNO = os.path.join(AQUI, "fijos", "argentina_ne10m.geojson")
MIN_HA = 10.0


def contorno_argentina():
    from shapely.geometry import shape
    from shapely.prepared import prep
    with open(CONTORNO, encoding="utf-8") as fh:
        return prep(shape(json.load(fh)["features"][0]["geometry"]))


def cajas_poligono():
    with open(os.path.join(fe.DATA, "basurales", "geometrias.geojson"), encoding="utf-8") as fh:
        feats = json.load(fh)["features"]
    salida = {}
    for f in feats:
        g = f.get("geometry")
        if not g or g["type"] not in ("Polygon", "MultiPolygon"):
            continue
        anillos = g["coordinates"] if g["type"] == "Polygon" else [a for pol in g["coordinates"] for a in pol]
        xy = np.array([p[:2] for a in anillos for p in a], dtype=float)
        salida[f["properties"]["id"]] = [xy[:, 0].min(), xy[:, 1].min(), xy[:, 0].max(), xy[:, 1].max()]
    return salida


def sitios_argentina(frames):
    """Los sitios del catálogo dentro de Argentina y fuera de las cajas de `frames`."""
    from shapely.geometry import Point
    arg = contorno_argentina()
    with open(os.path.join(fe.DATA, "basurales", "basurales_mundo.json"), encoding="utf-8") as fh:
        sitios = json.load(fh)["sitios"]
    dentro, en_caja = [], collections.Counter()
    for s in sitios:
        lat, lon = s.get("lat"), s.get("lon")
        if lat is None or not (-56 < lat < -21 and -74 < lon < -53) or not arg.contains(Point(lon, lat)):
            continue
        caja = next((f["frame"] for f in frames if f["bbox"][0] <= lon <= f["bbox"][2] and f["bbox"][1] <= lat <= f["bbox"][3]), None)
        if caja:
            en_caja[caja] += 1
            continue
        dentro.append(s)
    return dentro, en_caja


def por_celda(sitios):
    celdas = collections.defaultdict(list)
    for s in sitios:
        celdas[(math.floor(s["lon"]), math.floor(s["lat"]))].append(s)
    return celdas


def contar(args):
    frames = json.load(open(args.frames, encoding="utf-8"))["frames"]
    sitios, en_caja = sitios_argentina(frames)
    print(f"{len(sitios)} sitios en Argentina fuera de las cajas de frames.json "
          f"(sin campo `pais`: {sum(not s.get('pais') for s in sitios)}); en cajas ya elegidas: {dict(en_caja)}")
    filas = []
    for (lo, la), ss in por_celda(sitios).items():
        g = [s for s in ss if (s.get("area_ha") or 0) >= MIN_HA]
        filas.append((len(g), len(ss), lo, la, collections.Counter(s["estado"] for s in g)))
    filas.sort(key=lambda x: (-x[0], -x[1]))
    print(f"{'celda (lon, lat)':>18} {'>=10 ha':>8} {'total':>6}  estados de los >=10 ha")
    for n10, n, lo, la, est in filas[:args.top]:
        print(f"{f'({lo}, {la})':>18} {n10:>8} {n:>6}  {dict(est)}")


def agregar(args):
    with open(args.frames, encoding="utf-8") as fh:
        actual = json.load(fh)
    viejos = actual["frames"]
    sitios, _ = sitios_argentina(viejos)
    celdas = por_celda(sitios)
    pol = cajas_poligono()
    complejos, negativos = fe.cargar_catalogos()
    nombres = {f["frame"] for f in viejos}
    elegidos, descartadas = [], []
    a = argparse.Namespace(cache=args.cache, min_cobertura=0.75)
    for texto, nombre, ciudad in zip(args.celdas, args.nombres, args.ciudades):
        lo, la = (-int(v[:-1]) for v in texto.upper().split(","))  # "61O,33S" -> (-61, -33)
        ss = [s for s in celdas.get((lo, la), []) if (s.get("area_ha") or 0) >= MIN_HA]
        if not ss:
            descartadas.append({"celda": [lo, la], "frame": nombre, "motivo": "sin sitios de 10 ha o más"})
            continue
        if nombre in nombres:
            sys.exit(f"{nombre} ya está en frames.json")
        caja = fe.caja_con_margen([pol.get(s["id"], [s["lon"], s["lat"], s["lon"], s["lat"]]) for s in ss])
        toca = next((f["frame"] for f in viejos + elegidos if fe.se_tocan(caja, f["bbox"])), None)
        if toca:
            descartadas.append({"celda": [lo, la], "frame": nombre, "motivo": f"la caja se toca con la de {toca}"})
            print(f"{nombre}: no entra, la caja {caja} se toca con la de {toca}")
            continue
        ref = max(ss, key=lambda s: s["area_ha"])
        f = fe.evaluar_area(nombre, f"{ciudad} (alrededor de {ref.get('nombre') or ref['id']})", "ARG", caja, a, complejos, negativos)
        if f.get("sin_cobertura") or f["n_gunw"] < fe.MIN_PARES_AGREGAR:
            motivo = (f"sin frame GUNW PR que cubra el 75 % de la caja (mejor {f.get('mejor_cobertura')})" if f.get("sin_cobertura")
                      else f"sólo {f['n_gunw']} pares GUNW PR (hacen falta {fe.MIN_PARES_AGREGAR})")
            descartadas.append({"celda": [lo, la], "frame": nombre, "motivo": motivo})
            print(f"{nombre}: no entra, {motivo}")
            continue
        lon, lat = np.array([s["lon"] for s in ss]), np.array([s["lat"] for s in ss])
        cubre = np.zeros(len(ss), dtype=bool)
        for h in f["_huellas"]:
            cubre |= fe.dentro_poligono(lon, lat, h)
        f["n_sitios_10ha"] = {e: int(sum(c and s["estado"] == e for s, c in zip(ss, cubre))) for e in ("abierto", "cerrado", "desconocido")}
        f["n_sitios_total_celda"] = len(celdas[(lo, la)])
        f["criterio"], f["celda"] = "argentina", [lo, la]
        f["reservado_prueba"] = True
        f["prioridad"] = max(g["prioridad"] for g in viejos) + 1 + len(elegidos)
        print(f"{nombre}: entra con prioridad {f['prioridad']}, caja {f['bbox']}, {f['frames_nisar']}, {f['n_gunw']} pares "
              f"({f['fecha_inicio']} a {f['fecha_fin']}); sitios de 10 ha o más en la huella: {f['n_sitios_10ha']}")
        elegidos.append(f)
        nombres.add(nombre)

    claves = ["frame", "orbita", "ciudad", "pais", "hemisferio", "epsg", "bbox", "n_gunw", "fecha_inicio", "fecha_fin",
              "n_basurales_10ha", "n_negativos", "reservado_prueba", "frames_nisar",
              "prioridad", "puntaje", "n_negativos_a_10ha", "n_gunw_por_track", "cobertura", "criterio", "celda",
              "n_sitios_10ha", "n_sitios_total_celda"]
    actual["frames"] = viejos + [{k: f[k] for k in claves} for f in elegidos]
    actual["meta"]["argentina"] = {
        "generado": dt.date.today().isoformat(), "generado_por": "herramientas/frames_argentina.py agregar",
        "n": len(elegidos),
        "criterio": ("celdas de 1° de Argentina (contorno de Natural Earth 1:10m, no el campo `pais`) con más sitios del catálogo "
                     "de 10 ha o más, sin contar los de la caja del AMBA; caja achicada a esos sitios más 5 km; al menos "
                     f"{fe.MIN_PARES_AGREGAR} pares GUNW PR. Sólo para predecir: reservado_prueba = true, no se entrena con ellos"),
        "aviso": "ningún sitio de estas celdas tiene estado conocido (todos `desconocido`): no sirven para evaluar abiertos contra cerrados",
        "celdas_descartadas": descartadas,
    }
    import pandas as pd

    import contratos
    contratos.validar(pd.DataFrame(actual["frames"]), "frames")
    with open(args.frames, "w", encoding="utf-8") as fh:
        json.dump(actual, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print(f"\n{len(elegidos)} frames agregados a {os.path.relpath(args.frames)}; descartadas: {len(descartadas)}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("accion", choices=["contar", "agregar"])
    p.add_argument("--frames", default=os.path.join(fe.DATA, "frames.json"))
    p.add_argument("--top", type=int, default=12)
    p.add_argument("--celdas", nargs="+", default=[], help='esquina sudoeste de cada celda, en grados oeste y sur: 61O,33S es lon -61 a -60, lat -33 a -32')
    p.add_argument("--nombres", nargs="+", default=[], help="nombre del frame de cada celda, en el mismo orden")
    p.add_argument("--ciudades", nargs="+", default=[], help="ciudad de referencia de cada celda, en el mismo orden")
    p.add_argument("--cache", help="carpeta para guardar las respuestas de ASF")
    args = p.parse_args()
    if args.accion == "agregar" and not (len(args.celdas) == len(args.nombres) == len(args.ciudades)):
        sys.exit("--celdas, --nombres y --ciudades tienen que tener el mismo largo")
    (contar if args.accion == "contar" else agregar)(args)


if __name__ == "__main__":
    main()
