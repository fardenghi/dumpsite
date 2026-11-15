"""Genera versiones chicas y FALSAS de cada archivo de `contratos.py`, para probar código antes de tener datos reales.

    python herramientas/contratos_mock.py                       # escribe en datos/mock/ (no se sube al repo)
    python herramientas/contratos_mock.py --manchas-por-frame 60 --semilla 3 --salida otra/carpeta

Los archivos quedan todos en la misma carpeta, con el nombre del contrato, y son coherentes entre sí: los
`id_mancha` y los `id_catalogo` cruzan de un archivo al otro. Además escribe `catalogo_mock.geojson`, con los
polígonos de catálogo que usa el mock, para probar `cruce_manchas.py` sin los catálogos reales.

TODOS LOS VALORES SON INVENTADOS. No son resultados: no se citan, no van a la web ni al pitch.
Lo único real son los identificadores y los valores de radar de tres sitios del AMBA (Norte III, González
Catán y Luján), copiados de `salidas/fichas_80m.json`, para que el veredicto de prueba dé lo mismo que el real.

Qué hay en cada frame (con 10 manchas por frame, el valor por defecto):
  - 2 manchas sobre un basural y 4 sobre un negativo (aeropuerto, cantera, contenedores, humedal): son las que se etiquetan;
  - 1 mancha que toca un basural y un negativo a la vez, y 1 que apenas roza un negativo (menos del 30 %): no se etiquetan;
  - 2 manchas que no tocan nada: son las que hay que predecir;
  - 3 manchas descartadas (chica, lineal y lisa), que sólo están en `manchas.geojson`;
  - polígonos de catálogo sin mancha: un basural cerrado y quieto, uno abierto y quieto, uno de menos de 10 ha,
    un cultivo quieto y una obra chica.
Fuera del AMBA hay además un basural cerrado con una mancha encima ("cerrado pero despierto").
El AMBA es de Argentina, así que va a `prueba_final`; los otros tres frames son las particiones.
"""
import argparse
import json
import math
import os
import sys

import numpy as np
import pandas as pd

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import contratos as ct  # noqa: E402

SALIDA = os.path.join(AQUI, "datos", "mock")
AVISO = "DATOS FALSOS generados por herramientas/contratos_mock.py. No son resultados."

# bbox = [lon_oeste, lat_sur, lon_este, lat_norte]. Órbitas y fechas inventadas, salvo las del AMBA.
FRAMES = (
    dict(frame="AMBA", orbita=[10, 161], ciudad="Buenos Aires", pais="ARG", hemisferio="S", epsg=32721,
         bbox=[-59.35, -34.90, -58.25, -34.25], n_gunw=15, fecha_inicio="2026-06-25", fecha_fin="2026-10-12",
         reservado_prueba=True, frames_nisar=["010_D_106"]),
    dict(frame="DELHI", orbita=[27], ciudad="Delhi", pais="IND", hemisferio="N", epsg=32643,
         bbox=[76.80, 28.30, 77.60, 28.95], n_gunw=11, fecha_inicio="2026-06-20", fecha_fin="2026-10-30", reservado_prueba=False),
    dict(frame="CDMX", orbita=[92, 143], ciudad="Ciudad de México", pais="MEX", hemisferio="N", epsg=32614,
         bbox=[-99.45, 19.10, -98.80, 19.75], n_gunw=14, fecha_inicio="2026-06-22", fecha_fin="2026-11-01", reservado_prueba=False),
    dict(frame="NAIROBI", orbita=[64], ciudad="Nairobi", pais="KEN", hemisferio="S", epsg=32737,
         bbox=[36.60, -1.55, 37.20, -1.00], n_gunw=9, fecha_inicio="2026-07-01", fecha_fin="2026-10-23", reservado_prueba=False),
)

# Sitios reales del AMBA: id del catálogo, complejo, estado, área, y (insomnio, persistencia, eco_db) de fichas_80m.json.
AMBA_REALES = {
    "despierto_1": dict(id="BAS-053304", complejo="CPX-015400", nombre="Complejo Ambiental Norte III (CEAMSE)", estado="abierto",
                        area_ha=71.5, radar=(0.86, 0.6, -9.9)),
    "despierto_2": dict(id="BAS-000001", complejo="CPX-000001", nombre="Complejo Ambiental González Catán (CEAMSE)", estado="desconocido",
                        area_ha=155.16, radar=(1.0, 1.0, -11.6)),
    "cerrado_quieto": dict(id="BAS-000007", complejo="CPX-000007", nombre="Basural de Luján", estado="cerrado",
                           area_ha=43.72, radar=(0.0, 0.0, -7.5)),
    "aeropuerto": dict(id="NEG-AMBA-000931", nombre="Aeropuerto El Palomar", area_ha=303.8),
}

