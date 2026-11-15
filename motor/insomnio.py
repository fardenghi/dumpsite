"""Insomnia index, final version: the computation, without reading or writing files.

In goes a stack of per-pair coherence (NISAR GUNW) already cropped to a common grid, and out comes, per pixel:
  - absolute insomnia: fraction of pairs with coherence < threshold, normalized by the separation between passes;
  - relative insomnia: fraction of pairs with low coherence relative to the surroundings;
  - persistence: the minimum of that fraction across the three thirds of the series (whole period vs. seasonal);
  - candidates and blobs, without water, smooth surfaces or linear shapes.
And per known site: the pair-by-pair series against a ring and a verdict.

The two orbits are computed separately (they have different geometries) and averaged at the end.
How the thresholds were chosen: `pipeline_insomnio.py calibrar` and `../docs/insomnia-index.md`.
"""
import warnings
from dataclasses import asdict, dataclass

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from scipy import ndimage


@dataclass(frozen=True)
class Parametros:
    razon: float = 0.80  # a pair is "awake" if coherence < razon × that of the surroundings
    min_insomnio: float = 0.70  # minimum fraction of awake pairs to be a candidate or "awake"
    min_persistencia: float = 0.50  # minimum fraction of awake pairs in EACH third of the series
    max_quieto: float = 0.20  # a site is "quiet" if its insomnia doesn't exceed this
    eco_min_db: float = -13.0  # below this it's a smooth surface: low coherence says nothing
    agua_min: float = 10.0  # % of water occurrence (JRC) from which the cell is water
    borde_agua_m: float = 80.0  # the water mask is widened by this, because of the mixed coastal pixels
    radio_entorno_m: float = 2000.0  # radius of each pixel's surroundings
    anillo_m: float = 1500.0  # width of the ring around a site
    bloque_entorno_m: float = 320.0  # the surroundings are computed over blocks of this size
    suavizado_m: float = 240.0  # spatial median before comparing with the surroundings
    umbral_abs: float = 0.30  # coherence below which a pair counts in the absolute index
    min_ha: float = 10.0  # minimum blob area
    max_elongacion: float = 4.0  # more elongated than this is linear (road, stream)
    min_nucleo: float = 0.10  # fraction of the blob that survives a 1-pixel erosion; less is a thread
    min_px_sitio: int = 8  # a site with fewer land pixels than this can't be measured
    min_coh_anillo: float = 0.30  # if the ring doesn't reach this, the surroundings aren't coherent either
    min_pares_orbita: int = 3  # minimum valid pairs for an orbit to count at a pixel

    def dict(self):
        return asdict(self)


# ------------------------------------------------------------------ piezas
def mascara_agua(ocurrencia, paso, p):
    """Agua fija: ocurrencia de agua de JRC >= p.agua_min, ensanchada p.borde_agua_m."""
    agua = np.asarray(ocurrencia) >= p.agua_min
    n = int(round(p.borde_agua_m / paso))
    return ndimage.binary_dilation(agua, iterations=n) if n > 0 else agua


def factores_separacion(coh, tierra, orbitas, dias):
    """Per-pair factor to bring the coherence to that of a 12-day pair of the same orbit.

    It's empirical: median over land of the pairs with that separation / median of the 12-day pairs.
    The 12-day pairs stay at 1. Returns (factors, medians per pair).
    """
    med = np.array([np.nanmedian(c[tierra]) for c in coh])
    fac = np.ones(len(coh))
    for o in np.unique(orbitas):
        base = (orbitas == o) & (dias == 12)
        if not base.any():
            continue
        ref = np.median(med[base])
        for d in np.unique(dias[(orbitas == o) & (dias != 12)]):
            sel = (orbitas == o) & (dias == d)
            fac[sel] = np.median(med[sel]) / ref
    return fac, med


def suavizar(c, paso, p):
    """Spatial median of p.suavizado_m per side (3×3 at 80 m). NaNs are filled with the layer median."""
    n = max(3, int(round(p.suavizado_m / paso)) | 1)
    malo = ~np.isfinite(c)
    s = ndimage.median_filter(np.where(malo, np.nanmedian(c), c), size=n)
    s[malo] = np.nan
    return s


