"""Etapa 6: junta radar, óptico y cruce de cada mancha, la etiqueta y arma las particiones por frame.

Escribe `tabla_entrenamiento.parquet` y `particiones.json` según `../docs/contratos-datos.md`.

    python armar_tabla.py                                  # lee y escribe en ../data/salidas/
    python armar_tabla.py --datos datos/mock --salida datos/mock/prueba
    python armar_tabla.py --radar datos/amba_provisional/tabla_radar.parquet --salida datos/amba_provisional

Etiqueta (etapa 6 del plan):
- una mancha se cruza con un polígono si la intersección cubre al menos `--criterio` (0,30) del área menor y, si el
  cruce trae `inter_ha`, además mide al menos `--min-inter-ha` (5,12 ha = 8 píxeles de 80 m; ver `../docs/modelo.md`);
- se cruza sólo con basurales (de cualquier estado) → `basural_activo`; sólo con negativos → `otro_movil`;
  con los dos o con ninguno → no entra;
- un complejo cuenta una vez: si varias manchas caen sobre el mismo complejo (o el mismo negativo), queda la más grande;
- `id_catalogo` es el polígono de mayor `frac_area_menor`.

Opciones que se agregaron con la corrida 2 (ver `../docs/resultados.md`):
- `--negativos-osm`: suma como `otro_movil` las manchas candidatas que la etapa 4 marcó `clase_osm` = `uso_conocido`
  (aeródromos, golf, parques, cementerios, canteras, forestación, predios militares y reservas de OSM vía Overture) y
  que **no tocan ningún basural del catálogo** ni tienen nombre de relleno (`NOMBRE_DE_RELLENO`: "Freshkills Park"). Sólo en los frames que no son de la prueba final (en el AMBA esa marca
  sale de Nominatim y no es comparable). Su `id_catalogo` es `NEG-OSM-<id_mancha>` (no están en `data/catalogos/negativos/`),
  su `clase_negativo` es `osm_<tipo>` y, si el lugar tiene nombre, todas sus manchas cuentan una vez.
- `--etiquetas-optico` y `--positivos`: `salidas/etiquetas_optico_ia.json` dice, por basural, si en Sentinel-2 se ve
  actividad (`act`), no se ve (`sin`) o no se puede decir (`nose`). **Las puso una IA y no las revisó una persona.**
  `--positivos sin_sin` saca de `basural_activo` las manchas cuyo basural es `sin`; `--positivos solo_act` deja sólo
  las `act`. La columna `actividad_optica` queda en la tabla (no entra al modelo).

Particiones: por frame. Los frames con `reservado_prueba` (Argentina) van a `prueba_final`. Los demás se reparten en
hasta `--particiones` grupos, equilibrando la cantidad de filas (cada frame entero en un grupo).
Sin `frames.json`, el AMBA se toma como Buenos Aires, ARG, reservado para la prueba final.
"""
import argparse
import json
import os
import re
import sys

import numpy as np
import pandas as pd

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import contratos  # noqa: E402

FRAMES_POR_DEFECTO = {"AMBA": {"ciudad": "Buenos Aires", "pais": "ARG", "reservado_prueba": True}}
MIN_INTER_HA = 5.12  # 8 píxeles de 80 m: `insomnio.Parametros.min_px_sitio`


def leer_frames(camino):
    if camino and os.path.exists(camino):
        df = contratos.leer(camino)
        return {r["frame"]: {"ciudad": r["ciudad"], "pais": r["pais"], "reservado_prueba": bool(r["reservado_prueba"])}
                for _, r in df.iterrows()}
    print(f"Aviso: no hay frames.json ({camino or "../data/catalogos/frames.json"}); se usan los datos por defecto del AMBA.", file=sys.stderr)
    return dict(FRAMES_POR_DEFECTO)


POSITIVOS = ("todos", "sin_sin", "solo_act")


def leer_etiquetas_optico(camino):
    """{id_catalogo: 'act' | 'sin' | 'nose'} de `etiquetas_optico_ia.json` (etiquetas de una IA, sin revisar)."""
    with open(camino, encoding="utf-8") as fh:
        return {e["id_catalogo"]: e["final"] for e in json.load(fh)["etiquetas"]}


