"""POC: insomnia of a handful of catalog dump sites, anywhere in the world, without downloading the .h5 files.

For each site in `data/catalogos/basurales/` (by id) it finds the NISAR GUNWs that cover it in the public ASF API,
reads by URL only the site's window with its ring (a few MB per pair, not the 2 GB) and computes the same card
as the AMBA index (`insomnio.ficha`): the site's coherence against a 1.5 km ring, pair by pair, and the
verdict "despierto", "quieto" or "no_alcanza". Then it compares it with the catalog status.

    python poc_sitios.py buscar      # which pairs each site has (no credentials needed)
    python poc_sitios.py leer        # reads the windows by URL and saves them to data/salidas/poc_sitios/ (needs credentials)
    python poc_sitios.py ficha       # computes the cards from what was read, the table and the figure (no network)
    python poc_sitios.py todo

    python poc_sitios.py todo --sitios BAS-066227 BAS-066083     # other sites
    python poc_sitios.py leer --datos /mnt/datos                  # with the .h5 files already downloaded, no network

By default: four Los Angeles landfills, two closed and two open according to the EPA (LMOP).

NASA Earthdata credentials (free, https://urs.earthdata.nasa.gov): the EARTHDATA_TOKEN variable, or
EARTHDATA_USERNAME and EARTHDATA_PASSWORD, or ~/.netrc. They are also read from a `.env` file in motor/
(it's in the .gitignore). Never in the repo.

Differences with the AMBA index (`pipeline_insomnio.py`), on purpose, since this is a test:
- it doesn't use `geo.grilla` (fixed on the AMBA and on UTM 21 south): it builds a small grid per site in the product's UTM zone;
- there's no JRC water mask and no GCOV echo: it doesn't discard smooth surfaces;
- the ring excludes the other catalog dump sites that fall in the window (in the AMBA, only the site itself);
- the thresholds are the ones calibrated in the AMBA, untouched.

Sources: NISAR L2 GUNW (NASA/ISRO), ASF DAAC. Catalog: see `data/README.md` (OSM/Overture, EPA LMOP, Climate TRACE).
"""
import argparse
import concurrent.futures as cf
import glob
import json
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

RAIZ = os.path.dirname(AQUI)
DATA = os.path.join(RAIZ, "data", "catalogos", "basurales")
API_ASF = "https://api.daac.asf.alaska.edu/services/search/param"
GRUPO = "science/LSAR/GUNW/grids/frequencyA/unwrappedInterferogram"  # the 80 m layer, the calibrated one
PASO = 80.0
MARGEN_M = 2000.0  # 1.5 km ring plus a margin
SITIOS_DEFECTO = ["BAS-066227", "BAS-066488", "BAS-066083", "BAS-066391"]  # Puente Hills, Spadra, Olinda Alpha, Scholl Canyon


# ------------------------------------------------------------------ geometry
def utm(lat, lon, zona, norte):
    """lat, lon -> x, y in the given UTM zone. `geo.utm` is for the southern hemisphere: in the north the false northing is removed."""
    x, y = geo.utm(lat, lon, zona)
    return x, (y - 10000000 if norte else y)


def zona_de_epsg(epsg):
    """EPSG 326xx (norte) o 327xx (sur) -> (zona, norte)."""
    epsg = int(epsg)
    if epsg // 100 not in (326, 327):
        raise ValueError(f"EPSG {epsg} no es UTM WGS84")
    return epsg % 100, epsg // 100 == 326


def anillos(geometria):
    if geometria["type"] == "Polygon":
        return [geometria["coordinates"][0]]
    if geometria["type"] == "MultiPolygon":
        return [p[0] for p in geometria["coordinates"]]
    return []


def mascara(lista_anillos, xs, ys, zona, norte):
    m = np.zeros((len(ys), len(xs)), dtype=bool)
    for a in lista_anillos:
        lon, lat = np.asarray(a, dtype=float).T[:2]
        m |= geo.dentro(np.column_stack(utm(lat, lon, zona, norte)), xs, ys)
    return m


