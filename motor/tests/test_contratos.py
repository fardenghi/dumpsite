"""The mock follows the contracts, and `validar` fails with a clear message when something doesn't.

Run from `motor/`:  python -m pytest tests -q
"""
import json
import os
import sys

import pandas as pd
import pytest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
import contratos as ct  # noqa: E402
import contratos_mock  # noqa: E402

DOC = os.path.join(AQUI, "..", "..", "docs", "contratos-datos.md")


@pytest.fixture(scope="module")
def mock(tmp_path_factory):
    carpeta = str(tmp_path_factory.mktemp("mock"))
    contratos_mock.generar(carpeta)
    return carpeta


@pytest.fixture()
def radar(mock):
    return ct.leer(mock, "tabla_radar")


def test_el_mock_genera_todos_los_archivos_y_cumplen(mock):
    for nombre in ct.NOMBRES:
        assert os.path.exists(ct.ruta(nombre, mock)), nombre
        d = ct.leer(mock, nombre)  # validates on read
        if isinstance(d, pd.DataFrame):
            assert 4 <= len(d) <= 80, f"{nombre}: {len(d)} filas"
    assert ct.main([mock]) == 0


def test_el_mock_es_coherente_entre_archivos(mock):
    t = {n: ct.leer(mock, n) for n in ct.NOMBRES}
    manchas, frames = t["manchas"], t["frames"]
    assert "AMBA" in set(frames["frame"]) and set(manchas["frame"]) == set(frames["frame"])
    candidatas = set(manchas.loc[manchas["descartada"].isna(), "id_mancha"])
    assert set(manchas["descartada"].dropna()) == set(ct.DESCARTES)
    for n in ("tabla_radar", "tabla_optico", "predicciones"):
        assert set(t[n]["id_mancha"]) == candidatas, n
    assert set(t["cruce_manchas_catalogo"]["id_mancha"]) <= candidatas
    assert set(t["cruce_manchas_catalogo"]["id_catalogo"]) <= set(t["insomnio_catalogo"]["id_catalogo"])
    assert set(t["tabla_optico_catalogo"]["id_catalogo"]) == set(t["insomnio_catalogo"]["id_catalogo"])
    # the area is the same in the geojson and in the radar table
    ha = manchas.set_index("id_mancha")["ha"]
    assert (t["tabla_radar"].set_index("id_mancha")["area_ha"] == ha.loc[t["tabla_radar"]["id_mancha"]]).all()

    # the training table follows the stage 6 rule
    ent, cruce = t["tabla_entrenamiento"], t["cruce_manchas_catalogo"]
    fuerte = cruce[cruce["frac_area_menor"] >= ct.CRITERIO_CRUCE]
    catalogos = fuerte.groupby("id_mancha")["catalogo"].nunique()
    assert set(ent["id_mancha"]) == set(catalogos[catalogos == 1].index)
    assert (catalogos == 2).any(), "tiene que haber una mancha que toca los dos catálogos y queda afuera"
    assert (cruce["frac_area_menor"] < ct.CRITERIO_CRUCE).any(), "tiene que haber un cruce que no llega al 30 %"
    assert set(ent["clase"]) == set(ct.CLASES)
    assert set(ct.COLUMNAS_MODELO) <= set(ent.columns)

    # partitions: by frame, and Argentina separate
    partes = t["particiones"]
    ct.validar_particiones(partes, frames=list(frames["frame"]))
    por_frame = ct.particion_por_frame(partes)
    for _, f in frames.iterrows():
        assert (por_frame[f["frame"]] == ct.PRUEBA_FINAL) == bool(f["reservado_prueba"])
    assert por_frame["AMBA"] == ct.PRUEBA_FINAL


def test_el_mock_trae_los_casos_del_amba(mock):
    cat = ct.leer(mock, "insomnio_catalogo").set_index("id_catalogo")
    assert cat.loc["BAS-000007", ["estado", "radar"]].tolist() == ["cerrado", "quieto"]  # Luján
    assert cat.loc["BAS-053304", ["estado", "radar", "insomnio"]].tolist() == ["abierto", "despierto", 0.86]  # Norte III
    amba = cat[cat["frame"] == "AMBA"]
    assert not ((amba["estado"] == "cerrado") & (amba["radar"] == "despierto")).any()  # there are none in the real AMBA
    assert ((cat["estado"] == "cerrado") & (cat["radar"] == "despierto")).any()  # but the case exists to test the verdict


def test_el_mock_es_reproducible(mock, tmp_path):
    contratos_mock.generar(str(tmp_path))
    for n in ("tabla_radar", "tabla_entrenamiento", "insomnio_catalogo"):
        pd.testing.assert_frame_equal(ct.leer(mock, n), ct.leer(str(tmp_path), n))


def test_el_mock_acepta_mas_manchas(tmp_path):
    contratos_mock.generar(str(tmp_path), manchas_por_frame=40, semilla=1)
    assert len(ct.leer(str(tmp_path), "tabla_entrenamiento")) > 100


