"""Etapa 4: manchas y extractor de radar, frame por frame (ver `idea/plan-entrenamiento.md`).

Por cada frame, con los recortes que dejó `pipeline_insomnio.py procesar`:
  1. calcula el insomnio por píxel y arma las manchas (los mismos filtros del índice: agua, forma, eco y 10 ha);
  2. escribe cada mancha como polígono en `manchas.geojson` (todas, también las descartadas);
  3. mide cada mancha candidata contra su anillo de 1,5 km y escribe `tabla_radar.parquet`
     (las columnas de Movimiento, Rugosidad, Forma y Contexto de la sección 4 del plan);
  4. mide el insomnio de cada polígono de los catálogos del frame, haya quedado o no en una mancha, y escribe
     `insomnio_catalogo.parquet` (la segunda dirección del cruce: sin esto no hay "cerrado y quieto").

    python extraer_manchas.py --frame LOS_ANGELES             # un frame: escribe en ../salidas/LOS_ANGELES/
    python extraer_manchas.py --frame todos                   # todos los de data/frames.json que tengan recortes
    python extraer_manchas.py juntar                          # junta los frames en ../salidas/*.geojson y *.parquet

Los tres archivos siguen `idea/contratos-datos.md` (se validan con `contratos.py`). El anillo no tiene agua ni
polígonos de los catálogos. Todo sale de `insomnio.py`, sin copiar la lógica: `cocientes`, `por_orbita`,
`persistencia`, `anillo` y `ficha`.

Fuentes: NISAR L2 GUNW y GCOV (NASA/ISRO, ASF DAAC); JRC Global Surface Water v1.4; ESA WorldCover 2021 v200
(CC BY 4.0); catálogos de `data/` (Overture Maps / © colaboradores de OpenStreetMap, ODbL; EPA LMOP; Climate TRACE).
"""
import argparse
import dataclasses
import glob
import json
import os
import sys
import warnings
from collections import defaultdict

import numpy as np
import pandas as pd
from scipy import ndimage

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import contratos  # noqa: E402
import fuentes_fijas as ff  # noqa: E402
import geo  # noqa: E402
import insomnio as ins  # noqa: E402
import pipeline_insomnio as pl  # noqa: E402

IDEA = os.path.dirname(AQUI)
PARTES = ("manchas.geojson", "tabla_radar.parquet", "insomnio_catalogo.parquet")


# ------------------------------------------------------------------ de píxeles a polígonos
def contornos(mascara):
    """Anillos del borde de una máscara, en coordenadas de esquina de píxel (x = columna, y = fila).

    Recorre los lados de píxel que separan adentro de afuera, con el adentro siempre a la derecha. En un vértice
    donde se tocan dos píxeles en diagonal sigue por el mismo píxel, y si un anillo pasa dos veces por un vértice
    se parte en dos: así todos los anillos son simples. Devuelve (exteriores, agujeros): los exteriores tienen
    área positiva con la fórmula del cordón en estas coordenadas (y hacia abajo) y los agujeros, negativa.
    """
    p = np.pad(mascara, 1)
    r, c = np.nonzero(p)
    lados = []  # (x0, y0, x1, y1) en coordenadas sin el relleno
    for libre, a, b in ((~p[r - 1, c], (0, 0), (1, 0)), (~p[r, c + 1], (1, 0), (1, 1)),
                        (~p[r + 1, c], (1, 1), (0, 1)), (~p[r, c - 1], (0, 1), (0, 0))):
        x, y = c[libre] - 1, r[libre] - 1
        lados.append(np.column_stack([x + a[0], y + a[1], x + b[0], y + b[1]]))
    lados = np.concatenate(lados)
    sigue = defaultdict(list)
    for x0, y0, x1, y1 in lados.tolist():
        sigue[(x0, y0)].append((x1, y1))
    anillos = []
    while sigue:
        inicio = next(iter(sigue))
        camino, donde = [inicio], {inicio: 0}
        actual, previo = inicio, None
        while True:
            opciones = sigue[actual]
            if len(opciones) == 1 or previo is None:
                destino = opciones.pop(0)
            else:  # dos píxeles en diagonal: giro a la derecha, que es seguir por el mismo píxel
                dx, dy = actual[0] - previo[0], actual[1] - previo[1]
                giro = (actual[0] - dy, actual[1] + dx)
                destino = opciones.pop(opciones.index(giro) if giro in opciones else 0)
            if not opciones:
                del sigue[actual]
            previo, actual = actual, destino
            if actual in donde:  # se cerró un lazo: sale como anillo y el camino sigue desde ahí
                i = donde[actual]
                lazo = camino[i:]
                for v in lazo[1:]:
                    del donde[v]
                del camino[i + 1:]
                anillos.append(lazo)
                if i == 0 and actual not in sigue:
                    break
                previo = camino[-2] if len(camino) > 1 else None
            else:
                donde[actual] = len(camino)
                camino.append(actual)
    exteriores, agujeros = [], []
    for a in anillos:
        v = np.array(a, dtype=float)
        area = 0.5 * float((v[:, 0] * np.roll(v[:, 1], -1) - np.roll(v[:, 0], -1) * v[:, 1]).sum())
        # saco los vértices alineados: sólo quedan las esquinas
        d0, d1 = v - np.roll(v, 1, axis=0), np.roll(v, -1, axis=0) - v
        v = v[(d0 != d1).any(axis=1)]
        (exteriores if area > 0 else agujeros).append((abs(area), v))
    return exteriores, agujeros


