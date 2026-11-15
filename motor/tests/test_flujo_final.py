"""End of the flow: frames (stage 2), insomnia per catalog polygon, verdict (stage 9) and activity (stage 8).

Synthetic cases for each row of the verdict table and tests with the real AMBA (`salidas/`).
The exact-mode ones need the per-pair crops (`salidas/recortes_80m/`); if they're missing, they're skipped.

Run from `motor/`:  python -m pytest tests -q
"""
import json
import os
import sys

import numpy as np
import pandas as pd
import pytest

AQUI = os.path.dirname(os.path.abspath(__file__))
HERR = os.path.dirname(AQUI)
sys.path.insert(0, HERR)
import contratos as ct  # noqa: E402
import evaluar_actividad as ea  # noqa: E402
import frames_elegir as fe  # noqa: E402
import insomnio_catalogo as icat  # noqa: E402
import veredicto as ve  # noqa: E402

SALIDAS = os.path.join(HERR, "..", "data", "salidas")
DATA = os.path.join(HERR, "..", "data", "catalogos")
HAY_INDICE = os.path.exists(os.path.join(SALIDAS, "indice_80m.npz"))
HAY_RECORTES = os.path.isdir(os.path.join(SALIDAS, "recortes_80m"))

# catalog polygon -> pipeline record (same OSM object)
FICHAS = {"BAS-053307": "norte-iii", "BAS-053304": "norte-iii-disposicion", "BAS-016796": "ceamse-norte-oeste",
          "BAS-000001": "gonzalez-catan", "BAS-000007": "lujan"}


# ---------------------------------------------------------------- frames
def test_frames_json_cumple_el_contrato_y_no_se_superponen():
    d = ct.leer(os.path.join(DATA, "frames.json"))
    agregado = d["criterio"].eq("abiertos") if "criterio" in d else d["frame"].isna()  # the ones added by `--agregar` (prompt 6)
    assert 8 <= (~agregado).sum() <= 12
    # The added ones come after the original ones, in priority order, and all have open sites and 15 pairs or more.
    assert list(d["prioridad"]) == sorted(d["prioridad"]) and not agregado[: (~agregado).sum()].any()
    assert all(n["abierto"] >= 1 for n in d.loc[agregado, "n_sitios_10ha"]) and (d.loc[agregado, "n_gunw"] >= 15).all()
    assert d.loc[d["pais"] == "ARG", "reservado_prueba"].all() and not d.loc[d["pais"] != "ARG", "reservado_prueba"].any()
    assert (d["pais"] != "USA").sum() >= 3, "no sólo EE. UU."
    cajas = list(d["bbox"])
    for i in range(len(cajas)):
        for j in range(i + 1, len(cajas)):
            assert not fe.se_tocan(cajas[i], cajas[j]), (d["frame"][i], d["frame"][j])
    amba = d[d["frame"] == "AMBA"].iloc[0]
    assert sorted(amba["orbita"]) == [10, 161] and amba["n_gunw"] == 15 and amba["epsg"] == 32721


def test_caja_con_margen_y_nombre_de_celda():
    o, s, e, n = fe.caja_con_margen([[-84.0, 42.0, -83.9, 42.1], [-83.5, 42.5, -83.4, 42.6]], km=5.0)
    assert (s, n) == pytest.approx((42.0 - 5 / 111.32, 42.6 + 5 / 111.32), abs=1e-4)
    assert -84.0 - o == pytest.approx(e + 83.4, abs=1e-4) and 0.055 < -84.0 - o < 0.065  # 5 km a 42° de latitud
    assert fe._clave_area(-119, 34, "Sun Valley, Los Angeles, CA") == "USA_CA_LOS_ANGELES"
    assert fe._clave_area(-67, 18, "Ponce, Ponce, PR") == "PRI_PONCE" and fe._clave_area(-119, 34, None) == "CELDA_N34_W119"


def test_pares_por_frame_se_queda_con_pr_y_pares_unicos():
    w = "POLYGON ((0 0, 1 0, 1 1, 0 1, 0 0))"
    g = lambda n, p=10, f=106, d="DESCENDING": {"granuleName": n, "productType": "GUNW", "path": p, "frame": f,  # noqa: E731
                                                "flightDirection": d, "wkt": w}
    base = "NISAR_L2_{}_GUNW_032_010_D_106_033_2000_SH_20260930T220028_20260930T220103_20261012T220028_20261012T220103_P05023_N_F_J_00{}"
    grupos = fe.pares_por_frame([g(base.format("PR", 1)), g(base.format("PR", 2)), g(base.format("OP", 1))])
    assert list(grupos) == [(10, "D", 106)] and list(grupos[(10, "D", 106)]["pares"]) == [("20260930", "20261012")]
    assert fe.cobertura([0.2, 0.2, 0.8, 0.8], grupos[(10, "D", 106)]["huella"]) == 1.0


