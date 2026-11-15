# Contratos de datos del modelo (14/11/2026)

El formato de los archivos intermedios del modelo, para que las etapas de `modelo.md` se puedan escribir en paralelo sin esperarse. Cada etapa escribe sus archivos y lee los de las otras **con este formato y no otro**.

- **En código:** `motor/contratos.py` tiene las mismas columnas como constantes y la función `validar()`. Si este documento y el código no coinciden, manda el código (y hay un test que avisa).
- **Datos de prueba:** `python motor/contratos_mock.py` genera todos los archivos en `motor/datos/mock/`, con valores inventados.
- **Nada de esto se calculó con datos reales.** Los valores del mock no son resultados: no se citan ni van a la web.

## Cómo se usa
```python
import contratos                                        # desde motor/

contratos.validar(df, "tabla_radar")                    # falla con ErrorContrato y dice todo lo que está mal
contratos.guardar(df, "tabla_radar", "../data/salidas") # valida, ordena las columnas y escribe el parquet
df = contratos.leer("datos/mock", "tabla_radar")        # lee y valida (también manchas, frames y particiones)
contratos.COLUMNAS_MODELO                               # las 29 variables del modelo, en orden
```
```bash
python motor/contratos_mock.py                         # genera motor/datos/mock/
python motor/contratos.py motor/datos/mock             # valida todo lo que haya en una carpeta
python motor/contratos.py data/salidas/tabla_radar.parquet
```
Hacen falta `pandas` y `pyarrow` (están en `motor/requirements.txt`).

## Reglas comunes
- **Rutas:** relativas a `data/`, la carpeta de datos de la raíz del repo. `salidas/` tiene lo que escribe el motor y `catalogos/` los catálogos.
- **Se pueden agregar columnas. No se pueden sacar ni renombrar** las del contrato. Las marcadas como *opcional* pueden faltar; si están, se validan.
- **Tablas:** parquet, escritas con `contratos.guardar()` (pandas y pyarrow), sin índice. Los textos son texto, los números `float64` y los enteros `int64` (o `Int64` si puede haber vacíos).
- **Vacíos:** una columna sólo puede venir vacía (null o NaN) si la tabla dice "sí" en *¿Vacía?*. Vacío quiere decir "no se pudo medir", nunca cero.
- **Coordenadas:** grados, WGS84, en el orden de GeoJSON: **(lon, lat)**. Las cajas van como `[lon_oeste, lat_sur, lon_este, lat_norte]`. **Ojo:** `geo.CAJA` va en otro orden (`lat_norte, lon_oeste, lat_sur, lon_este`).
- **Fechas:** texto `AAAA-MM-DD`.
- **`frame`:** la clave de `frames.json`, en mayúsculas, con letras, números y guion bajo (`AMBA`, `DELHI`, `LOS_ANGELES`). Un frame es un área de trabajo; puede juntar más de una órbita de NISAR, como el AMBA (órbitas 10 y 161).
- **`id_mancha`:** `MAN-<frame>-<n>`, con `n` de cuatro cifras desde 1, en el orden de `insomnio.manchas()` (de mayor a menor superficie). Ejemplo: `MAN-AMBA-0001`. Lo arma `contratos.id_mancha(frame, n)`. El número cuenta también las manchas descartadas.
- **`id_catalogo`:** el `id` del polígono en los catálogos, tal cual: `BAS-…` para `data/catalogos/basurales/` y `NEG-…` para `data/catalogos/negativos/`. **No** son los ids de `fichas_80m.json` (`norte-iii`) ni los de `casos_curados_argentina.json` (`AR-LUJAN`).
- **Anillo:** 1,5 km alrededor de la mancha o del polígono, sin agua y sin los demás polígonos de los catálogos (`insomnio.anillo`, etapa 1).
- **Tamaño mínimo:** 10 ha. Lo que mide menos sale como `no_alcanza`.
- **Lo pesado no se sube:** un parquet de más de unos MB va a `datos/`.
- **Lenguaje:** "señal compatible con actividad" y "quieto según el radar". Nunca "basural ilegal".