def cargar_sitios(ids):
    """Requested sites (with their rings) and the rings of the whole catalog, to remove them from the control ring."""
    with open(os.path.join(DATA, "basurales_mundo.json"), encoding="utf-8") as fh:
        catalogo = {s["id"]: s for s in json.load(fh)["sitios"]}
    with open(os.path.join(DATA, "geometrias.geojson"), encoding="utf-8") as fh:
        geometrias = {f["properties"]["id"]: f["geometry"] for f in json.load(fh)["features"]}
    sitios = []
    for i in ids:
        if i not in catalogo:
            sys.exit(f"{i} no está en basurales_mundo.json")
        s, a = catalogo[i], anillos(geometrias.get(i, {"type": "Point"}))
        if not a:
            sys.exit(f"{i} ({s.get('nombre')}) no tiene polígono: no se puede medir contra un anillo")
        lon, lat = np.array([q[:2] for r in a for q in r]).T
        sitios.append({"id": i, "nombre": s.get("nombre") or i, "pais": s.get("pais"), "estado": s["estado"],
                       "fecha_cierre": s.get("fecha_cierre"), "area_ha": s.get("area_ha"), "lat": s["lat"], "lon": s["lon"],
                       "estados_por_fuente": s.get("estados_por_fuente", []), "anillos": a,
                       "caja": [float(lon.min()), float(lat.min()), float(lon.max()), float(lat.max())]})
    return sitios, geometrias


# ------------------------------------------------------------------ buscar
def _fechas(nombre):
    f = re.findall(r"_(\d{8})T\d{6}", nombre)
    return f[0], f[2] if len(f) > 2 else f[-1]


def buscar(args):
    """Per site, the PROVISIONAL GUNWs that cover it: one per (orbit, date pair), the newest full frame."""
    sitios, _ = cargar_sitios(args.sitios)
    productos = {}
    for s in sitios:
        o, su, e, n = s["caja"]
        wkt = f"POLYGON(({o} {su},{e} {su},{e} {n},{o} {n},{o} {su}))"
        params = {"dataset": "NISAR", "processingLevel": "GUNW", "intersectsWith": wkt, "output": "jsonlite", "maxResults": "5000"}
        with urllib.request.urlopen(API_ASF + "?" + urllib.parse.urlencode(params), timeout=120) as r:
            resultados = json.load(r)["results"]
        elegidos = {}
        for g in resultados:
            nombre = g["granuleName"]
            if "_PR_GUNW_" not in nombre or not g.get("downloadUrl"):  # a single maturity
                continue
            clave = (int(g["path"]),) + _fechas(nombre)
            rango = ("_F_" in nombre, nombre[-3:])
            if clave not in elegidos or rango > elegidos[clave][0]:
                elegidos[clave] = (rango, g)
        por_orbita = {}
        for (orbita, ref, sec), (_, g) in sorted(elegidos.items()):
            nombre = g["granuleName"]
            p = productos.setdefault(nombre, {"nombre": nombre, "url": g["downloadUrl"], "orbita": orbita, "frame": g.get("frame"),
                                              "direccion": g.get("flightDirection"), "fechas": [ref, sec], "sitios": []})
            p["sitios"].append(s["id"])
            por_orbita[orbita] = por_orbita.get(orbita, 0) + 1
        print(f"{s['id']} {s['nombre'][:34]:34s} {s['estado']:9s} {len(elegidos):3d} pares  órbitas {por_orbita}")
    lista = sorted(productos.values(), key=lambda x: (x["orbita"], x["fechas"]))
    if args.max_pares:
        # the most recent ones of each orbit
        por = {}
        for x in reversed(lista):
            por.setdefault(x["orbita"], []).append(x)
        lista = sorted((x for v in por.values() for x in v[:args.max_pares]), key=lambda x: (x["orbita"], x["fechas"]))
    os.makedirs(args.salida, exist_ok=True)
    destino = os.path.join(args.salida, "productos.json")
    with open(destino, "w", encoding="utf-8") as fh:
        json.dump(lista, fh, indent=1, ensure_ascii=False)
    print(f"Productos a leer: {len(lista)}. Lista: {destino}")


# ------------------------------------------------------------------ leer
def _credenciales():
    """Loads `.env` from motor/ (if it exists) into the environment, without printing anything."""
    ruta = os.path.join(AQUI, ".env")
    if os.path.exists(ruta):
        with open(ruta, encoding="utf-8") as fh:
            for linea in fh:
                m = re.match(r"\s*(?:export\s+)?(EARTHDATA_\w+)\s*=\s*['\"]?([^'\"\n]+)['\"]?\s*$", linea)
                if m:
                    os.environ.setdefault(m.group(1), m.group(2).strip())


