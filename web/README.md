# Basurales · web

Los basurales que el radar NISAR nunca ve quietos. Proyecto para el NASA Space Apps Challenge 2026 (challenge "Dancing with the SARs").

```bash
npm install
npm run dev      # http://localhost:5183
npm run build    # sitio estático en dist/
```

## Secciones
El mapa es el fondo de toda la web y queda siempre a la vista. Las secciones son paneles que flotan encima y se abren y cierran desde la barra de abajo (o con Esc).

| Ruta | Qué muestra |
|---|---|
| `#/mapa` | El AMBA con el índice de insomnio y los sitios. Al abrir uno: veredicto, coherencia par a par e imágenes Sentinel-2 por fecha. Los basurales del catálogo de los otros frames van como puntos; la leyenda tiene un botón para alejar el mapa hasta verlos todos |
| `#/inicio` | Panel "Resumen": cantidad de sitios, ranking de insomnio y el caso Luján |
| `#/sitios` | Panel con la lista filtrable por frame y por estado del radar, exportable a CSV. Arranca en el AMBA |
| `#/modelo` | Panel con la regla par por par (con un sitio de ejemplo), el embudo de la grilla a las manchas candidatas, los umbrales calibrados, **el modelo de abierto contra cerrado con sus métricas** (si `modelo.json` las trae) y el clasificador por mancha propuesto, que todavía no tiene métricas |

## Datos
**Son reales y están precalculados.** Los escribe el pipeline del índice de insomnio y no se editan a mano:

```bash
python ../idea-basurales-nisar/herramientas/pipeline_insomnio.py indice
```

| Archivo | Qué tiene |
|---|---|
| `src/data/seed/sitios.json` | 12 sitios del AMBA con la forma exacta de `Sitio[]` (`src/data/types.ts`): insomnio respecto del anillo de 1,5 km, veredicto del radar, 15 pares de NISAR (las dos órbitas, ordenados por fecha), registro con fuente y contorno de OpenStreetMap |
| `src/data/seed/fichas.json` | Por sitio, lo que no entra en `Sitio`: motivo del veredicto, persistencia, insomnio por órbita, órbita de cada par, eco, objetos de OSM y fuentes del registro. Lo usa el panel Modelo |
| `src/data/seed/candidatos.json` | Las 219 manchas candidatas con centro, superficie y clase (`relleno_osm`, `uso_conocido`, `sin_explicar`). El panel Modelo muestra el conteo por clase; en el mapa todavía no están. Las "sin explicar" no están verificadas: hablar de "señal compatible con actividad" |
| `public/indice/insomnio-amba.png` + `src/data/seed/indice.json` | El índice del AMBA como PNG (norte arriba, regular en Web Mercator) y sus límites: `oeste`, `sur`, `este`, `norte` y `coordinates`, las cuatro esquinas en el orden que pide una fuente `image` de MapLibre. `Mapa.tsx` lo carga así y el botón "Índice de insomnio" lo prende y lo apaga |

### Veredictos de todos los frames y modelo de abierto contra cerrado
Los escribe `python ../idea-basurales-nisar/herramientas/flujo.py --web`. **Los dos archivos son opcionales**: la web los busca con `import.meta.glob` (`src/data/veredictos.ts`) y, si faltan o no traen las claves nuevas, queda como antes.

| Archivo | Qué usa la web |
|---|---|
| `src/data/seed/veredictos.json` | `sitios[]`: un polígono del catálogo de basurales por fila, con `frame`, `registro`, `radar`, `insomnio`, `veredicto_texto`, `lat` y `lon`. Los del AMBA no se listan aparte: el AMBA sigue siendo los 12 sitios curados de `sitios.json`. Los de los otros frames son las filas nuevas de la lista y los puntos nuevos del mapa |
| `sitios[].modelo_estado` (opcional) | `{p_abierto, lectura, origen}`: lo que dice el modelo de abierto contra cerrado de ese polígono. Se muestra en la ficha y en la lista, **rotulado "según el modelo"** y aparte del estado del registro y del veredicto del radar. `p_abierto` va como "puntaje de abierto, de 0 a 1", no como probabilidad |
| `src/data/seed/modelo.json`, clave `estado` (opcional) | `{auc, ic95, n, abiertos, cerrados, frames, variables, validacion, limites, prueba_amba}`: el panel Modelo lo muestra tal como viene, con los límites y la prueba en el AMBA. Sin `estado`, el panel no muestra el modelo |

