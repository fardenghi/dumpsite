# Resultados

**Lenguaje:** "señal compatible con actividad" y "quieto según el radar". Nada de esto es una acusación.

## Los 30 frames
El pipeline corrió sobre **30 frames de NISAR, con 962 pares GUNW** en la capa de 80 m:

- **10 frames elegidos primero** por cantidad de basurales con estado conocido y de negativos: AMBA, Los Ángeles, CDMX, Delhi, Yakarta, Ponce (Puerto Rico) y cuatro condados de EE. UU.
- **20 frames de EE. UU. agregados** por cantidad de basurales abiertos.

| Frames | Pares | Manchas | Candidatas | En un basural del catálogo | Uso conocido (OSM) | Sin explicar | ha candidatas |
|---|---|---|---|---|---|---|---|
| Los 10 primeros | 333 | 22.874 | 2.578 | 41 | 639 | 1.898 | 84.382 |
| Los 20 agregados | 629 | 46.703 | 1.945 | 56 | 492 | 1.397 | 48.370 |

Una mancha es **candidata** si tiene insomnio de 0,70 o más, persistencia de 0,50 o más, no es agua ni lineal, tiene eco de −13 dB o más y mide 10 ha o más. Los umbrales se calibraron **sólo en el AMBA** y no se tocaron por frame. El detalle por frame está en `data/salidas/<FRAME>/` y lo resume `motor/resumen_etapa4.py`.

## Veredicto por sitio
`motor/flujo.py` junta el cruce en las dos direcciones (manchas sobre catálogo y catálogo sobre manchas) y da un veredicto por polígono del catálogo y por mancha sin catálogo. Está en `data/salidas/veredictos.json` y es lo que muestra la web.

**Controles del AMBA:**
- **González Catán:** sin registro, despierto, insomnio 1,0. Veredicto: activo, ya conocido.
- **Norte III:** abierto, despierto, insomnio 1,0. Veredicto: activo, ya conocido.
- **Basural de Luján:** cerrado, quieto, insomnio 0,0. Veredicto: **cerrado y quieto**.

## Matriz de actividad
¿El insomnio coincide con el registro? Sobre los basurales con estado conocido que el radar pudo medir, con intervalos de Wilson al 95 %:

| País | Abiertos despiertos | Cerrados quietos | Cerrados despiertos | Concordancia |
|---|---|---|---|---|
| ARG | 1/1 | 1/1 | 0/1 | 2/2 |
| PRI | 0/5 (0 % a 43 %) | 2/2 | 0/2 | 2/7 (29 %) |
| USA | 16/40 (40 %, 26 % a 55 %) | 10/26 (38 %) | 16/26 (62 %) | 26/66 (39 %) |

**Lectura honesta:** en EE. UU. salen despiertos el 40 % de los abiertos y el 62 % de los cerrados. **El insomnio solo no separa abiertos de cerrados.** Muchos rellenos cerrados siguen moviéndose por el biogás, el asentamiento, las obras o la vegetación. Esa es la razón del modelo del frente activo (`modelo.md`).

Sesgo: de los 193 sitios de estado conocido que el radar midió, 179 son de EE. UU. (salen de la EPA). La matriz vale para esos países, no "para el mundo".

## Regla contra modelo
Sobre los mismos 198 basurales de 10 ha o más con estado (26 frames, sin el AMBA):

| | Decide | Coincide con el registro |
|---|---|---|
| Regla del insomnio | 73 de 198 (37 %) | 28 de 73 (38 %) |
| **Modelo del frente** (umbral 0,5) | 198 de 198 | **170 de 198 (86 %)** |

Aplicado a los 148 basurales de 10 ha o más **sin estado** de los 30 frames, el modelo marca 56 con `p_abierto` mayor que 0,5. Están en `data/salidas/predicciones_estado.parquet`. **No están verificados.**

## Casos para mirar a mano
- **Cerrados pero despiertos: 16**, todos en EE. UU. Por ejemplo: Operating Industries (Los Ángeles, cerrado en 1984), Palos Verdes (1980), Norris Farms (Maryland, 1986) y Tri-Cities (California, 2012). En casi todos **no se descarta** una explicación obvia: muchos tienen captura de biogás según LMOP (pozos y cañerías mueven el suelo) o una planta de reciclaje en el predio. Antes de nombrar uno hay que mirarlo en óptico.
- **Abiertos pero quietos: 29.** La explicación más común es que el frente de descarga (1 a 3 ha) es más chico de lo que mueve la mediana de un predio grande, o que el registro de la EPA (2024) quedó desactualizado.

## Norte III
El modelo de radar daba "cerrado" al polígono de Norte III con estado "abierto". La etiqueta estaba en el polígono equivocado: `BAS-053304` es un sector cubierto de vegetación, y tanto el radar como el óptico ubican el cambio en otro polígono del mismo complejo, `BAS-016796`. Medido como complejo, el modelo da 0,99.

## Óptico
- **AMBA, con medias sobre el polígono:** el óptico **no separa** un relleno sanitario de un aeródromo con pasto. Los rellenos grandes del AMBA están casi todos tapados con vegetación, y el frente activo es una parte chica del predio.
- **1.008 basurales de estado conocido** (`motor/optico_estado_conocido.py`): la regla "menos verde que su entorno" (NDVI del predio menos el del anillo, menor que −0,15) marca **313 de 578 abiertos (54 %) y 71 de 369 cerrados (19 %)**, con un AUC de 0,77. El umbral se fijó antes y no se ajustó.

## Lo que no hay que decir
- Que el radar "detecta el cierre" en general. Se pueden mostrar casos puntuales, como Luján, con su contexto.
- Que las manchas sin explicar son basurales. Ninguna está verificada.
- Que `p_abierto` o `p_basural` son probabilidades calibradas.
