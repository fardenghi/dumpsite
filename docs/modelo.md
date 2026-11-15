# Modelo

Hay dos modelos y responden preguntas distintas:

| Modelo | Pregunta | Resultado | Estado |
|---|---|---|---|
| **Abierto contra cerrado** (`motor/modelo_estado.py`) | Con lo que mide NISAR sobre un predio, ¿el registro lo da abierto o cerrado? | AUC **0,91** (0,87 a 0,95) en frames que no vio | Principal |
| Basural contra otra cosa que se mueve (`motor/entrenar.py`) | Una mancha despierta, ¿es un basural o un aeródromo, una cantera, un puerto? | AUC 0,79 (0,72 a 0,87) | Flojo: sirve para ordenar, no como veredicto |

## El flujo
1. **Pipeline por frame** (`pipeline_insomnio.py`): el insomnio por píxel en cualquier frame de NISAR.
2. **Frames** (`frames_elegir.py`): 10 elegidos por cantidad de basurales con estado conocido y 20 más por cantidad de abiertos. Están en `data/catalogos/frames.json`.
3. **Manchas y radar** (`extraer_manchas.py`): manchas, variables de radar contra el anillo e insomnio de cada polígono del catálogo.
4. **Óptico** (`extraer_optico.py`): Sentinel-2 L2A por mancha y por polígono, contra el anillo.
5. **Cruce** (`cruce_manchas.py`): qué manchas tocan qué polígonos.
6. **Tabla y entrenamiento** (`armar_tabla.py`, `entrenar.py`, `modelo_por_frame.py`).
7. **Actividad** (`evaluar_actividad.py`): el radar contra el registro, con etiquetas independientes del insomnio.
8. **Veredicto y web** (`veredicto.py`, `flujo.py`).

Los archivos intermedios siguen `contratos-datos.md`. Argentina queda **fuera del entrenamiento**: el AMBA se reserva como prueba final.

## Cruce entre manchas y catálogo
Una mancha se asigna a un polígono si la intersección cubre **al menos el 30 % del área menor** y mide **al menos 5,12 ha** (8 píxeles de 80 m). El mínimo de superficie evita que un polígono diminuto adentro de una mancha grande la etiquete entera. Si una mancha toca a la vez un basural y un negativo, no entra.

## Modelo de abierto contra cerrado
- **Etiquetas:** el estado del registro (EPA LMOP, casos curados). **No salen del insomnio.**
- **Muestras:** 198 basurales de 10 ha o más con estado, de 26 frames (121 abiertos y 77 cerrados). Casi todos son de EE. UU. y 12 de Puerto Rico.
- **Validación:** se deja un frame afuera por vez. Intervalos del 95 % por remuestreo.
- **Ningún modelo usa el área:** en el registro los abiertos son más grandes, y el área sola ya da AUC 0,79.

### Variables del frente activo (`motor/radar_frente.py`)
En vez de la mediana del predio, se mira **la parte que más cambia**. Son 10 variables, todas contra el anillo de 1,5 km:

- **Eco:** desvío temporal del eco por píxel (HH y HV), el parche de 3×3 donde más cambia y el cambio neto entre el principio y el final de la serie.
- **Coherencia:** el peor parche de 3×3, el peor parche sobre la mediana del predio, la mayor zona que queda por debajo del anillo y cuánto se corre el peor parche.

### Resultado
| Variables | AUC (IC 95 %) |
|---|---|
| **Frente** (10, sólo NISAR) | **0,908 (0,867 a 0,946)** |
| Frente + óptico (18) | 0,927 (0,889 a 0,958) |
| Óptico (8, Sentinel-2) | 0,869 (0,807 a 0,920) |
| Radar del predio entero (7) | 0,778 (0,708 a 0,839) |

El criterio para elegir se fijó antes de mirar el AMBA: el más simple que no esté a más de 0,02 del mejor. **Queda el frente, que usa sólo NISAR.**

Por tamaño: AUC de 0,76 en los predios chicos (10 a 42 ha), 0,90 en los medianos y 0,97 en los grandes.

