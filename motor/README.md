# Herramientas (Python)

Instalación: `python -m venv .venv` y `.venv/Scripts/pip install -r requirements.txt` (en Windows) o `.venv/bin/pip install -r requirements.txt`.

| Script | Uso | Qué hace |
|---|---|---|
| `coherencia_gunw.py` | `python coherencia_gunw.py <GUNW.h5> [carpeta_salida]` | Lista las capas de coherencia del archivo, recorta alrededor de sitios fijos (Norte III, Luján, CABA, campo) y guarda una figura con el panorama del AMBA |
| `manchas.py` | `python manchas.py <GUNW.h5>` | Busca en el AMBA manchas de coherencia baja respecto de su entorno y las lista con superficie, coordenadas y elongación (compacta, alargada o lineal) |
| `predios.py` | `python predios.py <GUNW.h5> <carpeta_salida>` | Mide la coherencia adentro de predios conocidos (cajas de OSM) contra un anillo de 1,5 km, en las capas de 80 m y 20 m, y guarda una figura |

Notas:
- La estructura de los GUNW es `science/LSAR/GUNW/grids/frequencyA/{unwrappedInterferogram (80 m), wrappedInterferogram (20 m)}/HH/coherenceMagnitude`, en UTM 21S (EPSG 32721) para el AMBA.
- La conversión de lat/lon a UTM está escrita a mano para no depender de pyproj. Está verificada con el Obelisco.
- Las coordenadas de los sitios están en las constantes al principio de cada script.