## Resumen
| Archivo | Lo escribe | Lo lee | Una fila por |
|---|---|---|---|
| `salidas/manchas.geojson` | etapa 4 (en el AMBA, el prompt 3) | etapas 5, 6 y 9, y la web | una mancha de un frame, incluidas las descartadas |
| `salidas/tabla_radar.parquet` | etapa 4 | etapa 6 | una mancha candidata (no descartada) de un frame |
| `salidas/insomnio_catalogo.parquet` | etapa 4 (la lógica, el prompt 2) | etapas 8 y 9 | un polígono del catálogo (basural o negativo) en un frame, esté o no en una mancha |
| `salidas/tabla_optico.parquet` | etapa 5 | etapa 6 | una mancha candidata de un frame |
| `salidas/tabla_optico_catalogo.parquet` | etapa 5 | etapas 8 y 9 (ficha) | un polígono del catálogo en un frame |
| `salidas/cruce_manchas_catalogo.parquet` | etapa 6 (`cruce_manchas.py`) | etapas 6 y 9 | un par mancha y polígono del catálogo que se tocan (intersección > 0), sin filtrar por el 30 % |
| `catalogos/frames.json` | etapa 2 | etapas 1, 4, 6, 7, 8 y 9 | un frame (un área de trabajo cubierta por una o más órbitas de NISAR) |
| `salidas/particiones.json` | etapa 6 (`armar_tabla.py`) | etapa 7 y la CNN | no es una tabla: qué frames van en cada partición |
| `salidas/tabla_entrenamiento.parquet` | etapa 6 (`armar_tabla.py`) | etapa 7 y la CNN | una mancha etiquetada de un frame |
| `salidas/predicciones.parquet` | etapa 7 (o el mock, mientras no haya modelo) | etapa 9 (`veredicto.py`) | una mancha candidata de un frame |

Además el mock escribe `catalogo_mock.geojson`, que no es un contrato: son los polígonos de catálogo inventados contra los que se cruzan las manchas del mock.

---

## 1. `salidas/manchas.geojson`
- **Lo escribe:** la etapa 4, frame por frame. Para el AMBA lo arma el prompt 3, desde `salidas/indice_80m.npz` con `insomnio.manchas()`.
- **Lo leen:** la etapa 5 (óptico), la etapa 6 (cruce con el catálogo), la etapa 9 y la web.
- **Una fila por mancha y frame** porque la mancha es la unidad del modelo: se entrena y se predice sobre manchas, no sobre polígonos del catálogo.
- **Formato:** un `FeatureCollection` de GeoJSON. Cada feature es un `Polygon` o `MultiPolygon` en grados (lon, lat). Las propiedades son las columnas de abajo.
- **Están todas las manchas, también las descartadas** (`descartada` dice el motivo). Las candidatas son las que tienen `descartada` en null.
- **Sólo manchas.** Los polígonos del catálogo no van acá: su óptico va en `tabla_optico_catalogo.parquet`.

| Columna | Tipo | Unidad | ¿Vacía? | Qué es |
|---|---|---|---|---|
| `id_mancha` | texto | — | no | Identificador de la mancha: `MAN-<frame>-<n>` |
| `frame` | texto | — | no | Clave del frame, la de `frames.json` (por ejemplo `AMBA`) |
| `ha` | número | ha | no | Superficie de la mancha |
| `forma` | texto | — | no | Forma según `insomnio.manchas()`. Valores: `compacta`, `alargada`, `lineal` |
| `descartada` | texto | — | sí | Motivo del descarte, o null si es candidata. Valores: `chica`, `lineal`, `lisa` |
| `etiqueta` | entero | — | no | Número de la mancha en la capa `manchas` del índice |
| `insomnio` | número | fracción 0-1 | sí | Media del insomnio por píxel en la mancha |
| `persistencia` | número | fracción 0-1 | sí | Media de la persistencia por píxel |
| `eco_db` | número | dB | sí | Eco medio de la mancha |
| `elongacion` | número | cociente ≥ 1 | no | Eje mayor / eje menor |
| `nucleo` | número | fracción 0-1 | no | Parte de la mancha que sobrevive a una erosión de 1 píxel |
| `lat` | número | grados | no | *Opcional.* Latitud del centro |
| `lon` | número | grados | no | *Opcional.* Longitud del centro |

**Clave** (no se repite): `id_mancha`.

`insomnio`, `persistencia`, `eco_db`, `elongacion`, `nucleo`, `forma`, `descartada` y `etiqueta` son los resúmenes que devuelve `insomnio.manchas()`, sin cambios. Los valores permitidos de `descartada`: `chica` (menos de 10 ha), `lineal` (ruta o arroyo) y `lisa` (eco medio menor que −13 dB).

## 2. `salidas/tabla_radar.parquet`
- **Lo escribe:** la etapa 4 (`extraer_manchas.py`, en la VM).
- **Lo lee:** la etapa 6 (`armar_tabla.py`).
- **Una fila por mancha candidata y frame.** Las descartadas no entran. Todo se mide **mancha contra anillo**.
- Son las columnas de Movimiento, Rugosidad, Forma y Contexto de la sección 4 del plan.

