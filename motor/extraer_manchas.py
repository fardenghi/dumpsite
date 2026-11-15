"""Stage 4: blobs and radar extractor, frame by frame (see `../docs/model.md`).

For each frame, with the crops left by `pipeline_insomnio.py procesar`:
  1. computes the per-pixel insomnia and builds the blobs (the same filters as the index: water, shape, echo and 10 ha);
  2. writes each blob as a polygon in `manchas.geojson` (all of them, including the discarded ones);
  3. measures each candidate blob against its 1.5 km ring and writes `tabla_radar.parquet`
     (the Movement, Roughness, Shape and Context columns of section 4 of the plan);
  4. measures the insomnia of each catalog polygon in the frame, whether or not it ended up in a blob, and writes
     `insomnio_catalogo.parquet` (the second direction of the cross: without it there's no "closed and quiet").

    python extraer_manchas.py --frame LOS_ANGELES             # one frame: writes to ../data/salidas/LOS_ANGELES/
    python extraer_manchas.py --frame todos                   # all those in data/catalogos/frames.json that have crops
    python extraer_manchas.py juntar                          # joins the frames into ../data/salidas/*.geojson and *.parquet

The three files follow `../docs/data-contracts.md` (validated with `contratos.py`). The ring has no water or
catalog polygons. Everything comes from `insomnio.py`, without copying the logic: `cocientes`, `por_orbita`,
`persistencia`, `anillo` and `ficha`.

Sources: NISAR L2 GUNW and GCOV (NASA/ISRO, ASF DAAC); JRC Global Surface Water v1.4; ESA WorldCover 2021 v200
(CC BY 4.0); catalogs in `data/` (Overture Maps / © OpenStreetMap contributors, ODbL; EPA LMOP; Climate TRACE).
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

RAIZ = os.path.dirname(AQUI)
PARTES = ("manchas.geojson", "tabla_radar.parquet", "insomnio_catalogo.parquet")

# Activity index (experimental, not validated): combines two measurements of the most active part of the site.
#   contraste_p10  coherence of the least coherent 10 % of the site / ring coherence (median across pairs)
#   eco_var_p90    echo variation over time, per pixel (90th percentile of the site, dB)
# It's a logistic regression fitted with 53 sites from 9 frames (19 with activity visible in Sentinel-2 and 34 without),
# with optical labels assigned by AI (`salidas/etiquetas_optico_ia.json`). Leaving one frame out at a time it gives
# AUC 0.75 (95 % CI: 0.59 to 0.89), versus 0.60 for the site median. The AMBA wasn't used. See ../docs/insomnia-index.md.
ACTIVIDAD = {"intercepto": -0.75, "contraste_p10": (-1.17, 0.483, 0.136), "eco_var_p90": (0.65, 3.046, 0.790)}  # (coefficient, mean, deviation)
UMBRAL_ACTIVIDAD = 0.45  # the one that maximizes balanced accuracy over the 53 sites


def indice_actividad(contraste_p10, eco_var_p90):
    """Activity index between 0 and 1 (NaN if either measurement is missing). It's not a calibrated probability."""
    if not (np.isfinite(contraste_p10) and np.isfinite(eco_var_p90)):
        return np.nan
    z = ACTIVIDAD["intercepto"]
    for nombre, valor in (("contraste_p10", contraste_p10), ("eco_var_p90", eco_var_p90)):
        coef, media, desvio = ACTIVIDAD[nombre]
        z += coef * (valor - media) / desvio
    return float(1 / (1 + np.exp(-z)))