def entorno(c, tierra, paso, p):
    """Typical coherence around each pixel: median over land in a disk of p.radio_entorno_m.

    It's computed in blocks of p.bloque_entorno_m (median per block and then median of the disk's
    blocks) and interpolated to the grid. Water doesn't count.
    """
    b = max(1, int(round(p.bloque_entorno_m / paso)))
    h, w = c.shape
    hb, wb = -(-h // b), -(-w // b)
    lleno = np.full((hb * b, wb * b), np.nan, dtype=np.float32)
    lleno[:h, :w] = np.where(tierra, c, np.nan)
    bloques = lleno.reshape(hb, b, wb, b).transpose(0, 2, 1, 3).reshape(hb, wb, b * b)
    k = max(1, int(round(p.radio_entorno_m / (paso * b))))
    yy, xx = np.mgrid[-k:k + 1, -k:k + 1]
    disco = yy**2 + xx**2 <= k * k + 1
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # bloques y discos enteros de agua
        g = np.nanmedian(bloques, axis=-1)
        ventanas = sliding_window_view(np.pad(g, k, constant_values=np.nan), (2 * k + 1, 2 * k + 1))[..., disco]
        f = np.nanmedian(ventanas, axis=-1)
    f = np.where(np.isfinite(f), f, np.nanmedian(g))
    # center of block i in pixels: i*b + (b-1)/2
    fi = (np.arange(h) - (b - 1) / 2) / b
    ci = (np.arange(w) - (b - 1) / 2) / b
    return ndimage.map_coordinates(f, np.meshgrid(fi, ci, indexing="ij"), order=1, mode="nearest").astype(np.float32)


def tercios(fechas):
    """Splits the pairs into three consecutive segments by date of the second pass: 0, 1 or 2."""
    fechas = np.asarray(fechas)
    orden = np.argsort(fechas, kind="stable")
    t = np.empty(len(fechas), dtype=int)
    t[orden] = np.arange(len(fechas)) * 3 // len(fechas)
    return t


def fraccion(despierto, valido):
    """Fraction of awake pairs over the valid ones, along axis 0. NaN where there are none."""
    n = valido.sum(0)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(n > 0, (despierto & valido).sum(0) / n, np.nan), n


def por_orbita(despierto, valido, orbitas, min_pares):
    """Fraction of awake pairs in each orbit and the mean of the orbits with enough pairs."""
    partes = {}
    for o in np.unique(orbitas):
        f, n = fraccion(despierto[orbitas == o], valido[orbitas == o])
        partes[int(o)] = np.where(n >= min(min_pares, int((orbitas == o).sum())), f, np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmean(np.stack(list(partes.values())), axis=0), partes


def persistencia(despierto, valido, fechas):
    """The minimum, across the three thirds of the series, of the fraction of awake pairs.

    High: awake the whole period (compatible with a dump site). Low with high insomnia: awake seasonally.
    """
    t = tercios(fechas)
    partes = [fraccion(despierto[t == i], valido[t == i])[0] for i in range(3) if (t == i).any()]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmin(np.stack(partes), axis=0)


def eco_medio(eco, orbitas_eco):
    """Typical echo (dB) per pixel: median over time of each orbit and mean of the orbits."""
    if eco is None or not len(eco):
        return None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmean(np.stack([np.nanmedian(eco[orbitas_eco == o], axis=0) for o in np.unique(orbitas_eco)]), axis=0)


# ------------------------------------------------------------------ per-pixel index
def cocientes(coh, tierra, paso, p):
    """Smoothed coherence / surroundings coherence, per pair. It's the expensive part and doesn't depend on the thresholds."""
    salida = np.empty(coh.shape, dtype=np.float32)
    for i, c in enumerate(coh):
        with np.errstate(invalid="ignore", divide="ignore"):
            salida[i] = suavizar(c, paso, p) / entorno(c, tierra, paso, p)
    return salida


def calcular(coh, orbitas, dias, fechas, agua, paso, p, eco=None, orbitas_eco=None, cociente=None, eco_db=None):
    """Index layers. coh: (pairs, rows, columns) with NaN where there's no data; agua: boolean mask.

    `cociente` and `eco_db` can be passed already computed (to sweep thresholds without repeating the expensive part).
    """
    orbitas, dias = np.asarray(orbitas), np.asarray(dias)
    tierra = ~agua
    valido = np.isfinite(coh) & tierra
    fac, med = factores_separacion(coh, tierra, orbitas, dias)

    with np.errstate(invalid="ignore"):
        normal = np.clip(coh / fac[:, None, None], 0, 1)
        absoluto, abs_orbita = por_orbita(normal < p.umbral_abs, valido, orbitas, p.min_pares_orbita)

    # The ratio to the surroundings doesn't depend on the separation factor: each pair is compared with itself.
    if cociente is None:
        cociente = cocientes(coh, tierra, paso, p)
    with np.errstate(invalid="ignore"):
        despierto = cociente < p.razon
    relativo, rel_orbita = por_orbita(despierto, valido, orbitas, p.min_pares_orbita)
    persiste = persistencia(despierto, valido, fechas)
    if eco_db is None:
        eco_db = eco_medio(eco, orbitas_eco)

    with np.errstate(invalid="ignore"):
        alto = tierra & (relativo >= p.min_insomnio)
        candidato = alto & (persiste >= p.min_persistencia)
        estacional = alto & (persiste < p.min_persistencia)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        media = np.nanmean(np.where(valido, normal, np.nan), axis=0)
    return {
        "insomnio": np.where(tierra, relativo, np.nan), "insomnio_abs": np.where(tierra, absoluto, np.nan),
        "persistencia": np.where(tierra, persiste, np.nan), "coherencia_media": media,
        "insomnio_orbita": rel_orbita, "insomnio_abs_orbita": abs_orbita, "eco_db": eco_db,
        "candidato": candidato, "estacional": estacional, "agua": agua,
        "pares_validos": valido.sum(0), "factor_separacion": fac, "mediana_par": med,
    }


# ------------------------------------------------------------------ manchas
def manchas(candidato, capas, paso, p):
    """Groups the candidates into blobs and measures each one. Returns (list, labels).

    `forma` is "compacta", "alargada" or "lineal". Those under p.min_ha, the linear ones and the smooth ones (mean echo
    of the blob < p.eco_min_db: water not in the mask, runways, smooth soil) are reported with `descartada`
    and don't count as candidates. The echo is looked at per blob, not per pixel, because pixel by pixel it's very noisy.
    """
    etiquetas, n = ndimage.label(candidato)
    if n == 0:
        return [], etiquetas
    ff, cc = np.nonzero(etiquetas)
    e = etiquetas[ff, cc]
    suma = lambda v: np.bincount(e, weights=v, minlength=n + 1)[1:]  # noqa: E731
    px = suma(np.ones(len(e)))
    mf, mc = suma(ff) / px, suma(cc) / px
    vf = suma(ff * ff) / px - mf**2 + 1 / 12
    vc = suma(cc * cc) / px - mc**2 + 1 / 12
    cov = suma(ff * cc) / px - mf * mc
    raiz = np.sqrt(((vf - vc) / 2) ** 2 + cov**2)
    l1, l2 = (vf + vc) / 2 + raiz, np.maximum((vf + vc) / 2 - raiz, 1 / 12)
    elong = np.sqrt(l1 / l2)
    nucleo_px = np.bincount(etiquetas[ndimage.binary_erosion(candidato)], minlength=n + 1)[1:]
    nucleo = nucleo_px / px

    def media(capa):
        if capa is None:
            return np.full(n, np.nan)
        v = capa[ff, cc]
        ok = np.isfinite(v)
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.bincount(e[ok], weights=v[ok], minlength=n + 1)[1:] / np.bincount(e[ok], minlength=n + 1)[1:]

    ins, per, eco = media(capas["insomnio"]), media(capas["persistencia"]), media(capas.get("eco_db"))
    ha = px * paso * paso / 1e4
    lineal = (elong >= p.max_elongacion) | (nucleo < p.min_nucleo)
    forma = np.where(lineal, "lineal", np.where(elong >= 2.5, "alargada", "compacta"))
    lista = []
    for i in np.argsort(-ha):
        motivo = "chica" if ha[i] < p.min_ha else "lineal" if lineal[i] else "lisa" if eco[i] < p.eco_min_db else None
        lista.append({
            "etiqueta": int(i + 1), "ha": round(float(ha[i]), 1), "fila": float(mf[i]), "columna": float(mc[i]),
            "insomnio": round(float(ins[i]), 2), "persistencia": round(float(per[i]), 2),
            "eco_db": None if not np.isfinite(eco[i]) else round(float(eco[i]), 1),
            "elongacion": round(float(elong[i]), 1), "nucleo": round(float(nucleo[i]), 2), "forma": str(forma[i]),
            "descartada": motivo,
        })
    return lista, etiquetas


# ------------------------------------------------------------------ sitios
def anillo(mascara, tierra, paso, p, excluir=None):
    """Ring of p.anillo_m around a site, without the site, without water and without whatever `excluir` marks.

    `excluir` is a mask with all the catalog polygons (dump sites and negatives) of the frame: that way a
    neighboring landfill or an airfield, which also lose coherence, don't lower the site's reference.
    """
    n = int(round(p.anillo_m / paso))
    yy, xx = np.mgrid[-n:n + 1, -n:n + 1]
    f0, f1 = np.nonzero(mascara.any(1))[0][[0, -1]]
    c0, c1 = np.nonzero(mascara.any(0))[0][[0, -1]]
    sf = slice(max(f0 - n, 0), f1 + n + 1)
    sc = slice(max(c0 - n, 0), c1 + n + 1)
    salida = np.zeros_like(mascara)
    salida[sf, sc] = ndimage.binary_dilation(mascara[sf, sc], structure=yy**2 + xx**2 <= n * n)
    salida &= ~mascara & tierra
    return salida if excluir is None else salida & ~excluir


def ficha(mascara, coh, orbitas, fechas, tierra, paso, p, eco_db=None, excluir=None):
    """Pair-by-pair series and verdict for a site.

    For each pair it compares the median coherence inside the site with the ring's (without water and without the
    `excluir` polygons, see `anillo`). The pair is awake if inside < p.razon × ring. Verdicts:
      despierto   insomnia >= p.min_insomnio and persistence >= p.min_persistencia
      quieto      insomnia <= p.max_quieto, with coherent surroundings
      no_alcanza  everything else, with the reason
    """
    adentro = mascara & tierra
    aro = anillo(mascara, tierra, paso, p, excluir)
    n_px = int(adentro.sum())
    base = {"px": n_px, "px_anillo": int(aro.sum()), "pares": [], "insomnio": None, "persistencia": None,
            "insomnio_orbita": {}, "eco_db": None}
    if n_px == 0 or not aro.any():
        motivo = "el predio es agua o queda fuera de la grilla" if n_px == 0 else "no queda anillo: alrededor todo es agua o polígonos de los catálogos"
        return {**base, "radar": "no_alcanza", "motivo": motivo}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        m_sitio = np.nanmedian(coh[:, adentro], axis=1)
        m_aro = np.nanmedian(coh[:, aro], axis=1)
    valido = np.isfinite(m_sitio) & np.isfinite(m_aro)
    despierto = valido & (m_sitio < p.razon * m_aro)
    orbitas = np.asarray(orbitas)
    ins, partes = por_orbita(despierto[:, None], valido[:, None], orbitas, p.min_pares_orbita)
    per = persistencia(despierto[:, None], valido[:, None], fechas)
    ins, per = float(ins[0]), float(per[0])
    eco = float(np.nanmedian(eco_db[adentro])) if eco_db is not None and np.isfinite(eco_db[adentro]).any() else None
    base.update(
        pares=[{"fecha": str(f), "orbita": int(o), "sitio": round(float(s), 2), "anillo": round(float(a), 2), "despierto": bool(d)}
               for f, o, s, a, d, v in zip(fechas, orbitas, m_sitio, m_aro, despierto, valido) if v],
        insomnio=round(ins, 2), persistencia=round(per, 2),
        insomnio_orbita={o: round(float(v[0]), 2) for o, v in partes.items()}, eco_db=None if eco is None else round(eco, 1),
    )
    if n_px < p.min_px_sitio:
        radar, motivo = "no_alcanza", f"el predio ocupa {n_px} píxeles de {paso:.0f} m: menos de {p.min_px_sitio}"
    elif eco is not None and eco < p.eco_min_db:
        radar, motivo = "no_alcanza", f"superficie lisa (eco {eco:.1f} dB): la coherencia baja no distingue cambio de falta de señal"
    elif np.median(m_aro[valido]) < p.min_coh_anillo:
        radar, motivo = "no_alcanza", "el entorno tampoco es coherente"
    elif ins >= p.min_insomnio and per >= p.min_persistencia:
        radar, motivo = "despierto", "coherencia baja respecto del anillo en casi todos los pares y en los tres tramos de la serie"
    elif ins >= p.min_insomnio:
        radar, motivo = "no_alcanza", "despierto sólo en una parte de la serie (compatible con algo estacional)"
    elif ins <= p.max_quieto:
        radar, motivo = "quieto", "coherencia igual o mayor que la del anillo en casi todos los pares"
    else:
        radar, motivo = "no_alcanza", "señal intermedia: ni quieto ni despierto"
    return {**base, "radar": radar, "motivo": motivo}
