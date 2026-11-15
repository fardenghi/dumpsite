"""Prompt 3: blobs as polygons, cross with the catalog, optical, table and training.

Run from `motor/`:  python -m pytest tests -q
They don't use the network: the optical part is tested with synthetic bands.
"""
import json
import os
import sys

import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
import armar_tabla  # noqa: E402
import contratos as ct  # noqa: E402
import contratos_mock  # noqa: E402
import cruce_manchas  # noqa: E402
import entrenar  # noqa: E402
import extraer_optico as eo  # noqa: E402
import manchas_vectorizar  # noqa: E402


@pytest.fixture(scope="module")
def mock(tmp_path_factory):
    carpeta = str(tmp_path_factory.mktemp("mock"))
    contratos_mock.generar(carpeta, manchas_por_frame=30)
    return carpeta


# ------------------------------------------------------------------ manchas
def test_vectorizar_un_indice_sintetico(tmp_path):
    paso, n = 80.0, 60
    xs = 370000 + paso / 2 + paso * np.arange(n)
    ys = 6170000 - paso / 2 - paso * np.arange(n)
    cand = np.zeros((n, n), bool)
    cand[10:30, 10:30] = True  # 400 px = 256 ha
    cand[40:42, 40:42] = True  # 4 px = 2,56 ha: chica
    capa = np.where(cand, 0.9, 0.1).astype(np.float16)
    np.savez(tmp_path / "i.npz", insomnio=capa, persistencia=capa, eco_db=np.full((n, n), -9, np.float16),
             candidato=cand, xs=xs, ys=ys)
    fc = manchas_vectorizar.armar(str(tmp_path / "i.npz"), "PRUEBA", 32721)
    props = [f["properties"] for f in fc["features"]]
    assert [p["id_mancha"] for p in props] == ["MAN-PRUEBA-0001", "MAN-PRUEBA-0002"]
    assert props[0]["ha"] == 256.0 and props[0]["descartada"] is None
    assert props[1]["descartada"] == "chica"
    from catalogo_poligonos import a_utm
    from shapely.geometry import shape
    assert a_utm(shape(fc["features"][0]["geometry"]), 32721).area / 1e4 == pytest.approx(256, rel=1e-3)
    camino = tmp_path / "manchas.geojson"
    camino.write_text(json.dumps(fc))
    ct.leer(str(camino))


# ------------------------------------------------------------------ cruce
def test_cruce_mide_las_fracciones_en_metros():
    m = box(-58.60, -34.60, -58.59, -34.59)  # ~0,9 × 1,1 km
    mitad = box(-58.595, -34.60, -58.58, -34.59)  # overlaps the east half of the blob and is larger
    lejos = box(-58.50, -34.50, -58.49, -34.49)
    pol = [{"id_catalogo": "BAS-1", "catalogo": "basurales", "complejo": "CPX-1", "clase": None, "geom": mitad},
           {"id_catalogo": "NEG-1", "catalogo": "negativos", "complejo": None, "clase": "cantera", "geom": lejos}]
    df = cruce_manchas.cruzar([({"id_mancha": "MAN-X-0001", "frame": "X"}, m)], pol, lambda f, l: 32721)
    assert list(df["id_catalogo"]) == ["BAS-1"]
    r = df.iloc[0]
    assert r["frac_mancha"] == pytest.approx(0.5, abs=0.01)
    assert r["frac_poligono"] == pytest.approx(1 / 3, abs=0.01)
    assert r["frac_area_menor"] == pytest.approx(0.5, abs=0.01)
    ct.validar(df, "cruce_manchas_catalogo")


def test_el_cruce_del_mock_coincide_con_el_del_mock(mock):
    with open(ct.ruta("manchas", mock), encoding="utf-8") as fh:
        ms = cruce_manchas.cp.manchas(json.load(fh))
    pol = cruce_manchas._catalogo_archivo(os.path.join(mock, "catalogo_mock.geojson"))
    cajas = []

    def cargar(bbox):  # called once per frame, with that frame's box
        cajas.append(bbox)
        return pol
    df, _ = cruce_manchas.cruzar_por_frame(ms, {}, cargar)
    assert len(cajas) == len({p["frame"] for p, _ in ms}) == 4
    esperado = ct.leer(mock, "cruce_manchas_catalogo")
    ok = lambda d: set(map(tuple, d[d.frac_area_menor >= ct.CRITERIO_CRUCE][["id_mancha", "id_catalogo"]].values))  # noqa: E731
    assert ok(df) == ok(esperado)


# ------------------------------------------------------------------ etiquetas
def test_etiquetar_sigue_las_reglas_de_la_etapa_6():
    c = pd.DataFrame([
        ("MAN-A-0001", "BAS-1", "basurales", 0.9, 50.0, "CPX-1", None),   # dump site only
        ("MAN-A-0002", "NEG-1", "negativos", 0.8, 40.0, None, "aeropuerto"),  # negative only
        ("MAN-A-0003", "BAS-2", "basurales", 0.6, 30.0, "CPX-2", None),   # both: not included
        ("MAN-A-0003", "NEG-2", "negativos", 0.5, 20.0, None, "cantera"),
        ("MAN-A-0004", "BAS-3", "basurales", 0.2, 10.0, "CPX-3", None),   # less than 30 %: not included
        ("MAN-A-0005", "BAS-4", "basurales", 0.9, 0.6, "CPX-4", None),    # tiny polygon: not included
        ("MAN-A-0006", "NEG-3", "negativos", 0.1, 2.0, None, "obra"),     # roza uno y cubre otro
        ("MAN-A-0006", "NEG-4", "negativos", 0.7, 9.0, None, "obra"),
    ], columns=["id_mancha", "id_catalogo", "catalogo", "frac_area_menor", "inter_ha", "complejo", "clase_negativo"])
    e = armar_tabla.etiquetar(c).set_index("id_mancha")
    assert set(e.index) == {"MAN-A-0001", "MAN-A-0002", "MAN-A-0006"}
    assert e.loc["MAN-A-0001", "clase"] == "basural_activo" and e.loc["MAN-A-0001", "complejo"] == "CPX-1"
    assert e.loc["MAN-A-0002", "clase"] == "otro_movil" and e.loc["MAN-A-0002", "complejo"] == "NEG-1"
    assert e.loc["MAN-A-0006", "id_catalogo"] == "NEG-4"
    sin_minimo = armar_tabla.etiquetar(c, min_inter_ha=0)
    assert "MAN-A-0005" in set(sin_minimo["id_mancha"])