def test_elegir_reserva_argentina_evita_superposicion_y_mete_uno_de_afuera_arriba():
    f = lambda k, pais, caja, pt: {"frame": k, "pais": pais, "bbox": caja, "n_gunw": 20, "puntaje": pt,  # noqa: E731
                                   "reservado_prueba": pais == "ARG"}
    ev = [f("AMBA", "ARG", [0, 0, 1, 1], 5), f("A", "USA", [10, 0, 11, 1], 50), f("B", "USA", [10.5, 0, 11.5, 1], 49),
          f("C", "USA", [20, 0, 21, 1], 40), f("D", "USA", [30, 0, 31, 1], 30), f("E", "USA", [40, 0, 41, 1], 20),
          f("X", "IND", [50, 0, 51, 1], 3)]
    sel = fe.elegir(ev, n=10, max_usa=6, top=4)
    assert sel[0]["frame"] == "AMBA" and sel[0]["prioridad"] == 0
    assert "B" not in [x["frame"] for x in sel]  # overlaps with A
    assert "X" in [x["frame"] for x in sel[1:5]]  # among the first 4


# ---------------------------------------------------------------- insomnia per polygon (synthetic)
def test_medir_aproximado_quieto_despierto_y_liso():
    p = icat.ins.Parametros()
    n = 60
    d = {"insomnio": np.zeros((n, n), np.float32), "persistencia": np.zeros((n, n), np.float32),
         "eco_db": np.full((n, n), -8, np.float32), "agua": np.zeros((n, n), bool), "pares": np.full((n, n), 15, np.uint8),
         "coherencia_media": np.full((n, n), 0.6, np.float32)}
    m = np.zeros((n, n), bool)
    m[20:40, 20:40] = True
    assert icat.medir_aproximado(m, d, p)["radar"] == "quieto"
    d["insomnio"][m], d["persistencia"][m] = 0.9, 0.8
    r = icat.medir_aproximado(m, d, p)
    assert r["radar"] == "despierto" and r["insomnio"] == 0.9 and r["n_pares"] == 15
    d["eco_db"][m] = -16
    assert icat.medir_aproximado(m, d, p)["radar"] == "no_alcanza"


# ---------------------------------------------------------------- verdict (synthetic: each row of the table)
def _ic(filas):
    base = {"catalogo": "basurales", "complejo": None, "frame": "F", "persistencia": 0.8, "eco_db": -9.0, "n_pares": 15,
            "motivo": None, "area_ha": 50.0, "clase": None, "nombre": None}
    df = pd.DataFrame([{**base, **f} for f in filas])
    df["n_pares"] = df["n_pares"].astype("int64")
    return ct.validar(df, "insomnio_catalogo")


