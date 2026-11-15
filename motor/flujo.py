"""Etapa 9: el flujo completo sobre los frames procesados (veredicto por sitio, matriz de actividad y salida para la web).

Recorre los frames de `../data/frames.json` que ya tienen `salidas/<FRAME>/insomnio_catalogo.parquet` (los sube la
etapa 4) y, para cada uno, junta lo que haya:

| Entrada                          | De dónde, en orden                                                                     |
|----------------------------------|----------------------------------------------------------------------------------------|
| `insomnio_catalogo.parquet`      | `salidas/<FRAME>/`; el AMBA, mientras no llegue `salidas/AMBA/`, se calcula con       |
|                                  | `insomnio_catalogo.py --modo aproximado` en `datos/flujo/AMBA/` (y se dice)            |
| `manchas.geojson`                | `salidas/<FRAME>/`; el AMBA, `salidas/manchas.geojson` (lo vectorizó el prompt 3)      |
| `cruce_manchas_catalogo.parquet` | `salidas/<FRAME>/` o `salidas/` (prompt 4); si no está o no corresponde a esas         |
|                                  | manchas, se calcula con las funciones de `cruce_manchas.py` en `datos/flujo/<FRAME>/`  |
| `predicciones.parquet`           | `salidas/<FRAME>/` o `salidas/` (prompt 4). Si no está, las manchas sin catálogo       |
|                                  | salen `sin_clasificar`                                                                 |

Escribe (todo lo propio del prompt 5):
- `salidas/veredictos.json`: un veredicto por polígono del catálogo de basurales y por mancha sin catálogo.
- `salidas/evaluacion_actividad.json`: la matriz de abierto contra cerrado por país, con Wilson, con todas las fuentes
  del estado y sin los cerrados de OSM; los casos para mirar a mano con los descartes automáticos.
- `salidas/resumen_flujo.json`: los conteos de la frase del pitch por frame y en total, y qué entró de cada frame.
- `idea/resultados-flujo.md` y, con `--web`, `../insomnes-web/src/data/seed/veredictos.json` (y `modelo.json` si hay
  `salidas/metricas.json`).

Lo quieto no pasa por el modelo: "cerrado y quieto" sale del registro y del insomnio del polígono (`veredicto.py`).

    python flujo.py                         # todos los frames que haya
    python flujo.py --frame LOS_ANGELES AMBA
    python flujo.py --web                   # además, la salida para la web
"""
import argparse
import datetime as dt
import json
import math
import os
import re
import sys

import numpy as np
import pandas as pd

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
DATA = os.path.join(RAIZ, "data", "catalogos")
SALIDAS = os.path.join(RAIZ, "data", "salidas")
CACHE = os.path.join(AQUI, "datos", "flujo")
WEB_SEED = os.path.join(RAIZ, "web", "src", "data", "seed")
sys.path.insert(0, AQUI)
import contratos  # noqa: E402
import evaluar_actividad as ea  # noqa: E402
import veredicto as ve  # noqa: E402
import veredicto_estado as vest  # noqa: E402  (el modelo de abierto contra cerrado, al lado de la regla; no cambia veredictos)

FUENTES_TODAS = ("epa_lmop", "curado_manual", "osm")
FUENTES_SIN_OSM = ("epa_lmop", "curado_manual")
VECINO_KM = 1.5  # el anillo de control mide 1,5 km


def _rel(p):
    return None if p is None else os.path.relpath(p, RAIZ)


def _json(obj, ruta):
    os.makedirs(os.path.dirname(os.path.abspath(ruta)), exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1,
                  default=lambda o: o.item() if isinstance(o, np.generic) else (None if o is pd.NA else str(o)))
        fh.write("\n")


# ---------------------------------------------------------------- entradas por frame
def frames_conocidos():
    """Frames de frames.json en el orden de prioridad (el AMBA primero)."""
    with open(os.path.join(DATA, "frames.json"), encoding="utf-8") as fh:
        fr = json.load(fh)
    lista = fr["frames"] if isinstance(fr, dict) else fr
    return {f["frame"]: f for f in lista}


def _ids_manchas(manchas):
    return set() if manchas is None else set(manchas["id_mancha"])


def _filtrar(df, frame):
    if df is None or "frame" not in df:
        return None
    sub = df[df["frame"] == frame]
    return sub if len(sub) else None