| Columna | Tipo | Unidad | ¿Vacía? | Qué es |
|---|---|---|---|---|
| `id_mancha` | texto | — | no | Identificador de la mancha: `MAN-<frame>-<n>` |
| `frame` | texto | — | no | Clave del frame, la de `frames.json` (por ejemplo `AMBA`) |
| `insomnio` | número | fracción 0-1 | no | Fracción de pares con coherencia < 0,80 × la del anillo, promediando órbitas |
| `persistencia` | número | fracción 0-1 | no | Mínimo de la fracción despierta en los tres tramos de la serie |
| `contraste_mediana` | número | cociente | sí | Coherencia de la mancha / la del anillo: mediana entre pares |
| `contraste_desvio` | número | cociente | sí | Desvío estándar de ese cociente entre pares |
| `coherencia_media` | número | coherencia 0-1 | sí | Coherencia absoluta media, normalizada a 12 días |
| `tendencia` | número | coherencia por día | sí | Pendiente de la coherencia normalizada en el tiempo |
| `n_pares` | entero | pares | no | Pares GUNW válidos sobre la mancha |
| `n_orbitas` | entero | órbitas | no | Órbitas con pares suficientes |
| `eco_db` | número | dB | sí | Eco (backscatter HH, gamma0) medio de la mancha |
| `eco_contraste` | número | dB | sí | Eco de la mancha menos el del anillo |
| `eco_variacion` | número | dB | sí | Desvío estándar del eco medio entre fechas |
| `hv_hh` | número | dB | sí | Cociente entre polarizaciones: eco HV menos eco HH |
| `area_ha` | número | ha | no | Superficie de la mancha (igual a `ha` en `manchas.geojson`) |
| `elongacion` | número | cociente ≥ 1 | no | Eje mayor / eje menor (la de `insomnio.manchas()`) |
| `compacidad` | número | 0-1 | sí | 4π × área / perímetro²: 1 es un círculo |
| `agua_anillo` | número | fracción 0-1 | sí | Parte del anillo de 1,5 km que es agua (JRC) |
| `urbano_anillo` | número | fracción 0-1 | sí | Parte del anillo que es urbana (ESA WorldCover, clase 50) |
| `cultivo_anillo` | número | fracción 0-1 | sí | Parte del anillo que es cultivo (ESA WorldCover, clase 40) |

**Clave** (no se repite): `id_mancha`.

## 3. `salidas/insomnio_catalogo.parquet`
- **Lo escribe:** la etapa 4. La lógica es `insomnio_catalogo.py` (prompt 2).
- **Lo leen:** la etapa 8 (evaluación de la actividad) y la etapa 9 (veredicto).
- **Una fila por polígono del catálogo y frame, esté o no en una mancha.** Es la segunda dirección del cruce: sin esto no se puede decir "cerrado y quieto" de un basural que no formó ninguna mancha, como Luján.
- Entran los basurales y los negativos cuyo polígono cae en el frame. Los de menos de 10 ha también entran, con `radar` = `no_alcanza`.
- `radar` usa los umbrales de `insomnio.Parametros`: `despierto` (insomnio ≥ 0,70 y persistencia ≥ 0,50), `quieto` (insomnio ≤ 0,20 con un entorno coherente) y `no_alcanza` (todo lo demás).
- Referencia en el AMBA (`salidas/fichas_80m.json`): Norte III 0,86 despierto, González Catán 1,00 despierto y Luján 0,00 quieto.

| Columna | Tipo | Unidad | ¿Vacía? | Qué es |
|---|---|---|---|---|
| `id_catalogo` | texto | — | no | `id` del polígono en `data/basurales/` (`BAS-…`) o `data/negativos/` (`NEG-…`) |
| `catalogo` | texto | — | no | De qué catálogo sale el polígono. Valores: `basurales`, `negativos` |
| `complejo` | texto | — | sí | `CPX-…` de `complejos.json` para los basurales; null para los negativos |
| `frame` | texto | — | no | Clave del frame, la de `frames.json` (por ejemplo `AMBA`) |
| `insomnio` | número | fracción 0-1 | sí | Insomnio del polígono contra su anillo, como `insomnio.ficha()` |
| `persistencia` | número | fracción 0-1 | sí | Mínimo de la fracción despierta en los tres tramos |
| `eco_db` | número | dB | sí | Mediana del eco en el polígono |
| `n_pares` | entero | pares | no | Pares GUNW válidos sobre el polígono |
| `radar` | texto | — | no | Lo que dice el radar, con los umbrales de `insomnio.Parametros`. Valores: `despierto`, `quieto`, `no_alcanza` |
| `motivo` | texto | — | sí | *Opcional.* Por qué salió ese `radar` |
| `area_ha` | número | ha | sí | *Opcional.* Superficie del polígono según el catálogo |
| `estado` | texto | — | sí | *Opcional.* Estado del registro (sólo basurales). Valores: `abierto`, `cerrado`, `contradictorio`, `desconocido` |
| `clase` | texto | — | sí | *Opcional.* Clase del negativo (`aeropuerto`, `cantera`…); null en basurales |