def test_veredicto_cada_fila_de_la_tabla():
    ic = _ic([
        {"id_catalogo": "BAS-T1", "estado": "abierto", "insomnio": 0.9, "radar": "despierto"},     # mancha encima
        {"id_catalogo": "BAS-T2", "estado": "cerrado", "insomnio": 0.9, "radar": "despierto"},     # mancha encima
        {"id_catalogo": "BAS-T3", "estado": "cerrado", "insomnio": 0.0, "radar": "quieto"},
        {"id_catalogo": "BAS-T4", "estado": "abierto", "insomnio": 0.1, "radar": "quieto"},
        {"id_catalogo": "BAS-T5", "estado": "abierto", "insomnio": 0.9, "radar": "despierto", "area_ha": 4.0},
        {"id_catalogo": "BAS-T6", "estado": "desconocido", "insomnio": 0.9, "radar": "despierto"},  # no blob
        {"id_catalogo": "BAS-T7", "estado": "abierto", "insomnio": 0.4, "radar": "no_alcanza", "motivo": "intermedio"},
    ])
    cruce = pd.DataFrame({"id_mancha": ["MAN-F-0001", "MAN-F-0002", "MAN-F-0003", "MAN-F-0004", "MAN-F-0005"],
                          "id_catalogo": ["BAS-T1", "BAS-T2", "NEG-1", "NEG-2", "BAS-T4"],
                          "catalogo": ["basurales", "basurales", "negativos", "negativos", "basurales"], "frame": "F",
                          "frac_area_menor": [0.9, 0.5, 0.8, 0.9, 0.1], "clase_negativo": [None, None, "cantera", "aeropuerto", None]})
    pred = pd.DataFrame({"id_mancha": ["MAN-F-0001", "MAN-F-0002", "MAN-F-0003", "MAN-F-0004", "MAN-F-0005", "MAN-F-0006"],
                         "frame": "F", "p_basural": [0.9, 0.8, 0.2, 0.3, 0.9, 0.7]})
    vs = {v["id"]: v for v in ve.calcular(ic, cruce, None, pred)}
    assert vs["BAS-T1"]["veredicto"] == "activo_conocido"
    assert vs["BAS-T2"]["veredicto"] == "cerrado_despierto"
    assert vs["BAS-T3"]["veredicto"] == "cerrado_quieto"
    assert vs["BAS-T4"]["veredicto"] == "quieto_radar"  # the 10 % cross doesn't reach 30 %
    assert vs["BAS-T5"]["veredicto"] == "no_alcanza"
    assert vs["BAS-T6"]["veredicto"] == "activo_conocido" and "no formó mancha" in vs["BAS-T6"]["motivo"]
    assert vs["BAS-T7"]["veredicto"] == "no_alcanza" and vs["BAS-T7"]["motivo"] == "intermedio"
    assert vs["MAN-F-0003"]["veredicto"] == "descartada" and "cantera" in vs["MAN-F-0003"]["motivo"]
    assert vs["MAN-F-0005"]["veredicto"] == "posible_nuevo"  # grazes BAS-T4 with less than 30 %
    assert vs["MAN-F-0006"]["veredicto"] == "posible_nuevo"
    r = ve.resumen(list(vs.values()))
    assert r["cerrados_pero_despiertos"] == 1 and r["posibles_nuevos"] == 2 and r["activos_ya_conocidos"] == 3


def test_veredicto_sin_modelo_no_inventa_nuevos():
    ic = _ic([{"id_catalogo": "BAS-T1", "estado": "abierto", "insomnio": 0.9, "radar": "despierto"}])
    cruce = pd.DataFrame({"id_mancha": ["MAN-F-0001"], "id_catalogo": ["NEG-1"], "catalogo": ["negativos"], "frame": "F",
                          "frac_area_menor": [0.9]})
    vs = {v["id"]: v for v in ve.calcular(ic, cruce, None, None)}
    assert vs["MAN-F-0001"]["veredicto"] == "sin_clasificar"


def test_veredicto_con_el_mock(tmp_path):
    import contratos_mock
    contratos_mock.generar(str(tmp_path))
    vs, r = ve.main(["--carpeta", str(tmp_path), "--salida", str(tmp_path / "v.json")])
    hay = {v["veredicto"] for v in vs}
    assert {"activo_conocido", "cerrado_despierto", "cerrado_quieto", "quieto_radar", "posible_nuevo", "descartada", "no_alcanza"} <= hay


