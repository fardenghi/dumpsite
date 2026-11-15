# Context for continuing the Dumpsite videos

This document gathers what was learned while building the two videos: what was decided and why, what the team asked for and corrected, where each number comes from and what technical pitfalls there are. It's meant so that another person or agent can continue without repeating mistakes.

## 1. What the competition asks for

Source: the official Space Apps 2026 rules and the answer from the Buenos Aires Local Lead.

- **There's no live pitch.** Two videos are submitted and both are judged on the same 5 criteria: Impact, Creativity, Validity, Relevance and Presentation.
  - **International:** 30 s max, in English. It's the official demo on spaceappschallenge.org.
  - **Local:** 3 min max, preferably in Spanish, for the venue's jury.
- Submission closes on **Sunday 15/11/2026 at 23:59**, Buenos Aires time.
- AI-generated content is marked on screen, hence the "AI-generated imagery" / "Imagen generada con IA" pill and the AI line at the end.
- All sources have to be cited, even open ones, and NISAR has to be the central data.
- Don't accuse anyone: talk about a "signal compatible with activity", never an "illegal dump".

## 2. Content rules set by the team (don't break them)

They come from the feedback of many iterations.

**Name and links**
- The project is called **Dumpsite**; no "Insomnes" or "Basurales" on screen.
- The URL is **dumpsite.earth**. The repo shown (`github.com/fardenghi/dumpsite`) is provisional.
- The links are in `compartido/data.ts` (`RESULTADOS.url` and `RESULTADOS.repo`). When the final ones are ready, change them there and re-render both videos.

**The model**
- The model is **LightGBM**, not ResNet-50, a CNN or a neural network. None of those can appear.
- It's presented as finished and "trained on thousands of mapped dumps".
- What it flags is described as **"classified as dump by the model"** ("clasificado como basural por el modelo"). **Never "confirmed".**
- **No metrics on screen**: no AUC, accuracy or model percentages. The 0.794 AUC of the old run (592 patches) isn't shown.
- The visual that worked: wall of catalog dump sites → LightGBM box → two trays, "Dump / Something else" in English and "Basural / Otra cosa" in Spanish.
  - The examples are Norte III (dump site), El Palomar (airfield) and a quarry in Tres de Febrero.
  - The block is centered on screen: an empty space on the left was flagged as a mistake.

**The insomnia index**
- Don't show the "80 %" threshold (the coherence < 0.8 × surroundings rule). It's explained in words: "it changes more than its surroundings in almost every pass".

**The voice**
- **A single narrator.** Azure's styles (`express-as`) made it sound like another person, so they're not used.
- **No colons in the voice text**: they cause odd pauses. They're replaced with commas.
- Words the voice mispronounced, fixed with aliases:
  - "LightGBM" → "light G B M" in English and "lait yi bi em" in Spanish;
  - earlier, "ResNet 50" sounded split.
- The first sentence has to state the concrete problem: new dump sites appear and grow faster than they can be mapped, and they're almost never registered.
- Right after the problem comes what Dumpsite is.
- "real dumps" wasn't understood; say "actually dumpsites" or, better, avoid it.

**Images**
- The NISAR radar image goes as **a single image**: two "passes" that looked the same were confusing.
- The satellite at the start of the AI clip lasts **very little (≈1 s)**.
- The AI clip has no "beam" coming out of the satellite. The trash has to look like trash (colored bags, plastics), not dirt, and without bulldozers or trucks.

**Team members**
- The names of the 6 team members appear at the bottom right during the opening clip of both videos, without saying them out loud (the official guide suggests introducing the team at the start).
- Above the names goes the team name, **<=> (spaceship)**, a bit larger (`NOMBRE_EQUIPO`).
- They're in `EQUIPO` in `compartido/data.ts`, as listed on the team page, and the component is `Equipo` in `Overlays.tsx`: same font and shadow as the subtitles, smaller and without a box (as the team asked).

**Subtitles**
- White with a shadow over a dark gradient (never white on white).
- They appear word by word at the pace of the voice.
- In Spanish they're shown in blocks of 1 or 2 lines (`max={105}`), because the long sentences covered the image.

**Sources and placeholders**
- When sources are shown, say which they are: name, origin and license. They don't need to be said out loud.
- `MOSTRAR_PLACEHOLDERS = false` in `compartido/data.ts`. If enabled, provisional data shows an orange tag.

## 3. Figures that appear and where they come from

No number goes on screen without a source.