def _adentro(punto, anillo):
    x, y = punto
    x0, y0 = anillo[:, 0], anillo[:, 1]
    x1, y1 = np.roll(x0, -1), np.roll(y0, -1)
    cruza = (y0 > y) != (y1 > y)
    with np.errstate(divide="ignore", invalid="ignore"):
        return bool((cruza & (x < (x1 - x0) * (y - y0) / (y1 - y0) + x0)).sum() % 2)


def geometria(mascara, fila0, col0, xs, ys, fr):
    """GeoJSON (Polygon o MultiPolygon, en lon/lat) de una mancha dada por su máscara y la esquina de su ventana.

    También devuelve el perímetro en metros (todos los bordes, también los de los agujeros).
    """
    paso = float(xs[1] - xs[0])
    exteriores, agujeros = contornos(mascara)

    def lonlat(v):
        v = v[::-1]  # en el mapa el recorrido queda al revés: exteriores antihorarios y agujeros horarios, como pide GeoJSON
        lat, lon = fr.latlon(xs[0] + (v[:, 0] + col0 - 0.5) * paso, ys[0] - (v[:, 1] + fila0 - 0.5) * paso)
        anillo = [[round(float(a), 6), round(float(b), 6)] for a, b in zip(lon, lat)]
        return anillo + [anillo[0]]

    partes = [[lonlat(v)] for _, v in exteriores]
    for _, h in agujeros:
        medio = (h[0] + h[1]) / 2  # el medio de un lado del agujero: nunca cae sobre otro anillo
        for i, (_, v) in enumerate(exteriores):
            if len(exteriores) == 1 or _adentro(medio, v):
                partes[i].append(lonlat(h))
                break
    perimetro = sum(float(np.abs(np.roll(v, -1, axis=0) - v).sum()) for _, v in exteriores + agujeros) * paso
    if len(partes) == 1:
        return {"type": "Polygon", "coordinates": partes[0]}, perimetro
    return {"type": "MultiPolygon", "coordinates": partes}, perimetro


# ------------------------------------------------------------------ mancha contra anillo
def _ventana(mascara, n):
    """Recorte de la grilla que contiene la máscara y n píxeles alrededor."""
    f = np.nonzero(mascara.any(1))[0]
    c = np.nonzero(mascara.any(0))[0]
    return (slice(max(f[0] - n, 0), f[-1] + n + 1), slice(max(c[0] - n, 0), c[-1] + n + 1))


