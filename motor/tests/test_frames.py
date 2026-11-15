"""The pipeline over any frame (stage 1): other UTM zones, the northern hemisphere, the ring that excludes
the catalogs, the crops of two neighboring NISAR frames and the fixed sources per frame. All synthetic and offline.

Run from `motor/`:  python -m pytest tests -q
"""
import argparse
import json
import os
import struct
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fuentes_fijas as ff  # noqa: E402
import geo  # noqa: E402
import insomnio as ins  # noqa: E402
import pipeline_insomnio as pl  # noqa: E402

P = ins.Parametros()
LA = geo.frame_de_caja("LA", [-118.75, 33.85, -117.75, 34.50], epsg=32611)  # Los Angeles, zone 11 north


# ------------------------------------------------------------------ geo
@pytest.mark.parametrize("lat, lon, epsg, x, y", [  # values from pyproj 3.7 (PROJ), to the millimeter
    (-34.6037, -58.3816, 32721, 373317.502, 6170036.171),  # Obelisco, zona 21 sur
    (19.4270, -99.1677, 32614, 482395.083, 2148083.725),  # Mexico City, zone 14 north
])
def test_utm_en_los_dos_hemisferios(lat, lon, epsg, x, y):
    assert geo.utm(lat, lon, epsg) == pytest.approx((x, y), abs=0.01)
    assert geo.latlon(x, y, epsg) == pytest.approx((lat, lon), abs=1e-6)


def test_el_norte_no_lleva_falso_norte():
    # The same point in the north and south zone differs by the 10,000 km of the false northing, and nothing else.
    xn, yn = geo.utm(34.05, -118.25, 32611)
    xs, ys = geo.utm(34.05, -118.25, 32711)
    assert xn == pytest.approx(xs) and ys - yn == pytest.approx(10000000)
    assert 3.7e6 < yn < 3.8e6  # about 3,770 km north of the equator


def test_zona_y_epsg():
    assert geo.zona_de_epsg(32721) == (21, True) and geo.zona_de_epsg(32611) == (11, False)
    assert geo.epsg_de(-34.6, -58.4) == 32721 and geo.epsg_de(34.05, -118.25) == 32611
    assert geo.epsg_de(28.6, 77.2) == 32643 and geo.epsg_de(-6.2, 106.8) == 32748
    with pytest.raises(ValueError):
        geo.zona_de_epsg(3413)  # polar: not used


def test_sin_parametros_sigue_siendo_el_amba():
    xs, ys = geo.grilla(80.0)
    assert (len(ys), len(xs)) == (879, 1278) and xs[0] == 283560.0 and ys[0] == 6207640.0
    xa, ya = geo.AMBA.grilla(80.0)
    assert np.array_equal(xs, xa) and np.array_equal(ys, ya)
    assert geo.frame("amba") is geo.AMBA and geo.AMBA.hemisferio == "S"
    assert geo.AMBA.bbox == [-59.35, -34.90, -58.25, -34.25]  # the frames.json order


