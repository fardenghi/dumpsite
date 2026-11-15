# Contexto para seguir con los videos de Dumpsite

Este documento junta lo que se aprendió al armar los dos videos: qué se decidió y por qué, qué pidió y corrigió el equipo, de dónde sale cada número y qué trampas técnicas hay. Está pensado para que otra persona u otro agente siga sin repetir errores.

## 1. Lo que pide la competencia

Fuente: `../SPACE-APPS-2026-OFICIAL.md` y la respuesta del Local Lead de Buenos Aires.

- **No hay pitch en vivo.** Se entregan dos videos y los dos se juzgan con los mismos 5 criterios: Impact, Creativity, Validity, Relevance y Presentation.
  - **Internacional:** 30 s como máximo, en inglés. Es la demo oficial en spaceappschallenge.org.
  - **Local:** 3 min como máximo, preferentemente en castellano, para el jurado de la sede.
- La entrega cierra el **domingo 15/11/2026 a las 23:59**, hora de Buenos Aires.
- Lo generado con IA se marca en pantalla, por eso la píldora "AI-generated imagery" / "Imagen generada con IA" y la línea de IA en el cierre.
- Hay que citar todas las fuentes, incluso las abiertas, y NISAR tiene que ser el dato central.
- No acusar a nadie: se habla de "señal compatible con actividad", nunca de "basural ilegal".

## 2. Reglas de contenido que fijó el equipo (no romperlas)

Salen del feedback de muchas iteraciones.

**Nombre y links**
- El proyecto se llama **Dumpsite**; nada de "Insomnes" ni "Basurales" en pantalla.
- La URL es **dumpsite.earth**. El repo que aparece (`github.com/fardenghi/dumpsite`) es provisorio.
- Los links están en `compartido/data.ts` (`RESULTADOS.url` y `RESULTADOS.repo`). Cuando estén los definitivos, se cambian ahí y se re-renderizan los dos videos.

**El modelo**
- El modelo es **LightGBM**, no ResNet-50, ni una CNN, ni una red neuronal. Nada de eso puede aparecer.
- Se presenta como terminado y "entrenado con miles de basurales mapeados".
- Lo que marca se dice **"clasificado como basural por el modelo"** ("classified as dump by the model"). **Nunca "confirmado".**
- **Sin métricas en pantalla**: ni AUC, ni accuracy, ni porcentajes del modelo. El AUC de 0,794 de la corrida vieja (592 parches) no se muestra.
- El visual que gustó: pared de basurales del catálogo → caja LightGBM → dos bandejas, "Dump / Something else" en inglés y "Basural / Otra cosa" en castellano.
  - Los ejemplos son Norte III (basural), El Palomar (aeródromo) y una cantera de Tres de Febrero.
  - El bloque va centrado en pantalla: un espacio vacío a la izquierda se marcó como error.

**El índice de insomnio**
- No mostrar el umbral "80 %" (la regla de coherencia < 0,8 × entorno). Se explica en palabras: "cambia más que su entorno en casi todas las pasadas".

**La voz**
- **Un solo narrador.** Los estilos de Azure (`express-as`) hacían que pareciera otra persona, así que no se usan.
- **Sin dos puntos en el texto de la voz**: generan pausas raras. Se reemplazan por comas.
- Palabras que la voz pronunciaba mal y se corrigieron con alias:
  - "LightGBM" → "light G B M" en inglés y "lait yi bi em" en castellano;
  - antes "ResNet 50" sonaba separado.
- La primera frase tiene que plantear el problema concreto: basurales nuevos que aparecen y crecen más rápido de lo que se los puede mapear, y que casi nunca se registran.
- Justo después del problema va qué es Dumpsite.
- "real dumps" no se entendía; se dice "actually dumpsites" o, mejor, se evita.

**Imágenes**
- La imagen de radar de NISAR va como **una sola imagen**: dos "pasadas" que se veían iguales confundían.
- El satélite al principio del clip de IA dura **muy poco (≈1 s)**.
- El clip de IA no tiene "rayo" saliendo del satélite. La basura tiene que verse como basura (bolsas de colores, plásticos), no como tierra, y sin topadoras ni camiones.