# ---------------------------------------------------------------- activity (synthetic)
def test_evaluar_actividad_matriz_y_un_sitio_por_complejo():
    ec = {"frames": {"F": [
        {"id_catalogo": "BAS-A1", "estado": "abierto", "fuentes_estado": ["epa_lmop"], "area_ha": 50, "complejo": "CPX-1", "pais": "USA"},
        {"id_catalogo": "BAS-A2", "estado": "abierto", "fuentes_estado": ["epa_lmop"], "area_ha": 20, "complejo": "CPX-1", "pais": "USA"},
        {"id_catalogo": "BAS-C1", "estado": "cerrado", "fuentes_estado": ["osm"], "area_ha": 30, "complejo": "CPX-2", "pais": "USA"},
        {"id_catalogo": "BAS-C2", "estado": "cerrado", "fuentes_estado": ["epa_lmop"], "area_ha": 30, "complejo": "CPX-3", "pais": "USA"},
        {"id_catalogo": "BAS-C3", "estado": "cerrado", "fuentes_estado": ["epa_lmop"], "area_ha": 3, "complejo": "CPX-4", "pais": "USA"},
    ]}, "G": [{"id_catalogo": "BAS-G", "estado": "abierto", "fuentes_estado": ["epa_lmop"], "area_ha": 40, "complejo": "CPX-9"}]}
    ec["frames"]["G"] = ec.pop("G")
    ic = _ic([{"id_catalogo": "BAS-A1", "estado": "abierto", "insomnio": 0.9, "radar": "despierto"},
              {"id_catalogo": "BAS-A2", "estado": "abierto", "insomnio": 0.0, "radar": "quieto"},
              {"id_catalogo": "BAS-C1", "estado": "cerrado", "insomnio": 0.0, "radar": "quieto"},
              {"id_catalogo": "BAS-C2", "estado": "cerrado", "insomnio": 0.9, "radar": "despierto"},
              {"id_catalogo": "BAS-C3", "estado": "cerrado", "insomnio": 0.9, "radar": "despierto", "area_ha": 3.0}])
    r = ea.evaluar(ec, ic)
    m = r["por_pais"]["USA"]["matriz"]
    assert m["abierto"] == {"despierto": 1, "quieto": 0, "no_alcanza": 0}  # BAS-A2 doesn't count: same complex
    assert m["cerrado"] == {"despierto": 1, "quieto": 1, "no_alcanza": 0}
    assert r["chicos_menos_de_min_ha"] == {"USA": 1} and r["frames_sin_procesar"] == {"G": 1}
    assert [s["id_catalogo"] for s in r["discordantes"]["cerrados_pero_despiertos"]] == ["BAS-C2"]
    sin_osm = ea.evaluar(ec, ic, fuentes=("epa_lmop",))
    assert sin_osm["total"]["matriz"]["cerrado"]["quieto"] == 0
    assert ea.wilson(0, 0) is None and ea.wilson(5, 10)[0] < 0.5 < ea.wilson(5, 10)[1]


# ---------------------------------------------------------------- the real AMBA
@pytest.fixture(scope="module")
def amba_aproximado(tmp_path_factory):
    if not HAY_INDICE:
        pytest.skip("falta salidas/indice_80m.npz")
    carpeta = str(tmp_path_factory.mktemp("amba"))
    icat.main(["--modo", "aproximado", "--salida", carpeta])
    return carpeta


def test_amba_aproximado_lujan_quieto_y_norte_iii_activo(amba_aproximado):
    ic = ct.leer(amba_aproximado, "insomnio_catalogo")
    fila = ic.set_index("id_catalogo")
    assert fila.loc["BAS-000007", "radar"] == "quieto" and fila.loc["BAS-000007", "insomnio"] == 0.0
    assert fila.loc["BAS-000001", "radar"] == "despierto"
    vs = {v["id"]: v for v in ve.calcular(ic)}
    assert vs["BAS-000007"]["veredicto"] == "cerrado_quieto"
    assert vs["BAS-053304"]["veredicto"] == "activo_conocido"


def test_amba_actividad_con_estado_conocido(amba_aproximado):
    with open(os.path.join(SALIDAS, "estado_conocido.json"), encoding="utf-8") as fh:
        ec = json.load(fh)
    r = ea.evaluar(ec, ct.leer(amba_aproximado, "insomnio_catalogo"))
    assert r["por_pais"]["ARG"]["matriz"]["cerrado"]["quieto"] == 1  # Luján
    assert r["por_pais"]["ARG"]["matriz"]["abierto"]["despierto"] == 1  # Norte III


@pytest.mark.skipif(not HAY_RECORTES, reason="faltan salidas/recortes_80m/ (gs://basurales-514714-salidas/salidas-v3.tgz)")
def test_amba_exacto_reproduce_fichas_80m(tmp_path):
    with open(os.path.join(SALIDAS, "fichas_80m.json"), encoding="utf-8") as fh:
        fichas = json.load(fh)
    ic = icat.main(["--modo", "exacto", "--salida", str(tmp_path)]).set_index("id_catalogo")
    for bas, ficha in FICHAS.items():
        f = fichas[ficha]
        assert ic.loc[bas, "insomnio"] == pytest.approx(f["insomnio"], abs=0.005), bas
        assert ic.loc[bas, "persistencia"] == pytest.approx(f["persistencia"], abs=0.005), bas
        assert ic.loc[bas, "radar"] == f["radar"], bas
    vs = {v["id"]: v for v in ve.calcular(ic.reset_index())}
    assert vs["BAS-000007"]["veredicto"] == "cerrado_quieto"
    assert vs["BAS-053307"]["veredicto"] == "activo_conocido"  # Norte III, through the complex status
    assert vs["BAS-053304"]["veredicto"] == "activo_conocido"