def _actividad(ids, optico_ia):
    """Actividad óptica de una mancha según los basurales que cruza: `act` si en alguno se ve, `sin` si en ninguno se
    ve y en alguno se dijo que no, `nose` si no se pudo decir, y None si ninguno tiene etiqueta."""
    vistos = {optico_ia[i] for i in ids if i in optico_ia}
    return "act" if "act" in vistos else "sin" if "sin" in vistos else "nose" if vistos else None


# Un uso conocido cuyo nombre dice que es (o fue) un relleno no puede ser negativo: un basural de cualquier estado es
# `basural_activo` (etapa 6). No entra al entrenamiento ni como positivo (no está cruzado con el catálogo).
NOMBRE_DE_RELLENO = re.compile(r"landfill|fresh ?kills|relleno sanitario|vertedero|basur|tiradero|dump|tempat pembuangan|\bTPA\b", re.I)


def negativos_osm(radar, cruce, frames, ya_etiquetadas):
    """Manchas `uso_conocido` de OSM como `otro_movil`: las que no tocan ningún basural del catálogo, no están ya
    etiquetadas y son de frames que no van a la prueba final."""
    cols = ["id_mancha", "id_catalogo", "complejo", "clase_negativo", "clase"]
    if "clase_osm" not in radar.columns:
        raise SystemExit("--negativos-osm: la tabla de radar no trae `clase_osm` (la escribe la etapa 4).")
    tocan_basural = set(cruce.loc[cruce["catalogo"] == "basurales", "id_mancha"])
    r = radar[(radar["clase_osm"] == "uso_conocido") & ~radar["id_mancha"].isin(tocan_basural | set(ya_etiquetadas))
              & ~radar["frame"].map(lambda f: bool(frames.get(f, {}).get("reservado_prueba")))]
    filas = []
    for _, m in r.iterrows():
        que = m["que"] if isinstance(m.get("que"), str) and m["que"] else "sin_dato"
        if NOMBRE_DE_RELLENO.search(que):
            continue
        tipo, _, nombre = que.partition(":")
        filas.append({"id_mancha": m["id_mancha"], "id_catalogo": f"NEG-OSM-{m['id_mancha']}",
                      "complejo": f"OSM:{m['frame']}:{que}" if nombre.strip() else f"NEG-OSM-{m['id_mancha']}",
                      "clase_negativo": "osm_" + tipo.strip().replace(" ", "_"), "clase": "otro_movil"})
    return pd.DataFrame(filas, columns=cols)


def etiquetar(cruce, criterio=contratos.CRITERIO_CRUCE, min_inter_ha=MIN_INTER_HA, optico_ia=None):
    """Una fila por mancha etiquetada: id_mancha, id_catalogo, complejo, clase_negativo, clase (y `actividad_optica`
    si se pasan las etiquetas ópticas)."""
    c = cruce[cruce["frac_area_menor"] >= criterio].copy()
    if "inter_ha" in c.columns and min_inter_ha:
        c = c[c["inter_ha"] >= min_inter_ha]
    filas = []
    for idm, g in c.groupby("id_mancha"):
        cats = set(g["catalogo"])
        if len(cats) != 1:
            continue
        mejor = g.sort_values("frac_area_menor", ascending=False).iloc[0]
        es_bas = mejor["catalogo"] == "basurales"
        cpx = mejor.get("complejo") if es_bas else None
        filas.append({
            "id_mancha": idm, "id_catalogo": mejor["id_catalogo"],
            "complejo": cpx if isinstance(cpx, str) and cpx else mejor["id_catalogo"],
            "clase_negativo": None if es_bas else mejor.get("clase_negativo"),
            "clase": "basural_activo" if es_bas else "otro_movil",
            "actividad_optica": _actividad(list(g["id_catalogo"]), optico_ia) if es_bas and optico_ia is not None else None,
        })
    cols = ["id_mancha", "id_catalogo", "complejo", "clase_negativo", "clase"] + (["actividad_optica"] if optico_ia is not None else [])
    return pd.DataFrame(filas, columns=cols)