# ------------------------------------------------------------------ from pixels to polygons
def contornos(mascara):
    """Edge rings of a mask, in pixel-corner coordinates (x = column, y = row).

    Walks the pixel sides that separate inside from outside, always with the inside on the right. At a vertex
    where two pixels touch diagonally it continues along the same pixel, and if a ring passes twice through a vertex
    it's split in two: that way all rings are simple. Returns (exteriors, holes): exteriors have
    positive area with the shoelace formula in these coordinates (y downward) and holes, negative.
    """
    p = np.pad(mascara, 1)
    r, c = np.nonzero(p)
    lados = []  # (x0, y0, x1, y1) in coordinates without the padding
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
            else:  # two diagonal pixels: turn right, which means following the same pixel
                dx, dy = actual[0] - previo[0], actual[1] - previo[1]
                giro = (actual[0] - dy, actual[1] + dx)
                destino = opciones.pop(opciones.index(giro) if giro in opciones else 0)
            if not opciones:
                del sigue[actual]
            previo, actual = actual, destino
            if actual in donde:  # a loop closed: it comes out as a ring and the path continues from there
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
        # drop the collinear vertices: only the corners are left
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
    """GeoJSON (Polygon or MultiPolygon, in lon/lat) of a blob given by its mask and the corner of its window.

    It also returns the perimeter in meters (all edges, including those of the holes).
    """
    paso = float(xs[1] - xs[0])
    exteriores, agujeros = contornos(mascara)

    def lonlat(v):
        v = v[::-1]  # on the map the direction flips: exteriors counterclockwise and holes clockwise, as GeoJSON requires
        lat, lon = fr.latlon(xs[0] + (v[:, 0] + col0 - 0.5) * paso, ys[0] - (v[:, 1] + fila0 - 0.5) * paso)
        anillo = [[round(float(a), 6), round(float(b), 6)] for a, b in zip(lon, lat)]
        return anillo + [anillo[0]]

    partes = [[lonlat(v)] for _, v in exteriores]
    for _, h in agujeros:
        medio = (h[0] + h[1]) / 2  # the middle of a side of the hole: it never falls on another ring
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
    """Crop of the grid containing the mask and n pixels around it."""
    f = np.nonzero(mascara.any(1))[0]
    c = np.nonzero(mascara.any(0))[0]
    return (slice(max(f[0] - n, 0), f[-1] + n + 1), slice(max(c[0] - n, 0), c[-1] + n + 1))


def _media(capa, mascara):
    if capa is None:
        return np.nan
    v = capa[mascara]
    return float(np.nanmean(v)) if np.isfinite(v).any() else np.nan


def medir(mascara, d, p):
    """The radar columns of a blob (or of any mask) against its ring. `d` is the context from `preparar`."""
    paso = d["paso"]
    v = _ventana(mascara, int(round(p.anillo_m / paso)) + 1)
    m, tierra = mascara[v], d["tierra"][v]
    aro = ins.anillo(m, tierra, paso, p, excluir=d["catalogo_px"][v])
    aro_bruto = ins.anillo(m, np.ones_like(tierra), paso, p)  # with water and catalogs: for the context
    adentro = m & tierra
    coh = d["coh"][(slice(None),) + v]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        m_sitio = np.nanmedian(coh[:, adentro], axis=1) if adentro.any() else np.full(len(coh), np.nan)
        m_aro = np.nanmedian(coh[:, aro], axis=1) if aro.any() else np.full(len(coh), np.nan)
    valido = np.isfinite(m_sitio) & np.isfinite(m_aro) & (m_aro > 0)
    fila = {k: np.nan for k in ("insomnio", "persistencia", "contraste_mediana", "contraste_desvio", "tendencia",
                                "eco_contraste", "eco_variacion", "hv_hh", "urbano_anillo", "cultivo_anillo",
                                "contraste_p10", "eco_var_p90", "ha_insomnio_90")}
    fila["n_pares"], fila["n_orbitas"] = int(np.isfinite(m_sitio).sum()), 0
    if valido.any():
        cociente = m_sitio[valido] / m_aro[valido]
        despierto = np.zeros(len(coh), dtype=bool)
        despierto[valido] = cociente < p.razon
        i, partes = ins.por_orbita(despierto[:, None], valido[:, None], d["orbitas"], p.min_pares_orbita)
        fila.update(insomnio=float(i[0]), persistencia=float(ins.persistencia(despierto[:, None], valido[:, None], d["fechas"])[0]),
                    contraste_mediana=float(np.median(cociente)), contraste_desvio=float(np.std(cociente)),
                    n_pares=int(valido.sum()), n_orbitas=int(sum(np.isfinite(x[0]) for x in partes.values())))
    # The most active part of the site: the least coherent decile against the ring, pair by pair.
    if adentro.sum() >= 4 and aro.any():
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            p10 = np.nanpercentile(coh[:, adentro], 10, axis=1)
        ok = np.isfinite(p10) & np.isfinite(m_aro) & (m_aro > 0)
        if ok.any():
            fila["contraste_p10"] = float(np.median(p10[ok] / m_aro[ok]))
    # The largest connected area of the site with per-pixel insomnia >= 0.9 (ha).
    alto = adentro & (np.nan_to_num(d["insomnio_px"][v]) >= 0.9)
    etq, _ = ndimage.label(alto)
    fila["ha_insomnio_90"] = float(max(np.bincount(etq.ravel())[1:], default=0) * paso * paso / 1e4)
    con_dato = np.isfinite(m_sitio)
    if con_dato.sum() >= 3:  # slope over time of the blob's coherence, brought to 12-day pairs
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
        if desvios:  # between dates of the same orbit (each orbit looks with another geometry)
            fila["eco_variacion"] = float(np.mean(desvios))
        # The same per pixel: a moving front changes the echo of its pixels even if the site mean doesn't change.
        if adentro.any():
            por_px = [np.nanstd(eco[d["orbitas_eco"] == o][:, adentro], axis=0) for o in np.unique(d["orbitas_eco"]) if (d["orbitas_eco"] == o).sum() >= 3]
            if por_px:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", RuntimeWarning)
                    var_px = np.nanmean(np.stack(por_px), axis=0)
                if np.isfinite(var_px).any():
                    fila["eco_var_p90"] = float(np.nanpercentile(var_px, 90))
    if d["eco_hv_db"] is not None and np.isfinite(fila["eco_db"]):
        fila["hv_hh"] = _media(d["eco_hv_db"][v], adentro) - fila["eco_db"]
    fila["agua_anillo"] = float(d["agua"][v][aro_bruto].mean()) if aro_bruto.any() else np.nan
    for clave, capa in (("urbano_anillo", d["urbano"]), ("cultivo_anillo", d["cultivo"])):
        if capa is not None and aro_bruto.any():
            valores = capa[v][aro_bruto]
            valores = valores[valores <= 100]
            if len(valores):
                fila[clave] = float(valores.mean() / 100)
    fila["indice_actividad"] = indice_actividad(fila["contraste_p10"], fila["eco_var_p90"])
    fila["px"], fila["px_anillo"] = int(adentro.sum()), int(aro.sum())
    return fila


