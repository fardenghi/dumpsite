"""Baja y prepara las fuentes fijas que usa `pipeline_insomnio.py indice`. Se corre una sola vez, con red.

  python fuentes_fijas.py agua      máscara de agua de JRC Global Surface Water sobre la grilla del AMBA
  python fuentes_fijas.py sitios    contornos de OpenStreetMap de los sitios de sitios_registro.json
  python fuentes_fijas.py usos      polígonos de usos conocidos (aeródromos, golf, parques, ...) de OpenStreetMap

Los resultados quedan en `fijos/` y van al repo: el pipeline no necesita red.

Fuentes:
- JRC Global Surface Water v1.4 (1984-2021), capa `occurrence`. Pekel, Cottam, Gorelick y Belward (2016),
  Nature 540, 418-422, doi:10.1038/nature20584. Datos del EC JRC / Google, uso libre con cita.
  https://global-surface-water.appspot.com/download
- © colaboradores de OpenStreetMap, licencia ODbL 1.0. Geometrías por la API de OSM y por Nominatim.
"""
import argparse
import json
import os
import sys
import tempfile
import time
import urllib.parse
import urllib.request

import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import geo  # noqa: E402

FIJOS = os.path.join(AQUI, "fijos")
AGENTE = {"User-Agent": "insomnes-contornos/0.1"}
JRC = "https://storage.googleapis.com/global-surface-water/downloads2021/occurrence/occurrence_60W_30Sv1_4_2021.tif"
JRC_ORIGEN, JRC_PASO = (-60.0, -30.0), 0.00025  # esquina noroeste (lon, lat) y tamaño de píxel en grados
# Usos conocidos que también dan coherencia baja permanente: (búsqueda en Nominatim, clase OSM, tipo OSM, etiqueta).
USOS = [("aerodrome", "aeroway", "aerodrome", "aeródromo"), ("golf course", "leisure", "golf_course", "golf"),
        ("park", "leisure", "park", "parque"), ("cemetery", "landuse", "cemetery", "cementerio"),
        ("quarry", "landuse", "quarry", "cantera"), ("forest", "landuse", "forest", "forestación"),
        ("nature reserve", "leisure", "nature_reserve", "reserva")]


def pedir(url, pausa=1.2):
    with urllib.request.urlopen(urllib.request.Request(url, headers=AGENTE), timeout=120) as r:
        datos = json.load(r)
    time.sleep(pausa)  # la política de uso de OSM pide como mucho un pedido por segundo
    return datos


# ------------------------------------------------------------------ agua
def agua(args):
    import tifffile

    ruta = args.tif
    if not ruta:
        ruta = os.path.join(tempfile.gettempdir(), os.path.basename(JRC))
        if not os.path.exists(ruta):
            print("Bajando", JRC)
            urllib.request.urlretrieve(JRC, ruta)
    ocurrencia = tifffile.imread(ruta)  # 40000 × 40000, uint8: % de meses con agua; 255 = sin dato
    norte, oeste, sur, este = geo.CAJA
    f0, f1 = int((JRC_ORIGEN[1] - norte) / JRC_PASO) - 800, int((JRC_ORIGEN[1] - sur) / JRC_PASO) + 800
    c0, c1 = int((oeste - JRC_ORIGEN[0]) / JRC_PASO) - 800, int((este - JRC_ORIGEN[0]) / JRC_PASO) + 800
    rec = ocurrencia[f0:f1, c0:c1]
    rec = np.where(rec == 255, 0, rec).astype(np.float32)
    for capa, paso in (("80m", 80.0), ("20m", 20.0)):
        xs, ys = geo.grilla(paso)
        k = max(1, int(round(paso / 20)))  # submuestreo: la celda de JRC mide unos 25 m
        desvios = (np.arange(k) + 0.5) / k * paso - paso / 2
        suma = np.zeros((len(ys), len(xs)), dtype=np.float32)
        for dy in desvios:
            for dx in desvios:
                lat, lon = geo.latlon(xs[None, :] + dx, ys[:, None] + dy)
                f = np.floor((JRC_ORIGEN[1] - lat) / JRC_PASO).astype(int) - f0
                c = np.floor((lon - JRC_ORIGEN[0]) / JRC_PASO).astype(int) - c0
                suma += rec[f, c]
        media = np.rint(suma / (k * k)).astype(np.uint8)
        destino = os.path.join(FIJOS, f"agua_jrc_{capa}.npz")
        np.savez_compressed(destino, ocurrencia=media, fuente="JRC Global Surface Water v1.4, occurrence 1984-2021, tile 60W_30S")
        print(f"{destino}: {media.shape}, {os.path.getsize(destino) / 1e3:.0f} kB, celdas con ocurrencia >= 10 %: {(media >= 10).mean():.1%}")


