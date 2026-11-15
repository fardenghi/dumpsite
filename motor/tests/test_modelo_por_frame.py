"""Prompt 4: `modelo_por_frame.py` (cruce y óptico frame por frame, juntar) y los controles de `entrenar.py`.

Correr desde `motor/`:  python -m pytest tests -q
No usan la red: el óptico no se llama y las fechas se prueban con escenas inventadas.
"""
import json
import os
import shutil
import sys

import pandas as pd
import pytest
from shapely.geometry import box

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
import armar_tabla  # noqa: E402
import contratos as ct  # noqa: E402
import contratos_mock  # noqa: E402
import entrenar  # noqa: E402
import extraer_optico as eo  # noqa: E402
import modelo_por_frame as mpf  # noqa: E402


@pytest.fixture(scope="module")
def mock(tmp_path_factory):
    carpeta = str(tmp_path_factory.mktemp("mock"))
    contratos_mock.generar(carpeta, manchas_por_frame=30)
    return carpeta


@pytest.fixture()
def base(mock, tmp_path):
    """Una carpeta por frame, como las deja la etapa 4, armada desde el mock."""
    with open(os.path.join(mock, "manchas.geojson"), encoding="utf-8") as fh:
        fc = json.load(fh)
    for frame in ("DELHI", "CDMX"):
        os.makedirs(tmp_path / frame)
        sub = {"type": "FeatureCollection", "features": [f for f in fc["features"] if f["properties"]["frame"] == frame]}
        with open(tmp_path / frame / "manchas.geojson", "w", encoding="utf-8") as fh:
            json.dump(sub, fh)
    return str(tmp_path)


def _cruce_mock(mock, monkeypatch):
    import cruce_manchas as cm
    cat = cm._catalogo_archivo(os.path.join(mock, "catalogo_mock.geojson"))
    monkeypatch.setattr(mpf.cp, "catalogo", lambda bbox, *a: [p for p in cat if p["geom"].intersects(box(*bbox))])


def test_cruce_por_frame_y_estado(base, mock, monkeypatch):
    _cruce_mock(mock, monkeypatch)
    carpeta = os.path.join(base, "DELHI")
    assert mpf.falta(carpeta, "cruce", ["cruce_manchas_catalogo.parquet"])
    df = mpf.paso_cruce("DELHI", carpeta, avisar=lambda *_: None)
    assert len(df) and set(df["frame"]) == {"DELHI"}
    ct.leer(carpeta, "cruce_manchas_catalogo")  # valida
    assert not mpf.falta(carpeta, "cruce", ["cruce_manchas_catalogo.parquet"])
    estado = mpf.leer_estado(carpeta)
    assert estado["cruce"]["con_basurales"] >= 1 and estado["cruce"]["con_negativos"] >= 1


def test_se_rehace_si_cambian_las_manchas(base, mock, monkeypatch):
    _cruce_mock(mock, monkeypatch)
    carpeta = os.path.join(base, "DELHI")
    mpf.paso_cruce("DELHI", carpeta, avisar=lambda *_: None)
    camino = os.path.join(carpeta, "manchas.geojson")
    with open(camino, encoding="utf-8") as fh:
        fc = json.load(fh)
    fc["features"] = fc["features"][:-1]  # la etapa 4 volvió a subir el frame
    with open(camino, "w", encoding="utf-8") as fh:
        json.dump(fc, fh)
    assert mpf.falta(carpeta, "cruce", ["cruce_manchas_catalogo.parquet"])
    mpf.paso_cruce("DELHI", carpeta, avisar=lambda *_: None)
    os.remove(os.path.join(carpeta, "cruce_manchas_catalogo.parquet"))  # y si se borra el archivo, también falta
    assert mpf.falta(carpeta, "cruce", ["cruce_manchas_catalogo.parquet"])


def test_juntar_conserva_los_frames_sin_carpeta(base, mock, monkeypatch):
    _cruce_mock(mock, monkeypatch)
    # el archivo anterior tiene el AMBA (sin carpeta: se conserva) y un DELHI viejo (con carpeta: se reemplaza)
    viejo = ct.leer(mock, "cruce_manchas_catalogo")
    viejo = viejo[viejo["frame"].isin(["AMBA", "DELHI"])].copy()
    n_amba = int((viejo["frame"] == "AMBA").sum())
    viejo.loc[viejo["frame"] == "DELHI", "frac_mancha"] = 0.0123
    ct.guardar(viejo, "cruce_manchas_catalogo", base)
    for f in ("DELHI", "CDMX"):
        mpf.paso_cruce(f, os.path.join(base, f), avisar=lambda *_: None)
    juntos = mpf.juntar(base, avisar=lambda *_: None)["cruce_manchas_catalogo"]
    assert set(juntos["frame"]) == {"AMBA", "DELHI", "CDMX"}
    assert int((juntos["frame"] == "AMBA").sum()) == n_amba
    assert not (juntos.loc[juntos["frame"] == "DELHI", "frac_mancha"] == 0.0123).any()
    # y correrlo de nuevo no cambia nada
    otra = mpf.juntar(base, avisar=lambda *_: None)["cruce_manchas_catalogo"]
    assert len(otra) == len(juntos)


