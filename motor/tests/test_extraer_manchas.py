"""Etapa 4: de las manchas en píxeles a polígonos, la tabla de radar y el insomnio del catálogo. Sintético y sin red.

Correr desde `herramientas/`:  python -m pytest tests -q
"""
import argparse
import json
import os
import sys

import numpy as np
import pandas as pd
import pytest
from scipy import ndimage

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import contratos  # noqa: E402
import extraer_manchas as em  # noqa: E402
import geo  # noqa: E402
import insomnio as ins  # noqa: E402
import pipeline_insomnio as pl  # noqa: E402


def _mascara(texto):
    return np.array([[c == "#" for c in fila] for fila in texto.split()])


@pytest.mark.parametrize("texto, exteriores, agujeros", [
    ("#", 1, 0), ("## ##", 1, 0), ("### #.# ###", 1, 1),
    ("##. #.# ###", 1, 1),  # el agujero toca el exterior en un vértice
    ("#.. ##. .## ..#", 1, 0), ("###. #.## ##.# .###", 1, 2),
])
def test_contornos(texto, exteriores, agujeros):
    m = _mascara(texto)
    ext, agu = em.contornos(m)
    assert (len(ext), len(agu)) == (exteriores, agujeros)
    assert sum(a for a, _ in ext) - sum(a for a, _ in agu) == m.sum()  # el área de los anillos es la de los píxeles


def test_contornos_al_azar():
    rng = np.random.default_rng(0)
    for _ in range(60):
        etiquetas, n = ndimage.label(rng.random((12, 12)) < 0.55)
        for i in range(1, n + 1):
            m = etiquetas == i
            ext, agu = em.contornos(m)
            assert sum(a for a, _ in ext) - sum(a for a, _ in agu) == pytest.approx(m.sum())
            for _, v in ext + agu:
                assert len({tuple(x) for x in v.tolist()}) == len(v)  # anillos simples: ningún vértice repetido


def test_geometria_en_el_mapa():
    fr = geo.frame_de_caja("LA", [-118.75, 33.85, -117.75, 34.50], epsg=32611)
    xs, ys = fr.grilla(80.0)
    m = _mascara("#### #..# ####")  # 10 píxeles y un agujero de 2
    geom, perimetro = em.geometria(m, 400, 500, xs, ys, fr)
    assert geom["type"] == "Polygon" and len(geom["coordinates"]) == 2 and perimetro == (14 + 6) * 80
    exterior = np.array(geom["coordinates"][0])
    assert (exterior[0] == exterior[-1]).all() and len(exterior) == 5
    ha, (lat, lon) = geo.area_y_centro(exterior[:-1])
    assert ha == pytest.approx(12 * 0.64, rel=1e-3)  # el rectángulo de 4 × 3 píxeles de 80 m
    assert fr.latlon(xs[501] + 40, ys[401]) == pytest.approx((lat, lon), abs=1e-5)  # centrado donde están los píxeles
    x, y = exterior[:-1, 0], exterior[:-1, 1]
    assert (x * np.roll(y, -1) - np.roll(x, -1) * y).sum() > 0  # exterior antihorario, como pide GeoJSON


@pytest.fixture(scope="module")
def frame_sintetico(tmp_path_factory):
    """Un frame del hemisferio norte con recortes inventados: un relleno siempre despierto, un aeródromo quieto y campo."""
    base = tmp_path_factory.mktemp("etapa4")
    caja = [-118.32, 33.98, -118.20, 34.08]
    fr = geo.frame_de_caja("SINTE", caja, epsg=32611)
    xs, ys = fr.grilla(80.0)
    forma = (len(ys), len(xs))
    relleno = np.zeros(forma, dtype=bool)
    relleno[60:80, 50:75] = True  # 500 píxeles = 320 ha
    rng = np.random.default_rng(1)
    recortes = base / "salidas" / "SINTE" / "recortes_80m"
    recortes.mkdir(parents=True)
    fechas = ["20260601", "20260613", "20260625", "20260707", "20260719", "20260731", "20260812", "20260824", "20260905"]
    for orbita in (34, 13):
        for a, b in zip(fechas, fechas[1:]):
            coh = np.clip(0.70 + rng.normal(0, 0.03, forma), 0.01, 1).astype(np.float32)
            coh[relleno] = 0.25
            np.savez_compressed(recortes / f"gunw_{orbita:03d}_019_{a}_{b}_80m.npz", valor=coh.astype(np.float16), tipo="coherencia",
                                orbita=orbita, frame_nisar=19, fecha_ref=a, fecha_sec=b, producto=f"GUNW {orbita} {a}", epsg=32611, epsg_producto=32611)
        for a in fechas[:4]:
            for prefijo, tipo, valor in (("gcov", "eco_db", -8.0), ("gcovhv", "eco_hv_db", -15.0)):
                eco = np.full(forma, valor + (2.0 if prefijo == "gcov" else 0.0), dtype=np.float32)
                eco[relleno] = valor  # el relleno devuelve 2 dB menos que su entorno en HH
                np.savez_compressed(recortes / f"{prefijo}_{orbita:03d}_019_{a}_{a}_80m.npz", valor=eco.astype(np.float16), tipo=tipo,
                                    orbita=orbita, frame_nisar=19, fecha_ref=a, fecha_sec=a, producto=f"GCOV {orbita} {a}", epsg=32611, epsg_producto=32611)
    fijos = base / "fijos" / "SINTE"
    fijos.mkdir(parents=True)
    agua = np.zeros(forma, dtype=np.uint8)
    agua[:, :10] = 100  # una franja de agua al oeste
    np.savez_compressed(fijos / "agua_jrc_80m.npz", ocurrencia=agua)
    np.savez_compressed(fijos / "worldcover_80m.npz", urbano=np.full(forma, 60, dtype=np.uint8), cultivo=np.full(forma, 10, dtype=np.uint8))
    (fijos / "usos_osm.json").write_text(json.dumps({"usos": []}))

    def poligono(filas, cols):  # el contorno de un bloque de píxeles, en lon/lat
        esquinas = [(cols[0], filas[0]), (cols[1], filas[0]), (cols[1], filas[1]), (cols[0], filas[1])]
        lat, lon = fr.latlon(np.array([xs[0] + (c - 0.5) * 80 for c, _ in esquinas]), np.array([ys[0] - (f - 0.5) * 80 for _, f in esquinas]))
        return [[float(a), float(b)] for a, b in zip(lon, lat)]

    (fijos / "catalogo.json").write_text(json.dumps({"poligonos": [
        {"id": "BAS-000001", "catalogo": "basurales", "nombre": "Relleno de prueba", "estado": "cerrado", "complejo": "CPX-000001",
         "estado_complejo": "cerrado", "area_ha": 320.0, "anillos": [poligono((60, 80), (50, 75))]},
        {"id": "NEG-000001", "catalogo": "negativos", "nombre": "Aeródromo de prueba", "clase": "aeropuerto", "area_ha": 256.0,
         "anillos": [poligono((20, 40), (90, 110))]},
        {"id": "NEG-000002", "catalogo": "negativos", "nombre": "Silo", "clase": "acopio", "area_ha": 2.6, "anillos": [poligono((100, 102), (30, 32))]},
    ]}))
    (base / "salidas" / "SINTE" / "frame.json").write_text(json.dumps(fr.dict()))
    a = argparse.Namespace(frame=["SINTE"], caja=caja, epsg=32611, datos="", salida=str(base / "salidas"), fijos=str(base / "fijos"), web="",
                           orbitas=None, desde=None, hasta=None, capa="80m", sin_catalogos=False)
    return base, pl.preparar(a, "SINTE"), relleno