**Clave** (no se repite): `id_catalogo`, `frame`.

## 4. `salidas/tabla_optico.parquet`
- **Lo escribe:** la etapa 5 (`extraer_optico.py`).
- **Lo lee:** la etapa 6.
- **Una fila por mancha candidata y frame.** Se junta con `tabla_radar` por `id_mancha`.
- **Fuente:** Sentinel-2 L2A (Copernicus), 6 a 8 escenas con pocas nubes en el período de NISAR, con las nubes enmascaradas con la capa SCL. Las reflectancias van de 0 a 1, con el offset del producto ya aplicado.
- **Índices:** NDVI = (B08 − B04) / (B08 + B04); NDWI = (B03 − B08) / (B03 + B08); BSI = ((B11 + B04) − (B08 + B02)) / ((B11 + B04) + (B08 + B02)).
- "Media" es la media entre fechas del valor medio de adentro. "Contraste" es ese valor menos el del anillo. Si no hubo ninguna escena útil, `n_escenas` es 0 y lo demás va vacío.

| Columna | Tipo | Unidad | ¿Vacía? | Qué es |
|---|---|---|---|---|
| `id_mancha` | texto | — | no | Identificador de la mancha: `MAN-<frame>-<n>` |
| `frame` | texto | — | no | Clave del frame, la de `frames.json` (por ejemplo `AMBA`) |
| `ndvi_media` | número | índice −1 a 1 | sí | NDVI adentro, media entre fechas |
| `ndvi_variacion` | número | índice | sí | Desvío estándar del NDVI de adentro entre fechas |
| `bsi_media` | número | índice −1 a 1 | sí | Suelo desnudo (BSI) adentro, media entre fechas |
| `ndwi_media` | número | índice −1 a 1 | sí | NDWI (agua) adentro, media entre fechas |
| `swir_b11` | número | reflectancia 0-1 | sí | Banda B11 (1,6 µm) adentro, media entre fechas |
| `swir_b12` | número | reflectancia 0-1 | sí | Banda B12 (2,2 µm) adentro, media entre fechas |
| `ndvi_contraste` | número | índice | sí | `ndvi_media` menos el NDVI del anillo |
| `bsi_contraste` | número | índice | sí | `bsi_media` menos el BSI del anillo |
| `ndwi_contraste` | número | índice | sí | `ndwi_media` menos el NDWI del anillo |
| `swir_b11_contraste` | número | reflectancia | sí | `swir_b11` menos la B11 del anillo |
| `swir_b12_contraste` | número | reflectancia | sí | `swir_b12` menos la B12 del anillo |
| `n_escenas` | entero | escenas | no | Escenas de Sentinel-2 usadas |
| `fechas` | texto | AAAA-MM-DD | sí | Fechas de esas escenas, separadas por coma y en orden |

**Clave** (no se repite): `id_mancha`.

## 5. `salidas/tabla_optico_catalogo.parquet`
- **Lo escribe:** la etapa 5, con el mismo script.
- **Lo leen:** las etapas 8 y 9, para la ficha de cada sitio.
- **Una fila por polígono del catálogo y frame.** Son las mismas columnas ópticas, pero la clave es `id_catalogo` en vez de `id_mancha`.
- Existe para que los polígonos del catálogo no se mezclen con las manchas en `tabla_optico.parquet`. **No entra al entrenamiento.**

