// Capture of the web map in English, in the entry view (the whole world with the points of each region that was run),
// for the ending of the international video: public/web/en-mapa-mundo.png
// Usage (from video/): serve the web on :4174 (see capturas_web.mjs) and  node compartido/scripts/captura_mapa_en.mjs <path to chrome>
// When the web has the run of the large Argentine cities, capture again so their points show.
import puppeteer from "puppeteer-core";
const b = await puppeteer.launch({executablePath: process.argv[2], args: ["--no-sandbox", "--hide-scrollbars"], defaultViewport: {width: 1920, height: 1080}});
const pg = await b.newPage();
await pg.goto("http://localhost:4174/?lang=en&captura#/mapa", {waitUntil: "domcontentloaded"});
await pg.waitForFunction(() => window.mapa && window.mapa.isStyleLoaded(), {timeout: 60000});
await new Promise((r) => setTimeout(r, 10000));
await pg.screenshot({path: "public/web/en-mapa-mundo.png"});
await b.close();
console.log("listo");