def _media(capa, mascara):
    if capa is None:
        return np.nan
    v = capa[mascara]
    return float(np.nanmean(v)) if np.isfinite(v).any() else np.nan


def medir(mascara, d, p):
    """Las columnas de radar de una mancha (o de cualquier máscara) contra su anillo. `d` es el contexto de `preparar`."""
    paso = d["paso"]
    v = _ventana(mascara, int(round(p.anillo_m / paso)) + 1)
    m, tierra = mascara[v], d["tierra"][v]
    aro = ins.anillo(m, tierra, paso, p, excluir=d["catalogo_px"][v])
    aro_bruto = ins.anillo(m, np.ones_like(tierra), paso, p)  # con el agua y los catálogos: para el contexto
    adentro = m & tierra
    coh = d["coh"][(slice(None),) + v]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        m_sitio = np.nanmedian(coh[:, adentro], axis=1) if adentro.any() else np.full(len(coh), np.nan)
        m_aro = np.nanmedian(coh[:, aro], axis=1) if aro.any() else np.full(len(coh), np.nan)
    valido = np.isfinite(m_sitio) & np.isfinite(m_aro) & (m_aro > 0)
    fila = {k: np.nan for k in ("insomnio", "persistencia", "contraste_mediana", "contraste_desvio", "tendencia",
                                "eco_contraste", "eco_variacion", "hv_hh", "urbano_anillo", "cultivo_anillo")}
    fila["n_pares"], fila["n_orbitas"] = int(np.isfinite(m_sitio).sum()), 0
    if valido.any():
        cociente = m_sitio[valido] / m_aro[valido]
        despierto = np.zeros(len(coh), dtype=bool)
        despierto[valido] = cociente < p.razon
        i, partes = ins.por_orbita(despierto[:, None], valido[:, None], d["orbitas"], p.min_pares_orbita)
        fila.update(insomnio=float(i[0]), persistencia=float(ins.persistencia(despierto[:, None], valido[:, None], d["fechas"])[0]),
                    contraste_mediana=float(np.median(cociente)), contraste_desvio=float(np.std(cociente)),
                    n_pares=int(valido.sum()), n_orbitas=int(sum(np.isfinite(x[0]) for x in partes.values())))
    con_dato = np.isfinite(m_sitio)
    if con_dato.sum() >= 3:  # pendiente de la coherencia de la mancha, llevada a pares de 12 días, en el tiempo
        dias = d["dia"][con_dato]
        if np.ptp(dias) > 0:
            fila["tendencia"] = float(np.polyfit(dias, np.clip(m_sitio[con_dato] / d["factor"][con_dato], 0, 1), 1)[0])
    fila["coherencia_media"] = _media(d["coherencia_media"][v], adentro)
    fila["eco_db"] = _media(None if d["eco_db"] is None else d["eco_db"][v], adentro)
    if d["eco_db"] is not None and aro.any():
        fila["eco_contraste"] = fila["eco_db"] - _media(d["eco_db"][v], aro)
    if d["eco"] is not None:
        eco = d["eco"][(slice(None),) + v]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            serie = np.nanmean(eco[:, adentro], axis=1) if adentro.any() else np.full(len(eco), np.nan)
        desvios = [np.nanstd(serie[d["orbitas_eco"] == o]) for o in np.unique(d["orbitas_eco"]) if np.isfinite(serie[d["orbitas_eco"] == o]).sum() >= 2]
        if desvios:  # entre fechas de una misma órbita (cada órbita mira con otra geometría)
            fila["eco_variacion"] = float(np.mean(desvios))
    if d["eco_hv_db"] is not None and np.isfinite(fila["eco_db"]):
        fila["hv_hh"] = _media(d["eco_hv_db"][v], adentro) - fila["eco_db"]
    fila["agua_anillo"] = float(d["agua"][v][aro_bruto].mean()) if aro_bruto.any() else np.nan
    for clave, capa in (("urbano_anillo", d["urbano"]), ("cultivo_anillo", d["cultivo"])):
        if capa is not None and aro_bruto.any():
            valores = capa[v][aro_bruto]
            valores = valores[valores <= 100]
            if len(valores):
                fila[clave] = float(valores.mean() / 100)
    fila["px"], fila["px_anillo"] = int(adentro.sum()), int(aro.sum())
    return fila