def insomnio_catalogo_de(frame, salidas, cache, aproximar_amba=True):
    """(DataFrame, ruta, nota) o (None, None, motivo)."""
    ruta = os.path.join(salidas, frame, "insomnio_catalogo.parquet")
    if os.path.exists(ruta):
        return contratos.leer(ruta), ruta, None
    if frame == "AMBA" and aproximar_amba and os.path.exists(os.path.join(salidas, "indice_80m.npz")):
        destino = os.path.join(cache, "AMBA")
        ruta = os.path.join(destino, "insomnio_catalogo.parquet")
        if not os.path.exists(ruta):
            import insomnio_catalogo as icat
            icat.main(["--modo", "aproximado", "--indice", os.path.join(salidas, "indice_80m.npz"), "--salida", destino])
        return (contratos.leer(ruta), ruta,
                "AMBA en modo aproximado (mediana por píxel de indice_80m.npz): falta salidas/AMBA/ de la etapa 4")
    return None, None, "sin insomnio_catalogo.parquet"


def manchas_de(frame, salidas):
    ruta = os.path.join(salidas, frame, "manchas.geojson")
    if not os.path.exists(ruta) and frame == "AMBA":
        ruta = os.path.join(salidas, "manchas.geojson")
    if not os.path.exists(ruta):
        return None, None
    m = _filtrar(contratos.leer(ruta), frame)
    return (m, ruta) if m is not None else (None, None)


def _calcular_cruce(ruta_manchas, frame, cache):
    """Con las funciones de cruce_manchas.py (sin modificarlo). Se cachea en datos/flujo/<FRAME>/."""
    destino = os.path.join(cache, frame)
    ruta = os.path.join(destino, "cruce_manchas_catalogo.parquet")
    if os.path.exists(ruta) and os.path.getmtime(ruta) >= os.path.getmtime(ruta_manchas):
        return contratos.leer(ruta), ruta
    import catalogo_poligonos as cp
    import cruce_manchas as cm
    with open(ruta_manchas, encoding="utf-8") as fh:
        fc = json.load(fh)
    ms = [(p, g) for p, g in cp.manchas(fc, solo_candidatas=True) if p["frame"] == frame]
    if not ms:
        return None, None
    df, _ = cm.cruzar_por_frame(ms, fc, lambda bbox: cp.catalogo(bbox, "ambos"))
    contratos.guardar(df, "cruce_manchas_catalogo", destino)
    return df, ruta


def cruce_de(frame, salidas, manchas, ruta_manchas, cache):
    """El del prompt 4 si corresponde a estas manchas; si no, calculado. (df, ruta, origen)."""
    ids = _ids_manchas(manchas)
    for ruta in (os.path.join(salidas, frame, "cruce_manchas_catalogo.parquet"),
                 os.path.join(salidas, "cruce_manchas_catalogo.parquet")):
        if os.path.exists(ruta):
            df = _filtrar(contratos.leer(ruta), frame)
            if df is not None and set(df["id_mancha"]) <= ids:
                return df, ruta, "prompt_4"
    if ruta_manchas is None:
        return None, None, None
    df, ruta = _calcular_cruce(ruta_manchas, frame, cache)
    return df, ruta, None if df is None else "calculado_por_flujo"


def predicciones_de(frame, salidas, manchas):
    ids = _ids_manchas(manchas)
    for ruta in (os.path.join(salidas, frame, "predicciones.parquet"), os.path.join(salidas, "predicciones.parquet")):
        if os.path.exists(ruta):
            df = contratos.leer(ruta)
            df = _filtrar(df, frame) if "frame" in df else df
            if df is not None:
                df = df[df["id_mancha"].isin(ids)] if ids else df
                if len(df):
                    return df, ruta
    return None, None


# ---------------------------------------------------------------- modelo
def estado_modelo(salidas):
    """¿Hay un modelo validado? Sólo si `metricas.json` no es una prueba de humo y valida por frame."""
    ruta = os.path.join(salidas, "metricas.json")
    if not os.path.exists(ruta):
        return {"hay_metricas": False, "validado": False, "motivo": "no hay salidas/metricas.json (prompt 4)"}
    with open(ruta, encoding="utf-8") as fh:
        m = json.load(fh)
    texto = f"{m.get('validacion', '')} {m.get('advertencia', '')}".lower()
    if "humo" in texto:
        return {"hay_metricas": True, "validado": False, "motivo": "metricas.json es una prueba de humo", "metricas": m}
    frames = (m.get("fuera_de_particion") or {}).get("por_frame") or m.get("por_frame") or {}
    afuera = [f for f in frames if f != "AMBA"]
    if len(afuera) < 3:
        return {"hay_metricas": True, "validado": False, "metricas": m,
                "motivo": f"métrica por frame en {len(afuera)} frames de fuera de Argentina (hacen falta 3)"}
    return {"hay_metricas": True, "validado": True, "motivo": f"validado en {len(afuera)} frames", "metricas": m}