def _login():
    import earthaccess

    _credenciales()
    hay_env = os.environ.get("EARTHDATA_TOKEN") or (os.environ.get("EARTHDATA_USERNAME") and os.environ.get("EARTHDATA_PASSWORD"))
    if not hay_env and not os.path.exists(os.path.expanduser("~/.netrc")):
        sys.exit("Faltan las credenciales de Earthdata: definí EARTHDATA_TOKEN (o usuario y contraseña) en el entorno, "
                 f"en {os.path.relpath(os.path.join(AQUI, '.env'))} o en ~/.netrc. Ver el encabezado de este script.")
    auth = earthaccess.login(strategy="environment" if hay_env else "netrc")
    if not auth.authenticated:
        sys.exit("Earthdata rechazó las credenciales.")


def _ventana(f, sitio):
    """Crops the 80 m coherence around the site. Returns (coh, xs, ys, epsg) or None if it doesn't cover it."""
    ds = None
    for pol in ("HH", "VV", "HV", "VH"):
        if f"{GRUPO}/{pol}/coherenceMagnitude" in f:
            ds = f[f"{GRUPO}/{pol}/coherenceMagnitude"]
            break
    if ds is None:
        raise KeyError(f"No hay coherencia en {GRUPO}")
    xs, ys = f[f"{GRUPO}/xCoordinates"][()], f[f"{GRUPO}/yCoordinates"][()]
    epsg = int(np.asarray(f[f"{GRUPO}/projection"][()]).ravel()[0])
    zona, norte = zona_de_epsg(epsg)
    o, su, e, n = sitio["caja"]
    x, y = utm(np.array([su, su, n, n]), np.array([o, e, o, e]), zona, norte)
    cols = np.nonzero((xs >= x.min() - MARGEN_M) & (xs <= x.max() + MARGEN_M))[0]
    filas = np.nonzero((ys >= y.min() - MARGEN_M) & (ys <= y.max() + MARGEN_M))[0]
    if not len(cols) or not len(filas):
        return None
    coh = np.asarray(ds[filas[0]:filas[-1] + 1, cols[0]:cols[-1] + 1], dtype=np.float32)
    coh[(coh <= 0) | (coh > 1)] = np.nan
    return coh, xs[cols], ys[filas], epsg


def _leer_uno(tarea):
    producto, sitios, carpeta, datos = tarea
    import h5py

    pendientes = [s for s in sitios if not os.path.exists(os.path.join(carpeta, s["id"], f"{producto['nombre']}.npz"))]
    if not pendientes:
        return producto["nombre"], "ya estaba"
    try:
        if datos:
            origen = os.path.join(datos, producto["nombre"] + ".h5")
        else:
            import earthaccess

            origen = earthaccess.open([producto["url"]])[0]
        estados = []
        with h5py.File(origen, "r") as f:
            for s in pendientes:
                v = _ventana(f, s)
                if v is None:
                    estados.append(f"{s['id']} fuera")
                    continue
                coh, xs, ys, epsg = v
                os.makedirs(os.path.join(carpeta, s["id"]), exist_ok=True)
                np.savez_compressed(os.path.join(carpeta, s["id"], f"{producto['nombre']}.npz"), coh=coh.astype(np.float16), xs=xs, ys=ys,
                                    epsg=epsg, orbita=producto["orbita"], fecha_ref=producto["fechas"][0], fecha_sec=producto["fechas"][1])
                estados.append(f"{s['id']} {coh.shape[0]}x{coh.shape[1]} {np.isfinite(coh).mean():.0%}")
        return producto["nombre"], "ok " + ", ".join(estados)
    except Exception as e:  # a broken file doesn't stop the others
        return producto["nombre"], f"ERROR {type(e).__name__}: {e}"


def leer(args):
    sitios, _ = cargar_sitios(args.sitios)
    with open(os.path.join(args.salida, "productos.json"), encoding="utf-8") as fh:
        productos = json.load(fh)
    if not args.datos:
        _login()
    por_id = {s["id"]: s for s in sitios}
    tareas = [(p, [por_id[i] for i in p["sitios"] if i in por_id], args.salida, args.datos) for p in productos]
    print(f"Productos: {len(tareas)} ({'local' if args.datos else 'por URL, sin bajar'}, {args.hilos} hilos)")
    errores = 0
    with cf.ThreadPoolExecutor(max_workers=args.hilos) as ex:
        for nombre, estado in ex.map(_leer_uno, tareas):
            errores += estado.startswith("ERROR")
            print(f"  {nombre[17:28]} {'-'.join(_fechas(nombre))}: {estado}", flush=True)
    if errores:
        print(f"{errores} productos con error: se puede volver a correr `leer`, retoma lo que falta.")


# ------------------------------------------------------------------ ficha
def _dias(a, b):
    import datetime as dt

    return (dt.datetime.strptime(b, "%Y%m%d") - dt.datetime.strptime(a, "%Y%m%d")).days


