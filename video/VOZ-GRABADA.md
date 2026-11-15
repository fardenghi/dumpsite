# Reemplazar la voz sintética del video en castellano por una voz grabada

El video local (`DumpsiteLocal`) está sincronizado con `espanol/voz-es.json`: cada escena arranca cuando arranca su frase. Si se graba la voz y se regenera ese json con `compartido/scripts/voz_grabada.py`, **las escenas y los subtítulos se reacomodan solos**. No hace falta tocar `Local.tsx` mientras se mantengan los 11 ids de frase.

## 1. Antes de grabar
- **Fijar el texto final en `espanol/guion-es.json`.** Los subtítulos salen de ahí, así que el guion tiene que decir exactamente lo que se graba.
  - Si se cambia el texto, revisar que sigan existiendo las anclas que usa `Local.tsx` (sección 4 de `CONTEXTO.md`): "En Argentina", "NISAR toma", "Norte Tres", "Y le sumamos", "Cientos de", "Y lo validamos" y "Dumpsite".
  - Si un ancla desaparece, el elemento aparece al principio de la frase. Se arregla cambiando el ancla en `Local.tsx` por otro pedazo del texto nuevo.
- Los 11 ids, en orden, son: `problema`, `dumpsite`, `cambia`, `coherencia`, `mapa`, `casos`, `datos`, `modelo`, `resultados`, `web` y `cierre`.
- El texto completo para leer está en `espanol/guion-local.docx`, en la columna "Voz".
- **Duración:** la voz sintética dura 2:12 y el máximo del video es 3:00. Una persona suele hablar más lento que la voz sintética, que va a +8/+10 %. Hay margen, pero conviene no pasar de unos 2:45 de voz.

## 2. Grabar
- En un lugar silencioso, con el celular o el micrófono a un palmo y siempre a la misma distancia.
- Formato: cualquiera que lea ffmpeg (wav, m4a, mp3, ogg, opus). Un audio de WhatsApp también sirve.
- Dejar un segundo de silencio antes y después de cada frase. El script recorta los silencios de los bordes.

## 3. Pasar la grabación al video

**Forma A, un archivo por frase.** Nombrar cada archivo con el id de la frase, por ejemplo `problema.m4a`, `dumpsite.m4a`, …, `cierre.m4a`, y ponerlos todos en una carpeta:

```bash
cd video
python3 -I compartido/scripts/voz_grabada.py --carpeta ~/grabacion-dumpsite
```

**Forma B, una sola toma.** Abrir la toma en Audacity y marcar cada frase como una etiqueta de región (seleccionar el tramo y apretar Ctrl+B) con el id como nombre. Después exportar las etiquetas con Archivo › Exportar › Exportar etiquetas:

```bash
python3 -I compartido/scripts/voz_grabada.py --toma toma.wav --cortes etiquetas.txt
# con las pausas naturales de la toma en vez de los huecos fijos del guion:
python3 -I compartido/scripts/voz_grabada.py --toma toma.wav --cortes etiquetas.txt --tiempos-originales
```

**Qué hace el script:**
1. Convierte cada frase a WAV de 48 kHz mono.
2. Empareja el volumen entre frases (`loudnorm`).
3. Recorta los silencios de los bordes.
4. Las ubica una detrás de otra con los huecos de `huecos_s` del guion: 0,3 s antes de la primera, 0,7 s antes de la segunda y 0,45 s entre las demás.
5. Escribe `public/voz-es/frase-N.wav` y `espanol/voz-es.json`, y avisa si la voz no entra en 3 minutos o si dos frases se pisan.

**Opciones útiles:**
- `--umbral 800`: si hay ruido de fondo y no recorta bien los silencios.
- `--sin-recorte`: deja los silencios tal como están.
- Para cambiar el ritmo entre frases, editar `huecos_s` en `guion-es.json` y volver a correr el script.
- Para alargar la placa final, editar `cola_s`.

## 4. Revisar y renderizar

```bash
npm run studio           # elegir DumpsiteLocal y mirarlo entero
npm run render:espanol   # out/dumpsite-local.mp4
```

**Qué mirar en el studio:**
- Que cada escena cambie cuando la voz empieza a hablar de eso.
- Que los subtítulos vayan más o menos con la voz. Se reparten en proporción a los caracteres: con una persona puede haber un desfase leve. Si una frase larga queda muy desfasada, partirla en dos frases en el guion, grabarla en dos archivos y agregar el id nuevo. En ese caso hay que tocar `Local.tsx`: ver la lista `tramos` en `DumpsiteLocal`.
- Que el cierre llegue antes de los 3:00.

**Quitar la mención a la voz sintética.** El cierre dice "voz sintética (Azure AI Speech)" en la línea de IA. Con voz humana, borrar esa parte en `espanol/Local.tsx`: buscar "Contenido generado con IA" y dejar solo el clip inicial de Higgsfield.

## 5. Volver a la voz sintética

```bash
python3 -I compartido/scripts/voz_azure.py --guion espanol/guion-es.json --salida espanol/voz-es.json --audio voz-es --max 180
```

Necesita `AZURE_SPEECH_KEY` y `AZURE_SPEECH_REGION` en `video/.env.local`.