# ---------------------------------------------------------------- catálogo (para mirar a mano)
def sitios_catalogo():
    """id -> sitio de basurales_mundo.json (coordenadas, fuentes, operador)."""
    with open(os.path.join(DATA, "basurales", "basurales_mundo.json"), encoding="utf-8") as fh:
        return {s["id"]: s for s in json.load(fh)["sitios"]}


def _km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


PATRON_PLANTA = re.compile(r"transfer|recycl|recicl|compost|material recovery|mrf|c&d|construction|demolition|"
                           r"inert|organics|green ?waste|planta|ecoparque", re.I)


def descartes(caso, sitio, veredictos_frame, cat):
    """Lo obvio que se puede chequear solo, sin mirar imágenes. Devuelve (lista de chequeos, resultado)."""
    ch = []
    nombres = [caso.get("nombre") or ""]
    biogas, superfund = False, False
    for f in (sitio or {}).get("fuentes", []):
        d = f.get("datos") or {}
        nombres.append(d.get("nombre") or "")
        et = d.get("etiquetas") or {}
        nombres += [et.get("name") or "", et.get("description") or ""]
        if str(d.get("captura_biogas", "")).lower() == "yes":
            biogas = True
        if "USEPA" in f"{et.get('operator', '')} {et.get('ref', '')}" or "sfund" in str(et.get("url", "")):
            superfund = True
    planta = sorted({n for n in nombres if n and PATRON_PLANTA.search(n)})
    abierto = caso["registro"] == "abierto"

    # 1. una celda vecina activa: otro basural despierto del mismo complejo o a menos de 1,5 km del borde
    vecinos = []
    if sitio:
        for v in veredictos_frame:
            if v["tipo"] != "catalogo" or v["id"] == caso["id_catalogo"] or v["radar"] != "despierto":
                continue
            s2 = cat.get(v["id"])
            if s2 is None:
                continue
            r1 = math.sqrt((caso.get("area_ha") or 0) * 1e4 / math.pi) / 1e3
            r2 = math.sqrt((v.get("area_ha") or 0) * 1e4 / math.pi) / 1e3
            dist = _km((sitio["lat"], sitio["lon"]), (s2["lat"], s2["lon"])) - r1 - r2
            mismo = caso.get("complejo") and v.get("complejo") == caso.get("complejo")
            if mismo or dist < VECINO_KM:
                vecinos.append(f"{v['id']} {v.get('nombre') or ''} ({v['registro']}, "
                               f"{'mismo complejo' if mismo else f'a {max(dist, 0):.1f} km'})".replace("  ", " "))
    if not abierto:
        if vecinos:
            ch.append({"chequeo": "celda vecina activa", "resultado": "no se descarta",
                       "detalle": "basural despierto pegado: " + "; ".join(vecinos[:4])})
        else:
            ch.append({"chequeo": "celda vecina activa", "resultado": "descartado",
                       "detalle": f"ningún otro basural despierto del mismo complejo ni a menos de {VECINO_KM:g} km"})
        ch.append({"chequeo": "planta de transferencia o reciclaje en el predio",
                   "resultado": "no se descarta" if planta else "sin indicio en el nombre",
                   "detalle": ("el nombre lo sugiere: " + "; ".join(planta)) if planta else
                   "los nombres del catálogo no la mencionan; falta mirar óptico"})
        ch.append({"chequeo": "planta o pozos de biogás",
                   "resultado": "no se descarta" if biogas else "sin dato",
                   "detalle": "LMOP: captura de biogás = Yes (pozos, cañerías y mantenimiento mueven el suelo)" if biogas
                   else "el registro no lo dice"})
        ch.append({"chequeo": "obras de cierre o remediación",
                   "resultado": "no se descarta" if superfund or _cierre_reciente(caso) else "sin dato",
                   "detalle": ("sitio Superfund de la EPA (remediación)" if superfund else
                               f"cerró en {caso.get('fecha_cierre')}: puede haber obras de cierre" if _cierre_reciente(caso)
                               else "no hay dato de obras en el registro")})
    else:
        ch.append({"chequeo": "frente de descarga más chico que el píxel", "resultado": "no se descarta",
                   "detalle": f"el polígono mide {caso.get('area_ha')} ha; un frente activo de 1 a 3 ha no mueve la mediana"})
        ch.append({"chequeo": "registro desactualizado", "resultado": "no se descarta",
                   "detalle": "el estado de la EPA (LMOP) es de 2024-09; pudo cerrar después"})
    if any(c["resultado"] == "no se descarta" for c in ch):
        return ch, "hay una explicación obvia sin descartar"
    return ch, PASA