**Subtítulos**
- Blancos con sombra sobre un degradado oscuro (nunca blanco sobre blanco).
- Aparecen palabra por palabra al ritmo de la voz.
- En castellano se muestran de a bloques de 1 o 2 renglones (`max={105}`), porque las frases largas tapaban la imagen.

**Fuentes y placeholders**
- Cuando se muestran fuentes, se dice cuáles son: nombre, origen y licencia. No hace falta decirlas en voz alta.
- `MOSTRAR_PLACEHOLDERS = false` en `compartido/data.ts`. Si se activa, los datos provisorios muestran una etiqueta naranja.

## 3. Cifras que aparecen y de dónde salen

Ningún número va en pantalla sin fuente.

| Cifra | Fuente en el repo |
|---|---|
| ≈ 5.000 basurales a cielo abierto en Argentina (estimación del Ministerio de Ambiente, sin relevamiento formal) | `idea-basurales-nisar/context/README.md` |
| No hay inventario oficial abierto con coordenadas | ídem |
| NISAR: una imagen cada 12 días, radar banda L, de día, de noche y a través de las nubes | `context/README.md` |
| Norte III: insomnio 0,86; "inquieto en 8 de 8 pasadas" en la órbita principal | `idea/indice-final.md`, `salidas/fichas_80m.json` (en `compartido/datos-reales.json`) |
| Luján: cerrado el 1/07/2026, quieto en las 15 pasadas, insomnio 0 % | `idea/indice-final.md` |
| González Catán: insomnio 100 % (1,00) | ídem |
| 219 manchas candidatas en el AMBA (sin agua de JRC, rutas ni cultivos estacionales) | ídem |
| 66.981 basurales en el catálogo mundial | `data/basurales/basurales_mundo.json` |
| 29 variables del modelo: 12 radar, 11 ópticas Sentinel-2, 3 de forma, 3 del entorno; 300 árboles de profundidad 3 | `idea-basurales-nisar/idea/resultados-modelo.md` (29 variables) y `herramientas/entrenar.py` (300 árboles, profundidad 3, 7 hojas) |
| 42 basurales de catálogo activos en el radar, 13 registrados como cerrados que siguen activos (y 7 cerrados y quietos), en 10 regiones | `insomnes-web/src/data/seed/veredictos.json` |

Las 10 regiones son AMBA, Los Ángeles, Ohio Lake, Maryland Howard, Ciudad de México, Ponce, New Hampshire Hillsborough, New York Richmond, Delhi y Yakarta.

Cuando haya métricas del modelo entrenado con el catálogo completo, siguen sin ir en pantalla, salvo que el equipo decida otra cosa.

## 4. Cómo funciona el proyecto

**La voz manda los tiempos.**
1. El texto de la voz está en `ingles/guion.json` y `espanol/guion-es.json`. Cada frase tiene un `id` y una o más `partes`, con velocidad, tono, volumen, pausa y alias de pronunciación (`decir`).
2. `voz_azure.py` o `voz_grabada.py` producen un WAV por frase en `public/voz-en/` o `public/voz-es/`, más un json de tiempos (`voz.json` / `voz-es.json`) con `inicio`, `duracion` y `texto` de cada frase.
3. Las escenas arrancan cuando arranca su frase. **Si cambia la voz, el video se reacomoda solo.**

**Anclas dentro de una frase.**
- Para que algo aparezca a mitad de una frase, se busca un pedazo del texto y se estima su momento por la proporción de caracteres:
  - en castellano, `dentro(id, "texto")` en `espanol/Local.tsx`;
  - en inglés, `inicioDe(id, "texto")` en `ingles/Video.tsx`.
- **Si se cambia el texto y el ancla ya no existe**, en castellano el elemento aparece al principio de la frase y en inglés Remotion tira "inputRange must be strictly monotonically increasing". Al cambiar el guion, revisar las anclas.