def _apilar(carpeta_sitio):
    """The site's coherence stack on a common grid (the first crop's). Returns (coh, xs, ys, epsg, pares)."""
    rutas = sorted(glob.glob(os.path.join(carpeta_sitio, "*.npz")))
    if not rutas:
        return None
    pila, pares, xs0, ys0, epsg0 = [], [], None, None, None
    for ruta in rutas:
        with np.load(ruta) as d:
            coh, xs, ys, epsg = d["coh"].astype(np.float32), d["xs"], d["ys"], int(d["epsg"])
            par = {"orbita": int(d["orbita"]), "desde": str(d["fecha_ref"]), "hasta": str(d["fecha_sec"])}
        if xs0 is None:
            xs0, ys0, epsg0 = xs, ys, epsg
        if epsg != epsg0:
            print(f"  se saltea {os.path.basename(ruta)[:40]}: EPSG {epsg} distinto de {epsg0}")
            continue
        if coh.shape != (len(ys0), len(xs0)) or xs[0] != xs0[0] or ys[0] != ys0[0]:
            # another orbit can bring another window: nearest neighbour onto the first one's grid
            c = np.rint((xs0 - xs[0]) / (xs[1] - xs[0])).astype(int)
            f = np.rint((ys0 - ys[0]) / (ys[1] - ys[0])).astype(int)
            vc, vf = (c >= 0) & (c < len(xs)), (f >= 0) & (f < len(ys))
            nuevo = np.full((len(ys0), len(xs0)), np.nan, dtype=np.float32)
            nuevo[np.ix_(vf, vc)] = coh[np.ix_(f[vf], c[vc])]
            coh = nuevo
        pila.append(coh)
        pares.append({**par, "dias": _dias(par["desde"], par["hasta"])})
    return np.stack(pila), xs0, ys0, epsg0, pares


def _acuerdo(estado, radar):
    if radar == "no_alcanza" or estado not in ("abierto", "cerrado"):
        return None
    return (estado == "abierto") == (radar == "despierto")


def ficha(args):
    p = ins.Parametros()
    sitios, geometrias = cargar_sitios(args.sitios)
    salida = []
    for s in sitios:
        apilado = _apilar(os.path.join(args.salida, s["id"]))
        if apilado is None:
            print(f"{s['id']}: sin recortes, corré `leer`")
            continue
        coh, xs, ys, epsg, pares = apilado
        zona, norte = zona_de_epsg(epsg)
        propia = mascara(s["anillos"], xs, ys, zona, norte)
        # the ring doesn't overlap other catalog dump sites
        lat0, lon0, dlat = s["lat"], s["lon"], 0.2
        otros = [a for i, g in geometrias.items() if i != s["id"]
                 for a in anillos(g) if abs(a[0][1] - lat0) < dlat and abs(a[0][0] - lon0) < dlat]
        ajenos = mascara(otros, xs, ys, zona, norte) & ~propia
        # no data in more than half of the pairs: not measurable land (water, shadow, frame edge)
        tierra = ~ajenos & (np.isfinite(coh).mean(0) >= 0.5)
        f = ins.ficha(propia, coh, np.array([x["orbita"] for x in pares]), np.array([x["hasta"] for x in pares]), tierra, PASO, p)
        dias = {(x["orbita"], x["hasta"]): x["dias"] for x in pares}
        for x in f["pares"]:
            x["dias"] = dias[(x["orbita"], x["fecha"])]
        fila = {k: s[k] for k in ("id", "nombre", "pais", "estado", "fecha_cierre", "area_ha", "lat", "lon", "estados_por_fuente")}
        fila.update(f, acuerdo=_acuerdo(s["estado"], f["radar"]), epsg=epsg, px_otros_basurales=int(ajenos.sum()),
                    desde=min(x["desde"] for x in pares), hasta=max(x["hasta"] for x in pares))
        salida.append(fila)
    if not salida:
        sys.exit("No hay nada que calcular.")
    print(f"\n{'sitio':36s} {'catálogo':9s} {'radar':10s} insomnio persist. pares  px  órbitas")
    for x in salida:
        orb = " ".join(f"{o}:{v:.2f}" for o, v in x["insomnio_orbita"].items())
        print(f"{x['nombre'][:36]:36s} {x['estado']:9s} {x['radar']:10s} {x['insomnio'] if x['insomnio'] is not None else '-':>8} "
              f"{x['persistencia'] if x['persistencia'] is not None else '-':>8} {len(x['pares']):5d} {x['px']:3d}  {orb}")
        if x["radar"] == "no_alcanza":
            print(f"{'':36s} motivo: {x['motivo']}")
    medibles = [x for x in salida if x["acuerdo"] is not None]
    print(f"\nRadar y catálogo coinciden en {sum(x['acuerdo'] for x in medibles)} de {len(medibles)} sitios medibles "
          f"(abierto = despierto, cerrado = quieto). {len(salida) - len(medibles)} sin veredicto.")
    destino = os.path.join(args.salida, "poc_sitios.json")
    with open(destino, "w", encoding="utf-8") as fh:
        json.dump({"que": "POC del insomnio por sitio fuera del AMBA (poc_sitios.py)", "parametros": p.dict(),
                   "advertencias": ["sin máscara de agua de JRC", "sin eco de GCOV: no descarta superficies lisas",
                                    "umbrales calibrados en el AMBA, sin recalibrar"],
                   "fuentes": ["NISAR L2 GUNW PROVISIONAL (NASA/ISRO), ASF DAAC", "Catálogo data/basurales (OSM/Overture ODbL, EPA LMOP, Climate TRACE CC BY 4.0)"],
                   "sitios": salida}, fh, indent=1, ensure_ascii=False)
    print("Fichas:", destino)
    _figura(salida, p, os.path.join(args.salida, "poc_sitios.png"))


