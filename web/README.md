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
- Cada ficha tiene un enlace a Google Maps para ver el sitio con más detalle. Es solo un enlace: la web no usa imágenes de Google.

`python3 scripts/s2_fechas.py` consulta el catálogo STAC y guarda en `src/data/seed/imagenes.json` hasta 8 escenas con menos de 10 % de nubes por sitio. No tiene dependencias.

## Fuentes y licencias
- NISAR (NASA/ISRO), vía ASF DAAC.
- Blue Marble (NASA), vía GIBS.
- Sentinel-2 (ESA Copernicus), vía Microsoft Planetary Computer.
- OpenStreetMap, ODbL.
- Tipografías Roboto Slab (Apache 2.0) y DM Sans (OFL). Mapa con MapLibre GL JS (BSD-3).
- Código: Apache 2.0. Escrito con asistencia de IA (Claude).
