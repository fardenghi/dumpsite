#!/usr/bin/env python3
"""Datos del mapa que no entran en el bundle: se dejan en `public/datos/` y la web los pide al cargar.

    python3 scripts/datos_mapa.py

Lee (no modifica):
- `../data/basurales/basurales_mundo.json`: el catálogo de 66.981 basurales y rellenos.
- `../data/frames.json`: la caja y las fechas de cada frame de NISAR procesado.
- `../idea-basurales-nisar/salidas/manchas.geojson`: las manchas despiertas de todos los frames
  (el índice de insomnio por encima del umbral, vectorizado por `extraer_manchas.py`).
- `src/data/seed/veredictos.json`: el veredicto de cada mancha (`flujo.py --web`).
- `../idea-basurales-nisar/salidas/resumen_80m.json` y `calibracion_80m.json`: el embudo y la calibración del AMBA.

Escribe:
- `public/datos/catalogo.json`: el catálogo en columnas (lat, lon, estado, superficie, país, fuentes, nombre).
- `public/datos/manchas.geojson`: los polígonos de las manchas, simplificados, con su insomnio y su veredicto.
- `public/datos/frames.json`: las cajas de los frames.
- `src/data/seed/calibracion.json`: los números del panel Modelo (superficies, descartes, umbrales y su rango válido).

Sin dependencias. No inventa nada: lo que la fuente no trae queda vacío.
"""
import json
import os

AQUI = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.dirname(AQUI)
RAIZ = os.path.dirname(WEB)
SALIDA = os.path.join(WEB, "public", "datos")

ESTADO = {"desconocido": "d", "abierto": "a", "cerrado": "c", "contradictorio": "x"}
FUENTE = {"osm": 1, "climate_trace": 2, "epa_lmop": 4, "nasa_emit": 8, "curado_manual": 16}
# tolerancia de la simplificación de las manchas: un píxel del GUNW de 80 m
TOLERANCIA = 0.0009


def leer(*ruta):
    with open(os.path.join(*ruta), encoding="utf-8") as f:
        return json.load(f)