| Archivo | Anclas |
|---|---|
| `espanol/Local.tsx` | "En Argentina" (problema), "NISAR toma" (dumpsite), "Norte Tres" (casos), "Y le sumamos" (datos), "Cientos de" y "Y lo validamos" (modelo), "Dumpsite" (cierre) |
| `ingles/Video.tsx` | "active dumps" (insomnia), "at the links" (resultados) |

**Subtítulos.** `Subtitulos` en `compartido/components/Overlays.tsx` toma el texto del json de tiempos y reparte las palabras en proporción a los caracteres. Con voz humana es una aproximación razonable; si alguna frase queda desfasada, se puede partir en dos frases en el guion.

**Composiciones.** Están en `compartido/Root.tsx`, a 1920 × 1080 y 30 fps. La duración total de cada video sale de `duracion_video` del json de tiempos: el fin de la voz más `cola_s`, que es la placa final.

## 5. Video internacional (inglés, 29,5 s), casi final

Voz `en-US-AndrewMultilingualNeural`, velocidad +20 a +27 %.

| Frase | Texto | Escena |
|---|---|---|
| intro | "New dumps appear and grow faster than anyone can map them, and most are never registered." | Clip de IA (satélite ~1 s → nubes → basural), píldora "AI-generated imagery" |
| nisar | "So we built Dumpsite, a platform that tracks dump sites with NASA's NISAR radar, which images Earth every twelve days." | Pulso de radar, título Dumpsite, imagen de coherencia NISAR sobre Norte III |
| insomnia | "Radar coherence tells how alike two passes look, and active dumps never stop changing, so we turn that restlessness into our Insomnia score." | Serie Sentinel-2, pasadas con ojo y barras, mapa del índice en el AMBA |
| red | "Then our LightGBM model, trained on thousands of mapped dumps, classifies each one as a dump or not." | Pared del catálogo con contador a 66.981, caja LightGBM centrada y bandejas Dump / Something else |
| resultados | "It's all implemented and open, at the links on screen." | Navegador con la web, 42 y 13, links |

Lo único pendiente son los links definitivos.

## 6. Video local (castellano, 2:15), versión 1

Voz sintética `es-AR-TomasNeural`, con el guion en `espanol/guion-es.json`. Lo que se ve, escena por escena, está en `espanol/guion-local.docx`, que se regenera con `compartido/scripts/guion_docx.js`.

| # | Escena (componente en `Local.tsx`) | Frases | Qué se ve |
|---|---|---|---|
| 1 | Clip de IA + `Problema` | problema | Clip de IA y después el basural en cámara lenta con ≈5.000 y 0 inventarios |
| 2 | `Pulso` + `DumpsiteNisar` | dumpsite | Sentinel-2 con pin, título Dumpsite, radar NISAR con chips (12 días, día y noche, nubes, banda L) |
| 3 | `Insomnio` | cambia, coherencia, mapa | Serie S2 de 6 fechas, coherencia por pasada ("8 de 8", 0,86), mapa del AMBA con 219 manchas |
| 4 | `Casos` | casos | Capturas de la web: Luján (0 %), Norte III (86 %), González Catán (100 %) |
| 5 | `Datos` | datos | 28 recortes del catálogo, contador 66.981, fuentes, ejemplos de lo que se parece |
| 6 | `Modelo` | modelo | 29 variables, caja LightGBM con árboles ×300, bandejas, validación dejando una ciudad afuera |
| 7 | `Resultados` | resultados | 42 y 13, chips de las 10 regiones, "sin verificar en terreno" |
| 8 | `Web` | web | Recorrido: mapa del índice → ficha de Norte III → lista de sitios → modelo |
| 9 | `Cierre` | cierre | Tabla de fuentes con licencias, declaración de IA, links y placa DUMPSITE |

Lo más probable es que cambie:
- **La voz.** Alguien del equipo la graba; ver `VOZ-GRABADA.md`. Si se mantienen los 11 ids de frase, el video se adapta solo.
- **El texto**, a partir del docx que se mandó para refinar. Al cambiarlo hay que regenerar la voz y revisar las anclas de la sección 4.
- **Las capturas de la web**, si la web cambia. Las actuales (`public/web/es-*.png`) se sacaron de `main` con la marca cambiada a Dumpsite en local; en `main` la web todavía dice "Basurales".
- **La página Modelo de la web**: más abajo todavía menciona ResNet como "lo que sigue". En el video se muestra solo la parte de arriba (`es-modelo.png`). Si se corrige la web, conviene recapturar.

