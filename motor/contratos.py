"""Data contracts: the format of the model's intermediate files, in code.

The long explanation (who writes, who reads and why) is in `../docs/data-contracts.md`. Here are
each file's columns as constants and `validar()`, which fails with a clear message.

    import contratos
    contratos.validar(df, "tabla_radar")                  # a DataFrame you're about to write
    contratos.guardar(df, "tabla_radar", "../data/salidas")    # validates, orders the columns and writes
    df = contratos.leer("datos/mock", "tabla_radar")   # reads and validates

    python contratos.py datos/mock                     # validates everything it finds in a folder
    python contratos.py ../data/salidas/tabla_radar.parquet    # or a file

Rules: columns can be added, but the contract's can't be removed or renamed. Columns marked
as optional may be missing; if present, they're validated.
"""
import json
import os
import re
import sys
from dataclasses import dataclass

import numpy as np
import pandas as pd
from pandas.api import types as pdt

# ------------------------------------------------------------------ valores permitidos
CLASES = ("basural_activo", "otro_movil")
CATALOGOS = ("basurales", "negativos")
RADAR = ("despierto", "quieto", "no_alcanza")
FORMAS = ("compacta", "alargada", "lineal")
DESCARTES = ("chica", "lineal", "lisa")
ESTADOS = ("abierto", "cerrado", "contradictorio", "desconocido")
ESTADOS_FRAME = ("abierto", "cerrado", "desconocido")  # claves obligatorias de `n_basurales_10ha`
HEMISFERIOS = ("N", "S")
PRUEBA_FINAL = "prueba_final"

PATRON_FRAME = r"[A-Z0-9_]+"
PATRON_MANCHA = rf"MAN-{PATRON_FRAME}-\d{{4,}}"
PATRON_CATALOGO = r"(BAS|NEG)-.+"
PATRON_FECHA = r"\d{4}-\d{2}-\d{2}"
PATRON_FECHAS = rf"{PATRON_FECHA}(,{PATRON_FECHA})*"

# Thresholds in the plan (section 3, stage 6). They're saved in `particiones.json`.
CRITERIO_CRUCE = 0.30  # the intersection covers at least this much of the smaller area
MIN_HA = 10.0


def id_mancha(frame, n):
    """`MAN-<frame>-<n>`, with n from 1 in the order of `insomnio.manchas()` (largest area first)."""
    return f"MAN-{frame}-{int(n):04d}"


# ------------------------------------------------------------------ columnas
@dataclass(frozen=True)
class Col:
    nombre: str
    tipo: str  # str, float, int, bool, lista_int, lista_str, caja, conteos
    unidad: str
    que: str
    nulo: bool = False  # may it be empty?
    opcional: bool = False  # may the column be missing?
    valores: tuple = None
    rango: tuple = None  # (minimum, maximum); None at one end means "no limit"
    patron: str = None


F01 = (0.0, 1.0)

_ID_MANCHA = Col("id_mancha", "str", "", "Identificador de la mancha: `MAN-<frame>-<n>`", patron=PATRON_MANCHA)
_ID_CATALOGO = Col("id_catalogo", "str", "", "`id` del polígono en `data/catalogos/basurales/` (`BAS-…`) o `data/catalogos/negativos/` (`NEG-…`)",
                   patron=PATRON_CATALOGO)
_CATALOGO = Col("catalogo", "str", "", "De qué catálogo sale el polígono", valores=CATALOGOS)
_FRAME = Col("frame", "str", "", "Clave del frame, la de `frames.json` (por ejemplo `AMBA`)", patron=PATRON_FRAME)