def test_con_manchas_sigue_el_orden_de_frames(base):
    assert mpf.con_manchas(["AMBA", "CDMX", "DELHI", "NAIROBI"], base) == ["CDMX", "DELHI"]


# ------------------------------------------------------------------ fechas repartidas
def _escena(fecha, nube):
    return {"id": fecha, "fecha": fecha, "nube": nube, "epsg": 32611, "huella": box(-1, -1, 2, 2), "offset": 1000, "hrefs": {}}


def test_las_fechas_se_reparten_en_el_periodo():
    # un año: muchas escenas despejadas en verano y pocas, más nubladas, en invierno
    verano = [_escena(f"2026-07-{d:02d}", 1.0) for d in range(1, 29, 2)]
    resto = [_escena(f"2025-{m:02d}-15", 15.0) for m in (11, 12)] + [_escena(f"2026-{m:02d}-15", 15.0) for m in (1, 2, 3, 4, 5, 9)]
    caja = (0, 0, 1, 1)
    sin = eo.escenas_para(caja, verano + resto, 8)
    assert all(e["fecha"].startswith("2026-07") for e in sin)  # sin repartir, todas del verano
    con = eo.escenas_para(caja, verano + resto, 8, periodo=("2025-11-01", "2026-10-31"))
    meses = {e["fecha"][:7] for e in con}
    assert len(con) == 8 and len(meses) >= 7
    assert [e["fecha"] for e in con] == sorted(e["fecha"] for e in con)


def test_reparto_completa_los_tramos_vacios():
    escenas = [_escena(f"2026-07-{d:02d}", float(d)) for d in range(1, 11)]
    con = eo.escenas_para((0, 0, 1, 1), escenas, 6, periodo=("2025-11-01", "2026-10-31"))
    assert len(con) == 6  # todas caen en un tramo, pero se completa hasta 6 con las de menos nubes


# ------------------------------------------------------------------ controles del entrenamiento
def test_entrenar_controles_y_prueba_final_reservada(mock):
    cruce = ct.leer(mock, "cruce_manchas_catalogo")
    t, partes = armar_tabla.armar(ct.leer(mock, "tabla_radar"), ct.leer(mock, "tabla_optico"), cruce,
                                  armar_tabla.leer_frames(os.path.join(mock, "frames.json")), k=50)
    assert len(partes["particiones"]) == 3  # una por frame: se deja un frame afuera por vez
    radar, optico = ct.leer(mock, "tabla_radar"), ct.leer(mock, "tabla_optico")
    todas = radar.merge(optico.drop(columns=["frame", "n_escenas", "fechas"]), on="id_mancha", how="left")
    _, res, pred = entrenar.correr(t, partes, todas=todas, reservar=True, con_controles=True)
    assert isinstance(res["prueba_final"], str) and "AMBA" not in set(pred["frame"])
    assert not set(entrenar.CANTIDAD_DE_DATOS) & set(res["columnas"])
    c = res["controles"]
    assert {"completo", "sin_forma", "solo_radar", "solo_optico", "con_cantidad_de_datos"} <= set(c["variantes"])
    assert not set(entrenar.GRUPOS["forma"]) & set(entrenar.columnas(t)) - set(res["columnas"])
    assert c["variantes"]["solo_radar"]["columnas"] < c["variantes"]["completo"]["columnas"]
    assert len(c["mayores_errores"]) == 10 and {"id_mancha", "p_basural", "clase"} <= set(c["mayores_errores"][0])
    assert set(c["tamano"]["area_ha_por_clase"]) == {"basural_activo", "otro_movil"}
    # sin reservar, la prueba final se predice
    _, res2, pred2 = entrenar.correr(t, partes, todas=todas)
    assert "AMBA" in res2["prueba_final"] and "AMBA" in set(pred2["frame"])


def test_fuga_falla_con_columnas_prohibidas():
    entrenar.revisar_fuga(list(ct.COLUMNAS_MODELO))
    for mala in ("estado", "emit_metano_kg_h", "clase_negativo"):
        with pytest.raises(SystemExit):
            entrenar.revisar_fuga(["insomnio", mala])


