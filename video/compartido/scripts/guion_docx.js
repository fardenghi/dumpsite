// Genera espanol/guion-local.docx desde espanol/guion-es.json y espanol/voz-es.json.
// Uso (desde video/):  npm i --no-save docx && node compartido/scripts/guion_docx.js espanol/guion-local.docx
// Si cambia lo que se ve en pantalla, actualizar la lista ESCENAS de abajo.
const fs = require("fs");
const path = require("path");
const {Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, WidthType, ShadingType, PageOrientation, AlignmentType, LevelFormat, BorderStyle} = require("docx");

const BASE = path.join(__dirname, "..", "..", "espanol") + "/";
const guion = JSON.parse(fs.readFileSync(BASE + "guion-es.json", "utf8"));
const voz = JSON.parse(fs.readFileSync(BASE + "voz-es.json", "utf8"));
const texto = (id) => guion.frases.find((f) => f.id === id).partes.map((p) => p.texto).join(" ");
const t = (id) => voz.frases.find((f) => f.id === id);
const mmss = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
const rango = (a, b) => `${mmss(a)} – ${mmss(b)}`;
const ini = (id) => t(id).inicio;

// Escenas: [título, tiempo, ids de voz, lo que se ve en pantalla]
const ESCENAS = [
  ["1. El problema", rango(0, ini("dumpsite")), ["problema"], [
    "Clip generado con IA (Higgsfield): del espacio, a través de las nubes, hasta un basural. Píldora \"Imagen generada con IA\" visible todo el clip.",
    "Cifras sobre el basural en cámara lenta: ≈ 5.000 basurales a cielo abierto en Argentina (estimación del Ministerio de Ambiente, no sale de un relevamiento formal).",
    "0 inventarios oficiales abiertos con coordenadas.",
  ]],
  ["2. Dumpsite y NISAR", rango(ini("dumpsite") - 0.6, ini("cambia")), ["dumpsite"], [
    "Pulso de radar que revela la imagen satelital de Norte III (Sentinel-2) con pin \"Buenos Aires, Argentina\".",
    "Título \"Dumpsite · Una plataforma que sigue basurales desde el espacio\".",
    "Pasa a la imagen de coherencia de NISAR con el polígono del basural. Leyenda: suelo estable / suelo que cambia. Chips: cada 12 días · de día y de noche · a través de las nubes · radar banda L.",
  ]],
  ["3. Insomnio", rango(ini("cambia"), ini("casos")), ["cambia", "coherencia", "mapa"], [
    "\"Mismo basural, 6 fechas\": serie real de Sentinel-2 de Norte III, entre junio y octubre de 2026.",
    "\"Coherencia = qué tan parecidas son dos pasadas\" (1 = nada cambió, 0 = cambió todo). Ocho pasadas con un ojo abierto o cerrado y barras del basural contra el entorno.",
    "Contador \"inquieto en 8 de 8 pasadas\" e índice de insomnio de Norte III: 0,86.",
    "Mapa del Gran Buenos Aires con el índice: \"219 manchas candidatas\", sin agua (JRC), sin rutas ni arroyos, sin cultivos estacionales.",
  ]],
  ["4. Casos reales", rango(ini("casos"), ini("datos")), ["casos"], [
    "Capturas de la web en un navegador.",
    "Basural de Luján: cerrado el 1 de julio de 2026, quieto en las 15 pasadas, insomnio 0 %.",
    "Norte III (CEAMSE): relleno activo, insomnio 86 %.",
    "González Catán: sin registro abierto, insomnio 100 %.",
  ]],
  ["5. Los datos", rango(ini("datos"), ini("modelo")), ["datos"], [
    "Pared de 28 recortes satelitales del catálogo, con el país de cada uno.",
    "Contador hasta 66.981 basurales mapeados en todo el mundo.",
    "Fuentes: OpenStreetMap · Overture (polígonos de rellenos), Climate TRACE (emisiones por sitio), EPA LMOP (rellenos registrados en EE. UU.), NASA EMIT (plumas de metano).",
    "\"Y ejemplos de lo que se le parece, de OpenStreetMap\": canteras, aeródromos, campos de golf, parques.",
  ]],
  ["6. El modelo (LightGBM)", rango(ini("modelo"), ini("resultados")), ["modelo"], [
    "\"29 variables por mancha\": 12 de radar NISAR, 11 ópticas Sentinel-2, 3 de forma, 3 del entorno.",
    "Caja LightGBM (árboles de decisión con boosting) con chips: vegetación · NDVI, suelo desnudo · BSI, agua · NDWI, infrarrojo · SWIR, coherencia de radar, forma de la mancha. Árboles que se suman, \"× 300\".",
    "Bandejas \"Basural\" (Norte III, clasificado por el modelo) y \"Otra cosa\" (un aeródromo, una cantera).",
    "Validación: \"se deja una ciudad entera afuera y se predice esa\", recorriendo 9 ciudades. Sin métricas en pantalla.",
  ]],
  ["7. Resultados", rango(ini("resultados"), ini("web")), ["resultados"], [
    "42 basurales de catálogo, activos en el radar.",
    "13 figuran cerrados y siguen activos.",
    "Chips de las 10 regiones: Buenos Aires, Los Ángeles, Ciudad de México, Delhi, Yakarta, Ponce, Ohio, Maryland, New Hampshire, Nueva York.",
    "Nota: índice de insomnio cruzado con los catálogos · señal compatible con actividad, sin verificar en terreno.",
  ]],
  ["8. La web", rango(ini("web"), ini("cierre")), ["web"], [
    "Recorrido por dumpsite.earth en un navegador, en cuatro pasos: el mapa del índice de insomnio, la ficha de un sitio con su curva de coherencia, la lista con el registro oficial, cómo decide el modelo.",
  ]],
  ["9. Fuentes y cierre", rango(ini("cierre"), voz.duracion_video), ["cierre"], [
    "\"Solo datos abiertos\": lista de fuentes con licencia y para qué se usó cada una (ver abajo).",
    "Declaración: contenido generado con IA, clip inicial (Higgsfield) y voz sintética (Azure AI Speech).",
    "Links: Mapa en vivo dumpsite.earth · Código y modelo github.com/fardenghi/dumpsite.",
    "Cierre: DUMPSITE · \"Los basurales que el radar nunca ve quietos\" · NASA Space Apps 2026 · Dancing with the SARs · Buenos Aires.",
  ]],
];