# Perfil medio de cada tipo de superficie: eco, hv_hh, ndvi, bsi, ndwi, b11, b12. Inventado, pero con el signo esperado.
PERFILES = {
    "basural": (-10.0, -7.0, 0.18, 0.12, -0.25, 0.28, 0.22),
    "aeropuerto": (-12.0, -10.0, 0.45, -0.02, -0.40, 0.22, 0.14),
    "cantera": (-9.0, -8.0, 0.10, 0.20, -0.15, 0.33, 0.28),
    "puerto_playa_contenedores": (-5.0, -9.0, 0.08, 0.05, -0.10, 0.25, 0.22),
    "humedal": (-11.5, -6.0, 0.50, -0.15, -0.10, 0.15, 0.08),
    "obra": (-9.5, -8.5, 0.15, 0.18, -0.20, 0.30, 0.25),
    "chatarreria_desguace": (-6.5, -9.0, 0.12, 0.08, -0.15, 0.24, 0.20),
    "cultivo": (-11.0, -6.5, 0.60, -0.10, -0.45, 0.20, 0.10),
}
NEGATIVOS_DESPIERTOS = ("aeropuerto", "cantera", "puerto_playa_contenedores", "humedal", "obra", "chatarreria_desguace")
ESTADOS_DESPIERTOS = ("abierto", "desconocido", "abierto", "desconocido", "cerrado")
ANILLO = (-10.5, -7.5, 0.42, 0.00, -0.38, 0.22, 0.14)  # el entorno "típico"


# ------------------------------------------------------------------ geometría (rectángulos en metros locales)
class Plano:
    """Metros locales (x al este, y al norte) desde la esquina sudoeste del bbox, y de vuelta a grados."""

    def __init__(self, bbox):
        self.lon0, self.lat0 = bbox[0], bbox[1]
        self.my = 111_320.0
        self.mx = 111_320.0 * math.cos(math.radians((bbox[1] + bbox[3]) / 2))
        self.ancho, self.alto = (bbox[2] - bbox[0]) * self.mx, (bbox[3] - bbox[1]) * self.my

    def lonlat(self, x, y):
        return round(self.lon0 + x / self.mx, 6), round(self.lat0 + y / self.my, 6)

    def poligono(self, r):
        x0, y0, x1, y1 = r
        return {"type": "Polygon", "coordinates": [[list(self.lonlat(*q)) for q in ((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0))]]}


def rect(cx, cy, ancho, alto):
    return (cx - ancho / 2, cy - alto / 2, cx + ancho / 2, cy + alto / 2)


def cuadrado(cx, cy, ha):
    lado = math.sqrt(ha * 1e4)
    return rect(cx, cy, lado, lado)


def area_ha(r):
    return (r[2] - r[0]) * (r[3] - r[1]) / 1e4


def interseccion_ha(a, b):
    w, h = min(a[2], b[2]) - max(a[0], b[0]), min(a[3], b[3]) - max(a[1], b[1])
    return w * h / 1e4 if w > 0 and h > 0 else 0.0


