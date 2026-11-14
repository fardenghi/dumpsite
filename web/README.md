# Insomnes · web

Los basurales que el radar NISAR nunca ve quietos. Proyecto para el NASA Space Apps Challenge 2026 (challenge "Dancing with the SARs").

```bash
npm install
npm run dev      # http://localhost:5183
npm run build    # sitio estático en dist/
```

## Secciones
| Ruta | Qué muestra |
|---|---|
| `#/inicio` | Resumen: cantidad de sitios, ranking de insomnio y el caso Luján |
| `#/mapa` | Mapa navegable con todos los sitios. Al abrir uno: veredicto, coherencia par a par e imágenes Sentinel-2 por fecha |
| `#/sitios` | Tabla filtrable por país y por estado del radar, exportable a CSV |
| `#/modelo` | Cómo decide el modelo, con qué se entrenó y qué no ve. Las métricas están vacías hasta que exista la validación |

## Datos
**Hoy son de ejemplo.** `src/data/seed/sitios.json` tiene 17 sitios: las coordenadas del AMBA y la coherencia del último par salen de la prueba con un GUNW real; el resto de las series, las superficies y los sitios de otros países están puestos a mano para armar la interfaz, con coordenadas aproximadas. La barra lateral lo avisa con "datos de ejemplo".

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
`python3 scripts/contornos.py` baja de OpenStreetMap el polígono `landuse=landfill` de cada sitio y lo guarda en `src/data/seed/contornos.json`. Hoy 14 de los 17 sitios tienen contorno real. Quedan con un aro: la mancha al oeste de Luján (no es un predio registrado), Bordo Poniente y Payatas (OpenStreetMap no los tiene como relleno). **Pendiente:** un modelo que delimite el borde donde no hay polígono.

## Caché del mapa
`public/sw.js` guarda los tiles de Blue Marble y de Sentinel-2 la primera vez que se piden y después los sirve sin red. Además, al cargar la web se precarga la imagen Sentinel-2 más reciente de cada basural, que es lo que se recorre siempre. Los tiles de Google quedan afuera: sus términos no permiten guardarlos ni precargarlos, sólo el caché normal del navegador.

`python3 scripts/s2_fechas.py` consulta el catálogo STAC y guarda en `src/data/seed/imagenes.json` hasta 8 escenas con menos de 10 % de nubes por sitio. No tiene dependencias.

## Fuentes y licencias
- NISAR (NASA/ISRO), vía ASF DAAC.
- Blue Marble (NASA), vía GIBS.
- Sentinel-2 (ESA Copernicus), vía Microsoft Planetary Computer.
- OpenStreetMap, ODbL.
- Imagen satelital de Google (Map Tiles API), sólo si se configura la clave. Tiene copyright de Google y de sus proveedores: hay que declararla en el formulario de entrega.
- Tipografías Roboto Slab (Apache 2.0) y DM Sans (OFL). Mapa con MapLibre GL JS (BSD-3).
- Código: Apache 2.0. Escrito con asistencia de IA (Claude).