MOVIMIENTO = (
    Col("insomnio", "float", "fracción 0-1", "Fracción de pares con coherencia < 0,80 × la del anillo, promediando órbitas", rango=F01),
    Col("persistencia", "float", "fracción 0-1", "Mínimo de la fracción despierta en los tres tramos de la serie", rango=F01),
    Col("contraste_mediana", "float", "cociente", "Coherencia de la mancha / la del anillo: mediana entre pares", nulo=True, rango=(0, None)),
    Col("contraste_desvio", "float", "cociente", "Desvío estándar de ese cociente entre pares", nulo=True, rango=(0, None)),
    Col("coherencia_media", "float", "coherencia 0-1", "Coherencia absoluta media, normalizada a 12 días", nulo=True, rango=F01),
    Col("tendencia", "float", "coherencia por día", "Pendiente de la coherencia normalizada en el tiempo", nulo=True),
    Col("n_pares", "int", "pares", "Pares GUNW válidos sobre la mancha", rango=(0, None)),
    Col("n_orbitas", "int", "órbitas", "Órbitas con pares suficientes", rango=(0, None)),
)
RUGOSIDAD = (
    Col("eco_db", "float", "dB", "Eco (backscatter HH, gamma0) medio de la mancha", nulo=True),
    Col("eco_contraste", "float", "dB", "Eco de la mancha menos el del anillo", nulo=True),
    Col("eco_variacion", "float", "dB", "Desvío estándar del eco medio entre fechas", nulo=True, rango=(0, None)),
    Col("hv_hh", "float", "dB", "Cociente entre polarizaciones: eco HV menos eco HH", nulo=True),
)
FORMA = (
    Col("area_ha", "float", "ha", "Superficie de la mancha (igual a `ha` en `manchas.geojson`)", rango=(0, None)),
    Col("elongacion", "float", "cociente ≥ 1", "Eje mayor / eje menor (la de `insomnio.manchas()`)", rango=(1, None)),
    Col("compacidad", "float", "0-1", "4π × área / perímetro²: 1 es un círculo", nulo=True, rango=F01),
)
CONTEXTO = (
    Col("agua_anillo", "float", "fracción 0-1", "Parte del anillo de 1,5 km que es agua (JRC)", nulo=True, rango=F01),
    Col("urbano_anillo", "float", "fracción 0-1", "Parte del anillo que es urbana (ESA WorldCover, clase 50)", nulo=True, rango=F01),
    Col("cultivo_anillo", "float", "fracción 0-1", "Parte del anillo que es cultivo (ESA WorldCover, clase 40)", nulo=True, rango=F01),
)
OPTICO = (
    Col("ndvi_media", "float", "índice −1 a 1", "NDVI adentro, media entre fechas", nulo=True, rango=(-1, 1)),
    Col("ndvi_variacion", "float", "índice", "Desvío estándar del NDVI de adentro entre fechas", nulo=True, rango=(0, None)),
    Col("bsi_media", "float", "índice −1 a 1", "Suelo desnudo (BSI) adentro, media entre fechas", nulo=True, rango=(-1, 1)),
    Col("ndwi_media", "float", "índice −1 a 1", "NDWI (agua) adentro, media entre fechas", nulo=True, rango=(-1, 1)),
    Col("swir_b11", "float", "reflectancia 0-1", "Banda B11 (1,6 µm) adentro, media entre fechas", nulo=True, rango=(0, None)),
    Col("swir_b12", "float", "reflectancia 0-1", "Banda B12 (2,2 µm) adentro, media entre fechas", nulo=True, rango=(0, None)),
    Col("ndvi_contraste", "float", "índice", "`ndvi_media` menos el NDVI del anillo", nulo=True),
    Col("bsi_contraste", "float", "índice", "`bsi_media` menos el BSI del anillo", nulo=True),
    Col("ndwi_contraste", "float", "índice", "`ndwi_media` menos el NDWI del anillo", nulo=True),
    Col("swir_b11_contraste", "float", "reflectancia", "`swir_b11` menos la B11 del anillo", nulo=True),
    Col("swir_b12_contraste", "float", "reflectancia", "`swir_b12` menos la B12 del anillo", nulo=True),
)
_ESCENAS = (
    Col("n_escenas", "int", "escenas", "Escenas de Sentinel-2 usadas", rango=(0, None)),
    Col("fechas", "str", "AAAA-MM-DD", "Fechas de esas escenas, separadas por coma y en orden", nulo=True, patron=PATRON_FECHAS),
)
CNN = (Col("cnn_p_basural", "float", "probabilidad 0-1", "Lo que dice la ResNet-50, fuera de la partición", nulo=True, opcional=True, rango=F01),)

# The variables the model can use, in order (29). `clase` is the label and doesn't go here.
COLUMNAS_MODELO = tuple(c.nombre for c in MOVIMIENTO + RUGOSIDAD + OPTICO + FORMA + CONTEXTO)