def test_repartir_equilibra_y_no_parte_frames():
    g = armar_tabla.repartir({"A": 10, "B": 9, "C": 2, "D": 1}, 2)
    assert sorted(f for v in g.values() for f in v) == ["A", "B", "C", "D"]
    cargas = sorted(sum({"A": 10, "B": 9, "C": 2, "D": 1}[f] for f in v) for v in g.values())
    assert cargas == [11, 11]


# ------------------------------------------------------------------ optical
def test_indices_y_resumen_opticos():
    def dn(r):
        return np.full((4, 4), int(r * 10000 + 1000), np.uint16)
    bandas = {"B02": dn(0.05), "B03": dn(0.08), "B04": dn(0.06), "B08": dn(0.30), "B11": dn(0.20), "B12": dn(0.10),
              "SCL": np.full((4, 4), 4, np.uint8)}
    ind = eo.indices(bandas, offset=1000)
    assert ind["ndvi"][0, 0] == pytest.approx((0.30 - 0.06) / 0.36, abs=1e-3)
    assert ind["ndwi"][0, 0] == pytest.approx((0.08 - 0.30) / 0.38, abs=1e-3)
    assert ind["bsi"][0, 0] == pytest.approx((0.26 - 0.35) / 0.61, abs=1e-3)
    medidas = [{"fecha": f"2026-07-{d:02d}", "valido": 1.0, "ndvi": v, "ndvi_aro": 0.5, "bsi": 0.1, "bsi_aro": 0.0,
                "ndwi": -0.5, "ndwi_aro": -0.4, "b11": 0.2, "b11_aro": 0.1, "b12": 0.1, "b12_aro": 0.1}
               for d, v in zip(range(1, 11), np.linspace(0.2, 0.4, 10))]
    r = eo.resumir(medidas)
    assert r["n_escenas"] == eo.MAX_ESCENAS
    assert r["fechas"].count(",") == eo.MAX_ESCENAS - 1
    assert r["ndvi_contraste"] == pytest.approx(r["ndvi_media"] - 0.5)
    assert r["bsi_contraste"] == pytest.approx(0.1)
    assert eo.resumir([])["n_escenas"] == 0


def test_mascaras_del_anillo_excluyen_la_geometria_y_lo_excluido():
    from rasterio.transform import from_origin
    t = from_origin(0, 4000, 20, 20)
    g = box(1800, 1800, 2200, 2200)
    excl = box(0, 0, 1000, 4000)
    adentro, aro = eo.mascaras(g, excl, (200, 200), t)
    assert adentro.sum() == 400
    assert not (adentro & aro).any()
    assert not aro[:, :50].any()  # the excluded strip (x < 1000 m)
    assert aro.sum() > 0


# ------------------------------------------------------------------ end to end with the mock
def test_de_punta_a_punta_con_el_mock(mock, tmp_path):
    radar, optico = ct.leer(mock, "tabla_radar"), ct.leer(mock, "tabla_optico")
    cruce = ct.leer(mock, "cruce_manchas_catalogo")
    frames = armar_tabla.leer_frames(ct.ruta("frames", mock))
    t, partes = armar_tabla.armar(radar, optico, cruce, frames)
    ct.validar(t, "tabla_entrenamiento")
    ct.validar_particiones(partes, frames=sorted(set(t["frame"])))
    assert partes["prueba_final"] == ["AMBA"]
    esperado = ct.leer(mock, "tabla_entrenamiento")
    assert set(t["id_mancha"]) == set(esperado["id_mancha"])

    todas = radar.merge(optico.drop(columns=["frame", "n_escenas", "fechas"]), on="id_mancha", how="left")
    final, res, pred = entrenar.correr(t, partes, todas=todas)
    assert res["validacion"] == "por_frame" and res["advertencia"] is None
    assert set(res["fuera_de_particion"]["por_frame"]) == set(t["frame"]) - {"AMBA"}
    assert set(res["prueba_final"]) == {"AMBA"}
    assert res["importancia"] and res["errores_por_clase_negativo"]
    ct.validar(pred, "predicciones")
    assert len(pred) == len(radar)
    final.booster_.save_model(str(tmp_path / "modelo.txt"))
    json.dumps(res)  # it can be written


def test_humo_con_un_solo_frame(mock):
    t = ct.leer(mock, "tabla_entrenamiento")
    t = t[t["frame"] == "DELHI"].copy()
    partes = {"meta": {"umbral_insomnio": 0.7, "criterio_cruce": 0.3}, "particiones": {}, "prueba_final": ["DELHI"]}
    with pytest.raises(SystemExit):
        entrenar.correr(t, partes)
    _, res, _ = entrenar.correr(t, partes, humo=True)
    assert res["validacion"] == "humo_por_complejo" and "NO reportar" in res["advertencia"]