PASA = "pasa los chequeos automáticos; falta mirarlo en óptico"


def _cierre_reciente(caso):
    try:
        return int(str(caso.get("fecha_cierre"))[:4]) >= 2020
    except (TypeError, ValueError):
        return False


def casos_para_mirar(ev, veredictos, cat):
    por_frame = {}
    for v in veredictos:
        por_frame.setdefault(v["frame"], []).append(v)
    salida = {}
    for clave, lista in ev["discordantes"].items():
        filas = []
        for s in lista:
            sitio = cat.get(s["id_catalogo"])
            ch, res = descartes(s, sitio, por_frame.get(s["frame"], []), cat)
            filas.append({**{k: s.get(k) for k in ("frame", "pais", "id_catalogo", "nombre", "complejo", "area_ha", "registro",
                                                   "fuentes_estado", "fecha_cierre", "radar", "insomnio")},
                          "lat": None if sitio is None else sitio["lat"], "lon": None if sitio is None else sitio["lon"],
                          "chequeos": ch, "resultado": res})
        salida[clave] = sorted(filas, key=lambda f: (f["resultado"] != PASA,
                                                     -(f["insomnio"] or 0)))
    return salida


# ---------------------------------------------------------------- flujo
def correr(frames=None, salidas=SALIDAS, cache=CACHE, aproximar_amba=True):
    """Devuelve (veredictos, por_frame, ic_todo, entradas, modelo)."""
    conocidos = frames_conocidos()
    pedidos = frames or list(conocidos)
    modelo = estado_modelo(salidas)
    veredictos, por_frame, ics, entradas = [], {}, [], {}
    for fr in pedidos:
        ic, ruta_ic, nota = insomnio_catalogo_de(fr, salidas, cache, aproximar_amba)
        if ic is None:
            entradas[fr] = {"procesado": False, "motivo": nota}
            continue
        ic = ic[ic["frame"] == fr]
        manchas, ruta_m = manchas_de(fr, salidas)
        cruce, ruta_c, origen_c = cruce_de(fr, salidas, manchas, ruta_m, cache)
        pred, ruta_p = predicciones_de(fr, salidas, manchas)
        vs = ve.calcular(ic, cruce, manchas, pred, frame=fr)
        if manchas is not None:  # qué dice OSM de cada mancha sin catálogo (contexto para la web, no decide)
            info = manchas.set_index("id_mancha")
            for v in vs:
                if v["tipo"] == "mancha" and v["id"] in info.index:
                    r = info.loc[v["id"]]
                    v["que"] = r.get("que") if isinstance(r.get("que"), str) else None
                    v["clase_osm"] = r.get("clase_osm") if isinstance(r.get("clase_osm"), str) else None
        veredictos += vs
        ics.append(ic)
        f = conocidos.get(fr, {})
        por_frame[fr] = {"ciudad": f.get("ciudad"), "pais": f.get("pais"), "reservado_prueba": bool(f.get("reservado_prueba")),
                         **ve.resumen(vs)}
        entradas[fr] = {"procesado": True, "insomnio_catalogo": _rel(ruta_ic),
                        "modo_insomnio": sorted(ic["modo"].dropna().unique().tolist()) if "modo" in ic else None,
                        "manchas": _rel(ruta_m), "n_manchas_candidatas": None if manchas is None else int(manchas["descartada"].isna().sum()),
                        "cruce": _rel(ruta_c), "cruce_origen": origen_c, "predicciones": _rel(ruta_p), "nota": nota}
    ic_todo = pd.concat(ics, ignore_index=True) if ics else None
    return veredictos, por_frame, ic_todo, entradas, modelo


