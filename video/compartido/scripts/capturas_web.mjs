// Capturas de la web (en castellano) para el video local: public/web/es-*.png, 1920 × 1080.
// Uso (desde video/):
//   1. Servir la web:  cd ../insomnes-web && npm run build && npx vite preview --port 4174 --strictPort
//   2. npm i --no-save puppeteer-core
//   3. node compartido/scripts/capturas_web.mjs <ruta a chrome o chrome-headless-shell> public/web
// Remotion trae chrome-headless-shell en node_modules/.remotion/. En Ubuntu hace falta --no-sandbox (AppArmor).
// Las capturas en inglés (mapa, inicio, sitios, modelo) salieron de la rama web-ingles con este mismo método.
import puppeteer from "puppeteer-core";
const [,, chrome, out] = process.argv;
const b = await puppeteer.launch({executablePath: chrome, args: ["--no-sandbox", "--hide-scrollbars"], defaultViewport: {width: 1920, height: 1080}});
const pg = await b.newPage();
const espera = (ms) => new Promise((r) => setTimeout(r, ms));
const ir = async (h, ms = 9000) => { await pg.evaluate((x) => { location.hash = x; }, h); await espera(ms); };
await pg.goto("http://localhost:4174/#/mapa", {waitUntil: "domcontentloaded"}); await espera(10000);
await pg.screenshot({path: `${out}/es-mapa.png`}); console.log("mapa");
await pg.click("button.capa"); await espera(3500);
await pg.screenshot({path: `${out}/es-mapa-indice.png`}); console.log("indice");
await ir("/mapa?sitio=norte-iii", 11000); await pg.screenshot({path: `${out}/es-ficha-norte3.png`}); console.log("norte3");
await ir("/mapa?sitio=lujan", 11000); await pg.screenshot({path: `${out}/es-ficha-lujan.png`}); console.log("lujan");
await ir("/mapa?sitio=gonzalez-catan", 11000); await pg.screenshot({path: `${out}/es-ficha-catan.png`}); console.log("catan");
await ir("/inicio", 4000); await pg.screenshot({path: `${out}/es-inicio.png`}); console.log("inicio");
await ir("/sitios", 4000); await pg.screenshot({path: `${out}/es-sitios.png`}); console.log("sitios");
await ir("/modelo", 4000); await pg.screenshot({path: `${out}/es-modelo.png`}); console.log("modelo");
await b.close();