# ------------------------------------------------------------------ un frame
def preparar(a, p):
    """Lee el frame con el lector del pipeline y calcula las capas del índice. Devuelve (contexto, manchas, etiquetas)."""
    ctx = pl.cargar(a)
    fr = ctx["fr"]
    capas, lista, etiquetas, _ = pl.evaluar(ctx, p)
    cobertura = os.path.join(a.fijos, f"worldcover_{a.capa}.npz")
    urbano = cultivo = None
    try:
        if not os.path.exists(cobertura):
            print(f"Falta {os.path.relpath(cobertura)}: lo armo (fuentes_fijas.py)")
            ff.cobertura(fr, a.fijos, a.capa)
        with np.load(cobertura) as z:
            urbano, cultivo = z["urbano"], z["cultivo"]
    except Exception as e:  # sin red: las dos columnas de contexto quedan vacías
        print(f"AVISO: sin ESA WorldCover para {fr.nombre} ({type(e).__name__}: {e}): urbano_anillo y cultivo_anillo quedan vacías")
    import datetime as dt

    dia = np.array([(dt.date.fromisoformat(str(f)) - dt.date(2025, 1, 1)).days for f in ctx["fechas"]], dtype=float)
    d = {"fr": fr, "paso": ctx["paso"], "xs": ctx["xs"], "ys": ctx["ys"], "coh": ctx["coh"], "orbitas": ctx["orbitas"],
         "fechas": ctx["fechas"], "dia": dia, "factor": capas["factor_separacion"], "agua": capas["agua"], "tierra": ~capas["agua"],
         "catalogo_px": ctx["catalogo_px"], "catalogo": ctx["catalogo"], "coherencia_media": capas["coherencia_media"],
         "eco_db": capas["eco_db"], "eco": ctx["eco"], "orbitas_eco": ctx["orbitas_eco"],
         "eco_hv_db": ins.eco_medio(ctx.get("eco_hv"), ctx.get("orbitas_eco_hv")), "urbano": urbano, "cultivo": cultivo,
         "pares": ctx["pares"], "capas": capas}
    return d, lista, etiquetas


def manchas_y_tabla(d, lista, etiquetas, p):
    """(features de `manchas.geojson`, filas de `tabla_radar.parquet`) de un frame."""
    fr, xs, ys = d["fr"], d["xs"], d["ys"]
    cajas = ndimage.find_objects(etiquetas)
    features, filas = [], []
    nulo = lambda v: None if v is None or (isinstance(v, float) and not np.isfinite(v)) else v  # noqa: E731
    for n, m in enumerate(lista, start=1):  # el orden de `insomnio.manchas()`: de mayor a menor superficie
        sl = cajas[m["etiqueta"] - 1]
        mascara = etiquetas[sl] == m["etiqueta"]
        geom, perimetro = geometria(mascara, sl[0].start, sl[1].start, xs, ys, fr)
        ident = contratos.id_mancha(fr.nombre, n)
        features.append({"type": "Feature", "geometry": geom, "properties": {
            "id_mancha": ident, "frame": fr.nombre, "ha": m["ha"], "forma": m["forma"], "descartada": m["descartada"],
            "etiqueta": m["etiqueta"], "insomnio": nulo(m["insomnio"]), "persistencia": nulo(m["persistencia"]),
            "eco_db": nulo(m["eco_db"]), "elongacion": m["elongacion"], "nucleo": m["nucleo"], "lat": m["lat"], "lon": m["lon"],
            "clase_osm": m.get("clase"), "que": m.get("que")}})
        if m["descartada"]:
            continue
        entera = np.zeros(etiquetas.shape, dtype=bool)
        entera[sl] = mascara
        r = medir(entera, d, p)
        if not np.isfinite(r["insomnio"]):  # sin anillo (todo agua o catálogos alrededor): queda el promedio por píxel
            r["insomnio"], r["persistencia"] = float(m["insomnio"]), float(m["persistencia"])
        area_m2 = m["ha"] * 1e4
        filas.append({"id_mancha": ident, "frame": fr.nombre, **{k: r[k] for k in (
            "insomnio", "persistencia", "contraste_mediana", "contraste_desvio", "coherencia_media", "tendencia", "n_pares",
            "n_orbitas", "eco_db", "eco_contraste", "eco_variacion", "hv_hh")},
            "area_ha": float(m["ha"]), "elongacion": float(m["elongacion"]), "compacidad": float(min(1.0, 4 * np.pi * area_m2 / perimetro**2)),
            "agua_anillo": r["agua_anillo"], "urbano_anillo": r["urbano_anillo"], "cultivo_anillo": r["cultivo_anillo"],
            "px_anillo": r["px_anillo"], "insomnio_px": float(m["insomnio"]), "persistencia_px": float(m["persistencia"]),
            "clase_osm": m.get("clase"), "que": m.get("que")})
    return features, filas


