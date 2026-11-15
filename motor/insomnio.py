"""Índice de insomnio, versión final: el cálculo, sin lectura ni escritura de archivos.

Entra una pila de coherencia por par (GUNW de NISAR) ya recortada a una grilla común y sale, por píxel:
  - insomnio absoluto: fracción de pares con coherencia < umbral, normalizada por la separación entre pasadas;
  - insomnio relativo: fracción de pares con coherencia baja respecto del entorno;
  - persistencia: el mínimo de esa fracción entre los tres tercios de la serie (todo el período vs. por temporada);
  - candidatos y manchas, sin agua, sin superficies lisas y sin formas lineales.
Y por sitio conocido: la serie par a par contra un anillo y un veredicto.

Las dos órbitas se calculan por separado (tienen geometrías distintas) y se promedian al final.
Cómo se eligieron los umbrales: `pipeline_insomnio.py calibrar` y `../docs/indice-insomnio.md`.
"""
import warnings
from dataclasses import asdict, dataclass

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from scipy import ndimage


@dataclass(frozen=True)
class Parametros:
    razon: float = 0.80  # un par está "despierto" si la coherencia < razon × la del entorno
    min_insomnio: float = 0.70  # fracción mínima de pares despiertos para ser candidato o "despierto"
    min_persistencia: float = 0.50  # fracción mínima de pares despiertos en CADA tercio de la serie
    max_quieto: float = 0.20  # un sitio es "quieto" si su insomnio no pasa de esto
    eco_min_db: float = -13.0  # por debajo es superficie lisa: la coherencia baja no dice nada
    agua_min: float = 10.0  # % de ocurrencia de agua (JRC) a partir del cual la celda es agua
    borde_agua_m: float = 80.0  # la máscara de agua se ensancha esto, por los píxeles mixtos de la costa
    radio_entorno_m: float = 2000.0  # radio del entorno de cada píxel
    anillo_m: float = 1500.0  # ancho del anillo alrededor de un sitio
    bloque_entorno_m: float = 320.0  # el entorno se calcula sobre bloques de este tamaño
    suavizado_m: float = 240.0  # mediana espacial antes de comparar con el entorno
    umbral_abs: float = 0.30  # coherencia por debajo de la cual un par cuenta en el índice absoluto
    min_ha: float = 10.0  # superficie mínima de una mancha
    max_elongacion: float = 4.0  # más alargada que esto es lineal (ruta, arroyo)
    min_nucleo: float = 0.10  # fracción de la mancha que sobrevive a una erosión de 1 píxel; menos es un hilo
    min_px_sitio: int = 8  # un sitio con menos píxeles de tierra que esto no se puede medir
    min_coh_anillo: float = 0.30  # si el anillo no llega a esto, el entorno tampoco es coherente
    min_pares_orbita: int = 3  # pares válidos mínimos para que una órbita cuente en un píxel

    def dict(self):
        return asdict(self)


# ------------------------------------------------------------------ piezas
def mascara_agua(ocurrencia, paso, p):
    """Agua fija: ocurrencia de agua de JRC >= p.agua_min, ensanchada p.borde_agua_m."""
    agua = np.asarray(ocurrencia) >= p.agua_min
    n = int(round(p.borde_agua_m / paso))
    return ndimage.binary_dilation(agua, iterations=n) if n > 0 else agua


def factores_separacion(coh, tierra, orbitas, dias):
    """Factor por par para llevar la coherencia a la de un par de 12 días de la misma órbita.

    Es empírico: mediana sobre tierra de los pares con esa separación / mediana de los pares de 12 días.
    Los pares de 12 días quedan en 1. Devuelve (factores, medianas por par).
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
    """Mediana espacial de p.suavizado_m de lado (3×3 a 80 m). Los NaN se rellenan con la mediana de la capa."""
    n = max(3, int(round(p.suavizado_m / paso)) | 1)
    malo = ~np.isfinite(c)
    s = ndimage.median_filter(np.where(malo, np.nanmedian(c), c), size=n)
    s[malo] = np.nan
    return s


def entorno(c, tierra, paso, p):
    """Coherencia típica alrededor de cada píxel: mediana sobre tierra en un disco de p.radio_entorno_m.

    Se calcula en bloques de p.bloque_entorno_m (mediana por bloque y después mediana de los bloques
    del disco) y se interpola a la grilla. El agua no entra.
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
    # centro del bloque i en píxeles: i*b + (b-1)/2
    fi = (np.arange(h) - (b - 1) / 2) / b
    ci = (np.arange(w) - (b - 1) / 2) / b
    return ndimage.map_coordinates(f, np.meshgrid(fi, ci, indexing="ij"), order=1, mode="nearest").astype(np.float32)