# ------------------------------------------------------------------ contratos
@dataclass(frozen=True)
class Contrato:
    nombre: str
    ruta: str  # relative to `data/` (the data folder at the repo root)
    escribe: str
    lee: str
    fila: str
    clave: tuple
    columnas: tuple

    @property
    def archivo(self):
        return os.path.basename(self.ruta)

    @property
    def obligatorias(self):
        return tuple(c.nombre for c in self.columnas if not c.opcional)

    @property
    def nombres(self):
        return tuple(c.nombre for c in self.columnas)


CONTRATOS = {c.nombre: c for c in (
    Contrato(
        "manchas", "salidas/manchas.geojson", "etapa 4 (en el AMBA, el prompt 3)", "etapas 5, 6 y 9, y la web",
        "una mancha de un frame, incluidas las descartadas", ("id_mancha",),
        (
            _ID_MANCHA, _FRAME,
            Col("ha", "float", "ha", "Superficie de la mancha", rango=(0, None)),
            Col("forma", "str", "", "Forma según `insomnio.manchas()`", valores=FORMAS),
            Col("descartada", "str", "", "Motivo del descarte, o null si es candidata", nulo=True, valores=DESCARTES),
            Col("etiqueta", "int", "", "Número de la mancha en la capa `manchas` del índice", rango=(1, None)),
            Col("insomnio", "float", "fracción 0-1", "Media del insomnio por píxel en la mancha", nulo=True, rango=F01),
            Col("persistencia", "float", "fracción 0-1", "Media de la persistencia por píxel", nulo=True, rango=F01),
            Col("eco_db", "float", "dB", "Eco medio de la mancha", nulo=True),
            Col("elongacion", "float", "cociente ≥ 1", "Eje mayor / eje menor", rango=(1, None)),
            Col("nucleo", "float", "fracción 0-1", "Parte de la mancha que sobrevive a una erosión de 1 píxel", rango=F01),
            Col("lat", "float", "grados", "Latitud del centro", opcional=True, rango=(-90, 90)),
            Col("lon", "float", "grados", "Longitud del centro", opcional=True, rango=(-180, 180)),
        ),
    ),
    Contrato(
        "tabla_radar", "salidas/tabla_radar.parquet", "etapa 4", "etapa 6",
        "una mancha candidata (no descartada) de un frame", ("id_mancha",),
        (_ID_MANCHA, _FRAME) + MOVIMIENTO + RUGOSIDAD + FORMA + CONTEXTO,
    ),
    Contrato(
        "insomnio_catalogo", "salidas/insomnio_catalogo.parquet", "etapa 4 (la lógica, el prompt 2)", "etapas 8 y 9",
        "un polígono del catálogo (basural o negativo) en un frame, esté o no en una mancha", ("id_catalogo", "frame"),
        (
            _ID_CATALOGO, _CATALOGO,
            Col("complejo", "str", "", "`CPX-…` de `complejos.json` para los basurales; null para los negativos", nulo=True),
            _FRAME,
            Col("insomnio", "float", "fracción 0-1", "Insomnio del polígono contra su anillo, como `insomnio.ficha()`", nulo=True, rango=F01),
            Col("persistencia", "float", "fracción 0-1", "Mínimo de la fracción despierta en los tres tramos", nulo=True, rango=F01),
            Col("eco_db", "float", "dB", "Mediana del eco en el polígono", nulo=True),
            Col("n_pares", "int", "pares", "Pares GUNW válidos sobre el polígono", rango=(0, None)),
            Col("radar", "str", "", "Lo que dice el radar, con los umbrales de `insomnio.Parametros`", valores=RADAR),
            Col("motivo", "str", "", "Por qué salió ese `radar`", nulo=True, opcional=True),
            Col("area_ha", "float", "ha", "Superficie del polígono según el catálogo", nulo=True, opcional=True, rango=(0, None)),
            Col("estado", "str", "", "Estado del registro (sólo basurales)", nulo=True, opcional=True, valores=ESTADOS),
            Col("clase", "str", "", "Clase del negativo (`aeropuerto`, `cantera`…); null en basurales", nulo=True, opcional=True),
        ),
    ),
    Contrato(
        "tabla_optico", "salidas/tabla_optico.parquet", "etapa 5", "etapa 6",
        "una mancha candidata de un frame", ("id_mancha",),
        (_ID_MANCHA, _FRAME) + OPTICO + _ESCENAS,
    ),
    Contrato(
        "tabla_optico_catalogo", "salidas/tabla_optico_catalogo.parquet", "etapa 5", "etapas 8 y 9 (ficha)",
        "un polígono del catálogo en un frame", ("id_catalogo", "frame"),
        (_ID_CATALOGO, _CATALOGO, _FRAME) + OPTICO + _ESCENAS,
    ),
    Contrato(
        "cruce_manchas_catalogo", "salidas/cruce_manchas_catalogo.parquet", "etapa 6 (`cruce_manchas.py`)", "etapas 6 y 9",
        "un par mancha y polígono del catálogo que se tocan (intersección > 0), sin filtrar por el 30 %",
        ("id_mancha", "id_catalogo"),
        (
            _ID_MANCHA, _ID_CATALOGO, _CATALOGO, _FRAME,
            Col("frac_mancha", "float", "fracción 0-1", "Intersección / área de la mancha", rango=F01),
            Col("frac_poligono", "float", "fracción 0-1", "Intersección / área del polígono", rango=F01),
            Col("frac_area_menor", "float", "fracción 0-1", "Intersección / la menor de las dos áreas (el máximo de las otras dos)", rango=F01),
            Col("complejo", "str", "", "`CPX-…` del basural; null en negativos", nulo=True, opcional=True),
            Col("clase_negativo", "str", "", "Clase del negativo; null en basurales", nulo=True, opcional=True),
        ),
    ),
    Contrato(
        "frames", "catalogos/frames.json", "etapa 2", "etapas 1, 4, 6, 7, 8 y 9",
        "un frame (un área de trabajo cubierta por una o más órbitas de NISAR)", ("frame",),
        (
            _FRAME,
            Col("orbita", "lista_int", "", "Órbitas (tracks) de NISAR que se usan. El AMBA usa dos: `[10, 161]`"),
            Col("ciudad", "str", "", "Ciudad de referencia"),
            Col("pais", "str", "ISO 3166-1 alfa-3", "País, como en los catálogos (`ARG`, `USA`, `IND`)", patron=r"[A-Z]{3}"),
            Col("hemisferio", "str", "", "Hemisferio de la zona UTM", valores=HEMISFERIOS),
            Col("epsg", "int", "", "EPSG de la grilla UTM del producto (326xx norte, 327xx sur)", rango=(32601, 32760)),
            Col("bbox", "caja", "grados", "`[lon_oeste, lat_sur, lon_este, lat_norte]`, como en GeoJSON. OJO: `geo.CAJA` va en otro orden"),
            Col("n_gunw", "int", "pares", "Pares GUNW `PR` disponibles", rango=(0, None)),
            Col("fecha_inicio", "str", "AAAA-MM-DD", "Primera fecha de la serie", patron=PATRON_FECHA),
            Col("fecha_fin", "str", "AAAA-MM-DD", "Última fecha de la serie", patron=PATRON_FECHA),
            Col("n_basurales_10ha", "conteos", "complejos", "Basurales de 10 ha o más por estado, contando cada complejo una vez. Claves: `abierto`, `cerrado`, `desconocido`"),
            Col("n_negativos", "conteos", "polígonos", "Negativos por clase (`aeropuerto`, `cantera`…)"),
            Col("reservado_prueba", "bool", "", "true si queda fuera del entrenamiento (Argentina)"),
            Col("frames_nisar", "lista_str", "", "Track, dirección y frame de cada producto, como en el nombre: `010_D_106`", nulo=True, opcional=True),
        ),
    ),
    Contrato(
        "tabla_entrenamiento", "salidas/tabla_entrenamiento.parquet", "etapa 6 (`armar_tabla.py`)", "etapa 7 y la CNN",
        "una mancha etiquetada de un frame", ("id_mancha",),
        (
            _ID_MANCHA,
            Col("id_catalogo", "str", "", "El polígono con el que se cruza (el de mayor `frac_area_menor`)", patron=PATRON_CATALOGO),
            Col("complejo", "str", "", "`CPX-…` del basural; en los negativos, su propio `id_catalogo`. Sirve para agrupar"),
            _FRAME,
            Col("ciudad", "str", "", "La de `frames.json`"),
            Col("pais", "str", "ISO 3166-1 alfa-3", "El de `frames.json`", patron=r"[A-Z]{3}"),
            Col("clase_negativo", "str", "", "Clase del negativo (`aeropuerto`…); null si es basural", nulo=True),
        ) + MOVIMIENTO + RUGOSIDAD + OPTICO + FORMA + CONTEXTO + CNN + (
            Col("clase", "str", "", "La etiqueta", valores=CLASES),
        ),
    ),
    Contrato(
        "predicciones", "salidas/predicciones.parquet", "etapa 7 (o el mock, mientras no haya modelo)", "etapa 9 (`veredicto.py`)",
        "una mancha candidata de un frame", ("id_mancha",),
        (_ID_MANCHA, _FRAME, Col("p_basural", "float", "probabilidad 0-1", "Probabilidad de `basural_activo` según el modelo", rango=F01)),
    ),
)}