def catalogo_del_frame(d, p, min_ha=contratos.MIN_HA):
    """Una fila por polígono de los catálogos cuyo centro cae en la caja del frame: `insomnio.ficha()` contra su anillo.

    Es la lógica de `insomnio_catalogo.py` (modo exacto), con la grilla del frame y el anillo sin catálogos.
    """
    fr, xs, ys = d["fr"], d["xs"], d["ys"]
    filas = []
    for s in d["catalogo"]:
        lon, lat = np.array([q for a in s["anillos"] for q in a], dtype=float)[:, :2].T
        if not fr.contiene(lat.mean(), lon.mean()):
            continue
        mascara = fr.mascara_poligonos(s["anillos"], xs, ys)
        ha = s.get("area_ha")
        if ha is None:
            ha = sum(geo.area_y_centro(a)[0] for a in s["anillos"])
        if mascara.any():
            v = _ventana(mascara, int(round(p.anillo_m / d["paso"])) + 1)
            f = ins.ficha(mascara[v], d["coh"][(slice(None),) + v], d["orbitas"], d["fechas"], d["tierra"][v], d["paso"], p,
                          eco_db=None if d["eco_db"] is None else d["eco_db"][v], excluir=d["catalogo_px"][v])
        else:
            f = {"insomnio": None, "persistencia": None, "eco_db": None, "pares": [], "radar": "no_alcanza",
                 "motivo": "el predio queda fuera de la grilla o es más chico que un píxel", "px": 0, "px_anillo": 0}
        radar, motivo = f["radar"], f["motivo"]
        if ha < min_ha:
            radar, motivo = "no_alcanza", f"el polígono mide {ha:.1f} ha: menos de {min_ha:g} ha"
        filas.append({"id_catalogo": s["id"], "catalogo": s["catalogo"], "complejo": s.get("complejo"), "frame": fr.nombre,
                      "insomnio": f["insomnio"], "persistencia": f["persistencia"], "eco_db": f["eco_db"], "n_pares": len(f["pares"]),
                      "radar": radar, "motivo": motivo, "area_ha": float(ha), "estado": s.get("estado"), "clase": s.get("clase"),
                      "nombre": s.get("nombre") or None, "estado_complejo": s.get("estado_complejo"), "px": f["px"],
                      "px_anillo": f["px_anillo"], "modo": "exacto"})
    df = pd.DataFrame(filas, columns=["id_catalogo", "catalogo", "complejo", "frame", "insomnio", "persistencia", "eco_db", "n_pares",
                                      "radar", "motivo", "area_ha", "estado", "clase", "nombre", "estado_complejo", "px", "px_anillo", "modo"])
    for c in ("insomnio", "persistencia", "eco_db", "area_ha"):
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("float64")
    for c in ("n_pares", "px", "px_anillo"):
        df[c] = df[c].astype("int64")
    return df


