"""Stage 6: joins the radar, optical and cross data of each blob, labels it and builds the partitions by frame.

Writes `tabla_entrenamiento.parquet` and `particiones.json` following `../docs/data-contracts.md`.

    python armar_tabla.py                                  # reads and writes in ../data/salidas/
    python armar_tabla.py --datos datos/mock --salida datos/mock/prueba
    python armar_tabla.py --radar datos/amba_provisional/tabla_radar.parquet --salida datos/amba_provisional

Label (stage 6 of the plan):
- a blob crosses a polygon if the intersection covers at least `--criterio` (0.30) of the smaller area and, if the
  cross carries `inter_ha`, it also measures at least `--min-inter-ha` (5.12 ha = 8 pixels of 80 m; see `../docs/model.md`);
- it crosses only dump sites (any status) → `basural_activo`; only negatives → `otro_movil`;
  both or none → not included;
- a complex counts once: if several blobs fall on the same complex (or the same negative), the largest one is kept;
- `id_catalogo` is the polygon with the largest `frac_area_menor`.

Options added with run 2 (see `../docs/results.md`):
- `--negativos-osm`: adds as `otro_movil` the candidate blobs that stage 4 marked `clase_osm` = `uso_conocido`
  (airfields, golf courses, parks, cemeteries, quarries, plantations, military sites and reserves from OSM via Overture) and
  that **don't touch any catalog dump site** nor have a landfill name (`NOMBRE_DE_RELLENO`: "Freshkills Park"). Only in the frames that aren't the final test (in the AMBA that mark
  comes from Nominatim and isn't comparable). Their `id_catalogo` is `NEG-OSM-<id_mancha>` (they're not in `data/catalogos/negativos/`),
  their `clase_negativo` is `osm_<tipo>` and, if the place has a name, all its blobs count once.
- `--etiquetas-optico` and `--positivos`: `salidas/etiquetas_optico_ia.json` says, per dump site, whether activity is
  visible in Sentinel-2 (`act`), not visible (`sin`) or can't be told (`nose`). **They were assigned by an AI and no person reviewed them.**
  `--positivos sin_sin` removes from `basural_activo` the blobs whose dump site is `sin`; `--positivos solo_act` keeps only
  the `act` ones. The `actividad_optica` column stays in the table (it doesn't go into the model).

Partitions: by frame. Frames with `reservado_prueba` (Argentina) go to `prueba_final`. The others are spread over
up to `--particiones` groups, balancing the number of rows (each frame whole in one group).
Without `frames.json`, the AMBA is taken as Buenos Aires, ARG, reserved for the final test.
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
MIN_INTER_HA = 5.12  # 8 pixels of 80 m: `insomnio.Parametros.min_px_sitio`


def leer_frames(camino):
    if camino and os.path.exists(camino):
        df = contratos.leer(camino)
        return {r["frame"]: {"ciudad": r["ciudad"], "pais": r["pais"], "reservado_prueba": bool(r["reservado_prueba"])}
                for _, r in df.iterrows()}
    print(f"Aviso: no hay frames.json ({camino or "../data/catalogos/frames.json"}); se usan los datos por defecto del AMBA.", file=sys.stderr)
    return dict(FRAMES_POR_DEFECTO)


POSITIVOS = ("todos", "sin_sin", "solo_act")


def leer_etiquetas_optico(camino):
    """{id_catalogo: 'act' | 'sin' | 'nose'} from `etiquetas_optico_ia.json` (labels from an AI, not reviewed)."""
    with open(camino, encoding="utf-8") as fh:
        return {e["id_catalogo"]: e["final"] for e in json.load(fh)["etiquetas"]}


def _actividad(ids, optico_ia):
    """Optical activity of a blob according to the dump sites it crosses: `act` if it's visible in any, `sin` if it's visible
    in none and some were labeled as not, `nose` if it couldn't be told, and None if none has a label."""
    vistos = {optico_ia[i] for i in ids if i in optico_ia}
    return "act" if "act" in vistos else "sin" if "sin" in vistos else "nose" if vistos else None


# A known land use whose name says it is (or was) a landfill can't be a negative: a dump site of any status is
# `basural_activo` (stage 6). It doesn't go into training even as a positive (it isn't crossed with the catalog).
NOMBRE_DE_RELLENO = re.compile(r"landfill|fresh ?kills|relleno sanitario|vertedero|basur|tiradero|dump|tempat pembuangan|\bTPA\b", re.I)


def negativos_osm(radar, cruce, frames, ya_etiquetadas):
    """OSM `uso_conocido` blobs as `otro_movil`: those that touch no catalog dump site, aren't labeled already
    and come from frames that don't go to the final test."""
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
    """One row per labeled blob: id_mancha, id_catalogo, complejo, clase_negativo, clase (and `actividad_optica`
    if the optical labels are given)."""
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
    """Spreads frames into k groups balancing rows (the largest first, into the smallest group)."""
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
    if positivos != "todos":  # only in the training frames: the final test isn't touched
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
    if extra is not None:  # for example, cnn_p_basural
        t = t.merge(extra, on="id_mancha", how="left")
    t = t[t["insomnio"] >= umbral_insomnio]
    # a complex counts once per frame: the largest blob is kept
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
    a.add_argument("--datos", default=os.path.join(AQUI, "..", "data", "salidas"), help="folder with the input parquets")
    a.add_argument("--radar")
    a.add_argument("--optico")
    a.add_argument("--cruce")
    a.add_argument("--frames", help="frames.json (default ../data/catalogos/frames.json, or the one in --datos if it exists)")
    a.add_argument("--cnn", help="parquet with id_mancha and cnn_p_basural (optional)")
    a.add_argument("--salida", default=os.path.join(AQUI, "..", "data", "salidas"))
    a.add_argument("--criterio", type=float, default=contratos.CRITERIO_CRUCE)
    a.add_argument("--min-inter-ha", type=float, default=MIN_INTER_HA)
    a.add_argument("--umbral-insomnio", type=float, default=0.70,
                   help="minimum blob insomnia to train (noted in particiones.json)")
    a.add_argument("--particiones", type=int, default=5)
    a.add_argument("--negativos-osm", action="store_true", help="add the OSM `uso_conocido` blobs as `otro_movil`")
    a.add_argument("--etiquetas-optico", help="etiquetas_optico_ia.json (optical activity per dump site; from an AI, not reviewed)")
    a.add_argument("--positivos", choices=POSITIVOS, default="todos",
                   help="which dump sites count as `basural_activo` according to --etiquetas-optico")
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
