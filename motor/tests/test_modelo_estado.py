"""El modelo de abierto contra cerrado al lado de los veredictos (`veredicto_estado.py`) y la regla con que se elige
el modelo principal (`modelo_estado.elegir_principal`). Todo sintético y sin red.

Correr desde `herramientas/`:  python -m pytest tests -q
"""
import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import modelo_estado as me  # noqa: E402
import veredicto_estado as vest  # noqa: E402


def _salidas(tmp_path):
    pd.DataFrame([
        {"id_catalogo": "BAS-000001", "frame": "F1", "estado": "abierto", "p_abierto": 0.9, "lectura": "compatible con abierto",
         "origen": "validación: modelo entrenado sin su frame", "radar": "quieto"},
        {"id_catalogo": "BAS-000002", "frame": "F1", "estado": "cerrado", "p_abierto": 0.2, "lectura": "compatible con cerrado",
         "origen": "validación: modelo entrenado sin su frame", "radar": "despierto"},
        {"id_catalogo": "BAS-000003", "frame": "F2", "estado": "desconocido", "p_abierto": None, "lectura": "sin dato",
         "origen": "sin recortes de radar medidos", "radar": "no_alcanza"},
    ]).to_parquet(tmp_path / "predicciones_estado.parquet", index=False)
    modelo = {"modelo_principal": {"variables": "frente", "lista": ["eco_std_rel_p90", "otra"], "auc": 0.9, "ic95": [0.8, 0.95]},
              "muestras": {"n": 2, "abiertos": 1, "cerrados": 1, "frames": 1}, "limites": ["casi todo EE. UU."],
              "prueba": [{"id_catalogo": "BAS-000007", "nombre": "Basural de Luján", "estado": "cerrado", "p_abierto": 0.16}]}
    (tmp_path / "modelo_estado.json").write_text(json.dumps(modelo), encoding="utf-8")
    return str(tmp_path)


def test_anotar_suma_el_modelo_sin_tocar_el_veredicto(tmp_path):
    vs = [{"tipo": "catalogo", "id": "BAS-000001", "frame": "F1", "veredicto": "quieto_radar"},
          {"tipo": "catalogo", "id": "BAS-000003", "frame": "F2", "veredicto": "no_alcanza"},
          {"tipo": "catalogo", "id": "BAS-000009", "frame": "F1", "veredicto": "no_alcanza"},  # chico: no está en las predicciones
          {"tipo": "mancha", "id": "MAN-F1-0001", "frame": "F1", "veredicto": "sin_clasificar"}]
    assert vest.anotar(vs, _salidas(tmp_path)) == 1
    assert vs[0]["modelo_estado"] == {"p_abierto": 0.9, "lectura": "compatible con abierto", "origen": "validación: modelo entrenado sin su frame"}
    assert vs[1]["modelo_estado"]["p_abierto"] is None and vs[1]["modelo_estado"]["lectura"] == "sin dato"
    assert vs[2]["modelo_estado"] == {"p_abierto": None, "lectura": "sin dato", "origen": vest.SIN_MODELO}
    assert "modelo_estado" not in vs[3] and [v["veredicto"] for v in vs] == ["quieto_radar", "no_alcanza", "no_alcanza", "sin_clasificar"]


def test_sin_modelo_no_hace_nada(tmp_path):
    vs = [{"tipo": "catalogo", "id": "BAS-000001", "frame": "F1"}]
    assert vest.anotar(vs, str(tmp_path)) == 0 and "modelo_estado" not in vs[0]
    assert vest.bloque_web(str(tmp_path)) is None and vest.lineas_md(str(tmp_path)) == []


def test_bloque_de_la_web_y_matriz(tmp_path):
    s = _salidas(tmp_path)
    b = vest.bloque_web(s)
    assert set(b) == {"auc", "ic95", "n", "abiertos", "cerrados", "frames", "variables", "validacion", "limites", "prueba_amba"}
    assert b["variables"][0] == vest.ETIQUETAS["eco_std_rel_p90"] and b["variables"][1] == "otra"
    assert b["prueba_amba"] == [{"nombre": "Basural de Luján", "estado_registro": "cerrado", "p_abierto": 0.16}]
    m = vest.matriz(s)
    assert m["predios"] == 2 and m["regla_decide"] == 2 and m["regla_acierta"] == 0 and m["modelo_acierta"] == 2
    assert any("Regla del insomnio contra el modelo" in x for x in vest.lineas_md(s))


def test_las_etiquetas_cubren_todas_las_variables():
    assert set(me.FRENTE + me.OPTICO + me.RADAR) <= set(vest.ETIQUETAS)


def test_el_principal_es_el_mas_simple_dentro_de_la_tolerancia():
    auc = lambda a, b, c: dict(zip(me.CANDIDATOS, ({"auc": a}, {"auc": b}, {"auc": c})))  # noqa: E731
    assert me.elegir_principal(auc(0.90, 0.91, 0.915)) == me.CANDIDATOS[0]
    assert me.elegir_principal(auc(0.85, 0.91, 0.92)) == me.CANDIDATOS[1]
    assert me.elegir_principal(auc(0.80, 0.85, 0.92)) == me.CANDIDATOS[2]