| Columna | Tipo | Unidad | ¿Vacía? | Qué es |
|---|---|---|---|---|
| `id_catalogo` | texto | — | no | `id` del polígono en `data/basurales/` (`BAS-…`) o `data/negativos/` (`NEG-…`) |
| `catalogo` | texto | — | no | De qué catálogo sale el polígono. Valores: `basurales`, `negativos` |
| `frame` | texto | — | no | Clave del frame, la de `frames.json` (por ejemplo `AMBA`) |
| `ndvi_media` | número | índice −1 a 1 | sí | NDVI adentro, media entre fechas |
| `ndvi_variacion` | número | índice | sí | Desvío estándar del NDVI de adentro entre fechas |
| `bsi_media` | número | índice −1 a 1 | sí | Suelo desnudo (BSI) adentro, media entre fechas |
| `ndwi_media` | número | índice −1 a 1 | sí | NDWI (agua) adentro, media entre fechas |
| `swir_b11` | número | reflectancia 0-1 | sí | Banda B11 (1,6 µm) adentro, media entre fechas |
| `swir_b12` | número | reflectancia 0-1 | sí | Banda B12 (2,2 µm) adentro, media entre fechas |
| `ndvi_contraste` | número | índice | sí | `ndvi_media` menos el NDVI del anillo |
| `bsi_contraste` | número | índice | sí | `bsi_media` menos el BSI del anillo |
| `ndwi_contraste` | número | índice | sí | `ndwi_media` menos el NDWI del anillo |
| `swir_b11_contraste` | número | reflectancia | sí | `swir_b11` menos la B11 del anillo |
| `swir_b12_contraste` | número | reflectancia | sí | `swir_b12` menos la B12 del anillo |
| `n_escenas` | entero | escenas | no | Escenas de Sentinel-2 usadas |
| `fechas` | texto | AAAA-MM-DD | sí | Fechas de esas escenas, separadas por coma y en orden |

**Clave** (no se repite): `id_catalogo`, `frame`.

## 6. `salidas/cruce_manchas_catalogo.parquet`
- **Lo escribe:** la etapa 6 (`cruce_manchas.py`).
- **Lo leen:** la etapa 6 (`armar_tabla.py`, para etiquetar) y la etapa 9 (para saber si una mancha ya era conocida).
- **Una fila por par de mancha y polígono que se tocan** (intersección mayor que cero). Una mancha puede tener varias filas y un polígono también.
- **No se filtra por el 30 %:** el archivo trae todos los cruces y el que lo lee aplica el criterio (`contratos.CRITERIO_CRUCE`, 0,30 sobre `frac_area_menor`; es un supuesto que se ajusta mirando el AMBA).
- Las áreas se miden en metros (UTM del frame), no en grados.

| Columna | Tipo | Unidad | ¿Vacía? | Qué es |
|---|---|---|---|---|
| `id_mancha` | texto | — | no | Identificador de la mancha: `MAN-<frame>-<n>` |
| `id_catalogo` | texto | — | no | `id` del polígono en `data/basurales/` (`BAS-…`) o `data/negativos/` (`NEG-…`) |
| `catalogo` | texto | — | no | De qué catálogo sale el polígono. Valores: `basurales`, `negativos` |
| `frame` | texto | — | no | Clave del frame, la de `frames.json` (por ejemplo `AMBA`) |
| `frac_mancha` | número | fracción 0-1 | no | Intersección / área de la mancha |
| `frac_poligono` | número | fracción 0-1 | no | Intersección / área del polígono |
| `frac_area_menor` | número | fracción 0-1 | no | Intersección / la menor de las dos áreas (el máximo de las otras dos) |
| `complejo` | texto | — | sí | *Opcional.* `CPX-…` del basural; null en negativos |
| `clase_negativo` | texto | — | sí | *Opcional.* Clase del negativo; null en basurales |

**Clave** (no se repite): `id_mancha`, `id_catalogo`.

## 7. `catalogos/frames.json`
- **Lo escribe:** la etapa 2 (`frames_elegir.py`).
- **Lo leen:** la etapa 1 y la 4 (caja y EPSG de cada frame), la 6 y la 7 (ciudad, país y qué queda para la prueba final), la 8 y la 9.
- **Una entrada por frame.** Va en `data/`, en la raíz del repo, junto a los catálogos.
- **Formato:** `{"meta": {…}, "frames": [ {…}, … ]}`, como los catálogos. En `meta` van la fecha, el script, la fuente (API de ASF) y el criterio de elección.

```json
{
  "meta": {"generado_por": "motor/frames_elegir.py", "fuente": "ASF, productos GUNW PR"},
  "frames": [
    {
      "frame": "AMBA", "orbita": [10, 161], "ciudad": "Buenos Aires", "pais": "ARG",
      "hemisferio": "S", "epsg": 32721, "bbox": [-59.35, -34.90, -58.25, -34.25],
      "n_gunw": 15, "fecha_inicio": "2026-06-25", "fecha_fin": "2026-10-12",
      "n_basurales_10ha": {"abierto": 1, "cerrado": 1, "desconocido": 2},
      "n_negativos": {"aeropuerto": 12, "cantera": 30},
      "reservado_prueba": true
    }
  ]
}
```
Los conteos del ejemplo son ilustrativos.

