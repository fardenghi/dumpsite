// Todo lo editable del video está acá.
// - datos-reales.json: salidas del pipeline (scripts/preparar_assets.py).
// - guion.json + voz.json: guion con emoción por frase y los tiempos reales de la voz (scripts/voz_azure.py).
import reales from "./datos-reales.json";
import voz from "../ingles/voz.json";

export const FPS = 30;
export const ANCHO = 1920;
export const ALTO = 1080;

type Frase = {id: string; archivo: string; inicio: number; duracion: number; texto: string};
export const VOZ = voz as {voz: string; duracion_video: number; frases: Frase[]};
export const DURACION_S = VOZ.duracion_video; // < 30 s (límite de Space Apps)
const f = (id: string) => VOZ.frases.find((x) => x.id === id)!;

// Escenas sincronizadas con la voz: cada una arranca cuando empieza su frase.
const finIntro = f("intro").inicio + f("intro").duracion + 0.35;
export const ESCENAS = {
  ia: {desde: 0, hasta: finIntro},
  transicion: {desde: finIntro, hasta: f("nisar").inicio},
  nisar: {desde: f("nisar").inicio, hasta: f("insomnia").inicio},
  insomnia: {desde: f("insomnia").inicio, hasta: f("red").inicio},
  red: {desde: f("red").inicio, hasta: f("resultados").inicio},
  resultados: {desde: f("resultados").inicio, hasta: DURACION_S},
};
export const FRASES = VOZ.frases;

// Mientras sea true, cada dato de ejemplo lleva una etiqueta discreta arriba a la derecha.
// Integrantes, tal como figuran en la página del equipo en spaceappschallenge.org (aparecen al principio, abajo a la derecha)
export const NOMBRE_EQUIPO = "<=> (spaceship)";
export const EQUIPO = ["Nicolas Priotto", "Agustín Tomás Romero", "Ezequiel Testoni", "Filipo Ardenghi", "Santiago Bassi", "Juan Ignacio Lategana"];

export const MOSTRAR_PLACEHOLDERS = false; // ocultas en el video; lo único que falta reemplazar son las cifras finales (RESULTADOS)

// ---- PLACEHOLDER: cifras de ejemplo pedidas por el equipo hasta tener las reales ----
// (La web hoy muestra datos reales del AMBA: 12 sitios analizados, 6 despiertos, 4 despiertos sin registro.)
export const RESULTADOS = {
  // Reales: insomnes-web/src/data/seed/veredictos.json (flujo.py, 10 regiones). Índice de insomnio cruzado con catálogos, no del modelo.
  encontrados: 42, // basurales de catálogos que el radar ve activos
  sinRegistro: 13, // de ellos, figuran cerrados pero siguen activos (sin verificar a mano)
  registro: 0,
  region: "Buenos Aires, Argentina",
  url: "dumpsite.earth", // PLACEHOLDER hasta tener el deploy
  repo: "github.com/fardenghi/dumpsite", // PLACEHOLDER: confirmar el repo público
}

// ---- PLACEHOLDER: salida de la CNN por recorte (la clase OSM de cada recorte sí es real) ----
export const EJEMPLOS_CNN = [
  // Salida del clasificador (LightGBM): "classified as a dump by the model", nunca "confirmado".
  {id: "norte3-disp", clase: "Dump", detalle: "classified by the model", basural: true},
  {id: "el-palomar", clase: "Something else", detalle: "an airfield", basural: false},
  {id: "tres-febrero", clase: "Something else", detalle: "a quarry", basural: false},
]

export const DATOS = reales;
export type Par = {fecha: string; orbita: number; sitio: number; anillo: number; despierto: boolean};

// Fecha "2026-07-08" -> "Jul 8"
const MESES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export const fechaCorta = (iso: string) => `${MESES[Number(iso.slice(5, 7)) - 1]} ${Number(iso.slice(8, 10))}`;
