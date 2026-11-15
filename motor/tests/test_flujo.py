"""flujo.py (etapa 9): frames reales de salidas/<FRAME>/, controles del AMBA, matriz y casos para mirar a mano.

Correr desde `herramientas/`:  python -m pytest tests/test_flujo.py -q
Los tests con datos reales se saltean si la etapa 4 todavía no subió frames.
"""
import glob
import json
import os
import sys

import pytest

AQUI = os.path.dirname(os.path.abspath(__file__))
HERR = os.path.dirname(AQUI)
sys.path.insert(0, HERR)
import flujo  # noqa: E402

SALIDAS = os.path.join(HERR, "..", "data", "salidas")
FRAMES = sorted(os.path.basename(os.path.dirname(p)) for p in glob.glob(os.path.join(SALIDAS, "*", "insomnio_catalogo.parquet")))
HAY_INDICE = os.path.exists(os.path.join(SALIDAS, "indice_80m.npz"))


@pytest.fixture(scope="module")
def corrida(tmp_path_factory):
    if not FRAMES and not HAY_INDICE:
        pytest.skip("sin frames de la etapa 4 ni índice del AMBA")
    d = tmp_path_factory.mktemp("flujo")
    rs, ev = flujo.main(["--destino", str(d), "--md", str(d / "resultados.md")])
    with open(d / "veredictos.json", encoding="utf-8") as fh:
        vs = json.load(fh)
    return d, rs, ev, vs


def test_procesa_todos_los_frames_subidos(corrida):
    _, rs, _, _ = corrida
    assert set(FRAMES) <= set(rs["frames_procesados"])
    for f in rs["frames_procesados"]:
        r = rs["por_frame"][f]
        assert r["activos"] == r["activos_ya_conocidos"] + r["posibles_nuevos"]
    assert rs["total"]["activos_ya_conocidos"] == sum(r["activos_ya_conocidos"] for r in rs["por_frame"].values())


@pytest.mark.skipif(not HAY_INDICE, reason="sin indice_80m.npz del AMBA")
def test_controles_del_amba(corrida):
    _, _, _, vs = corrida
    v = {x["id"]: x for x in vs["veredictos"] if x["frame"] == "AMBA" and x["tipo"] == "catalogo"}
    assert v["BAS-000007"]["veredicto"] == "cerrado_quieto"  # Luján
    assert v["BAS-053304"]["veredicto"] == "activo_conocido"  # Norte III


def test_lo_quieto_no_pasa_por_el_modelo(corrida):
    """Un 'cerrado y quieto' nunca depende de p_basural: el veredicto es el mismo con una probabilidad cualquiera."""
    _, _, _, vs = corrida
    quietos = [x for x in vs["veredictos"] if x["veredicto"] in ("cerrado_quieto", "quieto_radar")]
    assert quietos and all(x["radar"] == "quieto" and not x["manchas"] for x in quietos)


def test_sin_modelo_no_hay_nuevos_y_la_frase_lo_dice(corrida):
    _, rs, _, _ = corrida
    if rs["modelo"]["validado"]:
        pytest.skip("hay modelo validado")
    assert rs["total"]["posibles_nuevos"] == 0
    assert "Sin modelo validado" in rs["total"]["frase"]


def test_matriz_por_pais_con_wilson_y_sin_osm(corrida):
    _, _, ev, _ = corrida
    assert ev["por_pais"] and "sin_cerrados_osm" in ev
    for d in list(ev["por_pais"].values()) + [ev["total"], ev["sin_cerrados_osm"]["total"]]:
        t = d["metricas"]["concordancia"]
        assert t["n"] == 0 or (t["ic95"][0] <= t["tasa"] <= t["ic95"][1])
    assert "EE. UU." in ev["meta"]["sesgo"]


def test_casos_para_mirar_tienen_chequeos(corrida):
    _, _, ev, _ = corrida
    for lista in ev["casos_para_mirar"].values():
        for c in lista:
            assert c["chequeos"] and c["resultado"]
            assert {"nombre", "pais", "area_ha", "insomnio", "fecha_cierre", "fuentes_estado"} <= set(c)


def test_descartes_vecino_activo_y_biogas():
    cat = {"BAS-1": {"lat": 0.0, "lon": 0.0, "fuentes": [{"datos": {"captura_biogas": "Yes", "nombre": "X Transfer Station"}}]},
           "BAS-2": {"lat": 0.005, "lon": 0.0, "fuentes": []}}
    caso = {"id_catalogo": "BAS-1", "nombre": "X", "registro": "cerrado", "area_ha": 20, "complejo": "CPX-1", "fecha_cierre": 1990}
    vecino = {"tipo": "catalogo", "id": "BAS-2", "nombre": "Y", "radar": "despierto", "registro": "abierto", "area_ha": 30,
              "complejo": "CPX-2"}
    ch, res = flujo.descartes(caso, cat["BAS-1"], [vecino], cat)
    r = {c["chequeo"]: c["resultado"] for c in ch}
    assert r["celda vecina activa"] == "no se descarta"
    assert r["planta o pozos de biogás"] == "no se descarta"
    assert r["planta de transferencia o reciclaje en el predio"] == "no se descarta"
    assert res == "hay una explicación obvia sin descartar"
    ch, res = flujo.descartes({**caso, "id_catalogo": "BAS-2"}, {"lat": 1.0, "lon": 1.0, "fuentes": []}, [], cat)
    assert res == flujo.PASA


def test_estado_modelo_humo_no_valida(tmp_path):
    (tmp_path / "metricas.json").write_text(json.dumps({"validacion": "humo_por_complejo", "advertencia": "PRUEBA DE HUMO"}))
    assert flujo.estado_modelo(str(tmp_path))["validado"] is False
    assert flujo.estado_modelo(str(tmp_path / "no"))["hay_metricas"] is False
