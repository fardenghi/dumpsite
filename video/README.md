# Dumpsite videos (Remotion)

The two videos the Buenos Aires venue of Space Apps 2026 asks for (challenge "Dancing with the SARs"). The project was called Insomnes and then Basurales; **it's now called Dumpsite** and its URL is **dumpsite.earth**.

| Video | Composition | Length | Status |
|---|---|---|---|
| International, in English (30 s max) | `DumpsiteIntl` | 29.5 s | **Almost final**: the team approved it. Only the final links are missing. |
| Local, in Spanish (3 min max) | `DumpsiteLocal` | 2:51 | **Voice recorded by the team**, as a single track (`public/voz-es/voz-completa.wav`), with each scene anchored to the word that names it (`compartido/scripts/palabras_voz.py`). See `VOZ-GRABADA.md`. |

The rendered mp4 files and the Higgsfield clip aren't in the repo: they're rebuilt with the commands below (`out/` is in `.gitignore`).

**If you're an agent or a person picking this up, read `CONTEXTO.md` first.** It has the decisions, the team's feedback and the technical pitfalls.

## Structure

```
video/
├── README.md            ← this file
├── CONTEXTO.md          ← everything learned: decisions, content rules, figures with sources, tools
├── VOZ-GRABADA.md       ← how to replace the Spanish video's synthetic voice with a recorded one
├── MODEL-CONTEXT.md     ← which model we actually trained (LightGBM, not ResNet-50) and what the script can say about it
├── package.json · tsconfig.json · remotion.config.ts · .env.example
├── compartido/          ← code shared by both videos
│   ├── index.ts · Root.tsx        registration of the two compositions
│   ├── theme.ts · data.ts         colors, fonts and shared data (data.ts reads ingles/voz.json for the English video)
│   ├── datos-reales.json          real pipeline data (Norte III pairs, polygons, S2 series, catalog)
│   ├── components/                Overlays (subtitles, titles, credits, AI notice, pin) and the AMBA Map
│   ├── escenas/Escenas.tsx        scenes of the English video and pieces the Spanish one reuses
│   ├── scripts/                   voice (Azure and recorded), assets, web screenshots, script docx
│   └── higgsfield/                generation and editing of the AI clip
├── ingles/              ← Video.tsx, guion.json (voice text), voz.json (timings)
├── espanol/             ← Local.tsx, guion-es.json, voz-es.json, guion-local.docx
└── public/              ← assets Remotion uses (images, web screenshots, voz-en/ and voz-es/ voices)
```

Remotion uses a single `public/` and a single `node_modules/` for both compositions; that's why `package.json` is in `video/` and not inside each language.

## Usage

```bash
cd video
npm install
# 1. The AI clip isn't in the repo: copy clip1-ai.mp4 to public/clip1-ai.mp4,
#    or regenerate it with compartido/higgsfield (see CONTEXTO.md, "Clip de IA").
npm run studio            # in-browser editor, with both compositions
npm run render:ingles     # out/dumpsite-intl.mp4
npm run render:espanol    # out/dumpsite-local.mp4
npm run check             # type check
```

Keys in `video/.env.local` (copy from `.env.example`) are only needed to regenerate things: Azure for the synthetic voice and Higgsfield for the AI clip. They're never committed.

| To… | Command (from `video/`) |
|---|---|
| Redo the English synthetic voice | `python3 -I compartido/scripts/voz_azure.py` |
| Redo the Spanish synthetic voice | `python3 -I compartido/scripts/voz_azure.py --guion espanol/guion-es.json --salida espanol/voz-es.json --audio voz-es --max 180` |
| Use a recorded voice in Spanish | `python3 -I compartido/scripts/voz_grabada.py --carpeta <recordings>` (see `VOZ-GRABADA.md`) |
| Redo maps, NISAR images and `datos-reales.json` | `python3 -I compartido/scripts/preparar_assets.py` |
| Redo the Sentinel-2 series and the catalog crops | `python3 -I compartido/scripts/serie_y_catalogo.py` |
| Redo the web screenshots | `compartido/scripts/capturas_web.mjs` (instructions in the file) |
| Redo the script in Word | `npm i --no-save docx && node compartido/scripts/guion_docx.js espanol/guion-local.docx` |

The Python scripts need `pillow` and `numpy`, and `voz_grabada.py` also needs `ffmpeg`.

## On-screen credits
- NISAR GUNW and GCOV: NASA/JPL–ISRO, via ASF DAAC.
- Sentinel-2: Copernicus (ESA), via Microsoft Planetary Computer, and EOX Sentinel-2 cloudless 2021 (s2maps.eu, CC BY-NC-SA 4.0).
- JRC Global Surface Water, OpenStreetMap and Overture (ODbL), Climate TRACE (CC BY 4.0), EPA LMOP and NASA EMIT.
- AI-generated content carries an on-screen notice: the opening clip (Higgsfield, Seedance 2.5) and the synthetic voice (Azure AI Speech).