| Columna | Tipo | Unidad | ¿Vacía? | Qué es |
|---|---|---|---|---|
| `frame` | texto | — | no | Clave del frame, la de `frames.json` (por ejemplo `AMBA`) |
| `orbita` | lista de enteros | — | no | Órbitas (tracks) de NISAR que se usan. El AMBA usa dos: `[10, 161]` |
| `ciudad` | texto | — | no | Ciudad de referencia |
| `pais` | texto | ISO 3166-1 alfa-3 | no | País, como en los catálogos (`ARG`, `USA`, `IND`) |
| `hemisferio` | texto | — | no | Hemisferio de la zona UTM. Valores: `N`, `S` |
| `epsg` | entero | — | no | EPSG de la grilla UTM del producto (326xx norte, 327xx sur) |
| `bbox` | lista de 4 números | grados | no | `[lon_oeste, lat_sur, lon_este, lat_norte]`, como en GeoJSON. OJO: `geo.CAJA` va en otro orden |
| `n_gunw` | entero | pares | no | Pares GUNW `PR` disponibles |
| `fecha_inicio` | texto | AAAA-MM-DD | no | Primera fecha de la serie |
| `fecha_fin` | texto | AAAA-MM-DD | no | Última fecha de la serie |
| `n_basurales_10ha` | objeto {clave: entero} | complejos | no | Basurales de 10 ha o más por estado, contando cada complejo una vez. Claves: `abierto`, `cerrado`, `desconocido` |
| `n_negativos` | objeto {clave: entero} | polígonos | no | Negativos por clase (`aeropuerto`, `cantera`…) |
| `reservado_prueba` | booleano | — | no | true si queda fuera del entrenamiento (Argentina) |
| `frames_nisar` | lista de textos | — | sí | *Opcional.* Track, dirección y frame de cada producto, como en el nombre: `010_D_106` |

**Clave** (no se repite): `frame`.

## 8. `salidas/tabla_entrenamiento.parquet`
- **Lo escribe:** la etapa 6 (`armar_tabla.py`).
- **Lo leen:** la etapa 7 (`entrenar.py`) y la CNN opcional.
- **Una fila por mancha etiquetada y frame.** Es la tabla de la sección 4 del plan: identificación, las 29 variables (`contratos.COLUMNAS_MODELO`) y la etiqueta.
- **Qué manchas entran** (etapa 6): las que se cruzan, con el criterio del 30 %, con polígonos de **un solo** catálogo. Con un basural de cualquier estado → `basural_activo`; con un negativo → `otro_movil`. Las que se cruzan con los dos, o con ninguno, no entran.
- **Un complejo cuenta una vez:** si varias manchas caen sobre el mismo complejo, queda una fila por `complejo` y frame.
- **Las variables de EMIT no entran** (sería fuga de datos).
- Los frames de Argentina están en la tabla, pero en `prueba_final` (ver `particiones.json`).

