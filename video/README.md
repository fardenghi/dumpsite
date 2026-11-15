# Videos de Dumpsite (Remotion)

Los dos videos que pide la sede Buenos Aires de Space Apps 2026 para la idea B (challenge "Dancing with the SARs"). El proyecto se llamaba Insomnes y después Basurales; **ahora se llama Dumpsite** y su URL es **dumpsite.earth**.

| Video | Composición | Duración | Estado |
|---|---|---|---|
| Internacional, en inglés (máximo 30 s) | `DumpsiteIntl` | 29,5 s | **Casi final**: el equipo lo aprobó. Solo faltan los links definitivos. |
| Local, en castellano (máximo 3 min) | `DumpsiteLocal` | 2:15 | **Versión 1, va a cambiar.** Probablemente se reemplace la voz sintética por una grabada (ver `VOZ-GRABADA.md`). |

Los mp4 de las últimas versiones (`dumpsite-intl-v12.mp4`, `dumpsite-local-v1.mp4`) y los clips de Higgsfield se pasan por WhatsApp: no están en el repo.

**Si sos un agente o una persona que sigue con esto, leé primero `CONTEXTO.md`.** Ahí están las decisiones, el feedback del equipo y las trampas técnicas.

## Estructura

```
video/
├── README.md            ← este archivo
├── CONTEXTO.md          ← todo lo aprendido: decisiones, reglas de contenido, cifras con fuente, herramientas
├── VOZ-GRABADA.md       ← cómo reemplazar la voz sintética del video en castellano por una grabada
├── package.json · tsconfig.json · remotion.config.ts · .env.example
├── compartido/          ← código que usan los dos videos
│   ├── index.ts · Root.tsx        registro de las dos composiciones
│   ├── theme.ts · data.ts         colores, fuentes y datos comunes (data.ts lee ingles/voz.json para el video en inglés)
│   ├── datos-reales.json          datos reales del pipeline (pares de Norte III, polígonos, serie S2, catálogo)
│   ├── components/                Overlays (subtítulos, títulos, créditos, aviso de IA, pin) y Mapa del AMBA
│   ├── escenas/Escenas.tsx        escenas del video en inglés y piezas que reusa el de castellano
│   ├── scripts/                   voz (Azure y grabada), assets, capturas de la web, docx del guion
│   └── higgsfield/                generación y montaje del clip de IA
├── ingles/              ← Video.tsx, guion.json (texto de la voz), voz.json (tiempos)
├── espanol/             ← Local.tsx, guion-es.json, voz-es.json, guion-local.docx
└── public/              ← assets que usa Remotion (imágenes, capturas de la web, voces voz-en/ y voz-es/)
```

Remotion usa un solo `public/` y un solo `node_modules/` para las dos composiciones; por eso `package.json` está en `video/` y no dentro de cada idioma.

## Uso

```bash
cd video
npm install
# 1. El clip de IA no está en el repo: copiar clip1-ai.mp4 (WhatsApp) a public/clip1-ai.mp4,
#    o regenerarlo con compartido/higgsfield (ver CONTEXTO.md, "Clip de IA").
npm run studio            # editor en el navegador, con las dos composiciones
npm run render:ingles     # out/dumpsite-intl.mp4
npm run render:espanol    # out/dumpsite-local.mp4
npm run check             # chequeo de tipos
```

Solo para regenerar cosas hacen falta claves en `video/.env.local` (copiar de `.env.example`): Azure para la voz sintética y Higgsfield para el clip de IA. Nunca se suben al repo.

| Para… | Comando (desde `video/`) |
|---|---|
| Rehacer la voz sintética en inglés | `python3 -I compartido/scripts/voz_azure.py` |
| Rehacer la voz sintética en castellano | `python3 -I compartido/scripts/voz_azure.py --guion espanol/guion-es.json --salida espanol/voz-es.json --audio voz-es --max 180` |
| Usar una voz grabada en castellano | `python3 -I compartido/scripts/voz_grabada.py --carpeta <grabaciones>` (ver `VOZ-GRABADA.md`) |
| Rehacer mapas, imágenes NISAR y `datos-reales.json` | `python3 -I compartido/scripts/preparar_assets.py` |
| Rehacer la serie Sentinel-2 y los recortes del catálogo | `python3 -I compartido/scripts/serie_y_catalogo.py` |
| Rehacer las capturas de la web | `compartido/scripts/capturas_web.mjs` (instrucciones en el archivo) |
| Rehacer el guion en Word | `npm i --no-save docx && node compartido/scripts/guion_docx.js espanol/guion-local.docx` |

Los scripts de Python necesitan `pillow` y `numpy`, y `voz_grabada.py` necesita además `ffmpeg`.

## Créditos que aparecen en pantalla
- NISAR GUNW y GCOV: NASA/JPL–ISRO, vía ASF DAAC.
- Sentinel-2: Copernicus (ESA), por Microsoft Planetary Computer, y Sentinel-2 cloudless 2021 de EOX (s2maps.eu, CC BY-NC-SA 4.0).
- JRC Global Surface Water, OpenStreetMap y Overture (ODbL), Climate TRACE (CC BY 4.0), EPA LMOP y NASA EMIT.
- Lo generado con IA lleva aviso en pantalla: el clip inicial (Higgsfield, Seedance 2.5) y la voz sintética (Azure AI Speech).
