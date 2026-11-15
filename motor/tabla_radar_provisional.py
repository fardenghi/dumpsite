"""**Provisional** AMBA radar table, taken only from the already computed index, to test the model end to end.

The real radar table (`salidas/tabla_radar.parquet`) is written by stage 4 on the VM (prompt 1), with the
pair-by-pair series. This one comes from the summary layers of `indice_80m.npz`, so it leaves empty the columns
that need the series (`contraste_mediana`, `contraste_desvio`, `tendencia`, `eco_variacion`, `hv_hh`) and the
WorldCover ones (`urbano_anillo`, `cultivo_anillo`). Also:
- `persistencia` is the per-pixel mean over the blob, not the per-segment minimum measured over the whole blob;
- the ring is `insomnio.anillo` (without water), still without excluding the other catalog polygons;
- `compacidad` is measured on the stair-step edge of the 80 m pixels (it comes out lower than the real one).

    python tabla_radar_provisional.py        # writes datos/amba_provisional/tabla_radar.parquet (not committed)

**It does not write to `salidas/`** so it doesn't overwrite the stage 4 file.
"""
import argparse
import json
import math
import os
import sys

import numpy as np
import pandas as pd
from shapely.geometry import shape

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import catalogo_poligonos as cp  # noqa: E402
import contratos  # noqa: E402
import insomnio as ins  # noqa: E402


def armar(indice, manchas_geojson, p=None):
    p = p or ins.Parametros()
    with np.load(indice) as z:
        d = {k: z[k] for k in z.files}
    paso = float(d["xs"][1] - d["xs"][0])
    etiquetas, agua = d["manchas"], d["agua"]
    tierra = ~agua
    eco = d["eco_db"].astype(np.float32)
    coh = d["coherencia_media"].astype(np.float32)
    orbitas = [k for k in d if k.startswith("insomnio_orbita_")]
    with open(manchas_geojson, encoding="utf-8") as fh:
        fc = json.load(fh)
    epsg = (fc.get("meta") or {}).get("epsg", 32721)
    n = int(round(p.anillo_m / paso))
    yy, xx = np.mgrid[-n:n + 1, -n:n + 1]
    disco = yy**2 + xx**2 <= n * n
    from scipy import ndimage
    filas = []
    for f in fc["features"]:
        m = f["properties"]
        if m["descartada"]:
            continue
        mascara = etiquetas == m["etiqueta"]
        aro = ins.anillo(mascara, tierra, paso, p)
        ff, cc = np.nonzero(mascara)
        sf = slice(max(ff.min() - n, 0), ff.max() + n + 1)
        sc = slice(max(cc.min() - n, 0), cc.max() + n + 1)
        aro_todo = np.zeros_like(mascara)
        aro_todo[sf, sc] = ndimage.binary_dilation(mascara[sf, sc], structure=disco)
        aro_todo &= ~mascara
        g = cp.a_utm(shape(f["geometry"]), epsg)
        compacidad = min(1.0, 4 * math.pi * g.area / g.length**2) if g is not None and g.length > 0 else None
        eco_in = np.nanmean(eco[mascara]) if np.isfinite(eco[mascara]).any() else np.nan
        eco_aro = np.nanmedian(eco[aro]) if aro.any() and np.isfinite(eco[aro]).any() else np.nan
        n_orb = sum(1 for k in orbitas if np.isfinite(d[k][mascara].astype(np.float32)).mean() > 0.5)
        filas.append({
            "id_mancha": m["id_mancha"], "frame": m["frame"],
            "insomnio": m["insomnio"], "persistencia": m["persistencia"],
            "contraste_mediana": None, "contraste_desvio": None,
            "coherencia_media": float(np.nanmean(coh[mascara])) if np.isfinite(coh[mascara]).any() else None,
            "tendencia": None,
            "n_pares": int(np.median(d["pares"][mascara])), "n_orbitas": int(n_orb),
            "eco_db": m["eco_db"], "eco_contraste": float(eco_in - eco_aro) if np.isfinite(eco_in - eco_aro) else None,
            "eco_variacion": None, "hv_hh": None,
            "area_ha": m["ha"], "elongacion": m["elongacion"], "compacidad": compacidad,
            "agua_anillo": float(agua[aro_todo].mean()) if aro_todo.any() else None,
            "urbano_anillo": None, "cultivo_anillo": None,
        })
    df = pd.DataFrame(filas)
    for c in ("contraste_mediana", "contraste_desvio", "tendencia", "eco_variacion", "hv_hh", "urbano_anillo", "cultivo_anillo",
              "eco_contraste", "coherencia_media", "compacidad", "agua_anillo", "eco_db"):
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("float64")
    return df


def main():
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--indice", default=os.path.join(AQUI, "..", "data", "salidas", "indice_80m.npz"))
    a.add_argument("--manchas", default=os.path.join(AQUI, "..", "data", "salidas", "manchas.geojson"))
    a.add_argument("--salida", default=os.path.join(AQUI, "datos", "amba_provisional"))
    args = a.parse_args()
    df = armar(args.indice, args.manchas)
    destino = contratos.guardar(df, "tabla_radar", args.salida)
    print(f"{destino}: {len(df)} manchas (PROVISIONAL: sin la serie par a par; la de verdad es de la etapa 4)")


if __name__ == "__main__":
    main()
