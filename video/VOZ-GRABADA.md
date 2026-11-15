# Replacing the Spanish video's synthetic voice with a recorded one

The local video (`DumpsiteLocal`) is synced with `espanol/voz-es.json`: each scene starts when its sentence starts. If the voice is recorded and that json is regenerated with `compartido/scripts/voz_grabada.py`, **the scenes and the subtitles rearrange themselves**. There's no need to touch `Local.tsx` as long as the 11 sentence ids are kept.

## 1. Before recording
- **Lock the final text in `espanol/guion-es.json`.** The subtitles come from there, so the script has to say exactly what gets recorded.
  - If the text changes, check that the anchors used by `Local.tsx` still exist (section 4 of `CONTEXTO.md`): "En Argentina", "NISAR toma", "Norte Tres", "Y le sumamos", "Cientos de", "Y lo validamos" and "Dumpsite".
  - If an anchor disappears, the element shows up at the start of the sentence. Fix it by changing the anchor in `Local.tsx` to another piece of the new text.
- The 11 ids, in order, are: `problema`, `dumpsite`, `cambia`, `coherencia`, `mapa`, `casos`, `datos`, `modelo`, `resultados`, `web` and `cierre`.
- The full text to read is in `espanol/guion-local.docx`, in the "Voz" column.
- **Length:** the synthetic voice lasts 2:12 and the video maximum is 3:00. A person usually speaks slower than the synthetic voice, which runs at +8/+10 %. There's room, but it's best not to go over about 2:45 of voice.

## 2. Recording
- In a quiet place, with the phone or microphone a hand's width away and always at the same distance.
- Format: anything ffmpeg reads (wav, m4a, mp3, ogg, opus). A WhatsApp voice note works too.
- Leave a second of silence before and after each sentence. The script trims the silences at the edges.

## 3. Bringing the recording into the video

**Option A, one file per sentence.** Name each file with the sentence id, for example `problema.m4a`, `dumpsite.m4a`, …, `cierre.m4a`, and put them all in one folder:

```bash
cd video
python3 -I compartido/scripts/voz_grabada.py --carpeta ~/grabacion-dumpsite
```

**Option B, a single take.** Open the take in Audacity and mark each sentence as a region label (select the segment and press Ctrl+B) with the id as its name. Then export the labels with File › Export › Export Labels:

```bash
python3 -I compartido/scripts/voz_grabada.py --toma toma.wav --cortes etiquetas.txt
# with the take's natural pauses instead of the script's fixed gaps:
python3 -I compartido/scripts/voz_grabada.py --toma toma.wav --cortes etiquetas.txt --tiempos-originales
```

**What the script does:**
1. Converts each sentence to 48 kHz mono WAV.
2. Evens out the volume between sentences (`loudnorm`).
3. Trims the silences at the edges.
4. Places them one after another with the script's `huecos_s` gaps: 0.3 s before the first, 0.7 s before the second and 0.45 s between the rest.
5. Writes `public/voz-es/frase-N.wav` and `espanol/voz-es.json`, and warns if the voice doesn't fit in 3 minutes or if two sentences overlap.

**Useful options:**
- `--umbral 800`: if there's background noise and the silences aren't trimmed well.
- `--sin-recorte`: leaves the silences as they are.
- To change the pace between sentences, edit `huecos_s` in `guion-es.json` and rerun the script.
- To lengthen the end card, edit `cola_s`.

## 4. Review and render

```bash
npm run studio           # pick DumpsiteLocal and watch it all
npm run render:espanol   # out/dumpsite-local.mp4
```

**What to check in the studio:**
- That each scene changes when the voice starts talking about it.
- That the subtitles roughly follow the voice. They're spread in proportion to the characters: with a person there can be a slight offset. If a long sentence ends up very off, split it into two sentences in the script, record it in two files and add the new id. In that case `Local.tsx` has to be touched: see the `tramos` list in `DumpsiteLocal`.
- That the ending arrives before 3:00.

**Remove the mention of the synthetic voice.** The ending says "voz sintética (Azure AI Speech)" in the AI line. With a human voice, delete that part in `espanol/Local.tsx`: look for "Contenido generado con IA" and keep only the opening Higgsfield clip.

## 5. Going back to the synthetic voice

```bash
python3 -I compartido/scripts/voz_azure.py --guion espanol/guion-es.json --salida espanol/voz-es.json --audio voz-es --max 180
```

It needs `AZURE_SPEECH_KEY` and `AZURE_SPEECH_REGION` in `video/.env.local`.
