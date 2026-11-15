// Imágenes de mapa para el video local, renderizadas con el mismo mapa de la web (MapLibre), sin la interfaz:
//   public/casos/argentina.jpg        Argentina con NASA GIBS Blue Marble
//   public/casos/<sitio>/<fecha>.jpg  Sentinel-2 L2A (Planetary Computer) del sitio en cada fecha que tiene la web
//   compartido/casos.json             contornos y puntos ya pasados a píxeles de esas imágenes, más las pasadas del radar
// Uso (desde video/):
//   1. cd ../insomnes-web && npm run build && npx vite preview --port 4174 --strictPort
//   2. node compartido/scripts/capturas_mapa.mjs <ruta a chrome>
// Necesita red (teselas de GIBS y de Planetary Computer).
import fs from "node:fs";
import puppeteer from "puppeteer-core";

const chrome = process.argv[2];
const RAIZ = new URL("../../../", import.meta.url).pathname;
const sitios = Object.fromEntries(JSON.parse(fs.readFileSync(`${RAIZ}insomnes-web/src/data/seed/sitios.json`)).map((s) => [s.id, s]));
const catalogo = JSON.parse(fs.readFileSync(`${RAIZ}data/basurales/basurales_mundo.json`)).sitios.filter((x) => x.pais === "ARG");
const S2 = (item) => `https://planetarycomputer.microsoft.com/api/data/v1/item/tiles/WebMercatorQuad/{z}/{x}/{y}@2x?collection=sentinel-2-l2a&item=${item}&assets=visual&asset_bidx=visual%7C1%2C2%2C3&nodata=0&format=png`;
const OUT = `${RAIZ}video/public/casos`;
fs.mkdirSync(OUT, {recursive: true});

const b = await puppeteer.launch({executablePath: chrome, headless: "new", args: ["--hide-scrollbars"]});
const pg = await b.newPage();
const espera = (ms) => new Promise((r) => setTimeout(r, ms));

async function preparar(w, h) {
  await pg.setViewport({width: w, height: h});
  await pg.goto("http://localhost:4174/?captura&lang=es#/mapa", {waitUntil: "domcontentloaded"});
  await pg.waitForFunction(() => window.mapa && window.mapa.isStyleLoaded() && window.mapa.getLayer("punto"), {timeout: 60000});
  await espera(1500);
  // fuera la interfaz y las capas propias de la web: sólo el fondo
  await pg.addStyleTag({content: ".map-top,.map-legend,.dock,.ficha,.panel,.maplibregl-ctrl,.map-credit,.map-cred,.cred,nav{display:none!important}"});
  await pg.evaluate(() => {
    const m = window.mapa;
    for (const l of m.getStyle().layers) if (l.id !== "fondo") m.setLayoutProperty(l.id, "visibility", "none");
  });
}
const quieto = () => pg.evaluate(() => new Promise((r) => { const m = window.mapa; if (m.loaded() && m.areTilesLoaded()) setTimeout(r, 400); else m.once("idle", () => setTimeout(r, 400)); }));
const proyectar = (pts) => pg.evaluate((pts) => pts.map(([lon, lat]) => { const p = window.mapa.project([lon, lat]); return [Math.round(p.x * 10) / 10, Math.round(p.y * 10) / 10]; }), pts);

const salida = {fuente: "capturas_mapa.mjs: insomnes-web/src/data/seed/sitios.json y data/basurales/basurales_mundo.json", argentina: {}, sitios: {}};

// 1 · Argentina
const [AW, AH] = [1920, 1080];
await preparar(AW, AH);
await pg.evaluate(() => {
  const m = window.mapa;
  // límites y costas de NASA GIBS (Reference_Features_15m) sobre el Blue Marble
  m.addSource("limites", {type: "raster", tiles: ["https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/Reference_Features_15m/default/default/GoogleMapsCompatible_Level13/{z}/{y}/{x}.png"], tileSize: 256, maxzoom: 9});
  m.addLayer({id: "limites", type: "raster", source: "limites", paint: {"raster-opacity": 0.9}});
  m.jumpTo({center: [-58.5, -39.5], zoom: 3.75});
});
await quieto();
await pg.screenshot({path: `${OUT}/argentina.jpg`, type: "jpeg", quality: 90});
salida.argentina = {ancho: AW, alto: AH, puntos: await proyectar(catalogo.map((x) => [x.lon, x.lat])), nombres: catalogo.map((x) => x.nombre),
  amba: (await proyectar([[-58.45, -34.6]]))[0]};
console.log("argentina", catalogo.length, "puntos");

// 2 · Cada sitio, en cada fecha de Sentinel-2
const LADO = 1000;
for (const id of ["lujan", "gonzalez-catan", "norte-iii"]) {
  const s = sitios[id];
  const anillo = s.contorno.coordinates[0];
  const lons = anillo.map((p) => p[0]), lats = anillo.map((p) => p[1]);
  const cx = (Math.min(...lons) + Math.max(...lons)) / 2, cy = (Math.min(...lats) + Math.max(...lats)) / 2;
  const medio = Math.max(Math.max(...lons) - Math.min(...lons), (Math.max(...lats) - Math.min(...lats)) / Math.cos((cy * Math.PI) / 180)) * 1.1;
  await preparar(LADO, LADO);
  await pg.evaluate(([cx, cy, medio, LADO]) => {
    const m = window.mapa;
    const dy = medio * Math.cos((cy * Math.PI) / 180);
    m.fitBounds([cx - medio, cy - dy, cx + medio, cy + dy], {padding: 0, duration: 0, maxZoom: 15});
  }, [cx, cy, medio, LADO]);
  fs.mkdirSync(`${OUT}/${id}`, {recursive: true});
  const fechas = [];
  for (const im of s.imagenes) {
    await pg.evaluate((url) => {
      const m = window.mapa;
      if (m.getLayer("cap")) m.removeLayer("cap");
      if (m.getSource("cap")) m.removeSource("cap");
      m.addSource("cap", {type: "raster", tiles: [url], tileSize: 512, minzoom: 8, maxzoom: 14});
      m.addLayer({id: "cap", type: "raster", source: "cap", paint: {"raster-fade-duration": 0}});
    }, S2(im.item));
    await quieto();
    await espera(800);
    await pg.screenshot({path: `${OUT}/${id}/${im.fecha}.jpg`, type: "jpeg", quality: 88});
    fechas.push(im.fecha);
    console.log(id, im.fecha);
  }
  salida.sitios[id] = {nombre: s.nombre, lugar: s.lugar, ha: s.ha, insomnio: s.insomnio, radar: s.radar, lado: LADO, fechas,
    contorno: await proyectar(anillo), pares: s.pares.map((p) => ({fecha: p.fecha, sitio: p.sitio, anillo: p.anillo}))};
}
fs.writeFileSync(`${RAIZ}video/compartido/casos.json`, JSON.stringify(salida));
await b.close();
console.log("listo");