| Columna | Tipo | Unidad | ¿Vacía? | Qué es |
|---|---|---|---|---|
| `id_mancha` | texto | — | no | Identificador de la mancha: `MAN-<frame>-<n>` |
| `id_catalogo` | texto | — | no | El polígono con el que se cruza (el de mayor `frac_area_menor`) |
| `complejo` | texto | — | no | `CPX-…` del basural; en los negativos, su propio `id_catalogo`. Sirve para agrupar |
| `frame` | texto | — | no | Clave del frame, la de `frames.json` (por ejemplo `AMBA`) |
| `ciudad` | texto | — | no | La de `frames.json` |
| `pais` | texto | ISO 3166-1 alfa-3 | no | El de `frames.json` |
| `clase_negativo` | texto | — | sí | Clase del negativo (`aeropuerto`…); null si es basural |
| `insomnio` | número | fracción 0-1 | no | Fracción de pares con coherencia < 0,80 × la del anillo, promediando órbitas |
| `persistencia` | número | fracción 0-1 | no | Mínimo de la fracción despierta en los tres tramos de la serie |
| `contraste_mediana` | número | cociente | sí | Coherencia de la mancha / la del anillo: mediana entre pares |
| `contraste_desvio` | número | cociente | sí | Desvío estándar de ese cociente entre pares |
| `coherencia_media` | número | coherencia 0-1 | sí | Coherencia absoluta media, normalizada a 12 días |
| `tendencia` | número | coherencia por día | sí | Pendiente de la coherencia normalizada en el tiempo |
| `n_pares` | entero | pares | no | Pares GUNW válidos sobre la mancha |
| `n_orbitas` | entero | órbitas | no | Órbitas con pares suficientes |
| `eco_db` | número | dB | sí | Eco (backscatter HH, gamma0) medio de la mancha |
| `eco_contraste` | número | dB | sí | Eco de la mancha menos el del anillo |
| `eco_variacion` | número | dB | sí | Desvío estándar del eco medio entre fechas |
| `hv_hh` | número | dB | sí | Cociente entre polarizaciones: eco HV menos eco HH |
| `ndvi_media` | número | índice −1 a 1 | sí | NDVI adentro, media entre fechas |
| `ndvi_variacion` | número | índice | sí | Desvío estándar del NDVI de adentro entre fechas |
| `bsi_media` | número | índice −1 a 1 | sí | Suelo desnudo (BSI) adentro, media entre fechas |
| `ndwi_media` | número | índice −1 a 1 | sí | NDWI (agua) adentro, media entre fechas |
| `swir_b11` | número | reflectancia 0-1 | sí | Banda B11 (1,6 µm) adentro, media entre fechas |
| `swir_b12` | número | reflectancia 0-1 | sí | Banda B12 (2,2 µm) adentro, media entre fechas |
| `ndvi_contraste` | número | índice | sí | `ndvi_media` menos el NDVI del anillo |
| `bsi_contraste` | número | índice | sí | `bsi_media` menos el BSI del anillo |
| `ndwi_contraste` | número | índice | sí | `ndwi_media` menos el NDWI del anillo |
| `swir_b11_contraste` | número | reflectancia | sí | `swir_b11` menos la B11 del anillo |
| `swir_b12_contraste` | número | reflectancia | sí | `swir_b12` menos la B12 del anillo |
| `area_ha` | número | ha | no | Superficie de la mancha (igual a `ha` en `manchas.geojson`) |
| `elongacion` | número | cociente ≥ 1 | no | Eje mayor / eje menor (la de `insomnio.manchas()`) |
| `compacidad` | número | 0-1 | sí | 4π × área / perímetro²: 1 es un círculo |
| `agua_anillo` | número | fracción 0-1 | sí | Parte del anillo de 1,5 km que es agua (JRC) |
| `urbano_anillo` | número | fracción 0-1 | sí | Parte del anillo que es urbana (ESA WorldCover, clase 50) |
| `cultivo_anillo` | número | fracción 0-1 | sí | Parte del anillo que es cultivo (ESA WorldCover, clase 40) |
| `cnn_p_basural` | número | probabilidad 0-1 | sí | *Opcional.* Lo que dice la ResNet-50, fuera de la partición |
| `clase` | texto | — | no | La etiqueta. Valores: `basural_activo`, `otro_movil` |

**Clave** (no se repite): `id_mancha`.

## 9. `salidas/particiones.json`
- **Lo escribe:** la etapa 6, junto con la tabla.
- **Lo leen:** la etapa 7 y la CNN, que tiene que usar las mismas particiones.
- **Las particiones van por frame:** todas las manchas de un frame caen en la misma, así un complejo nunca queda repartido. Los frames de Argentina (`reservado_prueba` en `frames.json`) van a `prueba_final` y no se usan para entrenar ni para elegir nada.

```json
{
  "meta": {"umbral_insomnio": 0.70, "criterio_cruce": 0.30},
  "particiones": {"0": ["DELHI", "LAGOS"], "1": ["CDMX"], "2": ["NAIROBI", "YAKARTA"]},
  "prueba_final": ["AMBA"]
}
```

| Clave | Tipo | Qué es |
|---|---|---|
| `meta.umbral_insomnio` | número | El insomnio mínimo con el que se armaron las manchas de entrenamiento (0,70, o menos si se bajó sólo para entrenar) |
| `meta.criterio_cruce` | número | La fracción del área menor que se usó para etiquetar (0,30) |
| `particiones` | objeto | Número de partición (como texto) → lista de frames. Al menos dos particiones, ninguna vacía |
| `prueba_final` | lista | Frames que quedan fuera del entrenamiento. Puede estar vacía |

Cada frame de la tabla aparece exactamente una vez. `contratos.particion_por_frame(d)` devuelve `{frame: partición}`. En `meta` se puede agregar lo que haga falta (semilla, conteos por clase).