def frase(total, modelo, frames):
    n = len(frames)
    base = f"En los {n} frames procesados ({', '.join(frames)})"
    if modelo["validado"]:
        return (f"{base}, el radar y el modelo encuentran {total['activos']} basurales activos: "
                f"{total['activos_ya_conocidos']} ya estaban en los catálogos y {total['posibles_nuevos']} son nuevos; "
                f"y de los conocidos, {total['cerrados_pero_despiertos']} figuran cerrados pero siguen despiertos.")
    return (f"{base}, el radar ve despiertos {total['activos_ya_conocidos']} basurales que ya estaban en los catálogos; "
            f"de ellos, {total['cerrados_pero_despiertos']} figuran cerrados pero siguen despiertos (sin verificar a mano), y "
            f"{total['cerrados_y_quietos']} figuran cerrados y salen quietos. (Sin modelo validado: no se cuentan nuevos.)")


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--frame", nargs="+", help="sólo estos frames (por defecto, todos los de frames.json que tengan datos)")
    a.add_argument("--salidas", default=SALIDAS)
    a.add_argument("--destino", default=SALIDAS, help="dónde escribir veredictos, evaluación y resumen")
    a.add_argument("--estado-conocido", default=os.path.join(SALIDAS, "estado_conocido.json"))
    a.add_argument("--web", action="store_true", help="escribir también ../insomnes-web/src/data/seed/veredictos.json")
    a.add_argument("--md", default=os.path.join(AQUI, "datos", "resultados-flujo.md"), help="'' para no escribirlo")
    args = a.parse_args(argv)

    vs, por_frame, ic, entradas, modelo = correr(args.frame, args.salidas)
    if ic is None:
        sys.exit("Ningún frame tiene insomnio_catalogo.parquet todavía.")
    vest.anotar(vs, args.salidas)  # suma `modelo_estado` a cada polígono de basural, si `modelo_estado.py` ya corrió
    frames = list(por_frame)
    ahora = dt.datetime.now().isoformat(timespec="seconds")
    total = ve.resumen(vs)
    total["frase"] = frase(total, modelo, frames)
    aviso = "Señal compatible con actividad, no prueba. Lo quieto es 'quieto según el radar'. Acotado a los frames procesados."

    # matriz de actividad (etapa 8), con y sin los cerrados de OSM
    with open(args.estado_conocido, encoding="utf-8") as fh:
        ec = json.load(fh)
    ec = {**ec, "frames": {k: v for k, v in ec["frames"].items() if not args.frame or k in args.frame}}
    ev = ea.evaluar(ec, ic, FUENTES_TODAS)
    ev_sin_osm = ea.evaluar(ec, ic, FUENTES_SIN_OSM)
    cat = sitios_catalogo()
    casos = casos_para_mirar(ev, vs, cat)
    paises = sorted(ev["por_pais"])
    sesgo = (f"El estado conocido sale casi todo de la EPA (EE. UU.): de los {len(ev['sitios'])} sitios "
             f"de estado conocido que el radar midió, {sum(1 for s in ev['sitios'] if s['pais'] == 'USA')} son de EE. UU. "
             f"La matriz vale para los países donde hay sitios ({', '.join(paises)}), no 'en el mundo'.")
    eval_json = {
        "meta": {"generado": ahora, "generado_por": "herramientas/flujo.py (evaluar_actividad.evaluar)",
                 "frames": frames, "modo_insomnio": {f: e.get("modo_insomnio") for f, e in entradas.items() if e["procesado"]},
                 "fuentes_del_estado": list(FUENTES_TODAS), "min_ha": contratos.MIN_HA,
                 "lectura": ("Filas: estado del registro. Columnas: lo que dice el radar sobre el polígono. Las tasas se "
                             "calculan sobre los que el radar pudo decidir; ic95 es el intervalo de Wilson."),
                 "sesgo": sesgo, "aviso": aviso,
                 "firms": "no se consultó: falta la variable de entorno FIRMS_MAP_KEY" if not os.environ.get("FIRMS_MAP_KEY")
                 else "pendiente"},
        **ev,
        "sin_cerrados_osm": {"fuentes_del_estado": list(FUENTES_SIN_OSM), "total": ev_sin_osm["total"],
                             "por_pais": ev_sin_osm["por_pais"]},
        "casos_para_mirar": casos,
    }
    _json(eval_json, os.path.join(args.destino, "evaluacion_actividad.json"))
    _json({"meta": {"generado": ahora, "generado_por": "herramientas/flujo.py", "frames": frames,
                    "umbral_p_basural": 0.5, "criterio_cruce": contratos.CRITERIO_CRUCE, "modelo": _sin_metricas(modelo),
                    "aviso": aviso},
           "resumen": total, "veredictos": vs}, os.path.join(args.destino, "veredictos.json"))
    resumen_json = {"meta": {"generado": ahora, "generado_por": "herramientas/flujo.py", "aviso": aviso},
                    "frames_procesados": frames, "entradas": entradas, "modelo": _sin_metricas(modelo),
                    "total": total, "por_frame": por_frame,
                    "actividad": {p: d["metricas"] for p, d in ev["por_pais"].items()}, "sesgo": sesgo}
    _json(resumen_json, os.path.join(args.destino, "resumen_flujo.json"))
    if args.web:
        escribir_web(vs, total, frames, modelo, ahora, estado=vest.bloque_web(args.salidas))
    if args.md:
        escribir_md(args.md, resumen_json, eval_json, vs, extra=vest.lineas_md(args.salidas))

    for fr, r in por_frame.items():
        print(f"{fr:20s} {r['complejos_por_veredicto']}  manchas: {r['manchas_por_veredicto']}")
    for p, d in ev["por_pais"].items():
        m = d["matriz"]
        print(f"  {p}: abierto {m['abierto']}  cerrado {m['cerrado']}")
    print(total["frase"])
    return resumen_json, eval_json