PARTICIONES = "particiones"  # salidas/particiones.json: it's not a table, see `validar_particiones`
RUTA_PARTICIONES = "salidas/particiones.json"
NOMBRES = tuple(CONTRATOS) + (PARTICIONES,)


class ErrorContrato(ValueError):
    """The file doesn't follow the contract. The message lists everything that's wrong."""


def _nombre(nombre):
    n = os.path.splitext(os.path.basename(str(nombre)))[0]
    if n not in NOMBRES:
        raise KeyError(f"No hay un contrato que se llame {n!r}. Los que hay: {', '.join(NOMBRES)}")
    return n


def columnas(nombre):
    """The names of the contract's columns, in order."""
    return CONTRATOS[_nombre(nombre)].nombres


# ------------------------------------------------------------------ validation
def _es_num(v):
    return isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(v, (bool, np.bool_))


def _es_ent(v):
    return isinstance(v, (int, np.integer)) and not isinstance(v, (bool, np.bool_))


def _es_lista(v):
    return isinstance(v, (list, tuple, np.ndarray))


_POR_CELDA = {
    "str": lambda v: isinstance(v, str),
    "float": _es_num,
    "int": _es_ent,
    "bool": lambda v: isinstance(v, (bool, np.bool_)),
    "lista_int": lambda v: _es_lista(v) and len(v) > 0 and all(_es_ent(x) for x in v),
    "lista_str": lambda v: _es_lista(v) and all(isinstance(x, str) for x in v),
    "caja": lambda v: _es_lista(v) and len(v) == 4 and all(_es_num(x) for x in v),
    "conteos": lambda v: isinstance(v, dict) and all(isinstance(k, str) and (x is None or _es_ent(x)) for k, x in v.items()),
}
_DICE = {
    "str": "texto", "float": "número", "int": "entero", "bool": "booleano (true o false)", "lista_int": "lista de enteros",
    "lista_str": "lista de textos", "caja": "lista de 4 números", "conteos": "objeto {clave: entero}",
}


