import {loadFont} from "@remotion/fonts";
import {staticFile} from "remotion";

// Local fonts (public/fonts, copied from @fontsource): rendering doesn't depend on the internet.
const FUENTES: [string, string, string][] = [
  ["IBM Plex Sans", "400", "ibm-plex-sans-latin-400-normal.woff2"],
  ["IBM Plex Sans", "500", "ibm-plex-sans-latin-500-normal.woff2"],
  ["IBM Plex Sans", "600", "ibm-plex-sans-latin-600-normal.woff2"],
  ["IBM Plex Mono", "400", "ibm-plex-mono-latin-400-normal.woff2"],
  ["IBM Plex Mono", "500", "ibm-plex-mono-latin-500-normal.woff2"],
  ["Barlow Condensed", "600", "barlow-condensed-latin-600-normal.woff2"],
  ["Barlow Condensed", "700", "barlow-condensed-latin-700-normal.woff2"],
];
for (const [family, weight, archivo] of FUENTES) {
  loadFont({family, weight, url: staticFile(`fonts/${archivo}`), display: "block"});
}

export const F = {
  sans: `"IBM Plex Sans", system-ui, sans-serif`,
  mono: `"IBM Plex Mono", ui-monospace, monospace`,
  display: `"Barlow Condensed", "Arial Narrow", sans-serif`,
};

// Night radar: near-black background, amber for what "doesn't sleep", cyan for what's stable.
export const C = {
  bg: "#05080c",
  ink: "#e7ebf1",
  muted: "#8e99a8",
  glow: "#ffa53d",
  radar: "#5fc0dc",
  panel: "rgba(10,15,22,0.82)",
  line: "rgba(231,235,241,0.18)",
  placeholder: "#ff7a1a",
};
