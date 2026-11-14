"""Pipeline del índice de insomnio sobre el AMBA con NISAR (Idea B).

Pasos (se pueden correr sueltos o todos con `todo`):
  buscar    consulta la API pública de ASF y guarda la lista de GUNW (y GCOV) sobre el AMBA
  bajar     baja los .h5 con earthaccess (credenciales por variable de entorno), en paralelo
  procesar  recorta la coherencia (y el backscatter de los GCOV, si hay) a una grilla común del AMBA, en paralelo
  indice    calcula el índice de insomnio final (insomnio.py), las fichas por sitio, las manchas candidatas,
            la figura y los archivos que lee la web (insomnes-web/)
  calibrar  barre los umbrales y dice con cuáles entran los sitios conocidos y no entran los controles

Con los recortes ya hechos, un solo comando reproduce todo lo que se informa:
  python pipeline_insomnio.py indice

Desde cero (en la VM):
  python pipeline_insomnio.py todo --datos /mnt/datos --orbitas 10 161 --capa 80m

Credenciales: EARTHDATA_TOKEN, o EARTHDATA_USERNAME y EARTHDATA_PASSWORD. Nunca en el repo.
"""
import argparse
import concurrent.futures as cf
import glob
import json
import math
import os
import re
import sys
import urllib.parse
import urllib.request

import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import geo  # noqa: E402
import insomnio as ins  # noqa: E402
from geo import CAJA, grilla  # noqa: E402

IDEA = os.path.dirname(AQUI)
FIJOS = os.path.join(AQUI, "fijos")
WEB = os.path.join(os.path.dirname(IDEA), "insomnes-web")
POLIGONO_AMBA = "POLYGON((-59.35 -34.25,-58.25 -34.25,-58.25 -34.90,-59.35 -34.90,-59.35 -34.25))"
API_ASF = "https://api.daac.asf.alaska.edu/services/search/param"
CAPAS = {
    "80m": ("unwrappedInterferogram", 80.0),
    "20m": ("wrappedInterferogram", 20.0),
}


# ---------------------------------------------------------------- grilla común
def recortar(ds, xs_src, ys_src, xs_dst, ys_dst):
    """Lleva ds (2D) a la grilla destino por vecino más cercano. Lee sólo la ventana necesaria."""
    dx, dy = xs_src[1] - xs_src[0], ys_src[1] - ys_src[0]
    cols = np.rint((xs_dst - xs_src[0]) / dx).astype(int)
    filas = np.rint((ys_dst - ys_src[0]) / dy).astype(int)
    vc = (cols >= 0) & (cols < len(xs_src))
    vf = (filas >= 0) & (filas < len(ys_src))
    salida = np.full((len(ys_dst), len(xs_dst)), np.nan, dtype=np.float32)
    if not vc.any() or not vf.any():
        return salida
    c0, c1 = cols[vc].min(), cols[vc].max() + 1
    f0, f1 = filas[vf].min(), filas[vf].max() + 1
    ventana = np.asarray(ds[f0:f1, c0:c1], dtype=np.float32)
    salida[np.ix_(vf, vc)] = ventana[np.ix_(filas[vf] - f0, cols[vc] - c0)]
    return salida


# ---------------------------------------------------------------- buscar
def buscar(args):
    os.makedirs(args.salida, exist_ok=True)
    params = {
        "dataset": "NISAR",
        "processingLevel": "GUNW,GCOV",
        "intersectsWith": POLIGONO_AMBA,
        "output": "jsonlite",
        "maxResults": "5000",
    }
    url = API_ASF + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=120) as r:
        resultados = json.load(r)["results"]
    elegidos = {}
    for g in resultados:
        nombre = g["granuleName"]
        if g.get("path") not in args.orbitas or not g.get("downloadUrl"):
            continue
        tipo = g["productType"]
        if tipo == "GUNW":
            fechas = re.findall(r"_(\d{8})T\d{6}", nombre)
            clave = (tipo, g["path"], fechas[0], fechas[2] if len(fechas) > 2 else fechas[-1])
        else:
            clave = (tipo, g["path"], g["startTime"][:10])
        # Preferimos frame completo (_F_) y la versión más nueva (sufijo _NNN).
        rango = ("_F_" in nombre, nombre[-3:])
        if clave not in elegidos or rango > elegidos[clave][0]:
            elegidos[clave] = (rango, g)
    lista = [
        {"tipo": k[0], "orbita": k[1], "fechas": list(k[2:]), "nombre": v[1]["granuleName"],
         "url": v[1]["downloadUrl"], "direccion": v[1].get("flightDirection")}
        for k, v in sorted(elegidos.items())
    ]
    destino = os.path.join(args.salida, "lista_productos.json")
    with open(destino, "w", encoding="utf-8") as fh:
        json.dump(lista, fh, indent=1, ensure_ascii=False)
    for t in ("GUNW", "GCOV"):
        print(f"{t}: {sum(1 for x in lista if x['tipo'] == t)}")
    print("Lista:", destino)