## 10. `salidas/predicciones.parquet`
- **Lo escribe:** la etapa 7, cuando haya modelo. Mientras tanto, el mock.
- **Lo lee:** la etapa 9 (`veredicto.py`).
- **Una fila por mancha candidata y frame.** Para los frames de entrenamiento, la probabilidad sale de la partición en la que la mancha no se usó para entrenar.

| Columna | Tipo | Unidad | ¿Vacía? | Qué es |
|---|---|---|---|---|
| `id_mancha` | texto | — | no | Identificador de la mancha: `MAN-<frame>-<n>` |
| `frame` | texto | — | no | Clave del frame, la de `frames.json` (por ejemplo `AMBA`) |
| `p_basural` | número | probabilidad 0-1 | no | Probabilidad de `basural_activo` según el modelo |

**Clave** (no se repite): `id_mancha`.

---

## Qué trae el mock
`python motor/contratos_mock.py` escribe en `motor/datos/mock/` (que no se sube) todos los archivos de arriba, con el mismo nombre y en una sola carpeta. Son coherentes entre sí: los ids cruzan de un archivo al otro.

- **Frames:** `AMBA` (Argentina, va a `prueba_final`) y tres más para que haya particiones: `DELHI`, `CDMX` y `NAIROBI`. Las órbitas, las fechas y los conteos de los tres son inventados.
- **Por frame, 10 manchas candidatas:** 2 sobre un basural, 4 sobre un negativo (aeropuerto, cantera, contenedores y humedal), 1 que toca un basural y un negativo, 1 que roza un negativo con menos del 30 %, y 2 que no tocan nada. Más 3 descartadas (chica, lineal y lisa), que sólo están en el geojson.
- **Polígonos del catálogo sin mancha:** un basural cerrado y quieto, uno abierto y quieto, uno de menos de 10 ha, un cultivo quieto y una obra chica. Fuera del AMBA hay además un basural cerrado con una mancha encima, para probar "cerrado pero despierto".
- **Lo único real:** los ids y los valores de radar de Norte III (`BAS-053304`), González Catán (`BAS-000001`) y Luján (`BAS-000007`) en `insomnio_catalogo.parquet`, copiados de `salidas/fichas_80m.json`, y el id del aeropuerto El Palomar (`NEG-AMBA-000931`). Sus geometrías en el mock son rectángulos inventados.
- **Más filas:** `--manchas-por-frame 60` (para probar el entrenamiento con algo más que 27 filas) y `--semilla`.

## Decisiones que se tomaron acá
Las que no estaban en el plan y hubo que fijar. Si alguna molesta, se discute en la mesa y se cambia en `contratos.py` y acá a la vez.

1. **`frames.json` va con los catálogos** (`data/catalogos/frames.json`), y `orbita` es una lista porque el AMBA usa dos órbitas.
2. **`reservado_prueba`** en cada frame, para que las particiones salgan de un solo lugar.
3. **Columnas de contraste óptico** (`ndvi_contraste`, `bsi_contraste`, `ndwi_contraste`, `swir_b11_contraste`, `swir_b12_contraste`): el plan pide los índices "adentro y contra el anillo" pero sólo nombra los de adentro.
4. **`tabla_optico_catalogo.parquet`**, para el óptico de los polígonos del catálogo, separado del de las manchas.
5. **`predicciones.parquet`**, con `p_basural`, para que el veredicto se pueda escribir antes de que haya modelo.
6. **`clase_negativo`** en la tabla de entrenamiento, para reportar en qué clase de negativo se equivoca el modelo; y `complejo` nunca vacío (en los negativos es su propio id), para agrupar sin casos especiales.
7. **`fechas` es un texto** con las fechas separadas por coma, no una lista: se lee igual desde cualquier herramienta.
8. **Unidades que el plan no decía:** `tendencia` en coherencia por día; `hv_hh` y `eco_contraste` en dB (restas); `compacidad` = 4π × área / perímetro²; `urbano_anillo` y `cultivo_anillo` con las clases 50 y 40 de ESA WorldCover.

## Fuentes
- NISAR GUNW y GCOV (NASA/ISRO, vía ASF DAAC): movimiento y rugosidad.
- Sentinel-2 L2A (Copernicus, ESA): óptico.
- JRC Global Surface Water y ESA WorldCover: contexto.
- OpenStreetMap vía Overture Maps (ODbL), Climate TRACE (CC BY 4.0), EPA LMOP (dominio público) y NASA EMIT: los catálogos de `data/catalogos/` (detalle en `data/README.md`).
