// Everything editable in the video is here.
// - datos-reales.json: pipeline outputs (scripts/preparar_assets.py).
// - guion.json + voz.json: script with emotion per sentence and the real voice timings (scripts/voz_azure.py).
import reales from "./datos-reales.json";
import voz from "../ingles/voz.json";

export const FPS = 30;
export const ANCHO = 1920;
export const ALTO = 1080;

type Frase = {id: string; archivo: string; inicio: number; duracion: number; texto: string};
export const VOZ = voz as {voz: string; duracion_video: number; frases: Frase[]};
export const DURACION_S = VOZ.duracion_video; // < 30 s (Space Apps limit)
const f = (id: string) => VOZ.frases.find((x) => x.id === id)!;

// Scenes synced with the voice: each one starts when its sentence starts.
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

// While true, each example figure carries a discreet tag at the top right.
// Team members, as listed on the team page at spaceappschallenge.org (they appear at the start, bottom right)
export const NOMBRE_EQUIPO = "<=> (spaceship)";
export const EQUIPO = ["Nicolas Priotto", "Agustín Tomás Romero", "Ezequiel Testoni", "Filipo Ardenghi", "Santiago Bassi", "Juan Ignacio Lategana"];

export const MOSTRAR_PLACEHOLDERS = false; // hidden in the video; the only thing left to replace is the final figures (RESULTADOS)

// ---- PLACEHOLDER: example figures requested by the team until the real ones are in ----
// (The web currently shows real AMBA data: 12 sites analyzed, 6 awake, 4 awake without a record.)
export const RESULTADOS = {
  // Real: web/src/data/seed/veredictos.json (flujo.py, 10 regions). Insomnia index crossed with catalogs, not from the model.
  encontrados: 42, // catalog dump sites that the radar sees as active
  sinRegistro: 13, // of those, listed as closed but still active (not checked by hand)
  registro: 0,
  region: "Buenos Aires, Argentina",
  url: "dumpsite.earth", // PLACEHOLDER until there's a deploy
  repo: "github.com/fardenghi/dumpsite", // PLACEHOLDER: confirm the public repo
}

// ---- PLACEHOLDER: CNN output per crop (the OSM class of each crop is real) ----
export const EJEMPLOS_CNN = [
  // Classifier output (LightGBM): "classified as a dump by the model", never "confirmed".
  {id: "norte3-disp", clase: "Dump", detalle: "classified by the model", basural: true},
  {id: "el-palomar", clase: "Something else", detalle: "an airfield", basural: false},
  {id: "tres-febrero", clase: "Something else", detalle: "a quarry", basural: false},
]

export const DATOS = reales;
export type Par = {fecha: string; orbita: number; sitio: number; anillo: number; despierto: boolean};

// Fecha "2026-07-08" -> "Jul 8"
const MESES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export const fechaCorta = (iso: string) => `${MESES[Number(iso.slice(5, 7)) - 1]} ${Number(iso.slice(8, 10))}`;