### Qué aprende
1. Hay **una zona chica que pierde coherencia mucho más que el resto** del predio (abierto).
2. **El eco cambia en el tiempo** (abierto).
3. Un predio **parejo y sin coherencia en toda su superficie** es, en estos datos, un relleno cerrado. Es compatible con vegetación sobre la cobertura final.

La variable que más pesa está mezclada con el tamaño: en un predio grande es más fácil que algún parche quede muy abajo. La variación del eco es la más limpia.

### Prueba en el AMBA (no entró al entrenamiento)
| Predio | Registro | `p_abierto` |
|---|---|---|
| Basural de Luján | Cerrado (1/07/2026) | **0,16** |
| Norte III, el complejo como una unidad | Abierto | **0,99** |
| Norte III, polígono `BAS-053304` | Lleva el "abierto" del complejo | 0,07 |
| Norte III, sector oeste (`BAS-016796`) | Sin estado propio | 0,96 |
| González Catán | Sin estado | 0,87 |

**Norte III:** el estado "abierto" quedó pegado al polígono más cercano a una coordenada aproximada, `BAS-053304`, que es un sector cubierto de vegetación. El radar y el óptico ubican el cambio en el sector oeste. Medido como complejo da 0,99. El polígono suelto sigue saliendo cerrado y no lo escondemos.

### Qué se puede decir
- **Sí:** "con variables de NISAR que miran el frente activo, un modelo entrenado con el registro de la EPA ordena abiertos y cerrados con AUC 0,91 en frames que no vio".
- **Con cuidado:** Luján 0,16 y Norte III 0,99 son dos casos, no una estadística.
- **No:** que funcione en predios chicos ni fuera de EE. UU., ni que `p_abierto` sea una probabilidad calibrada.

## Modelo de basural contra otra cosa que se mueve
LightGBM sobre una fila por mancha despierta (unas 30 variables de radar, óptico, forma y entorno): `basural_activo` contra `otro_movil` (aeródromos, contenedores, canteras, humedales). Lo quieto no pasa por el modelo.

- 39 basurales y 553 manchas de otra cosa, en 9 frames. Dejando un frame afuera, el AUC es **0,79**.
- Con el umbral de 0,5 encuentra 9 de 39 basurales (recall 0,23) y acierta 9 de las 31 que marca (precisión 0,29).
- **Sirve para ordenar** qué mancha sin explicar mirar primero. **No sirve como veredicto.**

## Etiquetas ópticas asignadas por IA
Para 89 basurales de 9 frames, un modelo de lenguaje con visión contestó "¿se ve actividad adentro del predio?" mirando Sentinel-2 en tres fechas. Lo hizo en dos pasadas independientes y a ciegas, sin nombre, registro ni radar. **No las revisó una persona.** Se usaron para el índice de actividad y para las variantes del modelo por mancha (`data/salidas/etiquetas_optico_ia.json`).

## Prueba de resolución: 20 m contra 80 m
`motor/prueba_resolucion.py` probó medir el frente con el eco y la coherencia a 20 m. **Ninguna variante mejora al modelo de 80 m más que el margen de error.** La única que suma algo es la coherencia a 20 m (+0,016 de AUC, con un intervalo de −0,022 a +0,061). No conviene rehacer los 30 frames.

## Qué existe afuera
Buscamos modelos o productos que clasifiquen rellenos en activos y cerrados desde satélite. **No encontramos ninguno con radar a escala**, ni con NISAR ni con Sentinel-1. Lo más cercano son detectores ópticos que dicen *dónde* hay un basural, inventarios de emisiones que toman el estado de registros oficiales y métodos de actividad con coherencia de Sentinel-1 en minería.

## Propuesta sin probar: CNN óptica
Una ResNet-50 preentrenada con SSL4EO-S12 (las 13 bandas de Sentinel-2, incluido SWIR) que mire el recorte de cada mancha y entre como una variable más del modelo por mancha. Quedó planteada y no se entrenó.