def tercios(fechas):
    """Reparte los pares en tres tramos consecutivos por fecha de la segunda pasada: 0, 1 o 2."""
    fechas = np.asarray(fechas)
    orden = np.argsort(fechas, kind="stable")
    t = np.empty(len(fechas), dtype=int)
    t[orden] = np.arange(len(fechas)) * 3 // len(fechas)
    return t


def fraccion(despierto, valido):
    """Fracción de pares despiertos sobre los válidos, a lo largo del eje 0. NaN donde no hay ninguno."""
    n = valido.sum(0)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(n > 0, (despierto & valido).sum(0) / n, np.nan), n


def por_orbita(despierto, valido, orbitas, min_pares):
    """Fracción de pares despiertos en cada órbita y el promedio de las órbitas con pares suficientes."""
    partes = {}
    for o in np.unique(orbitas):
        f, n = fraccion(despierto[orbitas == o], valido[orbitas == o])
        partes[int(o)] = np.where(n >= min(min_pares, int((orbitas == o).sum())), f, np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmean(np.stack(list(partes.values())), axis=0), partes


def persistencia(despierto, valido, fechas):
    """El mínimo, entre los tres tercios de la serie, de la fracción de pares despiertos.

    Alto: despierto todo el período (compatible con un basural). Bajo con insomnio alto: despierto por temporada.
    """
    t = tercios(fechas)
    partes = [fraccion(despierto[t == i], valido[t == i])[0] for i in range(3) if (t == i).any()]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmin(np.stack(partes), axis=0)


def eco_medio(eco, orbitas_eco):
    """Eco (dB) típico por píxel: mediana en el tiempo de cada órbita y promedio de las órbitas."""
    if eco is None or not len(eco):
        return None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmean(np.stack([np.nanmedian(eco[orbitas_eco == o], axis=0) for o in np.unique(orbitas_eco)]), axis=0)


# ------------------------------------------------------------------ índice por píxel
def cocientes(coh, tierra, paso, p):
    """Coherencia suavizada / coherencia del entorno, por par. Es lo caro del cálculo y no depende de los umbrales."""
    salida = np.empty(coh.shape, dtype=np.float32)
    for i, c in enumerate(coh):
        with np.errstate(invalid="ignore", divide="ignore"):
            salida[i] = suavizar(c, paso, p) / entorno(c, tierra, paso, p)
    return salida


def calcular(coh, orbitas, dias, fechas, agua, paso, p, eco=None, orbitas_eco=None, cociente=None, eco_db=None):
    """Capas del índice. coh: (pares, filas, columnas) con NaN donde no hay dato; agua: máscara booleana.

    `cociente` y `eco_db` se pueden pasar ya calculados (para barrer umbrales sin repetir lo caro).
    """
    orbitas, dias = np.asarray(orbitas), np.asarray(dias)
    tierra = ~agua
    valido = np.isfinite(coh) & tierra
    fac, med = factores_separacion(coh, tierra, orbitas, dias)

    with np.errstate(invalid="ignore"):
        normal = np.clip(coh / fac[:, None, None], 0, 1)
        absoluto, abs_orbita = por_orbita(normal < p.umbral_abs, valido, orbitas, p.min_pares_orbita)

    # El cociente con el entorno no depende del factor de separación: cada par se compara consigo mismo.
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
    """Agrupa los candidatos en manchas y mide cada una. Devuelve (lista, etiquetas).

    `forma` es "compacta", "alargada" o "lineal". Las de menos de p.min_ha, las lineales y las lisas (eco medio
    de la mancha < p.eco_min_db: agua que no está en la máscara, pistas, suelo liso) se informan con `descartada`
    y no cuentan como candidatas. El eco se mira por mancha y no por píxel porque píxel a píxel es muy ruidoso.
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
    """Anillo de p.anillo_m alrededor de un sitio, sin el sitio, sin agua y sin lo que marque `excluir`.

    `excluir` es una máscara con todos los polígonos de los catálogos (basurales y negativos) del frame: así un
    relleno vecino o un aeródromo, que también pierden coherencia, no bajan la referencia del sitio.
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
    """Serie par a par y veredicto de un sitio.

    Por cada par compara la mediana de la coherencia adentro del sitio con la del anillo (sin agua y sin los
    polígonos de `excluir`, ver `anillo`). El par está despierto si adentro < p.razon × anillo. Veredictos:
      despierto   insomnio >= p.min_insomnio y persistencia >= p.min_persistencia
      quieto      insomnio <= p.max_quieto, con un entorno coherente
      no_alcanza  todo lo demás, con el motivo
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