def escribir(nombre, dato):
    ruta = os.path.join(SALIDA, nombre)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(dato, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{nombre}: {os.path.getsize(ruta) / 1e6:.2f} MB")


def catalogo():
    mundo = leer(RAIZ, "data", "basurales", "basurales_mundo.json")
    sitios = mundo["sitios"]
    # el id es BAS-000001 en adelante, en orden: la web lo rearma con la posición
    assert all(s["id"] == f"BAS-{i + 1:06d}" for i, s in enumerate(sitios)), "los ids del catálogo no son correlativos"
    paises = sorted({s["pais"] for s in sitios if s.get("pais")})
    indice_pais = {p: i for i, p in enumerate(paises)}
    escribir("catalogo.json", {
        "generado": mundo["meta"].get("generado"),
        "origen": "data/basurales/basurales_mundo.json",
        "fuentes": {str(bit): mundo["meta"]["fuentes"][clave]["cita"] for clave, bit in FUENTE.items() if clave in mundo["meta"]["fuentes"]},
        "claves_fuente": {clave: bit for clave, bit in FUENTE.items()},
        "estados": {v: k for k, v in ESTADO.items()},
        "paises": paises,
        "n": len(sitios),
        "lat": [round(s["lat"], 4) for s in sitios],
        "lon": [round(s["lon"], 4) for s in sitios],
        "estado": "".join(ESTADO[s["estado"]] for s in sitios),
        # hectáreas con un decimal; -1 si la fuente no trae superficie
        "ha": [round(s["area_ha"], 1) if s.get("area_ha") is not None else -1 for s in sitios],
        "pais": [indice_pais[s["pais"]] if s.get("pais") else -1 for s in sitios],
        "fuente": [sum({FUENTE.get(f["fuente"], 0) for f in s.get("fuentes", [])}) for s in sitios],
        "nombre": {str(i): s["nombre"] for i, s in enumerate(sitios) if s.get("nombre")},
    })


def simplificar(anillo, tol=TOLERANCIA):
    """Douglas-Peucker sobre un anillo cerrado, sin recursión."""
    if len(anillo) < 6:
        return anillo
    queda = [False] * len(anillo)
    queda[0] = queda[-1] = True
    # el anillo es cerrado: se parte por el punto más lejano del primero para tener dos tramos abiertos
    lejos = max(range(len(anillo)), key=lambda i: (anillo[i][0] - anillo[0][0]) ** 2 + (anillo[i][1] - anillo[0][1]) ** 2)
    queda[lejos] = True
    pila = [(0, lejos), (lejos, len(anillo) - 1)]
    while pila:
        a, b = pila.pop()
        if b - a < 2:
            continue
        (x1, y1), (x2, y2) = anillo[a], anillo[b]
        dx, dy = x2 - x1, y2 - y1
        largo = (dx * dx + dy * dy) ** 0.5 or 1e-12
        peor, d_peor = -1, tol
        for i in range(a + 1, b):
            d = abs(dy * (anillo[i][0] - x1) - dx * (anillo[i][1] - y1)) / largo
            if d > d_peor:
                peor, d_peor = i, d
        if peor >= 0:
            queda[peor] = True
            pila += [(a, peor), (peor, b)]
    fino = [[round(p[0], 5), round(p[1], 5)] for p, q in zip(anillo, queda) if q]
    return fino if len(fino) >= 4 else [[round(p[0], 5), round(p[1], 5)] for p in anillo]


def geometria(g):
    if g["type"] == "Polygon":
        return {"type": "Polygon", "coordinates": [simplificar(a) for a in g["coordinates"]]}
    if g["type"] == "MultiPolygon":
        return {"type": "MultiPolygon", "coordinates": [[simplificar(a) for a in p] for p in g["coordinates"]]}
    return g


def manchas():
    crudo = leer(RAIZ, "idea-basurales-nisar", "salidas", "manchas.geojson")
    del_flujo = {v["id"]: v for v in leer(WEB, "src", "data", "seed", "veredictos.json")["sitios"] if v["tipo"] == "mancha"}
    veredicto = {i: v["veredicto"] for i, v in del_flujo.items()}
    # p: puntaje del clasificador de "basural contra otra cosa", si el flujo lo calculó; la web decide con qué umbral destacar
    puntaje = {i: round(v["p_basural"], 3) for i, v in del_flujo.items() if v.get("p_basural") is not None}
    features = []
    for f in crudo["features"]:
        p = f["properties"]
        features.append({
            "type": "Feature",
            "geometry": geometria(f["geometry"]),
            # v: el veredicto de flujo.py; las manchas chicas que el flujo no lista quedan como descartadas
            "properties": {"id": p["id_mancha"], "i": p["insomnio"], "v": veredicto.get(p["id_mancha"], "descartada"), "q": 1 if p.get("que") else 0,
                           **({"p": puntaje[p["id_mancha"]]} if p["id_mancha"] in puntaje else {})},
        })
    escribir("manchas.geojson", {
        "type": "FeatureCollection",
        "fuente": crudo.get("fuente"),
        "aviso": crudo.get("aviso"),
        "recorte": crudo.get("recorte"),
        "simplificacion": f"Douglas-Peucker, {TOLERANCIA}° (un píxel de 80 m)",
        "features": features,
    })
    print(f"  {len(features)} manchas en {len(crudo.get('frames', []))} frames")


def frames():
    escribir("frames.json", [
        {"frame": f["frame"], "ciudad": f.get("ciudad"), "pais": f.get("pais"), "bbox": f["bbox"], "pares": f.get("n_gunw"), "desde": f.get("fecha_inicio"), "hasta": f.get("fecha_fin")}
        for f in leer(RAIZ, "data", "frames.json")["frames"]
    ])


def rango_valido(tabla, clave, fija, valor_fijo, elegido):
    """Los valores seguidos de `clave` que cumplen la calibración alrededor del elegido, con `fija` en su valor elegido.
    Devuelve (desde, hasta, primer valor probado por encima que ya no cumple)."""
    cumple = {t[clave]: t["cumple"] for t in tabla if t[fija] == valor_fijo}
    valores = sorted(cumple)
    i = valores.index(elegido)
    assert cumple[elegido], f"el valor elegido de {clave} no cumple la calibración"
    a = b = i
    while a > 0 and cumple[valores[a - 1]]:
        a -= 1
    while b < len(valores) - 1 and cumple[valores[b + 1]]:
        b += 1
    return valores[a], valores[b], valores[b + 1] if b < len(valores) - 1 else None


def calibracion():
    salidas = os.path.join(RAIZ, "idea-basurales-nisar", "salidas")
    r = leer(salidas, "resumen_80m.json")
    c = leer(salidas, "calibracion_80m.json")
    p, sup, man, sitios, e = r["parametros"], r["superficie"], r["manchas"], r["sitios"], c["elegido"]
    razon = rango_valido(c["tabla"], "razon", "min_insomnio", e["min_insomnio"], e["razon"])
    insomnio = rango_valido(c["tabla"], "min_insomnio", "razon", e["razon"], e["min_insomnio"])
    # el eco mínimo queda entre lo liso con más eco y el relleno con menos eco
    liso = max(c["eco_db"]["lisos"].items(), key=lambda x: x[1])
    relleno = min(c["eco_db"]["rellenos"].items(), key=lambda x: x[1])
    nombre = lambda i: sitios[i]["nombre"].replace("Control: ", "")
    roles = [s["rol"] for s in sitios.values()]
    ruta = os.path.join(WEB, "src", "data", "seed", "calibracion.json")
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump({
            "origen": "idea-basurales-nisar/salidas/resumen_80m.json y calibracion_80m.json (pipeline_insomnio.py indice y calibrar)",
            "frame": r["frame"]["frame"],
            # el catálogo mundial con el que se entrena el clasificador
            "catalogo_sitios": len(leer(RAIZ, "data", "basurales", "basurales_mundo.json")["sitios"]),
            "superficie": {k: sup[k] for k in ("agua_ha", "tierra_ha", "candidata_ha", "estacional_ha")},
            "descartes": {"chicas": man["descartadas_chicas"], "lisas": man["descartadas_lisas"], "lineales": man["descartadas_lineales"]},
            "parametros": {k: p[k] for k in ("razon", "min_insomnio", "eco_min_db", "min_ha", "min_px_sitio")},
            "calibrado_con": {"rellenos": roles.count("calibracion"), "controles": roles.count("control")},
            "rangos": {
                "razon": {"desde": razon[0], "hasta": razon[1], "siguiente": razon[2]},
                "min_insomnio": {"desde": insomnio[0], "hasta": insomnio[1], "siguiente": insomnio[2]},
                "eco_min_db": {"desde": liso[1], "hasta": relleno[1], "liso": nombre(liso[0]), "relleno": nombre(relleno[0])},
            },
            # el relleno de calibración que queda afuera cuando se sube el insomnio mínimo
            "testigo": {"nombre": sitios["norte-iii"]["nombre"], "insomnio": sitios["norte-iii"]["insomnio"]},
        }, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print("seed/calibracion.json")


if __name__ == "__main__":
    os.makedirs(SALIDA, exist_ok=True)
    catalogo()
    manchas()
    frames()
    calibracion()