const FUENTES = [
  ["NISAR GUNW y GCOV", "NASA / ISRO · vía ASF DAAC", "coherencia y eco de radar"],
  ["Sentinel-2 L2A", "ESA Copernicus · Planetary Computer · EOX", "imágenes ópticas e índices"],
  ["JRC Global Surface Water", "Comisión Europea", "máscara de agua"],
  ["OpenStreetMap · Overture Maps", "ODbL", "polígonos de rellenos y de lo que se les parece"],
  ["Climate TRACE", "CC BY 4.0", "emisiones por sitio"],
  ["EPA LMOP", "dominio público", "rellenos registrados en EE. UU."],
  ["NASA EMIT", "LP DAAC", "plumas de metano"],
];

const FONT = "Arial";
const W = [1300, 1900, 5300, 5300]; // landscape A4 útil ≈ 13800 DXA
const TOTAL = W.reduce((a, b) => a + b, 0);
const borde = {style: BorderStyle.SINGLE, size: 4, color: "BFC7D1"};
const bordes = {top: borde, bottom: borde, left: borde, right: borde};
const p = (txt, opts = {}) => new Paragraph({spacing: {after: 80}, ...opts.par, children: [new TextRun({text: txt, font: FONT, size: opts.size || 20, bold: opts.bold, color: opts.color, italics: opts.italics})]});
const celda = (hijos, w, fondo) => new TableCell({width: {size: w, type: WidthType.DXA}, borders: bordes, margins: {top: 100, bottom: 100, left: 120, right: 120},
  shading: fondo ? {type: ShadingType.CLEAR, color: "auto", fill: fondo} : undefined, children: hijos});
const vineta = (txt) => new Paragraph({numbering: {reference: "v", level: 0}, spacing: {after: 60}, children: [new TextRun({text: txt, font: FONT, size: 19})]});

const encabezado = new TableRow({tableHeader: true, children: ["Tiempo", "Escena", "Voz (lo que se dice)", "En pantalla"].map((h, i) =>
  celda([p(h, {bold: true, color: "FFFFFF"})], W[i], "1F2A37"))});