def _nulos(s):
    return s.map(lambda v: v is None or (isinstance(v, (float, np.floating)) and np.isnan(v)) or v is pd.NA or v is pd.NaT)


def _tipo_ok(s, tipo):
    """Is the series (already without nulls) of the type? Returns (ok, example that fails)."""
    if tipo == "float" and pdt.is_numeric_dtype(s) and not pdt.is_bool_dtype(s):
        return True, None
    if tipo == "int" and pdt.is_integer_dtype(s):
        return True, None
    if tipo == "int" and pdt.is_float_dtype(s):
        return False, "la columna es de punto flotante; si tiene vacíos usá el tipo `Int64` de pandas, si no `.astype('int64')`"
    if tipo == "bool" and pdt.is_bool_dtype(s):
        return True, None
    mal = s[~s.map(_POR_CELDA[tipo])]
    return (True, None) if mal.empty else (False, f"por ejemplo {mal.iloc[0]!r} ({type(mal.iloc[0]).__name__})")


def _revisar_columna(s, c, errores):
    nulos = _nulos(s)
    if nulos.any() and not c.nulo:
        errores.append(f"`{c.nombre}`: tiene {int(nulos.sum())} valores vacíos y no puede tener ninguno")
    v = s[~nulos]
    if v.empty:
        return
    ok, ejemplo = _tipo_ok(v, c.tipo)
    if not ok:
        errores.append(f"`{c.nombre}`: tiene que ser {_DICE[c.tipo]}; {ejemplo}")
        return
    if c.valores is not None:
        raros = sorted({x for x in v if x not in c.valores})
        if raros:
            errores.append(f"`{c.nombre}`: valores no permitidos {raros[:5]}. Los permitidos: {list(c.valores)}")
    if c.patron is not None:
        mal = v[~v.map(lambda x: re.fullmatch(c.patron, x) is not None)]
        if not mal.empty:
            errores.append(f"`{c.nombre}`: {len(mal)} valores no tienen el formato `{c.patron}`; por ejemplo {mal.iloc[0]!r}")
    if c.rango is not None and c.tipo in ("float", "int"):
        n = pd.to_numeric(v)
        lo, hi = c.rango
        eps = 1e-6
        fuera = n[(n < lo - eps if lo is not None else False) | (n > hi + eps if hi is not None else False)]
        if not fuera.empty:
            tope = f"entre {lo} y {hi}" if lo is not None and hi is not None else f"mayor o igual que {lo}" if hi is None else f"menor o igual que {hi}"
            errores.append(f"`{c.nombre}` ({c.unidad}): {len(fuera)} valores fuera de rango (tiene que ser {tope}); por ejemplo {fuera.iloc[0]}")


