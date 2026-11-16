// World map for the results scene of the international video, with the same map as the web (MapLibre):
//   public/casos/mundo.jpg           NASA GIBS Blue Marble, without interface
//   public/casos/mundo-catalogo.jpg  the same with the dump-site catalog points as the web draws them
//   compartido/mundo.json            in pixels of those images: the center of each region run and the possible new sites
//                                    (p_basural >= 0.4 and no other known use in OSM, like the web's posiblesNuevos())
// Usage (from video/): serve the web on :4174 (see capturas_web.mjs) and  node compartido/scripts/captura_mundo.mjs <path to chrome>
import fs from "node:fs";
import puppeteer from "puppeteer-core";

const RAIZ = new URL("../../../", import.meta.url).pathname;
const frames = JSON.parse(fs.readFileSync(`${RAIZ}data/catalogos/frames.json`)).frames;
const ver = JSON.parse(fs.readFileSync(`${RAIZ}web/src/data/seed/veredictos.json`)).sitios;
const nuevos = ver.filter((x) => x.tipo === "mancha" && typeof x.p_basural === "number" && x.p_basural >= 0.4 && !x.que && typeof x.lat === "number");
const corridas = new Set(ver.map((x) => x.frame));
const regiones = frames.filter((f) => corridas.has(f.frame));

const b = await puppeteer.launch({executablePath: process.argv[2], args: ["--no-sandbox", "--hide-scrollbars"], defaultViewport: {width: 1920, height: 1080}});
const pg = await b.newPage();
const espera = (ms) => new Promise((r) => setTimeout(r, ms));
await pg.goto("http://localhost:4174/?captura&lang=en#/mapa", {waitUntil: "domcontentloaded"});
await pg.waitForFunction(() => window.mapa && window.mapa.isStyleLoaded() && window.mapa.getLayer("catalogo"), {timeout: 60000});
await espera(3000);
await pg.addStyleTag({content: ".map-top,.map-legend,.dock,.ficha,.panel,.maplibregl-ctrl,.map-credit,.map-cred,.cred,nav,header,footer,[class*=leyenda],[class*=legend]{display:none!important}"});
const solo = (capas) => pg.evaluate((capas) => { const m = window.mapa; for (const l of m.getStyle().layers) m.setLayoutProperty(l.id, "visibility", capas.includes(l.id) ? "visible" : "none"); }, capas);
const quieto = () => pg.evaluate(() => new Promise((r) => { const m = window.mapa; if (m.loaded() && m.areTilesLoaded()) setTimeout(r, 600); else m.once("idle", () => setTimeout(r, 600)); }));
await pg.evaluate(() => window.mapa.jumpTo({center: [5, 18], zoom: 1.92}));
await solo(["fondo"]); await quieto(); await espera(1500);
fs.mkdirSync("public/casos", {recursive: true});
await pg.screenshot({path: "public/casos/mundo.jpg", type: "jpeg", quality: 88});
await solo(["fondo", "catalogo"]); await quieto(); await espera(1500);
await pg.screenshot({path: "public/casos/mundo-catalogo.jpg", type: "jpeg", quality: 88});
const px = (pts) => pg.evaluate((pts) => pts.map(([lon, lat]) => { const p = window.mapa.project([lon, lat]); return [Math.round(p.x * 10) / 10, Math.round(p.y * 10) / 10]; }), pts);
const salida = {
  fuente: "captura_mundo.mjs: data/catalogos/frames.json, web/src/data/seed/veredictos.json",
  regiones: (await px(regiones.map((f) => [(f.bbox[0] + f.bbox[2]) / 2, (f.bbox[1] + f.bbox[3]) / 2]))).map((p, k) => ({frame: regiones[k].frame, pais: regiones[k].pais, p})),
  nuevos: await px(nuevos.map((x) => [x.lon, x.lat])),
};
fs.writeFileSync("compartido/mundo.json", JSON.stringify(salida));
console.log(salida.regiones.length, "regiones,", salida.nuevos.length, "nuevos");
await b.close();