# ---------------------------------------------------------------- bajar
def bajar(args):
    import earthaccess

    with open(os.path.join(args.salida, "lista_productos.json"), encoding="utf-8") as fh:
        lista = json.load(fh)
    if args.solo_gunw:
        lista = [x for x in lista if x["tipo"] == "GUNW"]
    os.makedirs(args.datos, exist_ok=True)
    faltan = [x["url"] for x in lista if not os.path.exists(os.path.join(args.datos, os.path.basename(x["url"])))]
    print(f"Productos: {len(lista)}; ya bajados: {len(lista) - len(faltan)}; a bajar: {len(faltan)}")
    if not faltan:
        return
    earthaccess.login(strategy="environment")
    earthaccess.download(faltan, local_path=args.datos, threads=args.hilos)


# ---------------------------------------------------------------- procesar
def _buscar_capa(f, grupo):
    """Devuelve (dataset de coherencia, xs, ys) para la primera polarización disponible del grupo."""
    base = f"science/LSAR/GUNW/grids/frequencyA/{grupo}"
    for pol in ("HH", "VV", "HV", "VH"):
        ruta = f"{base}/{pol}/coherenceMagnitude"
        if ruta in f:
            return f[ruta], f[f"{base}/xCoordinates"][()], f[f"{base}/yCoordinates"][()]
    raise KeyError(f"No hay coherencia en {base}")


def _buscar_eco(f):
    """Busca la capa de backscatter de un GCOV (HHHH o VVVV) y sus coordenadas."""
    encontrado = []

    import h5py

    def visitar(nombre, obj):
        if isinstance(obj, h5py.Dataset) and obj.ndim == 2 and nombre.split("/")[-1] in ("HHHH", "VVVV"):
            encontrado.append(nombre)

    f.visititems(visitar)
    if not encontrado:
        raise KeyError("No hay HHHH ni VVVV en el GCOV")
    ruta = sorted(encontrado)[0]
    grupo = ruta.rsplit("/", 1)[0]
    return f[ruta], f[grupo + "/xCoordinates"][()], f[grupo + "/yCoordinates"][()]


_SESION_REMOTA = None


def _abrir(ruta, remoto):
    """Abre un .h5 local, o remoto por URL con earthaccess (lee sólo los bloques que se piden)."""
    import h5py

    if not remoto:
        return h5py.File(ruta, "r")
    global _SESION_REMOTA
    import earthaccess

    if _SESION_REMOTA is None:  # una vez por proceso
        _SESION_REMOTA = earthaccess.login(strategy="environment")
    archivo = earthaccess.open([ruta])[0]
    return h5py.File(archivo, "r")


def _procesar_uno(tarea):
    ruta, capa, carpeta, remoto = tarea
    nombre = os.path.basename(ruta).replace(".h5", "")
    fechas = re.findall(r"_(\d{8})T\d{6}", nombre)
    orbita = int(re.search(r"_(?:GUNW|GCOV)_\d{3}_(\d{3})_", nombre).group(1))
    fecha_sec = fechas[2] if len(fechas) > 2 else fechas[0]
    prefijo = "gunw" if "_GUNW_" in nombre else "gcov"
    # Nombre corto: los nombres de NISAR superan el límite de rutas de Windows.
    destino = os.path.join(carpeta, f"{prefijo}_{orbita:03d}_{fechas[0]}_{fecha_sec}_{capa}.npz")
    if os.path.exists(destino):
        return destino, "ya estaba"
    xs_dst, ys_dst = grilla(CAPAS[capa][1])
    try:
        with _abrir(ruta, remoto) as f:
            if "_GUNW_" in nombre:
                ds, xs, ys = _buscar_capa(f, CAPAS[capa][0])
                valor = recortar(ds, xs, ys, xs_dst, ys_dst)
                valor[(valor <= 0) | (valor > 1)] = np.nan
                tipo = "coherencia"
            else:
                ds, xs, ys = _buscar_eco(f)
                lin = recortar(ds, xs, ys, xs_dst, ys_dst)
                with np.errstate(divide="ignore", invalid="ignore"):
                    valor = (10 * np.log10(lin)).astype(np.float32)
                valor[~np.isfinite(valor)] = np.nan
                tipo = "eco_db"
    except Exception as e:  # un archivo roto no frena a los demás
        return destino, f"ERROR {e}"
    np.savez_compressed(destino, valor=valor.astype(np.float16), tipo=tipo, orbita=orbita,
                        fecha_ref=fechas[0], fecha_sec=fecha_sec, producto=nombre)
    return destino, f"ok {tipo} cobertura {np.isfinite(valor).mean():.0%}"


