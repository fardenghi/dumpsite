# Índice de insomnio

El índice responde a **"¿se mueve?"**. Qué es lo que se mueve lo decide el cruce con los catálogos y el modelo (`modelo.md`).

- **Código:** `motor/insomnio.py` (el cálculo), `motor/geo.py` (grillas y proyecciones) y `motor/pipeline_insomnio.py` (lectura de NISAR, salidas y web).
- **Datos:** NISAR L2 GUNW (coherencia) y GCOV (eco), de NASA/ISRO vía ASF DAAC, en la capa de 80 m. Agua de JRC Global Surface Water v1.4.
- **Salidas:** `data/salidas/indice_80m.*`, `resumen_80m.json`, `fichas_80m.json` y `calibracion_80m.json`.

```bash
cd motor
python pipeline_insomnio.py indice      # AMBA, 14 s con los recortes ya hechos
python pipeline_insomnio.py calibrar    # barre los umbrales
```

## Primer chequeo: un solo par
Con un GUNW (órbita 10, del 30/09 al 12/10/2026) y la coherencia a 20 m, la mediana adentro de cada predio contra un anillo de 1,5 km dio:

| Predio | Adentro | Anillo | Lectura |
|---|---|---|---|
| Norte III (CEAMSE) | 0,38 | 0,51 | Más oscuro que el entorno: activo |
| González Catán | 0,42 | 0,53 | Más oscuro: se ve la huella del predio |
| Basural de Luján | 0,66 | 0,62 | Quieto, consistente con el cierre |
| Control: CABA (Palermo) | 0,74 | 0,73 | Estable |

Con un solo par, la coherencia encuentra **agua** antes que basurales: el embalse Roggero, los lagos de Nordelta, el Delta. De ahí salen la máscara de agua, el filtro por eco y el filtro por forma.

## Cómo se calcula
Sobre 15 GUNW y 19 GCOV del AMBA (órbitas 10 y 161, del 25/06 al 12/10/2026):

| Paso | Qué hace |
|---|---|
| **Máscara de agua** | JRC Global Surface Water, con ocurrencia de 10 % o más, ensanchada 80 m. Saca 97.493 ha de las 718.952 de la grilla |
| **Comparación con el entorno** | Un par cuenta como "despierto" si la coherencia es menor que 0,80 × la mediana del entorno (tierra en 2 km). Como compara cada par consigo mismo, no lo afecta mezclar pares de 12, 24 y 36 días |
| **Por órbita** | La fracción de pares despiertos se calcula por órbita y se promedia |
| **Persistencia** | La serie se parte en tres tramos y se toma el mínimo. Hace falta 0,5 o más en los tres. Así quedan afuera 4.226 ha que sólo se mueven por temporada |
| **Forma** | Se descartan las manchas lineales (rutas, arroyos) |
| **Eco** | Las manchas con eco medio de menos de −13 dB son superficies lisas (agua, pistas) y se descartan |
| **Tamaño** | 10 ha como mínimo, unos 16 píxeles de 80 m |

Para un sitio, el insomnio es la fracción de pares en los que la mediana de coherencia adentro del predio es menor que 0,80 × la de su anillo de 1,5 km. Del anillo se sacan el agua y **todos los polígonos de los catálogos**, para que un relleno vecino o un aeródromo no bajen la referencia.

## Sitios del AMBA (80 m)
| Sitio | Registro | ha | Insomnio | Radar |
|---|---|---|---|---|
| Norte III (calibración) | activo | 265 | **0,86** | despierto |
| González Catán (calibración) | sin registro | 155 | **1,00** | despierto |
| Norte III, disposición final | activo | 72 | 1,00 | despierto |
| Relleno junto a Norte III (oeste) | sin registro | 150 | 0,93 | despierto |
| **Basural de Luján** | cerrado el 1/07/2026 | 44 | **0,00** | **quieto** |
| Relleno sin nombre, Benavídez | sin registro | 11 | 0,13 | quieto |
| Villa Domínico | cerrado en 2004 | 8 | 0,33 | no alcanza |
| Control: CABA, Delta, embalse Roggero, campo | — | — | 0,00 | quieto |

- Los dos sitios de calibración salen despiertos y los controles, quietos.
- Los polígonos del complejo Norte que **no** se usaron para calibrar también salen despiertos (0,93 a 1,00).
- **Luján da 0,00 en los 15 pares.**

**Manchas candidatas: 219, que suman 7.050 ha (el 1,1 % de la tierra).** De esas, 7 pisan un relleno de OSM, 22 son usos conocidos (aeródromos, golf, cementerios) y 190 quedan sin explicar. **Las sin explicar no están verificadas.**

## Umbrales
Una combinación de umbrales es válida si Norte III y González Catán salen despiertos, CABA sale quieta y las manchas cubren menos del 5 % de cada control.

| Umbral | Valor | Rango válido |
|---|---|---|
| `razon` (coherencia / entorno) | 0,80 | 0,725 a 0,825 |
| `min_insomnio` | 0,70 | 0,5 a 0,8 |
| `eco_min_db` | −13 | −16,6 a −11,6 |
| `min_persistencia` | 0,50 | no se calibró |
| `min_ha` | 10 | no se calibró |

**No es una validación independiente:** son dos positivos y cinco controles. Fuera de la calibración, el cruce con los catálogos del AMBA da un **AUC de 0,88** con 4 complejos de basurales y 274 negativos. Con tan pocos positivos, el número sólo dice que el índice separa. No sirve como medida de precisión.

## Límites
- **El pasto de un aeródromo o un monte pierde coherencia en todos los pares,** igual que un relleno. El índice no los distingue: eso queda para el cruce con los negativos y el modelo.
- Los umbrales se calibraron **sólo en el AMBA** y no se recalibraron por frame.
- La **capa de 20 m** no es la referencia: a 20 m Norte III da 0,79 y "no alcanza". Habría que recalibrar.

## Variante descartada: percentil del entorno
Se probó que un par cuente como despierto si la coherencia está por debajo del percentil P del entorno. Con P = 20 salen 494 manchas en vez de 219 y el AUC del cruce baja de 0,88 a 0,77. Pierde porque un predio grande baja el percentil de su propio entorno. El código quedó en la historia del repo (`motor: variante del índice por percentil del entorno`).

## Índice de actividad (experimental)
El insomnio de un predio es la mediana de **todo** el polígono, y por eso falla de dos maneras: marca como despierto un relleno cerrado con pasto y no ve un frente de descarga chico en un predio grande. Para eso hay tres columnas nuevas en `tabla_radar.parquet` e `insomnio_catalogo.parquet`:

| Columna | Qué mide |
|---|---|
| `contraste_p10` | Coherencia del 10 % menos coherente del predio sobre la del anillo |
| `eco_var_p90` | Variación del eco en el tiempo, percentil 90 del predio |
| `indice_actividad` | Regresión logística con las dos anteriores, de 0 a 1. **No es una probabilidad** |

Se ajustó con 53 predios de 9 frames con etiquetas ópticas asignadas por IA. Contra el registro (59 predios, que no se usaron para ajustarlo) da un AUC de 0,69, contra 0,50 del insomnio. Es la idea que después tomó el modelo del frente activo (`modelo.md`).
