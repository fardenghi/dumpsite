"""Count of dump sites in Argentina from data/catalogos/basurales/basurales_mundo.json.

Sites that only come from OSM have no country, so they are located with the Natural Earth 10m
boundary (public domain). Usage:
    python conteo_argentina.py <ne_10m_admin_0_countries.geojson> <ne_10m_admin_1_states_provinces.geojson> <output.csv>
Category: assigned from the site name (OSM / Climate TRACE). The catalog's `tipo` field
is no use: Climate TRACE labels almost everything as "relleno sanitario".
"""
import csv, json, re, sys, collections as C
from pathlib import Path
from shapely.geometry import shape, Point
from shapely.prepared import prep

RAIZ = Path(__file__).resolve().parents[1]

CATEGORIAS = [  # (category, regex over the lowercase name), in priority order
    ("No es RSU (minería, nuclear, autos, industrial, humedal)",
     r"botadero|uranio|radioactiv|cementerio de autos|ceniza|humedal|ex canteras|razzini"),
    ("Ex basural / cerrado o antiguo", r"^ex |\bex basural|viejo|antiguo|clausurad"),
    ("Planta de tratamiento o reciclaje", r"planta|recicla|ecoplan|gfo"),
    ("Relleno sanitario o complejo de disposición final",
     r"relleno|ceamse|complejo|environmental complex|disposici|landfill|ecoparque|girsu|contenedor|ecoazul|celda|bower|piedras blancas|fachinal|^río cuarto$|san javier|galindo|lixiviad"),
    ("Microbasural o basural informal", r"micro|mini basural|informal|ramas"),
    ("Basural a cielo abierto / basurero / vertedero municipal",
     r"basur|vertedero|dump|predio|maría sara|basurál"),
]


def categoria(nombre):
    n = (nombre or "").lower().strip()
    if not n:
        return "Sin nombre en OSM"
    for cat, rx in CATEGORIAS:
        if re.search(rx, n):
            return cat
    return "Otro"


def main(ne0, ne1, salida):
    paises = json.load(open(ne0))["features"]
    arg = shape(next(f for f in paises if f["properties"]["ADM0_A3"] == "ARG")["geometry"])
    parg, pbuf = prep(arg), prep(arg.buffer(0.02))  # ~2 km for the coast
    otros = [prep(shape(f["geometry"])) for f in paises if f["properties"]["ADM0_A3"] != "ARG"]
    provs = [(f["properties"]["name"], prep(shape(f["geometry"]).buffer(0.02)))
             for f in json.load(open(ne1))["features"] if f["properties"]["adm0_a3"] == "ARG"]
    mundo = json.load(open(RAIZ / "data/catalogos/basurales/basurales_mundo.json"))
    filas = []
    for s in mundo["sitios"]:
        if s.get("pais") not in (None, "ARG"):
            continue
        p = Point(s["lon"], s["lat"])
        if not (parg.contains(p) or (pbuf.contains(p) and not any(o.contains(p) for o in otros))):
            continue
        fuentes = sorted({f["fuente"] for f in s["fuentes"]})
        filas.append({
            "id": s["id"], "nombre": s.get("nombre") or "", "categoria": categoria(s.get("nombre")),
            "provincia": next((n for n, g in provs if g.contains(p)), ""),
            "lat": s["lat"], "lon": s["lon"], "area_ha": s.get("area_ha"),
            "estado": s["estado"], "fuentes": "+".join(fuentes),
            "plumas_emit": s.get("plumas_metano_emit") or 0,
            "co2e_100yr_t_climate_trace": (s.get("emisiones_climate_trace") or {}).get("co2e_100yr_t"),
        })
    with open(salida, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0]))
        w.writeheader(); w.writerows(filas)
    print(len(filas), "sitios")
    for k in ("categoria", "provincia", "estado", "fuentes"):
        print(k, C.Counter(r[k] for r in filas).most_common())


if __name__ == "__main__":
    main(*sys.argv[1:4])