# ------------------------------------------------------------------ un frame
def preparar(a, p):
    """Reads the frame with the pipeline's reader and computes the index layers. Returns (context, blobs, labels)."""
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
    except Exception as e:  # offline: the two context columns stay empty
        print(f"AVISO: sin ESA WorldCover para {fr.nombre} ({type(e).__name__}: {e}): urbano_anillo y cultivo_anillo quedan vacías")
    import datetime as dt

    dia = np.array([(dt.date.fromisoformat(str(f)) - dt.date(2025, 1, 1)).days for f in ctx["fechas"]], dtype=float)
    d = {"fr": fr, "paso": ctx["paso"], "xs": ctx["xs"], "ys": ctx["ys"], "coh": ctx["coh"], "orbitas": ctx["orbitas"],
         "fechas": ctx["fechas"], "dia": dia, "factor": capas["factor_separacion"], "agua": capas["agua"], "tierra": ~capas["agua"],
         "catalogo_px": ctx["catalogo_px"], "catalogo": ctx["catalogo"], "coherencia_media": capas["coherencia_media"],
         "insomnio_px": capas["insomnio"],
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
    for n, m in enumerate(lista, start=1):  # the order of `insomnio.manchas()`: largest area first
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
        if not np.isfinite(r["insomnio"]):  # no ring (all water or catalogs around): the per-pixel mean is kept
            r["insomnio"], r["persistencia"] = float(m["insomnio"]), float(m["persistencia"])
        area_m2 = m["ha"] * 1e4
        filas.append({"id_mancha": ident, "frame": fr.nombre, **{k: r[k] for k in (
            "insomnio", "persistencia", "contraste_mediana", "contraste_desvio", "coherencia_media", "tendencia", "n_pares",
            "n_orbitas", "eco_db", "eco_contraste", "eco_variacion", "hv_hh")},
            "area_ha": float(m["ha"]), "elongacion": float(m["elongacion"]), "compacidad": float(min(1.0, 4 * np.pi * area_m2 / perimetro**2)),
            "agua_anillo": r["agua_anillo"], "urbano_anillo": r["urbano_anillo"], "cultivo_anillo": r["cultivo_anillo"],
            "px_anillo": r["px_anillo"], "insomnio_px": float(m["insomnio"]), "persistencia_px": float(m["persistencia"]),
            "contraste_p10": r["contraste_p10"], "eco_var_p90": r["eco_var_p90"], "ha_insomnio_90": r["ha_insomnio_90"], "indice_actividad": r["indice_actividad"],
            "clase_osm": m.get("clase"), "que": m.get("que")})
    return features, filas


def catalogo_del_frame(d, p, min_ha=contratos.MIN_HA):
    """One row per catalog polygon whose center falls in the frame's box: `insomnio.ficha()` against its ring.

    It's the logic of `insomnio_catalogo.py` (exact mode), with the frame's grid and the ring without catalogs.
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
        extra = medir(mascara, d, p) if mascara.any() else {}
        radar, motivo = f["radar"], f["motivo"]
        if ha < min_ha:
            radar, motivo = "no_alcanza", f"el polígono mide {ha:.1f} ha: menos de {min_ha:g} ha"
        filas.append({"id_catalogo": s["id"], "catalogo": s["catalogo"], "complejo": s.get("complejo"), "frame": fr.nombre,
                      "insomnio": f["insomnio"], "persistencia": f["persistencia"], "eco_db": f["eco_db"], "n_pares": len(f["pares"]),
                      "radar": radar, "motivo": motivo, "area_ha": float(ha), "estado": s.get("estado"), "clase": s.get("clase"),
                      "nombre": s.get("nombre") or None, "estado_complejo": s.get("estado_complejo"), "px": f["px"],
                      "px_anillo": f["px_anillo"], "modo": "exacto",
                      **{k: extra.get(k, np.nan) for k in ("contraste_p10", "eco_var_p90", "ha_insomnio_90", "hv_hh", "indice_actividad")}})
    df = pd.DataFrame(filas, columns=["id_catalogo", "catalogo", "complejo", "frame", "insomnio", "persistencia", "eco_db", "n_pares",
                                      "radar", "motivo", "area_ha", "estado", "clase", "nombre", "estado_complejo", "px", "px_anillo", "modo",
                                      "contraste_p10", "eco_var_p90", "ha_insomnio_90", "hv_hh", "indice_actividad"])
    for c in ("insomnio", "persistencia", "eco_db", "area_ha", "contraste_p10", "eco_var_p90", "ha_insomnio_90", "hv_hh", "indice_actividad"):
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


META = {"fuente": "NISAR L2 GUNW y GCOV (NASA/ISRO), ASF DAAC; índice de insomnio de motor/insomnio.py",
        "generado_por": "motor/extraer_manchas.py", "aviso": "Señal compatible con actividad; no son basurales verificados."}


def _sin_chicas(features, min_ha):
    """The ones discarded for being small are thousands per frame: of those only the ones of `min_ha` or more are kept. All the others are kept."""
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
    """Joins the files of all frames (`<base>/<FRAME>/`) into the three in `destino`, which are the contract's."""
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
    q.add_argument("--frame", nargs="+", default=["AMBA"], help="one or more frames from data/catalogos/frames.json, or `todos`")
    q.add_argument("--salida", default=os.path.join(RAIZ, "data", "salidas"), help="pipeline folder: a frame's crops are in <salida>/<FRAME>/ (the AMBA's, in <salida>/)")
    q.add_argument("--destino", help="folder to write to: each frame in <destino>/<FRAME>/ and `juntar` in <destino>/ (default: --salida)")
    q.add_argument("--fijos", default=pl.FIJOS, help="folder of the fixed sources (see pipeline_insomnio.py)")
    q.add_argument("--capa", choices=list(pl.CAPAS), default="80m")
    q.add_argument("--min-insomnio", type=float, help="insomnia threshold to build the blobs. Only to gather more training rows "
                   "(for example 0.5); the verdict uses the one in `insomnio.Parametros` (0.70)")
    q.add_argument("--min-ha-descartadas", type=float, default=5.0, help="minimum area of the blobs discarded for being small that get written "
                   "to `manchas.geojson` (they are thousands per frame; 0 = all). Candidates and the other discarded ones are always written")
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
