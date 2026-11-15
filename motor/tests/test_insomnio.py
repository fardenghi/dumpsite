"""Caso sintético: cada tipo de superficie tiene que caer donde corresponde.

Correr desde `motor/`:  python -m pytest tests -q
"""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import geo  # noqa: E402
import insomnio as ins  # noqa: E402

PASO = 80.0
P = ins.Parametros()
# 15 pares como los reales: dos órbitas, un par de 24 días y uno de 36.
ORBITAS = np.array([10] * 8 + [161] * 7)
DIAS = np.array([12, 12, 24, 12, 12, 12, 12, 12, 12, 12, 36, 12, 12, 12, 12])
FECHAS = np.array(["2026-07-08", "2026-07-20", "2026-08-13", "2026-08-25", "2026-09-06", "2026-09-18", "2026-09-30", "2026-10-12",
                   "2026-07-07", "2026-07-19", "2026-08-24", "2026-09-05", "2026-09-17", "2026-09-29", "2026-10-11"])
ZONAS = {  # (filas, columnas) en una escena de 200 × 200 píxeles de 80 m
    "ciudad": (slice(20, 50), slice(20, 50)),
    "basural": (slice(90, 105), slice(90, 105)),  # 15 × 15 px = 144 ha
    "agua": (slice(140, 180), slice(20, 60)),
    "campo": (slice(20, 60), slice(130, 180)),
    "ruta": (slice(120, 122), slice(70, 190)),
    "tosquera": (slice(150, 160), slice(120, 130)),  # agua que no está en la máscara
    "basurita": (slice(60, 62), slice(100, 102)),  # 4 px: más chico que lo que se puede medir
}


@pytest.fixture(scope="module")
def escena():
    rng = np.random.default_rng(0)
    forma = (200, 200)
    t = ins.tercios(FECHAS)
    coh = np.empty((len(FECHAS), *forma), dtype=np.float32)
    for i in range(len(FECHAS)):
        c = np.full(forma, 0.70)
        c[ZONAS["basural"]] = 0.25  # siempre despierto
        c[ZONAS["basurita"]] = 0.25
        c[ZONAS["ruta"]] = 0.25
        c[ZONAS["agua"]] = 0.10
        c[ZONAS["tosquera"]] = 0.10
        c[ZONAS["campo"]] = 0.20 if t[i] == 0 else 0.70  # arado sólo en el primer tercio
        c *= {12: 1.0, 24: 0.85, 36: 0.75}[int(DIAS[i])]  # más días, menos coherencia en toda la escena
        coh[i] = np.clip(c + rng.normal(0, 0.05, forma), 0.01, 1)
    eco = np.full((6, *forma), -8.0, dtype=np.float32)
    eco[:, ZONAS["agua"][0], ZONAS["agua"][1]] = -18
    eco[:, ZONAS["tosquera"][0], ZONAS["tosquera"][1]] = -18
    agua = np.zeros(forma, dtype=bool)
    agua[ZONAS["agua"]] = True
    capas = ins.calcular(coh, ORBITAS, DIAS, FECHAS, agua, PASO, P, eco=eco, orbitas_eco=np.array([10, 10, 10, 161, 161, 161]))
    lista, etiquetas = ins.manchas(capas["candidato"], capas, PASO, P)
    return {"coh": coh, "agua": agua, "capas": capas, "manchas": lista, "etiquetas": etiquetas}


def _zona(nombre):
    m = np.zeros((200, 200), dtype=bool)
    m[ZONAS[nombre]] = True
    return m


def _ficha(escena, nombre):
    return ins.ficha(_zona(nombre), escena["coh"], ORBITAS, FECHAS, ~escena["agua"], PASO, P, eco_db=escena["capas"]["eco_db"])


def test_factor_de_separacion(escena):
    fac = escena["capas"]["factor_separacion"]
    assert np.allclose(fac[DIAS == 12], 1)
    assert fac[DIAS == 24][0] == pytest.approx(0.85, abs=0.03)
    assert fac[DIAS == 36][0] == pytest.approx(0.75, abs=0.03)


def test_ciudad_quieta(escena):
    c = escena["capas"]
    assert np.nanmean(c["insomnio"][ZONAS["ciudad"]]) < 0.05
    assert np.nanmean(c["insomnio_abs"][ZONAS["ciudad"]]) < 0.05  # el par de 36 días no la despierta
    assert not c["candidato"][ZONAS["ciudad"]].any()
    assert _ficha(escena, "ciudad")["radar"] == "quieto"


def test_basural_despierto(escena):
    c = escena["capas"]
    assert np.nanmean(c["insomnio"][ZONAS["basural"]]) > 0.9
    assert c["candidato"][ZONAS["basural"]].mean() > 0.8
    f = _ficha(escena, "basural")
    assert f["radar"] == "despierto" and f["insomnio"] == 1.0 and len(f["pares"]) == 15
    assert set(f["insomnio_orbita"]) == {10, 161}


def test_agua_afuera(escena):
    c = escena["capas"]
    assert not c["candidato"][ZONAS["agua"]].any()
    assert np.isnan(c["insomnio"][ZONAS["agua"]]).all()
    en_tosquera = {int(e) for e in np.unique(escena["etiquetas"][ZONAS["tosquera"]]) if e}  # no está en la máscara: la saca el eco
    assert en_tosquera and all(m["descartada"] == "lisa" for m in escena["manchas"] if m["etiqueta"] in en_tosquera)
    assert _ficha(escena, "agua")["radar"] == "no_alcanza"
    assert _ficha(escena, "tosquera")["radar"] == "no_alcanza"


def test_campo_estacional(escena):
    c = escena["capas"]
    assert not c["candidato"][ZONAS["campo"]].any()
    assert np.nanmean(c["persistencia"][ZONAS["campo"]]) < 0.1
    assert _ficha(escena, "campo")["radar"] != "despierto"


def test_manchas(escena):
    buenas = [m for m in escena["manchas"] if not m["descartada"]]
    assert len(buenas) == 1  # sólo el basural
    f, c = buenas[0]["fila"], buenas[0]["columna"]
    assert 90 <= f <= 105 and 90 <= c <= 105 and buenas[0]["forma"] == "compacta"
    en_ruta = {int(e) for e in np.unique(escena["etiquetas"][ZONAS["ruta"]]) if e}
    assert all(m["descartada"] for m in escena["manchas"] if m["etiqueta"] in en_ruta)


def test_sitio_chico_no_alcanza(escena):
    assert _ficha(escena, "basurita")["radar"] == "no_alcanza"


def test_geo_ida_y_vuelta():
    x, y = geo.utm(-34.6037, -58.3816)
    assert (x, y) == pytest.approx((373317.5, 6170036.2), abs=0.1)
    assert geo.latlon(x, y) == pytest.approx((-34.6037, -58.3816), abs=1e-6)
    xs, ys = geo.grilla(80.0)
    m = geo.mascara_poligonos([geo.caja_a_anillo((-34.59, -34.575, -58.43, -58.41))], xs, ys)
    assert m.sum() * 0.64 == pytest.approx(1.665 * 1.834 * 100, rel=0.05)  # ha de la caja
