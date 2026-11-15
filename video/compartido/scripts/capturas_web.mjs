// Capturas de la web (en castellano, forzado con ?lang=es) para el video local: public/web/es-*.png, 1920 × 1080.
// Uso (desde video/):
//   1. Serve the web:  cd ../web && npm run build && npx vite preview --port 4174 --strictPort
//   2. npm i --no-save puppeteer-core
//   3. node compartido/scripts/capturas_web.mjs <ruta a chrome o chrome-headless-shell> public/web
// También escribe compartido/web-rects.json: rectángulos (x, y, ancho, alto, en píxeles de la captura) de lo que se resalta en el video.
// Remotion trae chrome-headless-shell en node_modules/.remotion/. En Ubuntu hace falta --no-sandbox (AppArmor).
// Las capturas en inglés (mapa, inicio, sitios, modelo) salieron de la rama web-ingles con este mismo método.
import fs from "node:fs";
import puppeteer from "puppeteer-core";
const [,, chrome, out] = process.argv;
const b = await puppeteer.launch({executablePath: chrome, args: ["--no-sandbox", "--hide-scrollbars"], defaultViewport: {width: 1920, height: 1080}});
const pg = await b.newPage();
const espera = (ms) => new Promise((r) => setTimeout(r, ms));
const rects = {};
const caja = (sel) => pg.evaluate((sel) => { const e = document.querySelector(sel); if (!e) return null; const r = e.getBoundingClientRect(); return [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)]; }, sel);
const fichaRects = async (id) => { rects[id] = {ficha: await caja(".ficha"), tag: await caja(".ficha .tag"), kpis: await caja(".ficha .kpis"), crece: await caja(".ficha .crece")}; };
const ir = async (h, ms = 9000) => { await pg.evaluate((x) => { location.hash = x; }, h); await espera(ms); };
await pg.goto("http://localhost:4174/?lang=es&captura#/mapa", {waitUntil: "domcontentloaded"}); await espera(10000);
await pg.screenshot({path: `${out}/es-mapa.png`}); console.log("mapa");
rects.mapa = {lujan: await pg.evaluate(() => { const p = window.mapa.project([-59.1182, -34.5204]); return [Math.round(p.x), Math.round(p.y)]; })};
await pg.click("button.capa"); await espera(3500);
await pg.screenshot({path: `${out}/es-mapa-indice.png`}); console.log("indice");
await ir("/mapa?sitio=norte-iii", 11000); await pg.screenshot({path: `${out}/es-ficha-norte3.png`}); await fichaRects("norte3"); console.log("norte3");
await ir("/mapa?sitio=lujan", 11000); await pg.screenshot({path: `${out}/es-ficha-lujan.png`}); await fichaRects("lujan"); console.log("lujan");
await ir("/mapa?sitio=gonzalez-catan", 11000); await pg.screenshot({path: `${out}/es-ficha-catan.png`}); console.log("catan");
await ir("/inicio", 4000); await pg.screenshot({path: `${out}/es-inicio.png`}); console.log("inicio");
await ir("/sitios", 4000); await pg.screenshot({path: `${out}/es-sitios.png`}); rects.sitios = {csv: await caja("[data-filtros] .btn"), lista: await caja(".lista")}; console.log("sitios");
await ir("/modelo", 4000); await pg.screenshot({path: `${out}/es-modelo.png`}); console.log("modelo");
fs.writeFileSync(new URL("../web-rects.json", import.meta.url), JSON.stringify(rects, null, 1));
await b.close();