def _tabla_radar(filas):
    df = pd.DataFrame(filas)
    for c in df.columns:
        if c in ("n_pares", "n_orbitas", "px_anillo"):
            df[c] = df[c].astype("int64")
        elif c not in ("id_mancha", "frame", "clase_osm", "que"):
            df[c] = pd.to_numeric(df[c], errors="coerce").astype("float64")
    return df


def _guardar_manchas(features, carpeta, meta):
    os.makedirs(carpeta, exist_ok=True)
    ruta = os.path.join(carpeta, "manchas.geojson")
    with open(ruta, "w", encoding="utf-8") as fh:
        fh.write('{"type":"FeatureCollection","name":"manchas",' + json.dumps(meta, ensure_ascii=False)[1:-1] + ',"features":[\n')
        fh.write(",\n".join(json.dumps(f, ensure_ascii=False, separators=(",", ":")) for f in features))
        fh.write("\n]}\n")
    contratos.leer(ruta)  # valida
    return ruta


META = {"fuente": "NISAR L2 GUNW y GCOV (NASA/ISRO), ASF DAAC; índice de insomnio de herramientas/insomnio.py",
        "generado_por": "herramientas/extraer_manchas.py", "aviso": "Señal compatible con actividad; no son basurales verificados."}


def _sin_chicas(features, min_ha):
    """Las descartadas por chicas son miles por frame: de ésas sólo quedan las de `min_ha` o más. Las demás, todas."""
    return [f for f in features if f["properties"]["descartada"] != "chica" or f["properties"]["ha"] >= min_ha]


def extraer(a, p, destino, min_ha_descartadas=0.0):
    """Corre un frame y escribe sus tres archivos en `destino`."""
    d, lista, etiquetas = preparar(a, p)
    fr = d["fr"]
    features, filas = manchas_y_tabla(d, lista, etiquetas, p)
    cat = catalogo_del_frame(d, p)
    orbitas = sorted({int(o) for o in d["orbitas"]})
    _guardar_manchas(_sin_chicas(features, min_ha_descartadas), destino, {
        **META, "frame": fr.nombre, "pares": len(d["pares"]), "orbitas": orbitas, "epsg": fr.epsg, "bbox": fr.bbox,
        "desde": min(x["desde"] for x in d["pares"]), "hasta": max(x["hasta"] for x in d["pares"]), "manchas_en_total": len(features),
        "recorte": f"de las descartadas por chicas sólo están las de {min_ha_descartadas:g} ha o más; las candidatas están todas"})
    if filas:
        contratos.guardar(_tabla_radar(filas), "tabla_radar", destino)
    if len(cat):
        contratos.guardar(cat, "insomnio_catalogo", destino)
    por_radar = cat.groupby(["catalogo", "radar"]).size().to_dict() if len(cat) else {}
    conocidas = sum(1 for f in filas if f["clase_osm"] == "relleno_osm")
    print(f"{fr.nombre}: {len(d['pares'])} pares; {len(features)} manchas, {len(filas)} candidatas ({conocidas} pisan un basural conocido); "
          f"{len(cat)} polígonos de los catálogos {por_radar}")
    return {"frame": fr.nombre, "pares": len(d["pares"]), "manchas": len(features), "candidatas": len(filas), "catalogo": len(cat)}