def celdas(plano, n, rng):
    """n centros de celda que no se pisan, en orden aleatorio. Cada celda tiene que alojar un polígono de 300 ha."""
    lado = math.sqrt(plano.ancho * plano.alto / (n * 1.3))
    if lado < 3500:
        raise SystemExit(f"No entran {n} sitios en el frame sin pisarse: bajá --manchas-por-frame.")
    cols, filas = int(plano.ancho // lado), int(plano.alto // lado)
    orden = rng.permutation(cols * filas)[:n]
    return [((i % cols + 0.5) * lado, (i // cols + 0.5) * lado) for i in orden]


# ------------------------------------------------------------------ un frame
def roles(n):
    """El papel de cada mancha candidata. Las primeras 10 cubren todos los casos; el resto repite los que se etiquetan."""
    base = ["basural", "basural", "negativo", "negativo", "negativo", "negativo", "nada", "nada", "ambos", "roce"]
    extra = ["basural", "negativo", "negativo", "nada"]
    return (base + [extra[i % len(extra)] for i in range(max(n - len(base), 0))])[:max(n, 1)]


def armar_frame(fr, n_manchas, rng, contador):
    """Devuelve (manchas, catálogo) del frame: listas de diccionarios con su rectángulo y lo que hace falta para las tablas."""
    plano = Plano(fr["bbox"])
    es_amba = fr["frame"] == "AMBA"
    papeles = roles(n_manchas)
    sin_mancha = ["cerrado_quieto", "abierto_quieto", "basural_chico", "cultivo_quieto", "obra_chica"]
    if not es_amba:
        papeles = papeles + ["cerrado_despierto"]
    centros = iter(celdas(plano, len(papeles) + 3 + len(sin_mancha), rng))
    manchas, catalogo = [], []
    n_bas = n_neg = 0

    def nuevo_id(pref):
        contador[pref] += 1
        return f"{pref}-{900000 + contador[pref]:06d}"

    def basural(r, estado, real=None, **extra):
        d = dict(id_catalogo=real["id"] if real else nuevo_id("BAS"), catalogo="basurales", frame=fr["frame"], rect=r,
                 estado=real["estado"] if real else estado, clase=None, nombre=real["nombre"] if real else None,
                 area_ha=real["area_ha"] if real else round(area_ha(r), 2), **extra)
        d["complejo"] = real["complejo"] if real else d["id_catalogo"].replace("BAS", "CPX")
        d["radar_real"] = real.get("radar") if real else None
        catalogo.append(d)
        return d

    def negativo(r, clase, real=None, **extra):
        d = dict(id_catalogo=real["id"] if real else nuevo_id("NEG"), catalogo="negativos", frame=fr["frame"], rect=r, estado=None,
                 clase=clase, nombre=real["nombre"] if real else None, complejo=None, radar_real=None,
                 area_ha=real["area_ha"] if real else round(area_ha(r), 2), **extra)
        catalogo.append(d)
        return d

    def mancha(r, tipo, papel, descartada=None, forma=None):
        ancho, alto = r[2] - r[0], r[3] - r[1]
        elong = max(ancho, alto) / min(ancho, alto)
        manchas.append(dict(rect=r, tipo=tipo, papel=papel, descartada=descartada, elongacion=round(max(elong, 1.0), 1),
                            forma=forma or ("alargada" if elong >= 2.5 else "compacta"),
                            compacidad=round(4 * math.pi * ancho * alto / (2 * (ancho + alto)) ** 2, 3)))

    def encima(p, cubre=(0.55, 0.95)):
        """Una mancha que cubre buena parte del rectángulo p, un poco corrida."""
        ancho, alto = p[2] - p[0], p[3] - p[1]
        w, h = max(ancho * rng.uniform(*cubre), 330), max(alto * rng.uniform(*cubre), 330)
        return rect((p[0] + p[2]) / 2 + rng.uniform(-0.15, 0.15) * ancho, (p[1] + p[3]) / 2 + rng.uniform(-0.15, 0.15) * alto, w, h)

    for papel in papeles:
        cx, cy = next(centros)
        if papel in ("basural", "cerrado_despierto"):
            n_bas += 1
            real = AMBA_REALES.get(f"despierto_{n_bas}") if es_amba else None
            estado = "cerrado" if papel == "cerrado_despierto" else ESTADOS_DESPIERTOS[(n_bas - 1) % len(ESTADOS_DESPIERTOS)]
            p = cuadrado(cx, cy, real["area_ha"] if real else rng.uniform(20, 160))
            basural(p, estado, real, radar="despierto")
            mancha(encima(p), "basural", "basural")
        elif papel == "negativo":
            n_neg += 1
            clase = NEGATIVOS_DESPIERTOS[(n_neg - 1) % len(NEGATIVOS_DESPIERTOS)]
            real = AMBA_REALES["aeropuerto"] if es_amba and n_neg == 1 else None
            p = cuadrado(cx, cy, real["area_ha"] if real else rng.uniform(250, 320) if clase == "aeropuerto" else rng.uniform(15, 150))
            negativo(p, clase, real, radar="despierto")
            mancha(encima(p, (0.35, 0.6) if clase == "aeropuerto" else (0.55, 0.95)), clase, "negativo")
        elif papel == "ambos":  # un basural y una cantera pegados, y la mancha arriba de los dos
            lado = math.sqrt(rng.uniform(25, 60) * 1e4)
            basural(rect(cx - lado / 2 - 50, cy, lado, lado), "desconocido", radar="despierto")
            negativo(rect(cx + lado / 2 + 50, cy, lado, lado), "cantera", radar="despierto")
            mancha(rect(cx, cy, lado * 1.2, lado * 0.8), "basural", "ambos")
        elif papel == "roce":  # la mancha pisa el 10 % del negativo: no alcanza para etiquetarla
            lado = math.sqrt(rng.uniform(20, 60) * 1e4)
            negativo(rect(cx - lado * 0.45, cy, lado, lado), "cultivo", radar="intermedio")
            mancha(rect(cx + lado * 0.45, cy, lado, lado), str(rng.choice(list(PERFILES))), "roce")
        else:  # nada: lo que hay que predecir
            ha = rng.uniform(10.5, 90)
            ancho = math.sqrt(ha * 1e4 * rng.uniform(1.0, 2.4))
            mancha(rect(cx, cy, ancho, ha * 1e4 / ancho), str(rng.choice(list(PERFILES))), "nada")

    for motivo, (ancho, alto), forma in (("chica", (240, 240), None), ("lineal", (2400, 160), "lineal"), ("lisa", (640, 560), None)):
        cx, cy = next(centros)
        mancha(rect(cx, cy, ancho, alto), "cultivo", "descartada", descartada=motivo, forma=forma)

    for caso in sin_mancha:
        cx, cy = next(centros)
        if caso == "cerrado_quieto":
            real = AMBA_REALES[caso] if es_amba else None
            basural(cuadrado(cx, cy, real["area_ha"] if real else rng.uniform(15, 80)), "cerrado", real, radar="quieto")
        elif caso == "abierto_quieto":
            basural(cuadrado(cx, cy, rng.uniform(12, 40)), "abierto", radar="quieto")
        elif caso == "basural_chico":
            basural(cuadrado(cx, cy, rng.uniform(2, 8)), "desconocido", radar="chico")
        elif caso == "cultivo_quieto":
            negativo(cuadrado(cx, cy, rng.uniform(30, 150)), "cultivo", radar="quieto")
        else:
            negativo(cuadrado(cx, cy, rng.uniform(2, 8)), "obra", radar="chico")

    # Como `insomnio.manchas()`: de mayor a menor superficie, y de ahí sale el número del id.
    manchas.sort(key=lambda m: -area_ha(m["rect"]))
    for i, m in enumerate(manchas, 1):
        m.update(id_mancha=ct.id_mancha(fr["frame"], i), etiqueta=i, frame=fr["frame"], ha=round(area_ha(m["rect"]), 1),
                 geometry=plano.poligono(m["rect"]))
        m["lon"], m["lat"] = plano.lonlat((m["rect"][0] + m["rect"][2]) / 2, (m["rect"][1] + m["rect"][3]) / 2)
    for c in catalogo:
        c["geometry"] = plano.poligono(c["rect"])
    return manchas, catalogo


# ------------------------------------------------------------------ valores
def r2(v, n=2):
    return round(float(v), n)


def optico(tipo, rng, fr):
    """Las columnas ópticas de una superficie de ese tipo, con ruido."""
    _, _, ndvi, bsi, ndwi, b11, b12 = PERFILES[tipo]
    v = dict(ndvi_media=ndvi + rng.normal(0, 0.05), ndvi_variacion=abs(rng.normal(0.03 if tipo != "cultivo" else 0.12, 0.01)),
             bsi_media=bsi + rng.normal(0, 0.04), ndwi_media=ndwi + rng.normal(0, 0.04),
             swir_b11=max(b11 + rng.normal(0, 0.03), 0.01), swir_b12=max(b12 + rng.normal(0, 0.03), 0.01))
    aro = dict(zip(("ndvi", "bsi", "ndwi", "swir_b11", "swir_b12"), np.array(ANILLO[2:]) + rng.normal(0, 0.04, 5)))
    v.update(ndvi_contraste=v["ndvi_media"] - aro["ndvi"], bsi_contraste=v["bsi_media"] - aro["bsi"],
             ndwi_contraste=v["ndwi_media"] - aro["ndwi"], swir_b11_contraste=v["swir_b11"] - aro["swir_b11"],
             swir_b12_contraste=v["swir_b12"] - aro["swir_b12"])
    v = {k: r2(x, 3) for k, x in v.items()}
    dias = pd.date_range(fr["fecha_inicio"], fr["fecha_fin"], freq="D").strftime("%Y-%m-%d").to_numpy()
    n = int(rng.integers(6, 9))
    v["n_escenas"] = n
    v["fechas"] = ",".join(sorted(rng.choice(dias, n, replace=False)))
    return v


def radar_mancha(m, rng, fr):
    eco, hv = PERFILES[m["tipo"]][:2]
    ins = rng.uniform(0.70, 1.0)
    agua = rng.uniform(0.10, 0.40) if m["tipo"] == "humedal" else rng.uniform(0, 0.12)
    urbano = rng.uniform(0, 0.8) * (1 - agua)
    eco_m = float(np.clip(eco + rng.normal(0, 1.2), -12.9, -2.0))  # nunca menos de −13 dB: sería "lisa" y estaría descartada
    return dict(
        id_mancha=m["id_mancha"], frame=m["frame"], insomnio=r2(ins), persistencia=r2(rng.uniform(0.5, ins)),
        contraste_mediana=r2(rng.uniform(0.45, 0.75)), contraste_desvio=r2(rng.uniform(0.05, 0.15)),
        coherencia_media=r2(rng.uniform(0.20, 0.40)), tendencia=r2(rng.normal(0, 0.0005), 5),
        n_pares=fr["n_gunw"], n_orbitas=len(fr["orbita"]),
        eco_db=r2(eco_m, 1), eco_contraste=r2(eco_m - ANILLO[0] + rng.normal(0, 0.8), 1),
        eco_variacion=r2(abs(rng.normal(1.2 if m["tipo"] == "basural" else 0.6, 0.3)), 2), hv_hh=r2(hv + rng.normal(0, 1.2), 1),
        area_ha=m["ha"], elongacion=m["elongacion"], compacidad=m["compacidad"],
        agua_anillo=r2(agua), urbano_anillo=r2(urbano), cultivo_anillo=r2(rng.uniform(0, 1 - agua - urbano)),
    )


def radar_catalogo(c, rng, fr):
    """La fila de `insomnio_catalogo` de un polígono, con el veredicto de `insomnio.ficha()` que le toca en el mock."""
    eco = PERFILES["basural" if c["catalogo"] == "basurales" else c["clase"]][0]
    eco = r2(np.clip(eco + rng.normal(0, 1.0), -12.9, -2.0), 1)
    n = fr["n_gunw"]
    if c["radar_real"]:
        ins, per, eco = c["radar_real"]
        radar = "despierto" if ins >= 0.70 else "quieto"
        motivo = "valores reales de salidas/fichas_80m.json"
    elif c["radar"] == "despierto":
        ins = r2(rng.uniform(0.75, 1.0))
        per, radar, motivo = r2(rng.uniform(0.5, ins)), "despierto", "coherencia baja respecto del anillo en casi todos los pares"
    elif c["radar"] == "quieto":
        ins, per, radar, motivo = r2(rng.uniform(0, 0.15)), 0.0, "quieto", "coherencia igual o mayor que la del anillo en casi todos los pares"
    elif c["radar"] == "intermedio":
        ins = r2(rng.uniform(0.30, 0.60))
        per, radar, motivo = r2(rng.uniform(0, 0.3)), "no_alcanza", "señal intermedia: ni quieto ni despierto"
    else:  # chico
        ins = per = eco = None
        radar, motivo, n = "no_alcanza", "el predio ocupa menos de 8 píxeles de 80 m", 0
    return dict(id_catalogo=c["id_catalogo"], catalogo=c["catalogo"], complejo=c["complejo"], frame=c["frame"], insomnio=ins,
                persistencia=per, eco_db=eco, n_pares=n, radar=radar, motivo=motivo, area_ha=c["area_ha"], estado=c["estado"],
                clase=c["clase"])


def p_basural(m, rng):
    lo, hi = {"basural": (0.70, 0.98), "negativo": (0.02, 0.30), "ambos": (0.40, 0.80)}.get(m["papel"], (0.05, 0.90))
    if m["papel"] in ("nada", "roce") and m["tipo"] == "basural":
        lo, hi = 0.60, 0.95
    return r2(rng.uniform(lo, hi))


# ------------------------------------------------------------------ todo
def generar(salida=SALIDA, manchas_por_frame=10, semilla=0):
    """Escribe todos los archivos del mock en `salida` y devuelve {nombre: ruta}."""
    rng = np.random.default_rng(semilla)
    contador = {"BAS": 0, "NEG": 0}
    manchas, catalogo, frames = [], [], []
    for fr in FRAMES:
        m, c = armar_frame(fr, manchas_por_frame, rng, contador)
        manchas += m
        catalogo += c
        grandes = [x for x in c if x["area_ha"] >= ct.MIN_HA]
        frames.append({
            **fr,
            "n_basurales_10ha": {e: sum(x["estado"] == e for x in grandes if x["catalogo"] == "basurales") for e in ct.ESTADOS_FRAME},
            "n_negativos": pd.Series([x["clase"] for x in c if x["catalogo"] == "negativos"]).value_counts().sort_index().to_dict(),
        })
    por_frame = {f["frame"]: f for f in frames}
    candidatas = [m for m in manchas if m["descartada"] is None]

    radar = pd.DataFrame([radar_mancha(m, rng, por_frame[m["frame"]]) for m in candidatas])
    tabla_optico = pd.DataFrame([{"id_mancha": m["id_mancha"], "frame": m["frame"], **optico(m["tipo"], rng, por_frame[m["frame"]])}
                                 for m in candidatas])
    insomnio_cat = pd.DataFrame([radar_catalogo(c, rng, por_frame[c["frame"]]) for c in catalogo])
    optico_cat = pd.DataFrame([{"id_catalogo": c["id_catalogo"], "catalogo": c["catalogo"], "frame": c["frame"],
                                **optico("basural" if c["catalogo"] == "basurales" else c["clase"], rng, por_frame[c["frame"]])}
                               for c in catalogo])
    cruce = pd.DataFrame([
        dict(id_mancha=m["id_mancha"], id_catalogo=c["id_catalogo"], catalogo=c["catalogo"], frame=m["frame"],
             frac_mancha=r2(i / area_ha(m["rect"]), 3), frac_poligono=r2(i / area_ha(c["rect"]), 3),
             frac_area_menor=r2(i / min(area_ha(m["rect"]), area_ha(c["rect"])), 3), complejo=c["complejo"], clase_negativo=c["clase"])
        for m in candidatas for c in catalogo
        if c["frame"] == m["frame"] and (i := interseccion_ha(m["rect"], c["rect"])) > 0
    ])
    predicciones = pd.DataFrame([dict(id_mancha=m["id_mancha"], frame=m["frame"], p_basural=p_basural(m, rng)) for m in candidatas])

    # La regla de la etapa 6: la mancha se etiqueta si se cruza (30 % del área menor) con polígonos de un solo catálogo.
    fuerte = cruce[cruce["frac_area_menor"] >= ct.CRITERIO_CRUCE]
    un_catalogo = fuerte.groupby("id_mancha")["catalogo"].transform("nunique") == 1
    mejor = fuerte[un_catalogo].sort_values("frac_area_menor", ascending=False).drop_duplicates("id_mancha")
    etiquetas = pd.DataFrame({
        "id_mancha": mejor["id_mancha"], "id_catalogo": mejor["id_catalogo"],
        "complejo": mejor["complejo"].fillna(mejor["id_catalogo"]),
        "clase_negativo": mejor["clase_negativo"],
        "clase": mejor["catalogo"].map({"basurales": "basural_activo", "negativos": "otro_movil"}),
    })
    entrenamiento = (etiquetas.merge(radar, on="id_mancha").merge(tabla_optico.drop(columns=["frame", "n_escenas", "fechas"]), on="id_mancha")
                     .sort_values("id_mancha").reset_index(drop=True))
    entrenamiento["ciudad"] = entrenamiento["frame"].map(lambda f: por_frame[f]["ciudad"])
    entrenamiento["pais"] = entrenamiento["frame"].map(lambda f: por_frame[f]["pais"])
    libres = [f["frame"] for f in frames if not f["reservado_prueba"]]
    particiones = {
        "meta": {"mock": True, "aviso": AVISO, "umbral_insomnio": 0.70, "criterio_cruce": ct.CRITERIO_CRUCE, "semilla": semilla,
                 "filas_por_clase": entrenamiento.groupby(["frame", "clase"]).size().unstack(fill_value=0).to_dict("index")},
        "particiones": {str(i): [f] for i, f in enumerate(libres)},
        ct.PRUEBA_FINAL: [f["frame"] for f in frames if f["reservado_prueba"]],
    }

    os.makedirs(salida, exist_ok=True)
    rutas = {}

    def escribir_json(nombre, contenido):
        rutas[nombre] = os.path.join(salida, nombre if "." in nombre else os.path.basename(ct.ruta(nombre, salida)))
        with open(rutas[nombre], "w", encoding="utf-8") as f:
            json.dump(contenido, f, ensure_ascii=False, indent=1)

    props = ("id_mancha", "frame", "ha", "forma", "descartada", "etiqueta", "elongacion", "lat", "lon")
    resumen = radar.set_index("id_mancha")
    feats = []
    for m in manchas:
        p = {k: m[k] for k in props}
        if m["descartada"] is None:
            p.update(insomnio=float(resumen.at[m["id_mancha"], "insomnio"]), persistencia=float(resumen.at[m["id_mancha"], "persistencia"]),
                     eco_db=float(resumen.at[m["id_mancha"], "eco_db"]))
        else:
            p.update(insomnio=r2(rng.uniform(0.70, 1.0)), persistencia=r2(rng.uniform(0.5, 0.7)),
                     eco_db=r2(rng.uniform(-19, -14), 1) if m["descartada"] == "lisa" else r2(rng.uniform(-12, -8), 1))
        p["nucleo"] = 0.05 if m["descartada"] == "lineal" else r2(rng.uniform(0.3, 0.8))
        feats.append({"type": "Feature", "properties": p, "geometry": m["geometry"]})
    escribir_json("manchas", {"type": "FeatureCollection", "mock": True, "aviso": AVISO, "features": feats})
    escribir_json("frames", {"meta": {"mock": True, "aviso": AVISO, "semilla": semilla}, "frames": frames})
    escribir_json(ct.PARTICIONES, particiones)
    escribir_json("catalogo_mock.geojson", {
        "type": "FeatureCollection", "mock": True, "aviso": AVISO + " Las geometrías son rectángulos inventados, también las de los ids reales.",
        "features": [{"type": "Feature", "geometry": c["geometry"],
                      "properties": {k: c[k] for k in ("id_catalogo", "catalogo", "frame", "nombre", "estado", "clase", "complejo", "area_ha")}}
                     for c in catalogo]})
    for nombre, df in (("tabla_radar", radar), ("tabla_optico", tabla_optico), ("tabla_optico_catalogo", optico_cat),
                       ("insomnio_catalogo", insomnio_cat), ("cruce_manchas_catalogo", cruce), ("predicciones", predicciones),
                       ("tabla_entrenamiento", entrenamiento)):
        rutas[nombre] = ct.guardar(df, nombre, salida)

    # Se relee todo desde el disco: lo que se valida es lo que van a leer los demás.
    for nombre in ct.NOMBRES:
        ct.leer(salida, nombre)
    ct.validar_particiones(particiones, frames=[f["frame"] for f in frames])
    return rutas


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--salida", default=SALIDA, help="carpeta de destino (por defecto, datos/mock/)")
    ap.add_argument("--manchas-por-frame", type=int, default=10, help="manchas candidatas por frame (por defecto 10)")
    ap.add_argument("--semilla", type=int, default=0)
    a = ap.parse_args()
    rutas = generar(a.salida, a.manchas_por_frame, a.semilla)
    print(AVISO)
    for nombre, camino in rutas.items():
        filas = ""
        if camino.endswith(".parquet"):
            filas = f"{len(pd.read_parquet(camino)):4d} filas"
        elif camino.endswith(".geojson"):
            with open(camino, encoding="utf-8") as f:
                filas = f"{len(json.load(f)['features']):4d} features"
        print(f"  {os.path.relpath(camino):55s} {filas}")
    print("Todo validado contra herramientas/contratos.py.")


if __name__ == "__main__":
    main()