def _sin_metricas(modelo):
    return {k: v for k, v in modelo.items() if k != "metricas"}


# ---------------------------------------------------------------- web y markdown
def escribir_web(vs, total, frames, modelo, ahora, carpeta=WEB_SEED, estado=None):
    """Archivos nuevos en el seed de la web; no toca los que ya están. `estado` es el bloque del modelo de abierto
    contra cerrado (`veredicto_estado.bloque_web`): va en la clave `estado` de `modelo.json`."""
    claves = ("tipo", "id", "frame", "nombre", "complejo", "area_ha", "registro", "radar", "insomnio", "persistencia",
              "p_basural", "veredicto", "veredicto_texto", "motivo", "lat", "lon", "que")
    cat = sitios_catalogo()
    filas = []
    for v in vs:
        if v["tipo"] == "mancha" and v["veredicto"] == "sin_clasificar" and not modelo["validado"]:
            continue  # sin modelo, la web no muestra las manchas sueltas como veredicto
        f = {k: v.get(k) for k in claves}
        if v["tipo"] == "catalogo" and v["id"] in cat:
            f["lat"], f["lon"] = cat[v["id"]]["lat"], cat[v["id"]]["lon"]
        if v.get("modelo_estado"):
            f["modelo_estado"] = v["modelo_estado"]
        filas.append(f)
    _json({"generado": ahora, "generado_por": "idea-basurales-nisar/herramientas/flujo.py", "frames": frames,
           "aviso": "Señal compatible con actividad, no prueba.", "resumen": total, "sitios": filas},
          os.path.join(carpeta, "veredictos.json"))
    if modelo.get("hay_metricas") or estado:
        m = modelo.get("metricas") or {}
        _json({"generado": ahora, "generado_por": "idea-basurales-nisar/herramientas/flujo.py (desde salidas/metricas.json)",
               "validado": modelo["validado"], "motivo": modelo["motivo"],
               "metricas": {k: m.get(k) for k in ("validacion", "advertencia", "umbral", "columnas", "filas",
                                                  "fuera_de_particion", "importancia")} if m else None,
               **({"estado": estado} if estado else {})},
              os.path.join(carpeta, "modelo.json"))


def _tasa(t):
    if t["n"] == 0:
        return "—"
    return f"{t['k']}/{t['n']} ({t['tasa']:.0%}, IC95 {t['ic95'][0]:.0%}–{t['ic95'][1]:.0%})"