def _coherencia(df, n, errores):
    """Chequeos entre columnas."""
    tiene = lambda *cs: all(c in df.columns for c in cs)  # noqa: E731
    if tiene("id_mancha", "frame"):
        ok = df["id_mancha"].map(lambda x: isinstance(x, str)) & df["frame"].map(lambda x: isinstance(x, str))
        d = df[ok]
        mal = d[[not i.startswith(f"MAN-{f}-") for i, f in zip(d["id_mancha"], d["frame"])]]
        if not mal.empty:
            errores.append(f"`id_mancha` no coincide con `frame` en {len(mal)} filas; por ejemplo "
                           f"{mal['id_mancha'].iloc[0]!r} con frame {mal['frame'].iloc[0]!r}")
    if tiene("id_catalogo", "catalogo"):
        pref = {"basurales": "BAS-", "negativos": "NEG-"}
        mal = [(i, c) for i, c in zip(df["id_catalogo"], df["catalogo"])
               if isinstance(i, str) and c in pref and not i.startswith(pref[c])]
        if mal:
            errores.append(f"`id_catalogo` no coincide con `catalogo` en {len(mal)} filas; por ejemplo {mal[0][0]!r} con {mal[0][1]!r}")
    if n == "frames":
        for _, f in df.iterrows():
            quien = f"frame {f.get('frame')!r}"
            if _es_ent(f.get("epsg")) and f.get("hemisferio") in HEMISFERIOS:
                if ("S" if 32701 <= f["epsg"] <= 32760 else "N") != f["hemisferio"]:
                    errores.append(f"{quien}: el EPSG {f['epsg']} no es del hemisferio {f['hemisferio']} (326xx es norte, 327xx es sur)")
            b = f.get("bbox")
            if _POR_CELDA["caja"](b) and not (-180 <= b[0] < b[2] <= 180 and -90 <= b[1] < b[3] <= 90):
                errores.append(f"{quien}: `bbox` tiene que ser [lon_oeste, lat_sur, lon_este, lat_norte]; vino {list(b)}")
            elif _POR_CELDA["caja"](b) and _es_ent(f.get("epsg")):
                meridiano = (f["epsg"] % 100) * 6 - 183  # the UTM zone's central one
                if abs((b[0] + b[2]) / 2 - meridiano) > 6:
                    errores.append(f"{quien}: el centro del `bbox` {list(b)} queda lejos de la zona UTM del EPSG {f['epsg']} "
                                   f"(meridiano {meridiano}°). ¿Está como [lon_oeste, lat_sur, lon_este, lat_norte]?")
            e = f.get("n_basurales_10ha")
            if isinstance(e, dict) and (set(ESTADOS_FRAME) - set(e) or set(e) - set(ESTADOS)):
                errores.append(f"{quien}: `n_basurales_10ha` tiene que tener las claves {list(ESTADOS_FRAME)} "
                               f"(y, si hace falta, `contradictorio`); vino {sorted(e)}")
            if isinstance(f.get("fecha_inicio"), str) and isinstance(f.get("fecha_fin"), str) and f["fecha_inicio"] > f["fecha_fin"]:
                errores.append(f"{quien}: `fecha_inicio` es posterior a `fecha_fin`")
    if n == "tabla_entrenamiento" and tiene("clase", "id_catalogo", "clase_negativo"):
        esperado = {"basural_activo": "BAS-", "otro_movil": "NEG-"}
        mal = [(i, c) for i, c in zip(df["id_catalogo"], df["clase"]) if isinstance(i, str) and c in esperado and not i.startswith(esperado[c])]
        if mal:
            errores.append(f"`clase` no coincide con `id_catalogo` en {len(mal)} filas; por ejemplo {mal[0][1]!r} con {mal[0][0]!r} "
                           "(`basural_activo` va con `BAS-…` y `otro_movil` con `NEG-…`)")