| Figure | Source in the repo |
|---|---|
| ≈ 5,000 open-air dump sites in Argentina (Ministry of Environment estimate, no formal survey) | `docs/idea.md` |
| There's no open official inventory with coordinates | same |
| NISAR: one image every 12 days, L-band radar, day, night and through clouds | `docs/idea.md` |
| Norte III: insomnia 0.86; "restless in 8 of 8 passes" on the main orbit | `docs/indice-insomnio.md`, `data/salidas/fichas_80m.json` (in `compartido/datos-reales.json`) |
| Luján: closed on 1/07/2026, quiet in all 15 passes, insomnia 0 % | `docs/indice-insomnio.md` |
| González Catán: insomnia 100 % (1.00) | same |
| 219 candidate blobs in the AMBA (without JRC water, roads or seasonal crops) | same |
| 66,981 dump sites in the world catalog | `data/catalogos/basurales/basurales_mundo.json` |
| 29 model variables: 12 radar, 11 Sentinel-2 optical, 3 shape, 3 context; 300 trees of depth 3 | `docs/resultados.md` (29 variables) and `motor/entrenar.py` (300 trees, depth 3, 7 leaves) |
| 42 catalog dump sites active on the radar, 13 registered as closed that are still active (and 7 closed and quiet), in 10 regions | `web/src/data/seed/veredictos.json` |

The 10 regions are AMBA, Los Angeles, Ohio Lake, Maryland Howard, Mexico City, Ponce, New Hampshire Hillsborough, New York Richmond, Delhi and Jakarta.

When there are metrics for the model trained on the full catalog, they still don't go on screen, unless the team decides otherwise.

## 4. How the project works

**The voice sets the timing.**
1. The voice text is in `ingles/guion.json` and `espanol/guion-es.json`. Each sentence has an `id` and one or more `partes`, with rate, pitch, volume, pause and pronunciation aliases (`decir`).
2. `voz_azure.py` or `voz_grabada.py` produce one WAV per sentence in `public/voz-en/` or `public/voz-es/`, plus a timing json (`voz.json` / `voz-es.json`) with each sentence's `inicio`, `duracion` and `texto`.
3. Scenes start when their sentence starts. **If the voice changes, the video rearranges itself.**

**Anchors within a sentence.**
- To make something appear in the middle of a sentence, a piece of the text is looked up and its moment is estimated by the proportion of characters:
  - in Spanish, `dentro(id, "texto")` in `espanol/Local.tsx`;
  - in English, `inicioDe(id, "texto")` in `ingles/Video.tsx`.
- **If the text changes and the anchor no longer exists**, in Spanish the element appears at the start of the sentence and in English Remotion throws "inputRange must be strictly monotonically increasing". When changing the script, check the anchors.

| File | Anchors |
|---|---|
| `espanol/Local.tsx` | "En Argentina" (problem), "NISAR toma" (dumpsite), "Norte Tres" (cases), "Y le sumamos" (data), "Cientos de" and "Y lo validamos" (model), "Dumpsite" (ending) |
| `ingles/Video.tsx` | "active dumps" (insomnia), "at the links" (results) |

**Subtitles.** `Subtitulos` in `compartido/components/Overlays.tsx` takes the text from the timing json and spreads the words in proportion to the characters. With a human voice it's a reasonable approximation; if some sentence ends up off, it can be split into two sentences in the script.

**Compositions.** They're in `compartido/Root.tsx`, at 1920 × 1080 and 30 fps. The total length of each video comes from `duracion_video` in the timing json: the end of the voice plus `cola_s`, which is the end card.

## 5. International video (English, 29.5 s), almost final

Voice `en-US-AndrewMultilingualNeural`, rate +20 to +27 %.

| Sentence | Text | Scene |
|---|---|---|
| intro | "New dumps appear and grow faster than anyone can map them, and most are never registered." | AI clip (satellite ~1 s → clouds → dump site), "AI-generated imagery" pill |
| nisar | "So we built Dumpsite, a platform that tracks dump sites with NASA's NISAR radar, which images Earth every twelve days." | Radar pulse, Dumpsite title, NISAR coherence image over Norte III |
| insomnia | "Radar coherence tells how alike two passes look, and active dumps never stop changing, so we turn that restlessness into our Insomnia score." | Sentinel-2 series, passes with an eye and bars, index map of the AMBA |
| red | "Then our LightGBM model, trained on thousands of mapped dumps, classifies each one as a dump or not." | Catalog wall with a counter up to 66,981, centered LightGBM box and Dump / Something else trays |
| resultados | "It's all implemented and open, at the links on screen." | Browser with the web, 42 and 13, links |

The only thing pending is the final links.

## 6. Local video (Spanish, 2:15), version 1

Synthetic voice `es-AR-TomasNeural`, with the script in `espanol/guion-es.json`. What's shown, scene by scene, is in `espanol/guion-local.docx`, which is regenerated with `compartido/scripts/guion_docx.js`.