# ------------------------------------------------------------------ corrida 2: negativos de OSM y etiquetas ópticas
def _radar_con_osm(mock):
    """El radar del mock con `clase_osm` y `que`, como el de la etapa 4: las manchas que no cruzan nada, de uso conocido."""
    radar = ct.leer(mock, "tabla_radar")
    cruce = ct.leer(mock, "cruce_manchas_catalogo")
    libres = ~radar["id_mancha"].isin(set(cruce["id_mancha"]))
    radar["clase_osm"] = ["uso_conocido" if x else "sin_explicar" for x in libres]
    radar["que"] = [("golf: Club de Prueba" if i % 2 else "forestación") if x else None for i, x in enumerate(libres)]
    return radar, cruce


def test_negativos_osm_entran_como_otro_movil(mock):
    radar, cruce = _radar_con_osm(mock)
    frames = armar_tabla.leer_frames(os.path.join(mock, "frames.json"))
    optico = ct.leer(mock, "tabla_optico")
    base, _ = armar_tabla.armar(radar, optico, cruce, frames, k=50)
    t, partes = armar_tabla.armar(radar, optico, cruce, frames, k=50, con_negativos_osm=True)
    ct.validar(t, "tabla_entrenamiento")
    osm = t[t["id_catalogo"].str.startswith("NEG-OSM-")]
    assert len(osm) and set(osm["clase"]) == {"otro_movil"} and set(osm["clase_negativo"]) == {"osm_golf", "osm_forestación"}
    assert "AMBA" not in set(osm["frame"])  # la prueba final no recibe negativos de OSM
    assert not set(osm["id_mancha"]) & set(cruce.loc[cruce["catalogo"] == "basurales", "id_mancha"])
    # un lugar con nombre cuenta una vez por frame; la forestación sin nombre, cada mancha
    golf = osm[osm["clase_negativo"] == "osm_golf"]
    assert golf.groupby("frame").size().max() == 1
    assert len(t) > len(base) and partes["meta"]["negativos_osm"] is True
    assert "clase_osm" not in t.columns and "que" not in t.columns  # no pueden llegar al modelo
    # un parque que se llama como un relleno no es un negativo
    i = radar.index[radar["clase_osm"] == "uso_conocido"][0]
    radar.loc[i, "que"] = "parque: Toyon Canyon Closed Landfill"
    t2, _ = armar_tabla.armar(radar, optico, cruce, frames, k=50, con_negativos_osm=True)
    assert radar.loc[i, "id_mancha"] not in set(t2["id_mancha"])


def test_positivos_segun_las_etiquetas_opticas(mock):
    radar, cruce = _radar_con_osm(mock)
    frames = armar_tabla.leer_frames(os.path.join(mock, "frames.json"))
    optico = ct.leer(mock, "tabla_optico")
    todos, _ = armar_tabla.armar(radar, optico, cruce, frames, k=50)
    bas = todos[(todos["clase"] == "basural_activo") & (todos["frame"] != "AMBA")]
    ids = list(bas["id_catalogo"])
    ia = {ids[0]: "act", ids[1]: "sin", ids[2]: "nose"}
    con, _ = armar_tabla.armar(radar, optico, cruce, frames, k=50, optico_ia=ia)
    assert dict(zip(con["id_catalogo"], con["actividad_optica"]))[ids[0]] == "act" and len(con) == len(todos)
    sin_sin, p1 = armar_tabla.armar(radar, optico, cruce, frames, k=50, optico_ia=ia, positivos="sin_sin")
    assert ids[1] not in set(sin_sin["id_catalogo"]) and ids[2] in set(sin_sin["id_catalogo"])
    assert p1["meta"]["positivos_sacados_por_el_optico"] == {"sin": 1}
    solo, _ = armar_tabla.armar(radar, optico, cruce, frames, k=50, optico_ia=ia, positivos="solo_act")
    entrena = solo[(solo["clase"] == "basural_activo") & (solo["frame"] != "AMBA")]
    assert list(entrena["id_catalogo"]) == [ids[0]]
    # la prueba final no se toca, y los negativos tampoco
    assert (solo["frame"] == "AMBA").sum() == (todos["frame"] == "AMBA").sum()
    assert (solo["clase"] == "otro_movil").sum() == (todos["clase"] == "otro_movil").sum()
    with pytest.raises(SystemExit):
        armar_tabla.armar(radar, optico, cruce, frames, k=50, positivos="solo_act")