def repartir(filas_por_frame, k):
    """Reparte frames en k grupos equilibrando filas (el más grande primero al grupo más chico)."""
    k = max(1, min(k, len(filas_por_frame)))
    grupos = [[] for _ in range(k)]
    carga = [0] * k
    for f, n in sorted(filas_por_frame.items(), key=lambda x: (-x[1], x[0])):
        i = int(np.argmin(carga))
        grupos[i].append(f)
        carga[i] += n
    return {str(i): sorted(g) for i, g in enumerate(grupos) if g}


def armar(radar, optico, cruce, frames, criterio=contratos.CRITERIO_CRUCE, min_inter_ha=MIN_INTER_HA,
          umbral_insomnio=0.70, k=5, extra=None, con_negativos_osm=False, optico_ia=None, positivos="todos"):
    if positivos not in POSITIVOS:
        raise SystemExit(f"--positivos tiene que ser uno de {POSITIVOS}")
    if positivos != "todos" and optico_ia is None:
        raise SystemExit("--positivos sin_sin y solo_act necesitan --etiquetas-optico")
    etiquetas = etiquetar(cruce, criterio, min_inter_ha, optico_ia)
    sacadas = {}
    if positivos != "todos":  # sólo en los frames de entrenamiento: la prueba final no se toca
        frame_de = dict(zip(radar["id_mancha"], radar["frame"]))
        entrena = ~etiquetas["id_mancha"].map(lambda i: bool(frames.get(frame_de.get(i), {}).get("reservado_prueba")))
        bas = etiquetas["clase"] == "basural_activo"
        fuera = bas & entrena & ((etiquetas["actividad_optica"] == "sin") if positivos == "sin_sin" else (etiquetas["actividad_optica"] != "act"))
        sacadas = etiquetas.loc[fuera, "actividad_optica"].fillna("sin_etiqueta").value_counts().to_dict()
        etiquetas = etiquetas[~fuera]
    n_osm = 0
    if con_negativos_osm:
        osm = negativos_osm(radar, cruce, frames, etiquetas["id_mancha"])
        n_osm = len(osm)
        etiquetas = pd.concat([etiquetas, osm], ignore_index=True)
    radar = radar.drop(columns=[c for c in ("clase_osm", "que") if c in radar.columns])
    opt = optico.drop(columns=[c for c in ("frame", "n_escenas", "fechas") if c in optico.columns])
    t = radar.merge(opt, on="id_mancha", how="left").merge(etiquetas, on="id_mancha", how="inner")
    if extra is not None:  # por ejemplo, cnn_p_basural
        t = t.merge(extra, on="id_mancha", how="left")
    t = t[t["insomnio"] >= umbral_insomnio]
    # un complejo cuenta una vez por frame: queda la mancha más grande
    t = t.sort_values(["area_ha", "id_mancha"], ascending=[False, True]).drop_duplicates(["frame", "complejo"])
    faltan = sorted(set(t["frame"]) - set(frames))
    if faltan:
        raise SystemExit(f"Frames sin datos en frames.json: {faltan}")
    t["ciudad"] = t["frame"].map(lambda f: frames[f]["ciudad"])
    t["pais"] = t["frame"].map(lambda f: frames[f]["pais"])
    for c in contratos.COLUMNAS_MODELO:
        if c not in t.columns:
            t[c] = np.nan
    t = t.sort_values("id_mancha").reset_index(drop=True)

    reservados = sorted(f for f in set(t["frame"]) if frames[f]["reservado_prueba"])
    entrenar = t[~t["frame"].isin(reservados)]
    partes = repartir(entrenar.groupby("frame").size().to_dict(), k) if len(entrenar) else {}
    conteos = {f: g["clase"].value_counts().to_dict() for f, g in t.groupby("frame")}
    particiones = {
        "meta": {"generado_por": "motor/armar_tabla.py", "umbral_insomnio": umbral_insomnio,
                 "criterio_cruce": criterio, "min_inter_ha": min_inter_ha if "inter_ha" in cruce.columns else None,
                 "negativos_osm": bool(con_negativos_osm), "negativos_osm_antes_de_agrupar": int(n_osm),
                 "positivos": positivos, "positivos_sacados_por_el_optico": sacadas,
                 "etiquetas_optico": None if optico_ia is None else "etiquetas de una IA sobre Sentinel-2, sin revisar por una persona",
                 "filas_por_clase": conteos},
        "particiones": partes, "prueba_final": reservados,
    }
    return t, particiones