# ------------------------------------------------------------------ contornos de OSM
def anillos_osm(objeto):
    """Anillos exteriores (lon, lat) de un way o de una relación multipolígono, por la API de OSM."""
    datos = pedir(f"https://api.openstreetmap.org/api/0.6/{objeto}/full.json")["elements"]
    nodos = {e["id"]: (round(e["lon"], 6), round(e["lat"], 6)) for e in datos if e["type"] == "node"}
    ways = {e["id"]: e["nodes"] for e in datos if e["type"] == "way"}
    tipo, ident = objeto.split("/")
    principal = next(e for e in datos if e["type"] == tipo and e["id"] == int(ident))
    if tipo == "way":
        tramos = [ways[int(ident)]]
    else:
        tramos = [ways[m["ref"]] for m in principal["members"] if m["type"] == "way" and m.get("role") in ("outer", "")]
    anillos, tramos = [], [list(t) for t in tramos]
    while tramos:  # une los tramos por las puntas hasta cerrar cada anillo
        actual = tramos.pop(0)
        while actual[0] != actual[-1]:
            for i, t in enumerate(tramos):
                if t[0] == actual[-1]:
                    actual += tramos.pop(i)[1:]
                    break
                if t[-1] == actual[-1]:
                    actual += tramos.pop(i)[-2::-1]
                    break
            else:
                break
        if actual[0] == actual[-1] and len(actual) >= 4:
            anillos.append([list(nodos[n]) for n in actual])
    return anillos, principal.get("tags", {})


def sitios(args):
    with open(os.path.join(AQUI, "sitios_registro.json"), encoding="utf-8") as fh:
        registro = json.load(fh)["sitios"]
    salida = {}
    for s in registro:
        if "osm" not in s:
            continue
        anillos, etiquetas = [], {}
        for objeto in s["osm"]:
            a, t = anillos_osm(objeto)
            anillos += a
            etiquetas = etiquetas or t
        ha = sum(geo.area_y_centro(a)[0] for a in anillos)
        lat, lon = geo.area_y_centro(max(anillos, key=lambda a: geo.area_y_centro(a)[0]))[1]
        lugar = pedir(f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=jsonv2&zoom=12&accept-language=es")
        d = lugar.get("address", {})
        salida[s["id"]] = {"osm": s["osm"], "etiquetas": etiquetas, "anillos": anillos,
                           "lugar_osm": d.get("city") or d.get("town") or d.get("village") or d.get("suburb") or d.get("county") or ""}
        print(f"{s['id']:24s} {len(anillos)} anillo(s), {ha:6.1f} ha, {salida[s['id']]['lugar_osm']}")
    with open(os.path.join(FIJOS, "contornos_osm.json"), "w", encoding="utf-8") as fh:
        json.dump({"fuente": "© colaboradores de OpenStreetMap, ODbL 1.0 (API de OSM y Nominatim)", "bajado": time.strftime("%Y-%m-%d"), "sitios": salida},
                  fh, ensure_ascii=False, separators=(",", ":"))


# ------------------------------------------------------------------ usos conocidos
def usos(args):
    norte, oeste, sur, este = geo.CAJA
    salida, vistos = [], set()
    for consulta, clase, tipo, etiqueta in USOS:
        hallados, excluir = [], []
        for _ in range(8):  # la búsqueda devuelve de a 50
            q = {"q": consulta, "viewbox": f"{oeste},{norte},{este},{sur}", "bounded": 1, "format": "jsonv2", "limit": 50}
            if excluir:
                q["exclude_place_ids"] = ",".join(map(str, excluir))
            r = pedir("https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(q))
            nuevos = [x for x in r if x["place_id"] not in excluir]
            if not nuevos:
                break
            excluir += [x["place_id"] for x in nuevos]
            hallados += [x for x in nuevos if x["category"] == clase and x["type"] == tipo and x["osm_type"] in ("way", "relation")]
        ids = sorted({x["osm_type"][0].upper() + str(x["osm_id"]) for x in hallados} - vistos)
        vistos |= set(ids)
        n = 0
        for i in range(0, len(ids), 50):
            r = pedir("https://nominatim.openstreetmap.org/lookup?" + urllib.parse.urlencode(
                {"osm_ids": ",".join(ids[i:i + 50]), "format": "json", "polygon_geojson": 1, "accept-language": "es"}))
            for x in r:
                g = x.get("geojson", {})
                partes = [g["coordinates"]] if g.get("type") == "Polygon" else g.get("coordinates", []) if g.get("type") == "MultiPolygon" else []
                anillos = [[[round(lon, 5), round(lat, 5)] for lon, lat in p[0]] for p in partes]
                if anillos:
                    salida.append({"osm": f"{x['osm_type']}/{x['osm_id']}", "uso": etiqueta, "nombre": x.get("name") or "", "anillos": anillos})
                    n += 1
        print(f"{etiqueta:12s} {n} polígonos")
    with open(os.path.join(FIJOS, "usos_osm.json"), "w", encoding="utf-8") as fh:
        json.dump({"fuente": "© colaboradores de OpenStreetMap, ODbL 1.0 (Nominatim)", "bajado": time.strftime("%Y-%m-%d"),
                   "advertencia": "No es exhaustivo: es lo que devuelve la búsqueda de Nominatim dentro de la caja del AMBA.",
                   "usos": salida}, fh, ensure_ascii=False, separators=(",", ":"))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("paso", choices=["agua", "sitios", "usos"])
    p.add_argument("--tif", help="tile de JRC ya bajado (si no, lo baja a la carpeta temporal)")
    args = p.parse_args()
    os.makedirs(FIJOS, exist_ok=True)
    globals()[args.paso](args)


if __name__ == "__main__":
    main()