def procesar(args):
    carpeta = os.path.join(args.salida, f"recortes_{args.capa}")
    os.makedirs(carpeta, exist_ok=True)
    if args.remoto:
        # Sin bajar nada: lee por URL sólo la ventana del AMBA (necesita `buscar` antes y credenciales).
        with open(os.path.join(args.salida, "lista_productos.json"), encoding="utf-8") as fh:
            lista = json.load(fh)
        archivos = [x["url"] for x in lista if x["orbita"] in args.orbitas and (x["tipo"] == "GUNW" or not args.solo_gunw)]
    else:
        archivos = sorted(glob.glob(os.path.join(args.datos, "NISAR_*_GUNW_*.h5")) + glob.glob(os.path.join(args.datos, "NISAR_*_GCOV_*.h5")))
    archivos = [a for a in archivos if int(re.search(r"_(?:GUNW|GCOV)_\d{3}_(\d{3})_", os.path.basename(a)).group(1)) in args.orbitas]
    modo = "remoto, sin bajar" if args.remoto else "local"
    print(f"Archivos a procesar: {len(archivos)} (capa {args.capa}, {args.procesos} procesos, {modo})")
    with cf.ProcessPoolExecutor(max_workers=args.procesos) as ex:
        for destino, estado in ex.map(_procesar_uno, [(a, args.capa, carpeta, args.remoto) for a in archivos]):
            print(f"  {os.path.basename(destino)}: {estado}")




# ---------------------------------------------------------------- índice
def _fecha(aaaammdd):
    return f"{aaaammdd[:4]}-{aaaammdd[4:6]}-{aaaammdd[6:]}"


