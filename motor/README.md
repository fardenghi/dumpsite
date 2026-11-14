# Herramientas (Python)

Instalación: `python -m venv .venv` y `.venv/Scripts/pip install -r requirements.txt` (en Windows) o `.venv/bin/pip install -r requirements.txt`.

| Script | Uso | Qué hace |
|---|---|---|
| `pipeline_insomnio.py` | `python pipeline_insomnio.py todo --datos /mnt/datos --salida salidas --orbitas 10 161 --capa 80m` | **El pipeline completo, pensado para la VM (`../infra/README.md`).** `buscar` lista los GUNW y GCOV del AMBA con la API de ASF; `bajar` los baja con earthaccess en paralelo; `procesar` recorta coherencia y backscatter a una grilla común del AMBA en paralelo; `indice` calcula el índice de insomnio, las estadísticas por sitio, las manchas candidatas y una figura. Probado (14/11) con el par local: `buscar` encontró 15 GUNW y 20 GCOV en las órbitas 10 y 161; `procesar` e `indice` andan a 80 m y a 20 m. **Sin probar:** `bajar` y `procesar --remoto` (necesitan credenciales) y el procesamiento de GCOV (no había ninguno bajado). El umbral de eco (`--eco-min-db -15`) es un supuesto a calibrar |
| `coherencia_gunw.py` | `python coherencia_gunw.py <GUNW.h5> [carpeta_salida]` | Lista las capas de coherencia del archivo, recorta alrededor de sitios fijos (Norte III, Luján, CABA, campo) y guarda una figura con el panorama del AMBA |
| `manchas.py` | `python manchas.py <GUNW.h5>` | Busca en el AMBA manchas de coherencia baja respecto de su entorno y las lista con superficie, coordenadas y elongación (compacta, alargada o lineal) |
| `predios.py` | `python predios.py <GUNW.h5> <carpeta_salida>` | Mide la coherencia adentro de predios conocidos (cajas de OSM) contra un anillo de 1,5 km, en las capas de 80 m y 20 m, y guarda una figura |

Notas:
- **`procesar --remoto`** lee por URL sólo la ventana necesaria, sin bajar los 2,2 GB: un sitio con su anillo son unos MB por par, y la coherencia de 80 m de un frame entero, unas decenas de MB. Necesita correr `buscar` antes y las credenciales de Earthdata. Si resulta muy lento (abrir el HDF5 a distancia hace muchas lecturas chicas), el plan B es `bajar` + `procesar`.
- La estructura de los GUNW es `science/LSAR/GUNW/grids/frequencyA/{unwrappedInterferogram (80 m), wrappedInterferogram (20 m)}/HH/coherenceMagnitude`, en UTM 21S (EPSG 32721) para el AMBA.
- La conversión de lat/lon a UTM está escrita a mano para no depender de pyproj. Está verificada con el Obelisco.
- Las coordenadas de los sitios están en las constantes al principio de cada script.