def test_extraer_un_frame(frame_sintetico):
    base, a, relleno = frame_sintetico
    destino = base / "destino"
    r = em.extraer(a, ins.Parametros(), str(destino / "SINTE"))
    assert r["candidatas"] == 1 and r["pares"] == 16

    manchas = contratos.leer(str(destino / "SINTE"), "manchas")  # valida contra el contrato
    candidatas = manchas[manchas["descartada"].isna()]
    assert list(candidatas["id_mancha"]) == ["MAN-SINTE-0001"] and candidatas["ha"].iloc[0] == pytest.approx(relleno.sum() * 0.64, rel=0.1)
    ha, (lat, lon) = geo.area_y_centro(candidatas["geometry"].iloc[0]["coordinates"][0][:-1])
    assert ha == pytest.approx(candidatas["ha"].iloc[0], rel=0.01)  # el polígono mide lo que dicen los píxeles
    assert (lat, lon) == pytest.approx((candidatas["lat"].iloc[0], candidatas["lon"].iloc[0]), abs=1e-3)
    assert candidatas["clase_osm"].iloc[0] == "relleno_osm" and candidatas["que"].iloc[0] == "BAS-000001"

    t = contratos.leer(str(destino / "SINTE"), "tabla_radar")
    assert len(t) == 1
    f = t.iloc[0]
    assert f["insomnio"] == 1.0 and f["persistencia"] == 1.0 and f["n_pares"] == 16 and f["n_orbitas"] == 2
    assert f["contraste_mediana"] == pytest.approx(0.25 / 0.70, abs=0.02) and f["contraste_desvio"] < 0.02
    assert f["eco_db"] == pytest.approx(-8.0, abs=0.01) and f["eco_contraste"] == pytest.approx(-2.0, abs=0.01)
    assert f["hv_hh"] == pytest.approx(-7.0, abs=0.01) and f["eco_variacion"] == pytest.approx(0.0, abs=0.01)
    assert f["urbano_anillo"] == pytest.approx(0.60) and f["cultivo_anillo"] == pytest.approx(0.10) and f["agua_anillo"] == 0.0
    assert abs(f["tendencia"]) < 1e-3 and 0.3 < f["compacidad"] <= 1.0 and f["area_ha"] == candidatas["ha"].iloc[0]

    c = contratos.leer(str(destino / "SINTE"), "insomnio_catalogo").set_index("id_catalogo")
    assert c.loc["BAS-000001", "radar"] == "despierto" and c.loc["BAS-000001", "insomnio"] == 1.0  # figura cerrado y está despierto
    assert c.loc["NEG-000001", "radar"] == "quieto" and c.loc["NEG-000001", "insomnio"] == 0.0  # no formó mancha y se mide igual
    assert c.loc["NEG-000002", "radar"] == "no_alcanza" and "menos de 10 ha" in c.loc["NEG-000002", "motivo"]
    assert c.loc["BAS-000001", "complejo"] == "CPX-000001" and c.loc["NEG-000001", "clase"] == "aeropuerto"

    em.juntar(str(destino), str(destino), 5.0)
    juntas = contratos.leer(str(destino), "manchas")
    assert set(juntas["id_mancha"]) >= {"MAN-SINTE-0001"} and (juntas["frame"] == "SINTE").all()
    assert not ((juntas["descartada"] == "chica") & (juntas["ha"] < 5)).any()
    assert len(contratos.leer(str(destino), "tabla_radar")) == 1 and len(contratos.leer(str(destino), "insomnio_catalogo")) == 3
    assert isinstance(pd.read_parquet(destino / "tabla_radar.parquet"), pd.DataFrame)