| # | Scene (component in `Local.tsx`) | Sentences | What's shown |
|---|---|---|---|
| 1 | AI clip + `Problema` | problema | AI clip and then the dump site in slow motion with ≈5,000 and 0 inventories |
| 2 | `Pulso` + `DumpsiteNisar` | dumpsite | Sentinel-2 with a pin, Dumpsite title, NISAR radar with chips (12 days, day and night, clouds, L band) |
| 3 | `Insomnio` | cambia, coherencia, mapa | 6-date S2 series, coherence per pass ("8 of 8", 0.86), AMBA map with 219 blobs |
| 4 | `Casos` | casos | Web screenshots: Luján (0 %), Norte III (86 %), González Catán (100 %) |
| 5 | `Datos` | datos | 28 catalog crops, 66,981 counter, sources, examples of look-alikes |
| 6 | `Modelo` | modelo | 29 variables, LightGBM box with ×300 trees, trays, validation leaving one city out |
| 7 | `Resultados` | resultados | 42 and 13, chips of the 10 regions, "not verified on the ground" |
| 8 | `Web` | web | Tour: index map → Norte III card → site list → model |
| 9 | `Cierre` | cierre | Table of sources with licenses, AI statement, links and DUMPSITE end card |

What's most likely to change:
- **The voice.** Someone on the team records it; see `VOZ-GRABADA.md`. If the 11 sentence ids are kept, the video adapts on its own.
- **The text**, based on the docx that was sent for refining. When it changes, regenerate the voice and check the anchors in section 4.
- **The web screenshots**, if the web changes. The current ones (`public/web/es-*.png`) were taken from `main` with the brand changed to Dumpsite locally; on `main` the web still says "Basurales".
- **The web's Model page**: further down it still mentions ResNet as "what's next". The video only shows the top part (`es-modelo.png`). If the web is fixed, it's worth retaking it.

## 7. Tools and technical pitfalls

### Remotion
- Version 4.0.543, with React 18.3.1.
  - Audio goes with `Html5Audio`.
  - Videos go with `OffthreadVideo` and `playbackRate`.
  - The AI clip lasts 4.733 s: in Spanish it plays at speed 1 (`CLIP_IA` in `Local.tsx`) and in English it's sped up with `playbackRate={4.733 / durTotal}`.
- `Easing.quint` doesn't exist: use `Easing.poly(5)`.
- The fonts are local (`public/fonts/*.woff2`, loaded with `@remotion/fonts` in `theme.ts`). Downloading Google Fonts while rendering timed out.
- To review without rendering everything:
  - `npx remotion still DumpsiteLocal out/x.png --frame=2700 --scale=0.4`;
  - for a contact sheet, extract frames from the mp4 with ffmpeg and join them with `-vf tile=4x6`.
- The full render of the local video takes several minutes.

### Azure AI Speech (synthetic voice)
- The REST API is used with SSML: `prosody` (rate, pitch, volume), `<sub alias>` for pronunciation and `xml:lang` according to the script's language.
- Output format `riff-48khz-16bit-mono-pcm`. The silence at the start and end of each take is trimmed.
- The key goes in `video/.env.local` (`AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION`). The script never prints it.
- Voices tried: `en-US-AndrewMultilingualNeural` for English and `es-AR-TomasNeural` for Spanish.

### Higgsfield (AI clip)
- API, not MCP: the `higgsfield-client` Python SDK (`subscribe`, `upload_file`), with the key `HF_KEY=key-id:key-secret` in `video/.env.local`.
- Seedance 2.5 model:
  - `bytedance/seedance-2.5/image-to-video` takes `image_url` and doesn't accept `aspect_ratio`;
  - `.../text-to-video` does accept `aspect_ratio`.
- The 480p draft (`draft: true`) costs about USD 0.12 per second.

**History of the clip:**
1. `descenso.py` (text-to-video, 5 s) came out ugly: the trash looked like dirt and there were bulldozers.
2. `satelite.py` (image-to-video, 10 s) starts at an official NISAR render (`nisar-primer-cuadro.jpg`) and descends to a dump site. It's the clip in use: `salidas/satelite-draft-203402.mp4`, shared outside the repo.
3. `montar_clip.sh` cuts it and retimes it to 4.73 s (satellite 1 s, clouds 1 s, dump site 2.7 s) and leaves it in `public/clip1-ai.mp4`.

- The team asked **not to touch Higgsfield unless asked**: each run costs money. Show the prompt and wait for the OK before sending.
- The Spanish video reuses the same clip.

### Web screenshots
- They're taken with puppeteer-core and the chrome-headless-shell that ships with Remotion, serving the web with `vite preview`.
- On Ubuntu `--no-sandbox` is needed: AppArmor blocks Chrome's sandbox. `--virtual-time-budget` hung; that's why real waits are used (the MapLibre map takes about 10 s).
- The English screenshots (`public/web/mapa.png`, `inicio.png`, `sitios.png`, `modelo.png`) came from the `web-ingles` branch, which has the translated web and the rename to Dumpsite.

## 8. Pending
- Final links (domain and repo) in `compartido/data.ts`, and re-render of both videos.
- Recorded voice and final text of the Spanish video.
- Fix the web's Model page (the ResNet mention) and the brand on `main`.