def validar(df, nombre):
    """Fails with `ErrorContrato` if `df` doesn't follow the `nombre` contract; if it does, returns `df`.

    `nombre` is the file's, with or without folder and extension: "tabla_radar" or "salidas/tabla_radar.parquet".
    For `manchas` pass the properties table (one row per feature) and for `frames` one row per frame;
    `leer()` builds them. For `particiones` pass the JSON dictionary.
    """
    n = _nombre(nombre)
    if n == PARTICIONES:
        return validar_particiones(df)
    c = CONTRATOS[n]
    if not isinstance(df, pd.DataFrame):
        raise ErrorContrato(f"{c.archivo}: se esperaba un DataFrame de pandas y vino {type(df).__name__}")
    errores = []
    faltan = [x for x in c.obligatorias if x not in df.columns]
    if faltan:
        errores.append(f"faltan las columnas {faltan}")
    for col in c.columnas:
        if col.nombre in df.columns:
            _revisar_columna(df[col.nombre], col, errores)
    if all(k in df.columns for k in c.clave):
        rep = df[df.duplicated(list(c.clave), keep=False)]
        if not rep.empty:
            errores.append(f"hay {len(rep)} filas con la clave {list(c.clave)} repetida; por ejemplo {rep[list(c.clave)].iloc[0].tolist()}")
    _coherencia(df, n, errores)
    if errores:
        raise ErrorContrato(f"{c.archivo} no cumple el contrato (ver ../docs/data-contracts.md):\n  - " + "\n  - ".join(errores))
    return df


def validar_particiones(d, frames=None):
    """Validates the content of `particiones.json`. With `frames` (those in the table) it checks they're all there."""
    errores = []
    if not isinstance(d, dict):
        raise ErrorContrato(f"particiones.json: se esperaba un objeto y vino {type(d).__name__}")
    for k in ("meta", "particiones", PRUEBA_FINAL):
        if k not in d:
            errores.append(f"falta la clave `{k}`")
    meta, partes, prueba = d.get("meta", {}), d.get("particiones", {}), d.get(PRUEBA_FINAL, [])
    if not isinstance(meta, dict) or not all(_es_num(meta.get(k)) for k in ("umbral_insomnio", "criterio_cruce")):
        errores.append("`meta` tiene que traer los números `umbral_insomnio` y `criterio_cruce` (los que se usaron para armar la tabla)")
    es_lista_frames = lambda v: isinstance(v, list) and all(isinstance(f, str) and re.fullmatch(PATRON_FRAME, f) for f in v)  # noqa: E731
    if not isinstance(partes, dict) or not all(es_lista_frames(v) and v for v in partes.values()):
        errores.append('`particiones` tiene que ser {"0": ["FRAME", …], "1": […]}, sin particiones vacías')
        partes = {}
    elif len(partes) < 2:
        errores.append(f"hacen falta al menos 2 particiones para validar y hay {len(partes)}")
    if not es_lista_frames(prueba):
        errores.append(f"`{PRUEBA_FINAL}` tiene que ser una lista de frames (puede estar vacía)")
        prueba = []
    todos = [f for v in partes.values() for f in v] + list(prueba)
    repetidos = sorted({f for f in todos if todos.count(f) > 1})
    if repetidos:
        errores.append(f"cada frame va en un solo lugar y están repetidos: {repetidos}")
    if frames is not None:
        faltan, sobran = sorted(set(frames) - set(todos)), sorted(set(todos) - set(frames))
        if faltan:
            errores.append(f"frames de la tabla que no están en ninguna partición: {faltan}")
        if sobran:
            errores.append(f"frames que no están en la tabla: {sobran}")
    if errores:
        raise ErrorContrato("particiones.json no cumple el contrato (ver ../docs/data-contracts.md):\n  - " + "\n  - ".join(errores))
    return d