def _dias(a, b):
    import datetime as dt

    return (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days


def _json(ruta, datos, **kw):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as fh:
        json.dump(datos, fh, ensure_ascii=False, **kw)
        fh.write("\n")


def cargar(args):
    """Lee una sola vez los recortes, la máscara de agua, los sitios y los usos conocidos."""
    paso = CAPAS[args.capa][1]
    xs, ys = grilla(paso)
    coh, pares, eco, orb_eco = [], [], [], []
    for ruta in sorted(glob.glob(os.path.join(args.salida, f"recortes_{args.capa}", "*.npz"))):
        with np.load(ruta) as d:
            if int(d["orbita"]) not in args.orbitas:
                continue
            valor = d["valor"].astype(np.float32)
            if str(d["tipo"]) == "coherencia":
                ref, sec = _fecha(str(d["fecha_ref"])), _fecha(str(d["fecha_sec"]))
                coh.append(valor)
                pares.append({"orbita": int(d["orbita"]), "desde": ref, "hasta": sec, "dias": _dias(ref, sec), "producto": str(d["producto"])})
            elif np.isfinite(valor).mean() >= 0.5:  # hay GCOV que no cubren el AMBA
                eco.append(valor)
                orb_eco.append(int(d["orbita"]))
    if not coh:
        sys.exit("No hay recortes de coherencia: corré `procesar` primero (o bajá los recortes, ver README).")
    coh = np.stack(coh)
    if coh.shape[1:] != (len(ys), len(xs)):
        sys.exit(f"Los recortes miden {coh.shape[1:]} y la grilla {(len(ys), len(xs))}.")
    with np.load(os.path.join(FIJOS, f"agua_jrc_{args.capa}.npz")) as d:
        ocurrencia = d["ocurrencia"]
    with open(os.path.join(AQUI, "sitios_registro.json"), encoding="utf-8") as fh:
        registro = json.load(fh)["sitios"]
    with open(os.path.join(FIJOS, "contornos_osm.json"), encoding="utf-8") as fh:
        contornos = json.load(fh)["sitios"]
    sitios = []
    for s in registro:
        anillos = contornos[s["id"]]["anillos"] if "osm" in s else [geo.caja_a_anillo(s["caja"])]
        mayor = max(anillos, key=lambda a: geo.area_y_centro(a)[0])
        sitios.append({**s, "anillos": anillos, "mascara": geo.mascara_poligonos(anillos, xs, ys),
                       "ha": sum(geo.area_y_centro(a)[0] for a in anillos), "centro": geo.area_y_centro(mayor)[1],
                       "lugar": s.get("lugar") or contornos.get(s["id"], {}).get("lugar_osm", "")})
    with open(os.path.join(FIJOS, "usos_osm.json"), encoding="utf-8") as fh:
        usos = json.load(fh)["usos"]
    uso_px = np.zeros((len(ys), len(xs)), dtype=np.int16)  # 0 = sin uso conocido; i = usos[i - 1]
    for i, u in enumerate(usos, start=1):
        uso_px[geo.mascara_poligonos(u["anillos"], xs, ys) & (uso_px == 0)] = i
    sitio_px = np.zeros_like(uso_px)
    for i, s in enumerate(sitios, start=1):
        if s["rol"] != "control":
            sitio_px[s["mascara"] & (sitio_px == 0)] = i
    return {"paso": paso, "xs": xs, "ys": ys, "coh": coh, "pares": pares,
            "orbitas": np.array([x["orbita"] for x in pares]), "dias": np.array([x["dias"] for x in pares]),
            "fechas": np.array([x["hasta"] for x in pares]),
            "eco": np.stack(eco) if eco else None, "orbitas_eco": np.array(orb_eco), "ocurrencia": ocurrencia,
            "sitios": sitios, "usos": usos, "uso_px": uso_px, "sitio_px": sitio_px}


def evaluar(ctx, p, cociente=None, eco_db=None):
    """Corre el índice con los parámetros p. Devuelve capas, manchas clasificadas y fichas."""
    paso = ctx["paso"]
    agua = ins.mascara_agua(ctx["ocurrencia"], paso, p)
    capas = ins.calcular(ctx["coh"], ctx["orbitas"], ctx["dias"], ctx["fechas"], agua, paso, p,
                         eco=ctx["eco"], orbitas_eco=ctx["orbitas_eco"], cociente=cociente, eco_db=eco_db)
    lista, etiquetas = ins.manchas(capas["candidato"], capas, paso, p)
    n = len(lista)
    # qué pisa cada mancha: un relleno de OSM, un uso conocido o nada
    ok = etiquetas > 0
    px = np.bincount(etiquetas[ok], minlength=n + 1)

    def mayoritario(ids):
        """Por mancha, el id más frecuente (sin contar el 0) y la fracción de la mancha que ocupa."""
        sel = ok & (ids > 0)
        pares_ = np.unique(np.column_stack([etiquetas[sel], ids[sel]]), axis=0, return_counts=True)
        mejor = {}
        for (e, i), c in zip(*pares_):
            if c > mejor.get(int(e), (0, 0))[1]:
                mejor[int(e)] = (int(i), int(c))
        return {e: (i, c / px[e]) for e, (i, c) in mejor.items()}

    en_sitio, en_uso = mayoritario(ctx["sitio_px"]), mayoritario(ctx["uso_px"])
    for m in lista:
        lat, lon = geo.latlon(ctx["xs"][0] + m["columna"] * paso, ctx["ys"][0] - m["fila"] * paso)
        m["lat"], m["lon"] = round(float(lat), 5), round(float(lon), 5)
        s, u = en_sitio.get(m["etiqueta"], (0, 0)), en_uso.get(m["etiqueta"], (0, 0))
        if s[1] >= 0.3:
            m["clase"], m["que"] = "relleno_osm", ctx["sitios"][s[0] - 1]["id"]
        elif u[1] >= 0.3:
            uso = ctx["usos"][u[0] - 1]
            m["clase"], m["que"] = "uso_conocido", f"{uso['uso']}: {uso['nombre']}".rstrip(": ")
        else:
            m["clase"], m["que"] = "sin_explicar", None
    fichas = {}
    for s in ctx["sitios"]:
        f = ins.ficha(s["mascara"], ctx["coh"], ctx["orbitas"], ctx["fechas"], ~agua, paso, p, eco_db=capas["eco_db"])
        tierra_px = max(int((s["mascara"] & ~agua).sum()), 1)
        buenas = np.isin(etiquetas, [m["etiqueta"] for m in lista if not m["descartada"]])
        f["cubierto_por_manchas"] = round(float((buenas & s["mascara"]).sum() / tierra_px), 2)
        f["agua"] = round(float((s["mascara"] & agua).sum() / max(int(s["mascara"].sum()), 1)), 2)
        fichas[s["id"]] = f
    return capas, lista, etiquetas, fichas


def _figura(ctx, capas, lista, etiquetas, p, destino):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap

    norte, oeste, sur, este = CAJA
    fig, ejes = plt.subplots(1, 3, figsize=(21, 6.6))
    marco = dict(extent=(oeste, este, sur, norte), aspect=1 / math.cos(math.radians((norte + sur) / 2)), interpolation="nearest")
    magma = plt.get_cmap("magma").copy()
    magma.set_bad("#9fb6c9")  # agua
    for eje, clave, titulo in ((ejes[0], "insomnio_abs", f"Absoluto: fracción de pares con coherencia < {p.umbral_abs}"),
                               (ejes[1], "insomnio", f"Relativo: fracción de pares con coherencia < {p.razon} × entorno")):
        im = eje.imshow(capas[clave], cmap=magma, vmin=0, vmax=1, **marco)
        eje.set_title(titulo, fontsize=10)
        fig.colorbar(im, ax=eje, fraction=0.03)
    clases = np.zeros(etiquetas.shape, dtype=np.uint8)
    for valor, clase in ((1, "uso_conocido"), (2, "sin_explicar"), (3, "relleno_osm")):
        clases[np.isin(etiquetas, [m["etiqueta"] for m in lista if not m["descartada"] and m["clase"] == clase])] = valor
    ejes[2].imshow(np.where(capas["agua"], np.nan, capas["coherencia_media"]), cmap="gray", vmin=0, vmax=1, **marco)
    ejes[2].imshow(np.ma.masked_equal(clases, 0), cmap=ListedColormap(["#3b82f6", "#f59e0b", "#ef4444"]), vmin=1, vmax=3, **marco)
    ejes[2].set_title("Manchas candidatas: rojo = relleno de OSM, naranja = sin explicar, azul = uso conocido (OSM)", fontsize=10)
    for s in ctx["sitios"]:
        if s["rol"] != "control":
            for a in s["anillos"]:
                lon, lat = np.array(a).T
                for eje in ejes:
                    eje.plot(lon, lat, color="#22d3ee", lw=0.8)
    fig.suptitle(f"Índice de insomnio, AMBA, {len(ctx['pares'])} pares de NISAR (GUNW, {ctx['paso']:.0f} m), órbitas "
                 f"{sorted(set(ctx['orbitas'].tolist()))}. Agua: JRC Global Surface Water. Contornos: © OpenStreetMap", fontsize=10)
    fig.tight_layout()
    fig.savefig(destino, dpi=110)
    plt.close(fig)


def _png_web(capas, ctx, destino):
    """PNG RGBA del índice relativo, norte arriba y regular en Web Mercator. Transparente en el agua y donde el índice es bajo."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    img, limites = geo.a_mercator(capas["insomnio"], ctx["xs"], ctx["ys"])
    rgba = plt.get_cmap("magma")(np.clip(np.nan_to_num(img), 0, 1))
    rgba[..., 3] = np.where(np.isfinite(img), np.clip((img - 0.3) / 0.4, 0, 1) * 0.85, 0)
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    plt.imsave(destino, rgba)
    return limites, img.shape


def _escribir_web(ctx, capas, lista, fichas, p, web):
    """Los archivos que lee insomnes-web. `sitios.json` tiene la forma exacta de `Sitio[]` (src/data/types.ts)."""
    seed = os.path.join(web, "src", "data", "seed")
    try:
        with open(os.path.join(seed, "imagenes.json"), encoding="utf-8") as fh:
            imagenes = json.load(fh)
    except FileNotFoundError:
        imagenes = {}
    sitios, contornos, detalle = [], {}, {}
    for s in ctx["sitios"]:
        f = fichas[s["id"]]
        if s["rol"] == "control" or not f["pares"]:
            continue
        mayor = max(s["anillos"], key=lambda a: geo.area_y_centro(a)[0])
        lon, lat = np.array([q for a in s["anillos"] for q in a]).T
        margen = 0.018  # ~1,6 km: el sitio con su anillo
        img = imagenes.get(s["id"]) or {}
        escenas = img.get("escenas", []) if isinstance(img, dict) else img
        caja = (img.get("caja") if isinstance(img, dict) else None) or [
            round(float(lon.min()) - margen / math.cos(math.radians(lat.mean())), 4), round(float(lat.min()) - margen, 4),
            round(float(lon.max()) + margen / math.cos(math.radians(lat.mean())), 4), round(float(lat.max()) + margen, 4)]
        fila = {"id": s["id"], "nombre": s["nombre"], "lugar": s["lugar"], "pais": s["pais"],
                "lat": round(s["centro"][0], 4), "lon": round(s["centro"][1], 4), "ha": round(s["ha"]),
                "registro": s["registro"]}
        if s.get("cierre"):
            fila["cierre"] = s["cierre"]
        fila.update(radar=f["radar"], insomnio=f["insomnio"],
                    pares=sorted(({"fecha": x["fecha"], "sitio": x["sitio"], "anillo": x["anillo"]} for x in f["pares"]), key=lambda x: x["fecha"]),
                    imagenes=escenas)
        if "osm" in s:
            fila["contorno"] = contornos[s["id"]] = {"type": "Polygon", "coordinates": [[[round(x, 5), round(y, 5)] for x, y in mayor]]}
        fila["caja"] = caja
        sitios.append(fila)
        detalle[s["id"]] = {"motivo": f["motivo"], "persistencia": f["persistencia"], "insomnio_orbita": f["insomnio_orbita"],
                            "eco_db": f["eco_db"], "px": f["px"], "cubierto_por_manchas": f["cubierto_por_manchas"],
                            "pares": f["pares"], "osm": s.get("osm", []), "nota": s.get("nota", ""), "fuentes": s.get("fuentes", [])}
    sitios.sort(key=lambda x: -x["insomnio"])
    filas = ",\n".join("  " + json.dumps(x, ensure_ascii=False) for x in sitios)
    with open(os.path.join(seed, "sitios.json"), "w", encoding="utf-8") as fh:
        fh.write(f"[\n{filas}\n]\n")
    _json(os.path.join(seed, "contornos.json"), contornos, separators=(",", ":"))
    _json(os.path.join(seed, "fichas.json"), detalle, indent=1)
    _json(os.path.join(seed, "candidatos.json"),
          [{k: m[k] for k in ("lat", "lon", "ha", "insomnio", "persistencia", "eco_db", "forma", "clase", "que")} for m in lista if not m["descartada"]],
          indent=0)
    limites, forma = _png_web(capas, ctx, os.path.join(web, "public", "indice", "insomnio-amba.png"))
    o, s_, e, n = limites
    _json(os.path.join(seed, "indice.json"), {
        "url": "indice/insomnio-amba.png", "oeste": o, "sur": s_, "este": e, "norte": n,
        "coordinates": [[o, n], [e, n], [e, s_], [o, s_]], "ancho": forma[1], "alto": forma[0],
        "que": "Índice de insomnio relativo (0 a 1), paleta magma; transparente por debajo de 0,3 y en el agua",
        "pares": len(ctx["pares"]), "desde": min(x["desde"] for x in ctx["pares"]), "hasta": max(x["hasta"] for x in ctx["pares"]),
        "parametros": {"razon": p.razon, "min_insomnio": p.min_insomnio, "min_persistencia": p.min_persistencia},
        "fuentes": ["NISAR GUNW (NASA/ISRO), vía ASF DAAC", "JRC Global Surface Water v1.4 (máscara de agua)"],
    }, indent=1)
    return len(sitios)


def indice(args):
    import time

    t0 = time.time()
    p = ins.Parametros()
    ctx = cargar(args)
    capas, lista, etiquetas, fichas = evaluar(ctx, p)
    capa, paso = args.capa, ctx["paso"]
    buenas = [m for m in lista if not m["descartada"]]
    tierra = ~capas["agua"]

    f16 = lambda a: np.asarray(a).astype(np.float16)  # noqa: E731
    np.savez_compressed(
        os.path.join(args.salida, f"indice_{capa}.npz"), insomnio=f16(capas["insomnio"]), insomnio_abs=f16(capas["insomnio_abs"]),
        persistencia=f16(capas["persistencia"]), coherencia_media=f16(capas["coherencia_media"]),
        eco_db=f16(capas["eco_db"] if capas["eco_db"] is not None else np.zeros(1)), agua=capas["agua"], candidato=capas["candidato"],
        manchas=etiquetas.astype(np.int32), pares=capas["pares_validos"].astype(np.uint8), xs=ctx["xs"], ys=ctx["ys"],
        **{f"insomnio_orbita_{o}": f16(v) for o, v in capas["insomnio_orbita"].items()})

    limpio = lambda m: {k: v for k, v in m.items() if k not in ("etiqueta", "fila", "columna")}  # noqa: E731
    resumen = {
        "capa": capa, "version": "final", "parametros": p.dict(),
        "pares": [{**x, "mediana_tierra": round(float(m), 3), "factor_separacion": round(float(f), 3)}
                  for x, m, f in zip(ctx["pares"], capas["mediana_par"], capas["factor_separacion"])],
        "gcov": int(len(ctx["orbitas_eco"])),
        "superficie": {
            "agua_ha": round(float(capas["agua"].sum() * paso * paso / 1e4)), "tierra_ha": round(float(tierra.sum() * paso * paso / 1e4)),
            "candidata_ha": round(float(sum(m["ha"] for m in buenas))),
            "estacional_ha": round(float(capas["estacional"].sum() * paso * paso / 1e4)),
            "lisa_ha": round(float(sum(m["ha"] for m in lista if m["descartada"] == "lisa"))),
        },
        "sitios": {s["id"]: {"nombre": s["nombre"], "rol": s["rol"], "registro": s.get("registro"), "cierre": s.get("cierre"),
                             "ha": round(s["ha"], 1), **{k: v for k, v in fichas[s["id"]].items() if k != "pares"}}
                   for s in ctx["sitios"]},
        "manchas": {"candidatas": len(buenas), "por_clase": {c: sum(1 for m in buenas if m["clase"] == c) for c in ("relleno_osm", "sin_explicar", "uso_conocido")},
                    "descartadas_lineales": sum(1 for m in lista if m["descartada"] == "lineal"),
                    "descartadas_lisas": sum(1 for m in lista if m["descartada"] == "lisa"),
                    "descartadas_chicas": sum(1 for m in lista if m["descartada"] == "chica"),
                    "primeras": [limpio(m) for m in buenas[:50]]},
        "fuentes": ["NISAR L2 GUNW y GCOV (NASA/ISRO), ASF DAAC", "JRC Global Surface Water v1.4", "© colaboradores de OpenStreetMap (ODbL)"],
    }
    _json(os.path.join(args.salida, f"resumen_{capa}.json"), resumen, indent=1)
    _json(os.path.join(args.salida, f"fichas_{capa}.json"), {k: v for k, v in fichas.items()}, indent=1)
    _figura(ctx, capas, lista, etiquetas, p, os.path.join(args.salida, f"indice_{capa}.png"))
    n_web = _escribir_web(ctx, capas, lista, fichas, p, args.web) if args.web and os.path.isdir(args.web) and capa == "80m" else 0

    print(f"{'sitio':26s} {'radar':10s} insomnio persist.  órbitas          eco   px  manchas")
    for s in ctx["sitios"]:
        f = fichas[s["id"]]
        orb = " ".join(f"{o}:{v:.2f}" for o, v in f["insomnio_orbita"].items())
        print(f"{s['id']:26s} {f['radar']:10s} {f['insomnio'] if f['insomnio'] is not None else '-':>8} {f['persistencia'] if f['persistencia'] is not None else '-':>8}  "
              f"{orb:16s} {f['eco_db'] if f['eco_db'] is not None else '-':>5} {f['px']:4d}  {f['cubierto_por_manchas']:.2f}")
    print(f"Manchas candidatas: {len(buenas)} ({resumen['manchas']['por_clase']}), {resumen['superficie']['candidata_ha']} ha "
          f"= {resumen['superficie']['candidata_ha'] / resumen['superficie']['tierra_ha']:.1%} de la tierra")
    for m in buenas[:10]:
        print(f"  {m['ha']:7.1f} ha  {m['lat']:.4f}, {m['lon']:.4f}  insomnio {m['insomnio']:.2f}  eco {m['eco_db']}  {m['forma']:9s} {m['clase']}: {m['que'] or ''}")
    if n_web:
        print(f"Web: {n_web} sitios en {os.path.relpath(args.web)}/src/data/seed/sitios.json y el PNG del índice")
    print(f"Listo en {time.time() - t0:.1f} s. Resumen: {os.path.join(args.salida, f'resumen_{capa}.json')}")


# ---------------------------------------------------------------- calibrar
def calibrar(args):
    """Barre `razon` y `min_insomnio` y marca las combinaciones en las que entran los sitios de calibración y no entran los controles.

    Criterios (todos a la vez):
      - los sitios con rol `calibracion` dan veredicto "despierto" y las manchas candidatas cubren al menos el 5 % de cada uno;
      - el control de la ciudad da "quieto";
      - las manchas candidatas cubren menos del 5 % de cada control.
    """
    import dataclasses

    base = ins.Parametros()
    ctx = cargar(args)
    agua = ins.mascara_agua(ctx["ocurrencia"], ctx["paso"], base)
    cociente = ins.cocientes(ctx["coh"], ~agua, ctx["paso"], base)
    eco_db = ins.eco_medio(ctx["eco"], ctx["orbitas_eco"])
    tierra_px = (~agua).sum()
    positivos = [s["id"] for s in ctx["sitios"] if s["rol"] == "calibracion"]
    controles = [s["id"] for s in ctx["sitios"] if s["rol"] == "control"]
    razones, minimos = [round(0.60 + 0.025 * i, 3) for i in range(15)], [0.5, 0.6, 0.7, 0.8, 0.9]
    tabla = []
    for r in razones:
        for t in minimos:
            p = dataclasses.replace(base, razon=r, min_insomnio=t)
            capas, lista, _, fichas = evaluar(ctx, p, cociente=cociente, eco_db=eco_db)
            cumple = (all(fichas[i]["radar"] == "despierto" and fichas[i]["cubierto_por_manchas"] >= 0.05 for i in positivos)
                      and fichas["control-caba"]["radar"] == "quieto"
                      and all(fichas[i]["cubierto_por_manchas"] < 0.05 for i in controles))
            tabla.append({"razon": r, "min_insomnio": t, "cumple": bool(cumple),
                          "tierra_candidata": round(float(sum(m["ha"] for m in lista if not m["descartada"]) * 1e4 / (ctx["paso"] ** 2) / tierra_px), 4),
                          "manchas": sum(1 for m in lista if not m["descartada"]),
                          **{i: {"radar": fichas[i]["radar"], "insomnio": fichas[i]["insomnio"], "cubierto": fichas[i]["cubierto_por_manchas"]}
                             for i in positivos + controles}})
    print("Filas: razon. Columnas: min_insomnio. Celda: '*' si cumple, % de la tierra que queda candidata.")
    print("        " + "".join(f"{t:>10.1f}" for t in minimos))
    for r in razones:
        print(f"  {r:.3f} " + "".join(f"{('*' if x['cumple'] else ' ') + format(x['tierra_candidata'], '.1%'):>10s}" for x in tabla if x["razon"] == r))
    # eco: el umbral tiene que quedar entre lo liso conocido y los rellenos conocidos
    eco_sitio = lambda i: float(np.nanmedian(eco_db[next(s for s in ctx["sitios"] if s["id"] == i)["mascara"]]))  # noqa: E731
    lisos = {i: round(eco_sitio(i), 1) for i in ("control-rio", "lujan-oeste")}
    rellenos = {i: round(eco_sitio(i), 1) for i in positivos}
    print(f"Eco (dB): lisos {lisos}; rellenos {rellenos}. El umbral tiene que caer entre {max(lisos.values())} y {min(rellenos.values())}; "
          f"usamos {base.eco_min_db}.")
    aguas = {str(a): round(float(ins.mascara_agua(ctx["ocurrencia"], ctx["paso"], dataclasses.replace(base, agua_min=a)).mean()), 4) for a in (5, 10, 25, 50, 75)}
    print("Fracción de la grilla que queda como agua según `agua_min` (% de ocurrencia JRC):", aguas)
    _json(os.path.join(args.salida, f"calibracion_{args.capa}.json"),
          {"criterios": calibrar.__doc__.split("Criterios")[1].strip(), "elegido": {"razon": base.razon, "min_insomnio": base.min_insomnio, "eco_min_db": base.eco_min_db},
           "eco_db": {"lisos": lisos, "rellenos": rellenos}, "agua_fraccion_por_umbral": aguas, "tabla": tabla}, indent=1)


# ---------------------------------------------------------------- main
def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("paso", choices=["buscar", "bajar", "procesar", "indice", "calibrar", "todo"])
    p.add_argument("--datos", default=os.path.join(IDEA, "datos"), help="carpeta de los .h5 (fuera del repo en la VM, por ejemplo /mnt/datos)")
    p.add_argument("--salida", default=os.path.join(IDEA, "salidas"), help="carpeta de productos chicos (lista, recortes, índice, figuras)")
    p.add_argument("--web", default=WEB, help="carpeta de insomnes-web; `indice` a 80 m escribe ahí los datos de la web ('' para no escribir)")
    p.add_argument("--orbitas", type=int, nargs="+", default=[10, 161], help="órbitas (path) a usar; 10 y 161 cubren todo el AMBA")
    p.add_argument("--capa", choices=list(CAPAS), default="80m")
    p.add_argument("--procesos", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    p.add_argument("--hilos", type=int, default=8, help="descargas en paralelo")
    p.add_argument("--solo-gunw", action="store_true", help="no bajar ni procesar GCOV")
    p.add_argument("--remoto", action="store_true", help="procesar leyendo por URL sólo la ventana necesaria, sin bajar los .h5 (necesita credenciales)")
    args = p.parse_args()
    pasos = ["buscar", "bajar", "procesar", "indice"] if args.paso == "todo" else [args.paso]
    for paso in pasos:
        print(f"== {paso}")
        globals()[paso](args)


if __name__ == "__main__":
    main()