@pytest.mark.parametrize("romper, dice", [
    (lambda d: d.drop(columns=["eco_db"]), "faltan las columnas ['eco_db']"),
    (lambda d: d.assign(insomnio=d["insomnio"].astype(str)), "`insomnio`: tiene que ser número"),
    (lambda d: d.assign(n_pares=d["n_pares"].astype(float)), "`n_pares`: tiene que ser entero"),
    (lambda d: d.assign(insomnio=1.5), "`insomnio` (fracción 0-1)"),
    (lambda d: d.assign(insomnio=None), "`insomnio`: tiene"),
    (lambda d: pd.concat([d, d.head(1)]), "clave ['id_mancha'] repetida"),
    (lambda d: d.assign(id_mancha=d["id_mancha"].str.replace("MAN-", "mancha_")), "`id_mancha`"),
    (lambda d: d.assign(frame="OTRO"), "`id_mancha` no coincide con `frame`"),
])
def test_validar_dice_que_esta_mal(radar, romper, dice):
    with pytest.raises(ct.ErrorContrato) as e:
        ct.validar(romper(radar), "tabla_radar")
    assert dice in str(e.value)
    assert "tabla_radar.parquet" in str(e.value)


def test_validar_junta_todos_los_errores_y_deja_pasar_columnas_de_mas(radar, mock):
    with pytest.raises(ct.ErrorContrato) as e:
        ct.validar(radar.drop(columns=["hv_hh"]).assign(persistencia=-1.0), "salidas/tabla_radar.parquet")
    assert "hv_hh" in str(e.value) and "persistencia" in str(e.value)
    ct.validar(radar.assign(columna_mia=1), "tabla_radar")
    vacios = radar.assign(eco_db=None, hv_hh=float("nan"))  # the ones that may be empty
    ct.validar(vacios, "tabla_radar")
    cat = ct.leer(mock, "insomnio_catalogo")
    with pytest.raises(ct.ErrorContrato, match="valores no permitidos"):
        ct.validar(cat.assign(radar="dormido"), "insomnio_catalogo")
    ct.validar(cat.drop(columns=["motivo", "estado", "clase", "area_ha"]), "insomnio_catalogo")  # the optional ones may be missing
    with pytest.raises(KeyError, match="No hay un contrato"):
        ct.validar(radar, "tabla_rara")


def test_validar_frames_y_particiones(mock):
    frames = ct.leer(mock, "frames")
    with pytest.raises(ct.ErrorContrato, match="no es del hemisferio"):
        ct.validar(frames.assign(hemisferio="N"), "frames")
    al_reves = frames.assign(bbox=[[b[1], b[0], b[3], b[2]] for b in frames["bbox"]])  # (lat, lon) en vez de (lon, lat)
    with pytest.raises(ct.ErrorContrato, match="lon_oeste, lat_sur"):
        ct.validar(al_reves.head(1), "frames")
    with pytest.raises(ct.ErrorContrato, match="n_basurales_10ha"):
        ct.validar(frames.assign(n_basurales_10ha=[{"abierto": 1}] * len(frames)), "frames")

    p = ct.leer(mock, "particiones")
    with pytest.raises(ct.ErrorContrato, match="repetidos"):
        ct.validar({**p, ct.PRUEBA_FINAL: ["AMBA", "DELHI"]}, "particiones")
    with pytest.raises(ct.ErrorContrato, match="no están en ninguna partición"):
        ct.validar_particiones(p, frames=list(frames["frame"]) + ["LAGOS"])
    with pytest.raises(ct.ErrorContrato, match="al menos 2 particiones"):
        ct.validar({**p, "particiones": {"0": ["DELHI"]}}, "particiones")


def test_manchas_en_utm_o_sin_poligono_fallan(mock, tmp_path):
    with open(ct.ruta("manchas", mock), encoding="utf-8") as f:
        geo = json.load(f)
    destino = ct.ruta("manchas", str(tmp_path))
    for romper, dice in (
        (lambda g: g["features"][0]["geometry"]["coordinates"][0].__setitem__(0, [373317.5, 6170036.2]), "en grados"),
        (lambda g: g["features"][0].__setitem__("geometry", {"type": "Point", "coordinates": [-58.4, -34.6]}), "Polygon"),
    ):
        roto = json.loads(json.dumps(geo))
        romper(roto)
        with open(destino, "w", encoding="utf-8") as f:
            json.dump(roto, f)
        with pytest.raises(ct.ErrorContrato, match=dice):
            ct.leer(destino)


def test_el_documento_nombra_todos_los_archivos_y_columnas():
    with open(DOC, encoding="utf-8") as f:
        doc = f.read()
    for c in ct.CONTRATOS.values():
        assert f"`{c.ruta}`" in doc, c.ruta
        for col in c.columnas:
            assert f"`{col.nombre}`" in doc, f"{c.archivo}: falta `{col.nombre}` en contratos-datos.md"
    assert f"`{ct.RUTA_PARTICIONES}`" in doc