const filas = ESCENAS.map(([titulo, tiempo, ids, pantalla], k) => new TableRow({cantSplit: true, children: [
  celda([p(tiempo, {size: 19})], W[0], k % 2 ? "F5F7FA" : undefined),
  celda([p(titulo, {bold: true})], W[1], k % 2 ? "F5F7FA" : undefined),
  celda(ids.map((id) => p(texto(id))), W[2], k % 2 ? "F5F7FA" : undefined),
  celda(pantalla.map(vineta), W[3], k % 2 ? "F5F7FA" : undefined),
]}));

const WF = [3800, 4800, 5200];
const tablaFuentes = new Table({width: {size: WF.reduce((a, b) => a + b, 0), type: WidthType.DXA}, columnWidths: WF, rows: [
  new TableRow({tableHeader: true, children: ["Fuente", "Origen / licencia", "Para qué se usa"].map((h, i) => celda([p(h, {bold: true, color: "FFFFFF"})], WF[i], "1F2A37"))}),
  ...FUENTES.map((f) => new TableRow({children: f.map((x, i) => celda([p(x)], WF[i]))})),
]});

const doc = new Document({
  styles: {
    default: {document: {run: {font: FONT, size: 20}}},
    paragraphStyles: [
      {id: "Title", name: "Title", basedOn: "Normal", run: {font: FONT, size: 40, bold: true}, paragraph: {spacing: {before: 0, after: 120}, keepNext: true}},
      {id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true, run: {font: FONT, size: 28, bold: true}, paragraph: {spacing: {before: 300, after: 120}, keepNext: true, outlineLevel: 0}},
    ],
  },
  numbering: {config: [{reference: "v", levels: [{level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: {paragraph: {indent: {left: 280, hanging: 200}}}}]}]},
  sections: [{
    properties: {page: {size: {width: 11906, height: 16838, orientation: PageOrientation.LANDSCAPE}, margin: {top: 1000, bottom: 1000, left: 1000, right: 1000}}},
    children: [
      new Paragraph({style: "Title", children: [new TextRun({text: "Dumpsite · Guion del video para el jurado local", font: FONT})]}),
      p(`NASA Space Apps 2026 · Dancing with the SARs · sede Buenos Aires. Duración: ${mmss(voz.duracion_video)} (máximo 3:00). Castellano, un solo narrador con voz sintética (Azure, es-AR-TomasNeural), subtítulos en pantalla.`, {color: "444444"}),
      p("Versión 1 (14/11/2026). Las cifras salen del repo: docs/idea.md, docs/indice-insomnio.md, data/catalogos/basurales y seed/veredictos.json. Lo que marca el modelo se dice \"clasificado como basural por el modelo\", nunca \"confirmado\". Los tiempos son de la locución actual y cambian si se cambia el texto.", {color: "666666", italics: true, size: 18}),
      new Paragraph({heading: "Heading1", children: [new TextRun({text: "Guion escena por escena", font: FONT})]}),
      new Table({width: {size: TOTAL, type: WidthType.DXA}, columnWidths: W, rows: [encabezado, ...filas]}),
      new Paragraph({heading: "Heading1", children: [new TextRun({text: "Fuentes que se muestran al cierre", font: FONT})]}),
      tablaFuentes,
      new Paragraph({heading: "Heading1", children: [new TextRun({text: "Para refinar antes de entregar", font: FONT})]}),
      vineta("Links definitivos: dumpsite.earth y github.com/fardenghi/dumpsite son provisorios."),
      vineta("Página Modelo de la web: más abajo todavía menciona ResNet como \"lo que sigue\". En el video se muestra solo la parte de arriba; conviene corregirla."),
      vineta("Cifra de 5.000 basurales: es una estimación del Ministerio de Ambiente sin relevamiento formal; así se aclara en pantalla y en la voz."),
      vineta("Resultados (42 / 13): señal compatible con actividad, sin verificar en terreno. No acusar a nadie."),
      vineta("Si se cambia el texto de la voz, hay que regenerar el audio y los tiempos se reacomodan solos."),
    ],
  }],
});

Packer.toBuffer(doc).then((b) => { fs.writeFileSync(process.argv[2], b); console.log("ok"); });