def particion_por_frame(d):
    """{frame: "0" | "1" | … | "prueba_final"} from the content of `particiones.json`."""
    salida = {f: k for k, v in d["particiones"].items() for f in v}
    salida.update({f: PRUEBA_FINAL for f in d[PRUEBA_FINAL]})
    return salida


# ------------------------------------------------------------------ leer y guardar
def ruta(nombre, carpeta):
    """Where a contract's file is inside `carpeta` (no subfolders: works for `salidas/` and `datos/mock/`)."""
    n = _nombre(nombre)
    return os.path.join(carpeta, os.path.basename(RUTA_PARTICIONES) if n == PARTICIONES else CONTRATOS[n].archivo)


def _leer_json(camino):
    with open(camino, encoding="utf-8") as f:
        return json.load(f)


def _tabla_manchas(geo, archivo="manchas.geojson"):
    feats = geo.get("features") if isinstance(geo, dict) else None
    if not isinstance(geo, dict) or geo.get("type") != "FeatureCollection" or not isinstance(feats, list):
        raise ErrorContrato(f"{archivo}: tiene que ser un FeatureCollection de GeoJSON")
    mal = [i for i, f in enumerate(feats) if (f.get("geometry") or {}).get("type") not in ("Polygon", "MultiPolygon")]
    if mal:
        raise ErrorContrato(f"{archivo}: {len(mal)} features no son Polygon ni MultiPolygon; la primera es la número {mal[0]}")
    for f in feats:
        g = f["geometry"]
        lon, lat = (g["coordinates"][0] if g["type"] == "Polygon" else g["coordinates"][0][0])[0][:2]
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise ErrorContrato(f"{archivo}: las coordenadas van en grados (lon, lat; WGS84), no en UTM; vino ({lon}, {lat})")
    return pd.DataFrame([f.get("properties") or {} for f in feats], columns=None if feats else list(CONTRATOS["manchas"].nombres))


def leer(carpeta_o_archivo, nombre=None):
    """Reads a contract file, validates it and returns it.

    Tables come back as DataFrame; `manchas` as a DataFrame of properties with the `geometry` column
    (each blob's GeoJSON dictionary); `frames` as a DataFrame, one row per frame; `particiones` as a dict.
    """
    camino = carpeta_o_archivo if nombre is None else ruta(nombre, carpeta_o_archivo)
    n = _nombre(camino)
    if n == PARTICIONES:
        return validar_particiones(_leer_json(camino))
    if n == "manchas":
        geo = _leer_json(camino)
        df = validar(_tabla_manchas(geo, camino), n)
        df["geometry"] = [f["geometry"] for f in geo["features"]]
        return df
    if n == "frames":
        d = _leer_json(camino)
        if not isinstance(d, dict) or not isinstance(d.get("frames"), list):
            raise ErrorContrato(f'{camino}: tiene que ser {{"meta": {{…}}, "frames": [ … ]}}')
        return validar(pd.DataFrame(d["frames"], columns=None if d["frames"] else list(CONTRATOS[n].nombres)), n)
    return validar(pd.read_parquet(camino), n)


def guardar(df, nombre, carpeta):
    """Validates a table, puts the contract's columns first and in order, and writes it to parquet. Returns the path."""
    n = _nombre(nombre)
    c = CONTRATOS[n]
    if not c.ruta.endswith(".parquet"):
        raise ValueError(f"{c.archivo} no es una tabla parquet: escribilo como JSON y validalo con `leer()`")
    validar(df, n)
    orden = [x for x in c.nombres if x in df.columns]
    os.makedirs(carpeta, exist_ok=True)
    destino = ruta(n, carpeta)
    df[orden + [x for x in df.columns if x not in orden]].to_parquet(destino, index=False)
    return destino


def main(args):
    if not args:
        print(__doc__)
        return 2
    fallas = 0
    for a in args:
        caminos = [ruta(n, a) for n in NOMBRES] if os.path.isdir(a) else [a]
        for camino in caminos:
            if not os.path.exists(camino):
                continue
            try:
                d = leer(camino)
                print(f"ok     {camino}" + (f"  ({len(d)} filas)" if isinstance(d, pd.DataFrame) else ""))
            except ErrorContrato as e:
                fallas += 1
                print(f"FALLA  {e}")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