def _figura(salida, p, destino):
    import datetime as dt

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    color = {"despierto": "#c2410c", "quieto": "#1d4ed8", "no_alcanza": "#6b7280"}
    fig, ejes = plt.subplots(len(salida), 1, figsize=(9, 2.3 * len(salida) + 0.6), sharex=True, sharey=True, squeeze=False)
    for eje, x in zip(ejes[:, 0], salida):
        pares = sorted(x["pares"], key=lambda q: q["fecha"])
        t = [dt.datetime.strptime(q["fecha"], "%Y%m%d") for q in pares]
        razon = [q["sitio"] / q["anillo"] if q["anillo"] else np.nan for q in pares]
        eje.axhline(p.razon, color="#9ca3af", lw=1, ls="--")
        eje.axhline(1, color="#d1d5db", lw=1)
        eje.scatter(t, razon, s=22, color=color[x["radar"]], zorder=3)
        cierre = f", cerró en {x['fecha_cierre']}" if x.get("fecha_cierre") else ""
        eje.set_title(f"{x['nombre']} · catálogo: {x['estado']}{cierre} · radar: {x['radar'].replace('_', ' ')} "
                      f"(insomnio {x['insomnio']})", fontsize=9.5, loc="left")
        eje.set_ylabel("sitio / anillo", fontsize=8.5)
        eje.set_ylim(0, 1.6)
        eje.tick_params(labelsize=8)
        for lado in ("top", "right"):
            eje.spines[lado].set_visible(False)
    ejes[0, 0].annotate(f"despierto por debajo de {p.razon}", (0.995, p.razon / 1.6), xycoords="axes fraction", ha="right", va="bottom",
                        fontsize=7.5, color="#6b7280")
    fig.suptitle("Coherencia de cada par de NISAR adentro del sitio, relativa a su anillo de 1,5 km", fontsize=10.5, x=0.01, ha="left")
    fig.text(0.01, 0.005, "NISAR L2 GUNW (NASA/ISRO, ASF DAAC), capa de 80 m. Estado: catálogo data/basurales. Figura hecha con asistencia de IA.",
             fontsize=7, color="#6b7280")
    fig.tight_layout(rect=(0, 0.02, 1, 0.98))
    fig.savefig(destino, dpi=130)
    plt.close(fig)
    print("Figura:", destino)


# ------------------------------------------------------------------ main
def main():
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("paso", choices=["buscar", "leer", "ficha", "todo"])
    a.add_argument("--sitios", nargs="+", default=SITIOS_DEFECTO, help="catalog ids (BAS-...)")
    a.add_argument("--salida", default=os.path.join(RAIZ, "data", "salidas", "poc_sitios"))
    a.add_argument("--datos", default="", help="folder with the .h5 files already downloaded; if not given, they are read by URL")
    a.add_argument("--max-pares", type=int, default=0, help="at most this many pairs per orbit, the most recent ones (0 = all)")
    a.add_argument("--hilos", type=int, default=6)
    args = a.parse_args()
    for paso in (["buscar", "leer", "ficha"] if args.paso == "todo" else [args.paso]):
        print(f"== {paso}")
        globals()[paso](args)


if __name__ == "__main__":
    main()