def test_grilla_y_mascara_en_el_norte():
    xs, ys = LA.grilla(80.0)
    assert xs[0] % 80 == 40 and ys[0] % 80 == 40  # centers aligned like the GUNWs
    assert ys[0] > ys[-1] and xs[0] < xs[-1]  # de norte a sur y de oeste a este
    lat, lon = LA.latlon(xs[len(xs) // 2], ys[len(ys) // 2])
    assert LA.contiene(lat, lon)
    caja = (34.00, 34.02, -118.30, -118.27)  # lat_min, lat_max, lon_min, lon_max
    m = LA.mascara_poligonos([geo.caja_a_anillo(caja)], xs, ys)
    ha, (la, lo) = geo.area_y_centro(geo.caja_a_anillo(caja))
    assert m.sum() * 0.64 == pytest.approx(ha, rel=0.05) and ha == pytest.approx(2.218 * 2.767 * 100, rel=0.02)
    assert (la, lo) == pytest.approx((34.01, -118.285), abs=1e-3)
    f, c = np.nonzero(m)
    assert LA.latlon(xs[c].mean(), ys[f].mean()) == pytest.approx((34.01, -118.285), abs=2e-3)


def test_frame_de_frames_json(tmp_path):
    ruta = tmp_path / "frames.json"
    ruta.write_text(json.dumps({"meta": {}, "frames": [
        {"frame": "DELHI", "orbita": [55, 156], "ciudad": "Delhi", "pais": "IND", "hemisferio": "N", "epsg": 32643,
         "bbox": [76.8, 28.3, 77.6, 28.95], "n_gunw": 49, "fecha_inicio": "2026-01-10", "fecha_fin": "2026-11-01"}]}))
    fr = geo.frame("delhi", ruta=str(ruta))
    assert fr.caja == (28.95, 76.8, 28.3, 77.6) and fr.epsg == 32643 and fr.orbitas == (55, 156) and fr.epsg_fijo
    assert (fr.desde, fr.hasta, fr.hemisferio) == ("2026-01-10", "2026-11-01", "N")
    assert list(geo.frames_conocidos(str(ruta))) == ["DELHI", "AMBA"]  # the AMBA is always there
    with pytest.raises(KeyError):
        geo.frame("LAGOS", ruta=str(ruta))
    sin_epsg = geo.frame_de_caja("X", [-99.4, 19.1, -98.8, 19.8])
    assert sin_epsg.epsg == 32614 and not sin_epsg.epsg_fijo  # the center's, until `procesar` reads the product's


# ------------------------------------------------------------------ anillo
def test_el_anillo_excluye_los_catalogos():
    """A landfill surrounded by other landfills: with the old ring it doesn't wake up, because it's compared with its neighbors."""
    paso, forma = 80.0, (120, 120)
    sitio = np.zeros(forma, dtype=bool)
    sitio[50:70, 50:70] = True
    vecinos = np.zeros(forma, dtype=bool)  # the rest of the complex: it takes up almost the whole 1.5 km ring
    vecinos[35:85, 35:85] = True
    vecinos &= ~sitio
    tierra = np.ones(forma, dtype=bool)
    coh = np.full((12, *forma), 0.70, dtype=np.float32)
    coh[:, sitio | vecinos] = 0.25
    orbitas, fechas = np.array([10] * 12), np.array([f"2026-{m:02d}-{d:02d}" for m in (7, 8, 9, 10) for d in (5, 15, 25)])
    catalogos = sitio | vecinos

    viejo = ins.anillo(sitio, tierra, paso, P)
    nuevo = ins.anillo(sitio, tierra, paso, P, excluir=catalogos)
    assert (viejo & vecinos).mean() > 0.5 * viejo.mean() and not (nuevo & catalogos).any() and nuevo.sum() < viejo.sum()
    assert np.array_equal(ins.anillo(sitio, tierra, paso, P, excluir=None), viejo)  # without catalogs, as before

    f_viejo = ins.ficha(sitio, coh, orbitas, fechas, tierra, paso, P)
    f_nuevo = ins.ficha(sitio, coh, orbitas, fechas, tierra, paso, P, excluir=catalogos)
    assert f_viejo["radar"] != "despierto" and f_viejo["insomnio"] == 0.0  # it looks like its neighbors, which fill its ring
    assert f_nuevo["radar"] == "despierto" and f_nuevo["insomnio"] == 1.0
    assert f_nuevo["px_anillo"] < f_viejo["px_anillo"]

    todo = np.ones(forma, dtype=bool)  # if no ring is left, no verdict is made up
    f = ins.ficha(sitio, coh, orbitas, fechas, tierra, paso, P, excluir=todo)
    assert f["radar"] == "no_alcanza" and "anillo" in f["motivo"]


# ------------------------------------------------------------------ recortes
def test_recortar_entre_zonas_utm():
    """A product in zone 10 north brought to a grid in zone 11 north (box right at the zone edge)."""
    fr = geo.frame_de_caja("BORDE", [-120.2, 35.0, -119.8, 35.3], epsg=32611)
    xs_dst, ys_dst = fr.grilla(80.0)
    x0, y0 = geo.utm(35.35, -120.25, 32610)  # the product covers the box with a margin, in ITS zone
    xs_src = np.floor(x0 / 80) * 80 + 40 + 80 * np.arange(700)
    ys_src = np.floor(y0 / 80) * 80 + 40 - 80 * np.arange(700)
    lat_src, lon_src = geo.latlon(xs_src[None, :], ys_src[:, None], 32610)
    valor = (lat_src - 35.0).astype(np.float32)  # a smooth field: the latitude
    salida = pl.recortar(valor, xs_src, ys_src, xs_dst, ys_dst, 32610, 32611)
    lat_dst, _ = fr.latlon(xs_dst[None, :], ys_dst[:, None])
    assert np.isfinite(salida).mean() > 0.99
    assert np.nanmax(np.abs(salida - (lat_dst - 35.0))) < 80 / 111000  # each cell takes a pixel within 80 m
    # With the same zone it's the usual crop: it picks the exact pixel.
    misma = pl.recortar(valor, xs_src, ys_src, xs_src[100:200], ys_src[300:350], 32610, 32610)
    assert np.array_equal(misma, valor[300:350, 100:200])
    assert np.array_equal(pl.recortar(valor, xs_src, ys_src, xs_src[100:200], ys_src[300:350]), misma)


def test_juntar_dos_frames_de_nisar():
    a = np.full((4, 6), np.nan, dtype=np.float32)
    b = a.copy()
    a[:, :4], b[:, 3:] = 0.2, 0.9  # they overlap in one column: the one that covers more wins
    j = pl._juntar([b, a])
    assert np.isfinite(j).all() and (j[:, :4] == np.float32(0.2)).all() and (j[:, 4:] == np.float32(0.9)).all()


def test_partes_del_nombre():
    n = "NISAR_L2_PR_GUNW_024_034_A_018_025_4000_SH_20260628T130752_20260628T130826_20260710T130751_20260710T130826_P05023_N_F_J_001"
    assert pl._partes(n) == ("GUNW", 34, 18)
    assert pl._partes("NISAR_L2_PR_GCOV_035_010_D_106_2005_DHDH_A_20261105T220029_20261105T220104_P05036_N_F_J_001") == ("GCOV", 10, 106)


def _gunw_de_mentira(ruta, epsg, lat, lon, valor):
    """A minimal GUNW, with the same structure as NISAR's: 80 m coherence, coordinates and `projection`."""
    import h5py

    x, y = geo.utm(lat, lon, epsg)
    xs = np.floor(x / 80) * 80 + 40 + 80 * np.arange(-300, 300)
    ys = np.floor(y / 80) * 80 + 40 - 80 * np.arange(-300, 300)
    with h5py.File(ruta, "w") as f:
        g = f.create_group("science/LSAR/GUNW/grids/frequencyA/unwrappedInterferogram")
        g["xCoordinates"], g["yCoordinates"] = xs, ys
        d = g.create_dataset("projection", data=np.uint32(epsg))
        d.attrs["epsg_code"] = np.int64(epsg)
        g.create_dataset("HH/coherenceMagnitude", data=np.full((600, 600), valor, dtype=np.float32))


def test_procesar_e_indice_en_el_norte(tmp_path):
    """End to end with synthetic northern hemisphere products: `procesar` takes the EPSG from the product
    (`projection` dataset) and `indice` runs with the frame's fixed sources."""
    pytest.importorskip("h5py")
    datos, salida = tmp_path / "datos" / "NORTE", tmp_path / "salidas"
    datos.mkdir(parents=True)
    caja = [-118.32, 33.98, -118.22, 34.06]  # unos 9 × 9 km
    fechas = ["20260628", "20260710", "20260722", "20260803", "20260815", "20260827", "20260908"]
    for i, (a, b) in enumerate(zip(fechas, fechas[1:])):
        nombre = f"NISAR_L2_PR_GUNW_0{24 + i}_034_A_018_025_4000_SH_{a}T130752_{a}T130826_{b}T130751_{b}T130826_P05023_N_F_J_001.h5"
        _gunw_de_mentira(datos / nombre, 32611, 34.02, -118.27, 0.6)
    a = argparse.Namespace(frame=["NORTE"], caja=caja, epsg=None, datos=str(tmp_path / "datos"), salida=str(salida), web="",
                           orbitas=None, desde=None, hasta=None, capa="80m", procesos=1, hilos=1, solo_gunw=True,
                           remoto=False, borrar=True, sin_catalogos=False, fijos=str(tmp_path / "fijos"))
    arg = pl.preparar(a, "NORTE")
    assert arg.fr.epsg == 32611 and not arg.fr.epsg_fijo and arg.salida.endswith("NORTE")
    fijos = tmp_path / "fijos" / "NORTE"  # the frame's fixed sources, fake and offline
    assert arg.fijos == str(fijos)
    pl.procesar(arg)
    assert arg.fr.epsg_fijo and arg.fr.hemisferio == "N"
    assert json.load(open(salida / "NORTE" / "frame.json"))["epsg"] == 32611
    recortes = sorted(os.listdir(salida / "NORTE" / "recortes_80m"))
    assert len(recortes) == 6 and recortes[0] == "gunw_034_018_20260628_20260710_80m.npz"
    assert not list(datos.iterdir())  # --borrar: each .h5 is deleted after cropping it
    xs, ys = arg.fr.grilla(80.0)
    with np.load(salida / "NORTE" / "recortes_80m" / recortes[0]) as d:
        assert d["valor"].shape == (len(ys), len(xs)) and np.isfinite(d["valor"]).all() and int(d["epsg_producto"]) == 32611
    fijos.mkdir(parents=True)
    np.savez_compressed(fijos / "agua_jrc_80m.npz", ocurrencia=np.zeros((len(ys), len(xs)), dtype=np.uint8))
    (fijos / "usos_osm.json").write_text(json.dumps({"usos": []}))
    relleno = geo.caja_a_anillo((34.01, 34.03, -118.28, -118.26))
    (fijos / "catalogo.json").write_text(json.dumps({"poligonos": [{"id": "BAS-1", "catalogo": "basurales", "anillos": [relleno]}]}))
    pl.indice(arg)
    resumen = json.load(open(salida / "NORTE" / "resumen_80m.json"))
    assert resumen["frame"]["hemisferio"] == "N" and resumen["frame"]["epsg"] == 32611 and len(resumen["pares"]) == 6
    assert resumen["anillo_excluye"]["basurales"] == 1 and resumen["manchas"]["candidatas"] == 0  # todo coherente: nada despierto
    with np.load(salida / "NORTE" / "indice_80m.npz") as z:
        assert int(z["epsg"]) == 32611 and str(z["frame"]) == "NORTE" and z["catalogo"].sum() * 0.64 == pytest.approx(408, rel=0.1)
        assert np.nanmax(z["insomnio"]) == 0


# ------------------------------------------------------------------ fuentes fijas
def test_tiles_de_jrc():
    assert ff.tile_jrc(11, 12) == "60W_30S"  # the AMBA's
    assert ff.tile_jrc(4, 6) == "120W_40N" and ff.tile_jrc(5, 25) == "70E_30N" and ff.tile_jrc(8, 18) == "0E_0N"
    assert ff.carpeta(geo.AMBA) == ff.FIJOS and ff.carpeta(LA) == os.path.join(ff.FIJOS, "LA")


def test_wkb_a_anillos():
    def poligono(*anillos):
        b = struct.pack("<BII", 1, 3, len(anillos))
        for a in anillos:
            b += struct.pack("<I", len(a)) + b"".join(struct.pack("<dd", *p) for p in a)
        return b

    exterior = [(-58.5, -34.6), (-58.4, -34.6), (-58.4, -34.5), (-58.5, -34.5), (-58.5, -34.6)]
    agujero = [(-58.46, -34.56), (-58.44, -34.56), (-58.44, -34.54), (-58.46, -34.56)]
    assert ff._wkb_exteriores(poligono(exterior, agujero)) == [[list(p) for p in exterior]]  # only the exterior
    otro = [(x + 1, y) for x, y in exterior]
    multi = struct.pack("<BII", 1, 6, 2) + poligono(exterior) + poligono(otro)
    assert ff._wkb_exteriores(multi) == [[list(p) for p in exterior], [list(p) for p in otro]]


def test_catalogo_del_frame(tmp_path):
    """Only polygons that touch the box (with its margin) are included; points aren't."""
    cuadrado = lambda lon, lat: {"type": "Polygon", "coordinates": [[[lon, lat], [lon + .01, lat], [lon + .01, lat + .01], [lon, lat + .01], [lon, lat]]]}  # noqa: E731
    (tmp_path / "basurales").mkdir()
    (tmp_path / "negativos").mkdir()
    (tmp_path / "basurales" / "geometrias.geojson").write_text(json.dumps({"features": [
        {"properties": {"id": "BAS-1", "nombre": "adentro", "estado": "abierto", "area_ha": 100}, "geometry": cuadrado(-118.3, 34.0)},
        {"properties": {"id": "BAS-2", "nombre": "en el AMBA", "estado": "cerrado", "area_ha": 44}, "geometry": cuadrado(-59.0, -34.5)},
        {"properties": {"id": "BAS-3", "nombre": "punto", "estado": "abierto"}, "geometry": {"type": "Point", "coordinates": [-118.3, 34.0]}}]}))
    (tmp_path / "basurales" / "complejos.json").write_text(json.dumps({"complejo_por_sitio": {"BAS-1": "CPX-1"}}))
    (tmp_path / "negativos" / "geometrias_amba.geojson").write_text(json.dumps({"features": [
        {"properties": {"id": "NEG-AMBA-1", "clase": "aeropuerto", "area_ha": 50}, "geometry": cuadrado(-58.6, -34.6)}]}))
    ff.catalogo(LA, str(tmp_path / "fijos"), str(tmp_path))
    d = json.load(open(tmp_path / "fijos" / "catalogo.json"))
    assert [p["id"] for p in d["poligonos"]] == ["BAS-1"] and d["poligonos"][0]["complejo"] == "CPX-1"
    assert d["conteo"] == {"basurales": 1, "negativos": 0} and d["bbox"] == LA.bbox
    ff.catalogo(geo.AMBA, str(tmp_path / "fijos_amba"), str(tmp_path))
    d = json.load(open(tmp_path / "fijos_amba" / "catalogo.json"))
    assert [p["id"] for p in d["poligonos"]] == ["BAS-2", "NEG-AMBA-1"]