def juntar(base, destino, min_ha_descartadas):
    """Junta los archivos de todos los frames (`<base>/<FRAME>/`) en los tres de `destino`, que son los del contrato."""
    carpetas = sorted(os.path.dirname(r) for r in glob.glob(os.path.join(base, "*", "manchas.geojson")))
    if not carpetas:
        sys.exit(f"No hay frames extraídos en {base}.")
    features, frames = [], []
    for c in carpetas:
        with open(os.path.join(c, "manchas.geojson"), encoding="utf-8") as fh:
            fs = json.load(fh)["features"]
        frames.append(fs[0]["properties"]["frame"] if fs else os.path.basename(c))
        features += _sin_chicas(fs, min_ha_descartadas)
    ruta = _guardar_manchas(features, destino, {**META, "frames": frames,
                            "recorte": f"de las descartadas por chicas sólo están las de {min_ha_descartadas:g} ha o más; las candidatas están todas"})
    print(f"{os.path.relpath(ruta)}: {len(features)} manchas de {len(frames)} frames, {os.path.getsize(ruta) / 1e6:.1f} MB")
    for nombre in ("tabla_radar", "insomnio_catalogo"):
        partes = [pd.read_parquet(r) for r in sorted(glob.glob(os.path.join(base, "*", f"{nombre}.parquet")))]
        if partes:
            ruta = contratos.guardar(pd.concat(partes, ignore_index=True), nombre, destino)
            print(f"{os.path.relpath(ruta)}: {sum(len(x) for x in partes)} filas, {os.path.getsize(ruta) / 1e6:.2f} MB")


def main():
    q = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    q.add_argument("paso", nargs="?", choices=["extraer", "juntar"], default="extraer")
    q.add_argument("--frame", nargs="+", default=["AMBA"], help="uno o más frames de data/frames.json, o `todos`")
    q.add_argument("--salida", default=os.path.join(IDEA, "salidas"), help="carpeta del pipeline: los recortes de un frame están en <salida>/<FRAME>/ (los del AMBA, en <salida>/)")
    q.add_argument("--destino", help="carpeta donde escribir: cada frame en <destino>/<FRAME>/ y `juntar` en <destino>/ (por defecto, --salida)")
    q.add_argument("--fijos", default=pl.FIJOS, help="carpeta de las fuentes fijas (ver pipeline_insomnio.py)")
    q.add_argument("--capa", choices=list(pl.CAPAS), default="80m")
    q.add_argument("--min-insomnio", type=float, help="umbral de insomnio para armar las manchas. Sólo para juntar más filas de entrenamiento "
                   "(por ejemplo 0,5); el veredicto usa el de `insomnio.Parametros` (0,70)")
    q.add_argument("--min-ha-descartadas", type=float, default=5.0, help="superficie mínima de las manchas descartadas por chicas que se escriben "
                   "en `manchas.geojson` (son miles por frame; 0 = todas). Las candidatas y las demás descartadas van siempre")
    args = q.parse_args()
    destino = args.destino or args.salida
    if args.paso == "juntar":
        juntar(destino, destino, args.min_ha_descartadas)
        return
    p = ins.Parametros() if args.min_insomnio is None else dataclasses.replace(ins.Parametros(), min_insomnio=args.min_insomnio)
    nombres = list(geo.frames_conocidos()) if args.frame == ["todos"] else [n.upper() for n in args.frame]
    base = argparse.Namespace(frame=nombres, caja=None, epsg=None, datos="", salida=args.salida, fijos=args.fijos, web="", orbitas=None,
                              desde=None, hasta=None, capa=args.capa, sin_catalogos=False)
    resumen, fallados = [], []
    for nombre in nombres:
        a = pl.preparar(base, nombre)
        if not glob.glob(os.path.join(a.salida, f"recortes_{args.capa}", "gunw_*.npz")):
            print(f"{nombre}: no hay recortes en {a.salida}: corré antes `pipeline_insomnio.py procesar --frame {nombre}`")
            fallados.append(nombre)
            continue
        try:
            resumen.append(extraer(a, p, os.path.join(destino, a.fr.nombre), args.min_ha_descartadas))
        except (Exception, SystemExit) as e:
            if len(nombres) == 1:
                raise
            fallados.append(nombre)
            print(f"ERROR en {nombre}: {type(e).__name__}: {e}", flush=True)
    if fallados:
        print("Frames sin extraer:", ", ".join(fallados))


if __name__ == "__main__":
    main()