## 7. Herramientas y trampas técnicas

### Remotion
- Versión 4.0.543, con React 18.3.1.
  - El audio va con `Html5Audio`.
  - Los videos van con `OffthreadVideo` y `playbackRate`.
  - El clip de IA dura 4,733 s: en castellano se reproduce a velocidad 1 (`CLIP_IA` en `Local.tsx`) y en inglés se acelera con `playbackRate={4.733 / durTotal}`.
- `Easing.quint` no existe: usar `Easing.poly(5)`.
- Las fuentes son locales (`public/fonts/*.woff2`, cargadas con `@remotion/fonts` en `theme.ts`). Bajar Google Fonts al renderizar daba timeout.
- Para revisar sin renderizar todo:
  - `npx remotion still DumpsiteLocal out/x.png --frame=2700 --scale=0.4`;
  - para una hoja de contacto, extraer cuadros del mp4 con ffmpeg y juntarlos con `-vf tile=4x6`.
- El render completo del video local tarda varios minutos.

### Azure AI Speech (voz sintética)
- Se usa la API REST con SSML: `prosody` (rate, pitch, volume), `<sub alias>` para la pronunciación y `xml:lang` según el idioma del guion.
- Formato de salida `riff-48khz-16bit-mono-pcm`. Se recorta el silencio del principio y del final de cada toma.
- La clave va en `video/.env.local` (`AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION`). El script nunca la imprime.
- Voces probadas: `en-US-AndrewMultilingualNeural` para inglés y `es-AR-TomasNeural` para castellano.

### Higgsfield (clip de IA)
- API, no MCP: SDK de Python `higgsfield-client` (`subscribe`, `upload_file`), con la clave `HF_KEY=key-id:key-secret` en `video/.env.local`.
- Modelo Seedance 2.5:
  - `bytedance/seedance-2.5/image-to-video` recibe `image_url` y no acepta `aspect_ratio`;
  - `.../text-to-video` sí acepta `aspect_ratio`.
- El borrador a 480p (`draft: true`) cuesta unos USD 0,12 por segundo.

**Historia del clip:**
1. `descenso.py` (text-to-video, 5 s) salió feo: la basura parecía tierra y había topadoras.
2. `satelite.py` (image-to-video, 10 s) arranca en un render oficial de NISAR (`nisar-primer-cuadro.jpg`) y baja hasta un basural. Es el clip que se usa: `salidas/satelite-draft-203402.mp4`, que se pasa por WhatsApp.
3. `montar_clip.sh` lo corta y lo re-temporiza a 4,73 s (satélite 1 s, nubes 1 s, basural 2,7 s) y lo deja en `public/clip1-ai.mp4`.

- El equipo pidió **no tocar Higgsfield sin que lo pidan**: cada corrida cuesta plata. Mostrar el prompt y esperar el OK antes de mandar.
- Para el video en castellano se reusa el mismo clip.

### Capturas de la web
- Se hacen con puppeteer-core y el chrome-headless-shell que trae Remotion, sirviendo la web con `vite preview`.
- En Ubuntu hace falta `--no-sandbox`: AppArmor bloquea el sandbox de Chrome. `--virtual-time-budget` se colgaba; por eso se usan esperas reales (el mapa de MapLibre tarda unos 10 s).
- Las capturas en inglés (`public/web/mapa.png`, `inicio.png`, `sitios.png`, `modelo.png`) salieron de la rama `web-ingles`, que tiene la web traducida y el cambio de nombre a Dumpsite.

## 8. Pendientes
- Links definitivos (dominio y repo) en `compartido/data.ts`, y re-render de los dos videos.
- Voz grabada y texto final del video en castellano.
- Corregir la página Modelo de la web (la mención a ResNet) y la marca en `main`.