def escribir_md(ruta, rs, ev, vs, extra=None):
    L = ["# Resultados del flujo (etapas 8 y 9)", "",
         f"Generado por `herramientas/flujo.py` el {rs['meta']['generado']} (`python flujo.py --web` desde `herramientas/`). "
         "No editar a mano: se rehace con cada frame nuevo. Salidas: `salidas/veredictos.json`, "
         "`salidas/evaluacion_actividad.json` y `salidas/resumen_flujo.json`.", "",
         "**Lenguaje:** \"señal compatible con actividad\" y \"quieto según el radar\". Nada de esto es una acusación.", "",
         "## La frase del pitch", "", f"> {rs['total']['frase']}", "",
         f"- Modelo: {rs['modelo']['motivo']}. " + ("Por eso la frase no tiene X ni Z (activos totales y nuevos)."
                                                   if not rs["modelo"]["validado"] else ""),
         "- Cada complejo cuenta una vez, con su veredicto más activo. El registro sale de `complejos.json` (todas las fuentes, "
         "también los sin estado propio que toman el del complejo), así que los conteos de la frase pueden ser más que los "
         "de la matriz de actividad, que sólo usa `estado_conocido.json`.",
         "- Los \"cerrados pero despiertos\" son señal compatible con actividad: ver la lista para mirar a mano antes de nombrar uno.", "",
         "## Frames procesados", "",
         "| Frame | País | Insomnio del catálogo | Cruce | Predicciones | Activos conocidos | Cerrados despiertos | Cerrados quietos | Quietos (abiertos o sin estado) | No alcanza |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for fr, r in rs["por_frame"].items():
        e = rs["entradas"][fr]
        c = r["complejos_por_veredicto"]
        L.append(f"| `{fr}`{' (prueba final)' if r['reservado_prueba'] else ''} | {r['pais']} | {', '.join(e['modo_insomnio'] or [])} | "
                 f"{e['cruce_origen'] or '—'} | {'sí' if e['predicciones'] else 'no'} | {c.get('activo_conocido', 0)} | "
                 f"{c.get('cerrado_despierto', 0)} | {c.get('cerrado_quieto', 0)} | {c.get('quieto_radar', 0)} | {c.get('no_alcanza', 0)} |")
    faltan = [f for f, e in rs["entradas"].items() if not e["procesado"]]
    notas = [f"`{f}`: {e['nota']}" for f, e in rs["entradas"].items() if e.get("nota")]
    L += ["", f"Sin procesar todavía: {', '.join(f'`{f}`' for f in faltan) or 'ninguno'}."] + [f"- {n}" for n in notas]

    L += ["", "## Controles del AMBA", ""]
    amba = [v for v in vs if v["frame"] == "AMBA" and v["id"] in ("BAS-000007", "BAS-053304", "BAS-000001")]
    for v in amba:
        L.append(f"- **{v['nombre']}** (`{v['id']}`): registro {v['registro']}, radar {v['radar']}, insomnio {v['insomnio']} → "
                 f"**{v['veredicto_texto']}**. {v['motivo']}.")

    L += ["", "## Matriz de actividad (etapa 8)", "",
          "Filas: estado del registro. Columnas: lo que dice el radar sobre el polígono. Tasas sobre los que el radar pudo decidir; "
          "intervalo de Wilson al 95 %.", ""]
    for titulo, bloque in (("Con todas las fuentes del estado (EPA, casos curados y OSM)", ev),
                           ("Sin los cerrados de OSM (sin fecha de cierre)", ev["sin_cerrados_osm"])):
        L += [f"### {titulo}", "", "| País | Abiertos despiertos | Abiertos quietos | Cerrados quietos | Cerrados despiertos | No alcanza | Concordancia |",
              "|---|---|---|---|---|---|---|"]
        for p, d in list(bloque["por_pais"].items()) + [("Total", bloque["total"])]:
            mt = d["metricas"]
            L.append(f"| {p} | {_tasa(mt['abiertos_que_salen_despiertos'])} | {_tasa(mt['abiertos_que_salen_quietos'])} | "
                     f"{_tasa(mt['cerrados_que_salen_quietos'])} | {_tasa(mt['cerrados_que_salen_despiertos'])} | "
                     f"{_tasa(mt['el_radar_no_alcanza'])} | {_tasa(mt['concordancia'])} |")
        L.append("")
    usa = ev["por_pais"].get("USA")
    if usa:
        a_d, c_d = usa["metricas"]["abiertos_que_salen_despiertos"], usa["metricas"]["cerrados_que_salen_despiertos"]
        if a_d["n"] and c_d["n"]:
            L += ["**Lectura honesta (EE. UU.):** "
                  f"salen despiertos el {a_d['tasa']:.0%} de los abiertos y el {c_d['tasa']:.0%} de los cerrados. "
                  + ("Con estos intervalos, el insomnio solo **no separa** abiertos de cerrados en EE. UU.: muchos cerrados "
                     "siguen moviéndose (biogás, asentamiento, obras, vegetación). No se puede decir \"el radar detecta el cierre\" "
                     "en general; sí mostrar casos puntuales, como Luján, con su contexto."
                     if c_d["ic95"][1] >= a_d["ic95"][0] else
                     "Los intervalos no se tocan: el insomnio separa abiertos de cerrados en esta muestra."), ""]
    L += [f"- Sitios de estado conocido sin polígono o fuera de la grilla: {ev['sin_poligono_o_fuera_de_grilla']}; "
          f"de menos de 10 ha: {ev['chicos_menos_de_min_ha']}.",
          f"- Frames de estado conocido sin procesar (sitios grandes esperando): {ev['frames_sin_procesar']}.",
          f"- **Sesgo:** {ev['meta']['sesgo']}",
          f"- **FIRMS:** {ev['meta']['firms']}.", ""]

    L += list(extra or [])
    L += ["## Casos para mirar a mano", "",
          "Antes de que un caso llegue al pitch hay que descartar lo obvio. Los chequeos automáticos usan sólo el catálogo "
          "(nombres de OSM, Overture y la EPA; captura de biogás de LMOP; sitios Superfund; vecinos despiertos). Lo que dice "
          "\"no se descarta\" o \"sin dato\" falta mirarlo en óptico (Sentinel-2) antes de usarlo.", ""]
    for clave, titulo in (("cerrados_pero_despiertos", "Cerrados pero despiertos"), ("abiertos_pero_quietos", "Abiertos pero quietos")):
        L += [f"### {titulo} ({len(ev['casos_para_mirar'][clave])})", "",
              "| Sitio | Frame | País | ha | Insomnio | Cierre | Fuente del estado | Chequeos | Resultado |", "|---|---|---|---|---|---|---|---|---|"]
        for c in ev["casos_para_mirar"][clave]:
            chs = "<br>".join(f"{x['chequeo']}: **{x['resultado']}** ({x['detalle']})" for x in c["chequeos"])
            L.append(f"| {c['nombre']} (`{c['id_catalogo']}`, {c['lat']:.4f}, {c['lon']:.4f}) | `{c['frame']}` | {c['pais']} | "
                     f"{c['area_ha']} | {c['insomnio']} | {c['fecha_cierre'] or '—'} | {', '.join(c['fuentes_estado'])} | {chs} | {c['resultado']} |")
        L.append("")

    L += ["## Formato para la web", "",
          "`python flujo.py --web` escribe archivos **nuevos** en `insomnes-web/src/data/seed/` (no toca los que ya están):", "",
          "- `veredictos.json`: `{generado, generado_por, frames, aviso, resumen, sitios: [...]}`. Cada sitio: `tipo` "
          "(`catalogo` o `mancha`), `id` (`BAS-…` o `MAN-<frame>-<n>`), `frame`, `nombre`, `complejo`, `area_ha`, `registro` "
          "(`abierto`, `cerrado`, `desconocido`, `no_figura`), `radar` (`despierto`, `quieto`, `no_alcanza`), `insomnio`, "
          "`persistencia`, `p_basural` (null sin modelo), `veredicto` (clave), `veredicto_texto` (para mostrar), `motivo`, "
          "`lat`, `lon` y `que` (lo que dice OSM de una mancha). Sin modelo validado no van las manchas `sin_clasificar`. "
          "Los polígonos de basural traen además `modelo_estado`: `{p_abierto, lectura, origen}`, del modelo de abierto contra "
          "cerrado (`modelo_estado.py`); no cambia el veredicto.",
          "- `modelo.json`: sólo cuando exista `salidas/metricas.json`; `validado` dice si se puede mostrar como resultado. "
          "La clave `estado` trae el modelo de abierto contra cerrado: `{auc, ic95, n, abiertos, cerrados, frames, variables, "
          "validacion, limites, prueba_amba}`.",
          "- Las claves de `veredicto`: " + ", ".join(f"`{k}` ({t})" for k, t in ve.TEXTOS.items()) + ".", "",
          "## Fuentes", "",
          "- NISAR L2 GUNW (NASA/ISRO, vía ASF DAAC): insomnio por polígono (`insomnio_catalogo.parquet`, etapa 4).",
          "- Estado del registro: EPA LMOP (dominio público, EE. UU.), OpenStreetMap vía Overture Maps (ODbL) y casos curados "
          "de Argentina (`data/basurales/casos_curados_argentina.json`, con sus fuentes).",
          "- Agua: JRC Global Surface Water (Copernicus, CC BY 4.0).", ""]
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))


if __name__ == "__main__":
    main()
