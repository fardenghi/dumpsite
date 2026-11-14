"""Etapa 6: junta radar, óptico y cruce de cada mancha, la etiqueta y arma las particiones por frame.

Escribe `tabla_entrenamiento.parquet` y `particiones.json` según `idea/contratos-datos.md`.

    python armar_tabla.py                                  # lee y escribe en ../salidas/
    python armar_tabla.py --datos ../datos/mock --salida ../datos/mock/prueba
    python armar_tabla.py --radar ../datos/amba_provisional/tabla_radar.parquet --salida ../datos/amba_provisional

Etiqueta (etapa 6 del plan):
- una mancha se cruza con un polígono si la intersección cubre al menos `--criterio` (0,30) del área menor y, si el
  cruce trae `inter_ha`, además mide al menos `--min-inter-ha` (5,12 ha = 8 píxeles de 80 m; ver `idea/criterio-cruce.md`);
- se cruza sólo con basurales (de cualquier estado) → `basural_activo`; sólo con negativos → `otro_movil`;
  con los dos o con ninguno → no entra;
- un complejo cuenta una vez: si varias manchas caen sobre el mismo complejo (o el mismo negativo), queda la más grande;
- `id_catalogo` es el polígono de mayor `frac_area_menor`.

Particiones: por frame. Los frames con `reservado_prueba` (Argentina) van a `prueba_final`. Los demás se reparten en
hasta `--particiones` grupos, equilibrando la cantidad de filas (cada frame entero en un grupo).
Sin `frames.json`, el AMBA se toma como Buenos Aires, ARG, reservado para la prueba final.
"""
import argparse
import json
import os
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
    print(f"Aviso: no hay frames.json ({camino or "../../data/frames.json"}); se usan los datos por defecto del AMBA.", file=sys.stderr)
    return dict(FRAMES_POR_DEFECTO)


def etiquetar(cruce, criterio=contratos.CRITERIO_CRUCE, min_inter_ha=MIN_INTER_HA):
    """Una fila por mancha etiquetada: id_mancha, id_catalogo, complejo, clase_negativo, clase."""
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
        })
    return pd.DataFrame(filas, columns=["id_mancha", "id_catalogo", "complejo", "clase_negativo", "clase"])


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
          umbral_insomnio=0.70, k=5, extra=None):
    etiquetas = etiquetar(cruce, criterio, min_inter_ha)
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
        "meta": {"generado_por": "herramientas/armar_tabla.py", "umbral_insomnio": umbral_insomnio,
                 "criterio_cruce": criterio, "min_inter_ha": min_inter_ha if "inter_ha" in cruce.columns else None,
                 "filas_por_clase": conteos},
        "particiones": partes, "prueba_final": reservados,
    }
    return t, particiones


def main():
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--datos", default=os.path.join(AQUI, "..", "salidas"), help="carpeta con los parquets de entrada")
    a.add_argument("--radar")
    a.add_argument("--optico")
    a.add_argument("--cruce")
    a.add_argument("--frames", help="frames.json (por defecto ../../data/frames.json, o el de --datos si existe)")
    a.add_argument("--cnn", help="parquet con id_mancha y cnn_p_basural (opcional)")
    a.add_argument("--salida", default=os.path.join(AQUI, "..", "salidas"))
    a.add_argument("--criterio", type=float, default=contratos.CRITERIO_CRUCE)
    a.add_argument("--min-inter-ha", type=float, default=MIN_INTER_HA)
    a.add_argument("--umbral-insomnio", type=float, default=0.70,
                   help="insomnio mínimo de la mancha para entrenar (se anota en particiones.json)")
    a.add_argument("--particiones", type=int, default=5)
    args = a.parse_args()

    radar = contratos.leer(args.radar or contratos.ruta("tabla_radar", args.datos))
    optico = contratos.leer(args.optico or contratos.ruta("tabla_optico", args.datos))
    cruce = contratos.leer(args.cruce or contratos.ruta("cruce_manchas_catalogo", args.datos))
    frames_json = args.frames or next((c for c in (os.path.join(args.datos, "frames.json"),
                                                   os.path.join(AQUI, "..", "..", "data", "frames.json")) if os.path.exists(c)), None)
    frames = leer_frames(frames_json)
    extra = pd.read_parquet(args.cnn)[["id_mancha", "cnn_p_basural"]] if args.cnn else None

    t, partes = armar(radar, optico, cruce, frames, args.criterio, args.min_inter_ha, args.umbral_insomnio, args.particiones, extra)
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