def main():
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--datos", default=os.path.join(AQUI, "..", "data", "salidas"), help="carpeta con los parquets de entrada")
    a.add_argument("--radar")
    a.add_argument("--optico")
    a.add_argument("--cruce")
    a.add_argument("--frames", help="frames.json (por defecto ../data/catalogos/frames.json, o el de --datos si existe)")
    a.add_argument("--cnn", help="parquet con id_mancha y cnn_p_basural (opcional)")
    a.add_argument("--salida", default=os.path.join(AQUI, "..", "data", "salidas"))
    a.add_argument("--criterio", type=float, default=contratos.CRITERIO_CRUCE)
    a.add_argument("--min-inter-ha", type=float, default=MIN_INTER_HA)
    a.add_argument("--umbral-insomnio", type=float, default=0.70,
                   help="insomnio mínimo de la mancha para entrenar (se anota en particiones.json)")
    a.add_argument("--particiones", type=int, default=5)
    a.add_argument("--negativos-osm", action="store_true", help="sumar las manchas `uso_conocido` de OSM como `otro_movil`")
    a.add_argument("--etiquetas-optico", help="etiquetas_optico_ia.json (actividad en óptico por basural; de una IA, sin revisar)")
    a.add_argument("--positivos", choices=POSITIVOS, default="todos",
                   help="qué basurales cuentan como `basural_activo` según --etiquetas-optico")
    args = a.parse_args()

    radar = contratos.leer(args.radar or contratos.ruta("tabla_radar", args.datos))
    optico = contratos.leer(args.optico or contratos.ruta("tabla_optico", args.datos))
    cruce = contratos.leer(args.cruce or contratos.ruta("cruce_manchas_catalogo", args.datos))
    frames_json = args.frames or next((c for c in (os.path.join(args.datos, "frames.json"),
                                                   os.path.join(AQUI, "..", "data", "catalogos", "frames.json")) if os.path.exists(c)), None)
    frames = leer_frames(frames_json)
    extra = pd.read_parquet(args.cnn)[["id_mancha", "cnn_p_basural"]] if args.cnn else None

    optico_ia = leer_etiquetas_optico(args.etiquetas_optico) if args.etiquetas_optico else None
    t, partes = armar(radar, optico, cruce, frames, args.criterio, args.min_inter_ha, args.umbral_insomnio, args.particiones, extra,
                      con_negativos_osm=args.negativos_osm, optico_ia=optico_ia, positivos=args.positivos)
    destino = contratos.guardar(t, "tabla_entrenamiento", args.salida)
    print(f"{destino}: {len(t)} filas: {t['clase'].value_counts().to_dict()}")
    print("Por frame:", json.dumps(partes["meta"]["filas_por_clase"], ensure_ascii=False))
    camino = contratos.ruta("particiones", args.salida)
    try:
        contratos.validar_particiones(partes, frames=sorted(set(t["frame"])))
    except contratos.ErrorContrato as e:
        print(f"Aviso: particiones.json no es válido para entrenar por frame ({str(e).splitlines()[-1].strip()}). "
              "Se escribe igual: `entrenar.py --humo` lo puede usar para probar que corre.", file=sys.stderr)
    with open(camino, "w", encoding="utf-8") as fh:
        json.dump(partes, fh, ensure_ascii=False, indent=1)
    print(f"{camino}: {partes['particiones']} · prueba final: {partes['prueba_final']}")


if __name__ == "__main__":
    main()
