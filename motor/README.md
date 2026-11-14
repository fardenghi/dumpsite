# Herramientas (Python)

Instalación: `python -m venv .venv` y `.venv/Scripts/pip install -r requirements.txt` (en Windows) o `.venv/bin/pip install -r requirements.txt`.

| Script | Uso | Qué hace |
|---|---|---|
| `pipeline_insomnio.py` | `python pipeline_insomnio.py indice` | **El pipeline completo.** `buscar` lista los GUNW y GCOV del AMBA con la API de ASF; `bajar` los baja con earthaccess; `procesar` recorta coherencia y backscatter a una grilla común (necesita `h5py`). **`indice` calcula la versión final del índice** con los recortes ya hechos: tarda 14 s a 80 m y escribe `../salidas/` y los datos de `../../insomnes-web/`. `calibrar` barre los umbrales. `todo` corre desde cero, pensado para la VM (`../infra/README.md`). Resultados: `../idea/indice-final.md` |
| `insomnio.py` | se importa | El cálculo del índice, sin lectura ni escritura: máscara de agua, factor de separación, entorno, fracción por órbita, persistencia, manchas y ficha con veredicto por sitio. Los umbrales están en `Parametros` |
| `geo.py` | se importa | UTM 21S ↔ lat/lon vectorizado, grilla común del AMBA, rasterizado de polígonos y remuestreo a Web Mercator para la web |
| `fuentes_fijas.py` | `python fuentes_fijas.py agua` (o `sitios`, `usos`) | Se corre una sola vez, con red. Baja la máscara de agua de JRC Global Surface Water y los polígonos de OpenStreetMap, y los deja en `fijos/` (van al repo: `indice` no necesita red). Necesita `tifffile` e `imagecodecs` para `agua` |
| `sitios_registro.json` | se edita a mano | Los sitios con ficha: objeto de OSM o caja, registro, fecha de cierre y fuentes. `rol` dice cuáles se usaron para calibrar y cuáles son controles |
| `tests/test_insomnio.py` | `python -m pytest tests -q` | Caso sintético: ciudad quieta, basural despierto, agua, tosquera sin máscara, campo estacional, ruta y un predio demasiado chico |
| `coherencia_gunw.py` | `python coherencia_gunw.py <GUNW.h5> [carpeta_salida]` | Lista las capas de coherencia del archivo, recorta alrededor de sitios fijos (Norte III, Luján, CABA, campo) y guarda una figura con el panorama del AMBA |
| `manchas.py` | `python manchas.py <GUNW.h5>` | Busca en el AMBA manchas de coherencia baja respecto de su entorno y las lista con superficie, coordenadas y elongación (compacta, alargada o lineal) |
| `predios.py` | `python predios.py <GUNW.h5> <carpeta_salida>` | Mide la coherencia adentro de predios conocidos (cajas de OSM) contra un anillo de 1,5 km, en las capas de 80 m y 20 m, y guarda una figura |
| `cruce_catalogo.py` | `python cruce_catalogo.py [--indice X.npz] [--min-ha 10]` | Cruza un índice ya calculado con los polígonos de basurales (por complejo) y de negativos de `../../data/`: insomnio mediano por polígono, por clase y AUC. No necesita los recortes: usa `../salidas/indice_80m.npz`. Resultados en `../idea/indice-final.md` |

## Reproducir el índice sin la VM
Los recortes por par (35 `.npz` por capa) están en `gs://basurales-514714-salidas/salidas-v3.tgz` (1,1 GB, proyecto `basurales-514714`). Se extraen `recortes_80m/` y `recortes_20m/` en `../salidas/` (el `.gitignore` los excluye) y se corre `python pipeline_insomnio.py indice`. No hacen falta los `.h5` ni credenciales de Earthdata.

Notas:
- **`procesar --remoto`** lee por URL sólo la ventana necesaria, sin bajar los 2,2 GB: un sitio con su anillo son unos MB por par, y la coherencia de 80 m de un frame entero, unas decenas de MB. Necesita correr `buscar` antes y las credenciales de Earthdata. Si resulta muy lento (abrir el HDF5 a distancia hace muchas lecturas chicas), el plan B es `bajar` + `procesar`.
- La estructura de los GUNW es `science/LSAR/GUNW/grids/frequencyA/{unwrappedInterferogram (80 m), wrappedInterferogram (20 m)}/HH/coherenceMagnitude`, en UTM 21S (EPSG 32721) para el AMBA.
- La conversión de lat/lon a UTM está escrita a mano para no depender de pyproj (`geo.py`). Está verificada con el Obelisco.
- Los sitios del índice final están en `sitios_registro.json`. `coherencia_gunw.py`, `manchas.py` y `predios.py` son las pruebas de la primera hora, con las coordenadas en constantes.

## Licencia y uso de IA
Código: Apache 2.0. El índice final (`insomnio.py`, `geo.py`, `fuentes_fijas.py`, `pipeline_insomnio.py` y los tests) se escribió con asistencia de IA (Claude); hay que declararlo en el campo "Use of SI" de la entrega.
