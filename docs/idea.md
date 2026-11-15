# La idea: lo que el radar nunca ve quieto

**Challenge:** Dancing with the SARs (NISAR), NASA Space Apps 2026.

## El problema
En Argentina se estima que hay unos 5.000 basurales a cielo abierto. El dato es del Ministerio de Ambiente y no sale de un relevamiento formal. En la Provincia de Buenos Aires, 81 de 135 municipios usaban basurales según el informe de 2023. Los cierres se anuncian, pero no hay un inventario abierto y georreferenciado que permita controlar si un basural "cerrado" sigue recibiendo residuos.

## Qué hace
NISAR pasa sobre el mismo lugar cada 12 días. Al comparar dos pasadas, mide cuánto se parecen (la **coherencia**). Un campo pierde coherencia por la estación (cosecha, lluvia) y una ciudad casi nunca la pierde. Un basural activo, en cambio, la pierde en todos los pares, porque lo remueven todos los días.

Dumpsite busca los lugares que **nunca se ven quietos**:

1. Calcula un **índice de insomnio** por píxel: la fracción de pares en los que la coherencia cae muy por debajo de la de su entorno (`indice-insomnio.md`).
2. Arma **manchas candidatas** y descarta agua, rutas y superficies lisas.
3. **Cruza** las manchas con un catálogo de 66.981 basurales del mundo y con 64.986 negativos (lo que el radar confunde con un basural: aeródromos, canteras, playas de contenedores).
4. Da un **veredicto por sitio** contra el registro oficial: "activo, ya conocido", "cerrado pero despierto", "cerrado y quieto" o "el radar no alcanza".
5. Con un **modelo de abierto contra cerrado** entrenado con el registro de la EPA, ordena los sitios según qué tan compatibles son con un basural abierto (`modelo.md`).

Todo se ve en una web con el mapa del índice, una ficha por sitio y el panel del modelo.

## El caso Luján
El basural de Luján dejó de recibir residuos el **1/07/2026**, tras unos 52 años. NISAR tiene unos 3,5 meses de pares posteriores al cierre.

- **Luján da insomnio 0,00 en los 15 pares** (dos órbitas, del 25/06 al 12/10/2026). En ningún par la coherencia del predio bajó respecto de su anillo. El veredicto es "cerrado y quieto".
- **Norte III (CEAMSE)**, el relleno que recibe la mayor parte de la basura del AMBA, da 0,86, y González Catán da 1,00. La ciudad (Palermo) da 0,00.
- El modelo de abierto contra cerrado, entrenado sólo con EE. UU., le da 0,16 a Luján y 0,99 al complejo Norte III.

Límite: el primer par de cada órbita cruza el 1/07, así que no hay un "antes" del cierre con NISAR.

## Para quién
Autoridades ambientales provinciales y municipales, periodistas y ONG que auditan cierres. La salida es una lista que se puede revisar sitio por sitio, con la fuente de cada número.

## Lo que no dice
- **No acusa a nadie.** Habla de "señal compatible con actividad" y de "quieto según el radar".
- **No separa todo.** El pasto de un aeródromo, un humedal o una playa de contenedores también pierden coherencia. Por eso se cruza con los negativos.
- **No ve lo chico.** Abajo de 10 ha, que son unos 16 píxeles de 80 m, el veredicto es "el radar no alcanza".
- **La serie es corta.** Los datos públicos de NISAR arrancan a mediados de 2026: en el AMBA hay cuatro meses de pares y en EE. UU., hasta un año.

## Por qué no es obvia
Lo típico del challenge es comparar antes y después de un evento: una inundación, la deforestación o la subsidencia. Esta idea no busca un cambio, busca la firma temporal de lo que cambia **siempre**. Usa la coherencia perdida que los demás descartan y la cruza contra un registro oficial.