- **Ningún número del modelo está escrito en el código**: todo sale de esos dos JSON. Los tipos están en `src/data/types.ts` (`Veredicto`, `LecturaModelo`, `ModeloEstado`).
- **Cómo se le asigna la lectura del modelo a un sitio curado del AMBA:** `sitios.json` no trae el id del catálogo, así que se busca el polígono del catálogo del frame `AMBA` que está a menos de 0,4 km y mide lo mismo (cociente de superficies de hasta 1,25). Si no hay uno claro, el sitio queda sin lectura (por ejemplo, la mancha al oeste de Luján, que no es un predio). Ver `veredictoDeSitio` en `src/data/veredictos.ts`.
- **El nombre de cada frame sale de su clave** (`USA_OH_LAKE` → "Lake, OH, USA"): el seed no trae la ciudad.
- **Fuera del AMBA no hay contorno, serie de coherencia ni imágenes por fecha**: la ficha muestra el veredicto, el registro, el insomnio, la superficie, el motivo y la lectura del modelo, y el mapa se acerca menos (el fondo de Blue Marble llega hasta el zoom 8).
- **Lenguaje:** "compatible con abierto según el modelo" y "señal compatible con actividad". El estado sólo se muestra cuando lo da el registro; los polígonos sin estado dicen "En el catálogo, sin estado".

Los sitios de otros países que tenía el seed se sacaron: no tienen NISAR procesado. `scripts/contornos.py` quedó sin uso (los contornos los escribe el pipeline). Cómo se calcula cada número: `../idea-basurales-nisar/idea/indice-final.md`.

Toda la web lee los datos por `src/data/api.ts`. Para conectar un backend alcanza con definir `VITE_API_URL` (ver `.env.example`) y que responda `GET /sitios` con la forma de `Sitio` en `src/data/types.ts`.

## Imágenes satelitales
Sin claves ni cuentas:
- **Blue Marble** (NASA GIBS) como fondo del mundo.
- **Sentinel-2 L2A, 10 m** (ESA Copernicus) por fecha, al abrir un sitio. Los tiles los sirve [Microsoft Planetary Computer](https://planetarycomputer.microsoft.com/dataset/sentinel-2-l2a).
- Cada ficha tiene un enlace a Google Maps para ver el sitio con más detalle.

**Opcional, con clave: alta resolución de Google** (Map Tiles API, satelital 2D). Con `VITE_GOOGLE_MAPS_KEY` en `.env.local` (ver `.env.example`), al abrir un basural el mapa encuadra el predio y muestra la imagen de Google, de menos de 1 m. Sirve para el impacto visual: se ve que es un basural.
- **Cada tile se cobra**, así que se piden sólo adentro de la caja del sitio abierto y desde zoom 13. El resto del mapa nunca le pega a Google.
- **No tiene fecha.** Para comparar momentos se sigue usando Sentinel-2: al elegir una fecha en la ficha se vuelve a esa vista.
- Sin clave, o si la sesión falla, la web anda igual que antes.
- La clave queda visible en el navegador: restringirla por referrer HTTP y a la Map Tiles API. No va al repo.
- Google exige mostrar su nombre y el copyright de la zona; el mapa lo hace abajo a la derecha. Probado el 14/11 con una clave real.

## Contornos de los predios
Los contornos salen del pipeline del índice (polígonos `landuse=landfill` de OpenStreetMap, bajados por `fuentes_fijas.py`): 11 de los 12 sitios tienen contorno real. Queda con un aro la mancha al oeste de Luján, que no es un predio registrado. `scripts/contornos.py` sirve para sitios nuevos fuera del AMBA, pero ya no escribe los de este seed.

## Caché del mapa
`public/sw.js` guarda los tiles de Blue Marble y de Sentinel-2 la primera vez que se piden y después los sirve sin red. Además, al cargar la web se precarga la imagen Sentinel-2 más reciente de cada basural, que es lo que se recorre siempre. Los tiles de Google quedan afuera: sus términos no permiten guardarlos ni precargarlos, sólo el caché normal del navegador.

`python3 scripts/s2_fechas.py` consulta el catálogo STAC y guarda en `src/data/seed/imagenes.json` hasta 8 escenas con menos de 10 % de nubes por sitio. No tiene dependencias.

## Fuentes y licencias
- NISAR L2 GUNW y GCOV (NASA/ISRO), vía ASF DAAC.
- JRC Global Surface Water v1.4 (Pekel et al., 2016, Nature 540), para la máscara de agua.
- Blue Marble (NASA), vía GIBS.
- Sentinel-2 (ESA Copernicus), vía Microsoft Planetary Computer.
- OpenStreetMap, ODbL.
- Catálogo de basurales de los otros frames: polígonos de OpenStreetMap vía Overture Maps (release 2026-10-21.0, ODbL) y estado del registro de U.S. EPA LMOP (2024-09, dominio público). Detalle en `../data/README.md`.
- Imagen satelital de Google (Map Tiles API), sólo si se configura la clave. Tiene copyright de Google y de sus proveedores: hay que declararla en el formulario de entrega.
- Tipografías Roboto Slab (Apache 2.0) y DM Sans (OFL). Mapa con MapLibre GL JS (BSD-3).
- Código: Apache 2.0. Escrito con asistencia de IA (Claude).
