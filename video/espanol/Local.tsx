// Video for the local Buenos Aires jury: up to 3 minutes, in Spanish, same style as the international one.
// Voice recorded by the team (a single track, voz-es.json → "pista") with the time of each word (palabras_voz.py):
// each scene and each element is anchored to the word that names it, so if the voice changes it rearranges itself.
// Figures: docs/idea.md, docs/results.md, web/src/data/seed (sitios.json), data/catalogos/basurales (catalog),
// compartido/casos.json (capturas_mapa.mjs) and compartido/web-rects.json (capturas_web.mjs). See guion-es.json.
import React from "react";
import {AbsoluteFill, Easing, Html5Audio, Img, OffthreadVideo, Sequence, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig} from "remotion";
import {ALTO, ANCHO, EQUIPO, FPS, RESULTADOS} from "../compartido/data";
import {C, F} from "../compartido/theme";
import {AvisoIA, Creditos, PinUbicacion, Placeholder, Subtitulos, TituloSeccion} from "../compartido/components/Overlays";
import {MapaAmba, caminoPoligono, cajaNorte3EnAmba} from "../compartido/components/Mapa";
import {EscenaMundo, MUNDO_EN, TextosMundo} from "../ingles/Final";
import {Arbol, Cuadro, OFFSET_Y, Ojo, Poligono, clamp, cxNa, cxS2, cyNa, cyS2, entreno, n3, pasadas, serie, zoomExp} from "../compartido/escenas/Escenas";
import casosJson from "../compartido/casos.json";
import rectsJson from "../compartido/web-rects.json";
import voz from "./voz-es.json";

type Frase = {id: string; archivo: string; inicio: number; duracion: number; texto: string; palabras: [string, number][]};
const VOZ_ES = voz as unknown as {duracion_video: number; pista: string; frases: Frase[]};
export const DURACION_LOCAL = VOZ_ES.duracion_video;
const fr = (id: string) => VOZ_ES.frases.find((x) => x.id === id)!;
const norm = (p: string) => p.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]/g, "");
// second (absolute) at which the voice says the n-th word of the sentence that starts with `palabra`
const en = (id: string, palabra: string, n = 1) => {
  let c = 0;
  for (const [p, t] of fr(id).palabras) if (norm(p).startsWith(norm(palabra)) && ++c === n) return t;
  throw new Error(`No está "${palabra}" en la frase ${id}`);
};
const s = (seg: number) => Math.round(seg * FPS);
const enAlguna = (id: string, palabras: string[], siNo: number) => {
  for (const w of palabras) for (const [p, t] of fr(id).palabras) if (norm(p).startsWith(norm(w))) return t;
  return siNo;
};

type Rect = [number, number, number, number];
type Sitio = {nombre: string; lugar: string; ha: number; insomnio: number; radar: string; lado: number; fechas: string[]; contorno: number[][]; pares: {fecha: string; sitio: number; anillo: number}[]};
const CASOS = casosJson as unknown as {argentina: {ancho: number; alto: number; puntos: number[][]; amba: number[]}; sitios: Record<string, Sitio>};
const RECTS = rectsJson as unknown as {mapa: {lujan: number[]}; lujan: Record<string, Rect>; norte3: Record<string, Rect>; sitios: {csv: Rect; lista: Rect}};

const RADAR_ES: [string, string] = ["Radar", "NASA–ISRO NISAR · ASF DAAC"];
const OPTICO_ES: [string, string] = ["Óptico", "Sentinel-2 · Copernicus · EOX (CC BY-NC-SA)"];
const CLIP_IA = 4.733; // the Higgsfield clip at normal speed: it covers the first sentence
const FOTO_EQUIPO: string | null = "equipo.jpg"; // photo of the six in public/
const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
const fechaEs = (iso: string) => `${Number(iso.slice(8, 10))} ${MESES[Number(iso.slice(5, 7)) - 1]}`;
const FONDO = "radial-gradient(ellipse at 50% 45%, #0d1a26 0%, #05080c 72%)";
const FONDO_AZUL = "radial-gradient(ellipse at 50% 50%, #0f2a3d 0%, #081521 55%, #05080c 100%)";

const Texto: React.FC<{children: React.ReactNode; size?: number; color?: string; style?: React.CSSProperties}> = ({children, size = 30, color = "#fff", style}) => (
  <div style={{fontFamily: F.sans, fontSize: size, color, textShadow: "0 2px 8px rgba(0,0,0,0.9)", ...style}}>{children}</div>
);
const Pill: React.FC<{children: React.ReactNode; color?: string; v?: number; size?: number}> = ({children, color = "rgba(95,192,220,0.55)", v = 1, size = 18}) => (
  <span style={{display: "inline-block", opacity: v, transform: `translateY(${(1 - v) * 12}px)`, fontFamily: F.mono, fontSize: size, color: "#e7f6fb",
    padding: "6px 14px", borderRadius: 999, border: `1px solid ${color}`, background: "rgba(10,25,36,0.85)", whiteSpace: "nowrap"}}>{children}</span>
);
const Mono: React.FC<{children: React.ReactNode; size?: number; color?: string; style?: React.CSSProperties}> = ({children, size = 18, color = "rgba(231,235,241,0.6)", style}) => (
  <div style={{fontFamily: F.mono, fontSize: size, color, ...style}}>{children}</div>
);
// standard entrance of an element from a frame on
const useEntra = () => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  return (desde: number, damping = 15) => spring({frame: f - desde, fps, config: {damping}});
};
const Aparece: React.FC<{v: number; dy?: number; dx?: number; children: React.ReactNode; style?: React.CSSProperties}> = ({v, dy = 18, dx = 0, children, style}) => (
  <div style={{opacity: Math.min(1, v * 1.4), transform: `translate(${(1 - v) * dx}px, ${(1 - v) * dy}px)`, ...style}}>{children}</div>
);
// end of the section title movement: only then the rest comes in (so nothing sits under the title)
const tras = (salida: number) => salida + 20;

/* 1 · AI clip (first sentence) */
const ClipIA: React.FC = () => (
  <AbsoluteFill>
    <OffthreadVideo src={staticFile("clip1-ai.mp4")} muted style={{width: ANCHO, height: ALTO, objectFit: "cover"}} />
    <AbsoluteFill style={{background: "radial-gradient(ellipse at center, rgba(0,0,0,0) 55%, rgba(0,0,0,0.45) 100%)"}} />
    <AvisoIA texto="Imagen generada con IA" />
  </AbsoluteFill>
);

/* 2 · Argentina: the dump sites that do have a public location, and for none of them is it officially known whether it is still active.
   No total figure on screen: the national estimate isn't validated (the voice says "hundreds"). */
const Argentina: React.FC<{t0: number; dur: number}> = ({t0, dur}) => {
  const f = useCurrentFrame();
  const e = useEntra();
  const at = (abs: number) => s(abs - t0);
  const n = s(dur);
  const A = CASOS.argentina;
  const fin = fr("problema").inicio + fr("problema").duracion;
  const tArg = at(enAlguna("problema", ["argentina"], t0 + 0.3));
  // the points appear as soon as the scene starts; with "no existe" it adds that many more are uncatalogued
  const p0 = Math.max(4, tArg + 2), p1 = p0 + s(1.6);
  const duda = e(at(enAlguna("problema", ["existe", "relevamiento"], fin - 4)) - 6, 16);
  const zoom = interpolate(f, [0, n], [1.0, 1.12], clamp);
  return (
    <AbsoluteFill style={{background: C.bg, opacity: interpolate(f, [0, 8], [0, 1], clamp)}}>
      <div style={{position: "absolute", inset: 0, transform: `scale(${zoom})`, transformOrigin: `${A.amba[0]}px ${A.amba[1]}px`}}>
        <Img src={staticFile("casos/argentina.jpg")} style={{width: ANCHO, height: ALTO, filter: "brightness(0.8) saturate(0.9)"}} />
        <svg width={ANCHO} height={ALTO} style={{position: "absolute", inset: 0}}>
          {A.puntos.map(([x, y], k) => {
            const v = e(p0 + ((p1 - p0) * k) / A.puntos.length, 12);
            const latido = 0.5 + 0.5 * Math.sin((f - k * 3) / 7);
            return v > 0.01 ? (
              <g key={k} opacity={Math.min(1, v * 1.5)}>
                <circle cx={x} cy={y} r={9 + latido * 6} fill="none" stroke={`rgba(255,165,61,${0.45 * (1 - duda) + 0.25 * duda})`} strokeWidth={1.5} />
                <circle cx={x} cy={y} r={4.5 * v} fill={C.glow} stroke={C.bg} strokeWidth={1.4} />
              </g>
            ) : null;
          })}
        </svg>
        <div style={{position: "absolute", left: A.amba[0] - 345, top: A.amba[1] + 120, opacity: e(tArg - 4) * 0.9,
          fontFamily: F.display, fontWeight: 700, fontSize: 46, letterSpacing: 12, color: "rgba(255,255,255,0.85)", textShadow: "0 2px 12px rgba(0,0,0,0.9)"}}>ARGENTINA</div>
      </div>
      <AbsoluteFill style={{background: "linear-gradient(270deg, rgba(5,8,12,0.9) 0%, rgba(5,8,12,0.6) 30%, rgba(5,8,12,0) 50%)"}} />
      <div style={{position: "absolute", left: 1240, top: 300, width: 600, display: "grid", gap: 28}}>
        <Aparece v={e(p0)} dx={30} dy={0}>
          <div style={{display: "flex", alignItems: "center", gap: 16}}>
            <svg width={30} height={30}><circle cx={15} cy={15} r={12} fill="none" stroke="rgba(255,165,61,0.5)" strokeWidth={2} /><circle cx={15} cy={15} r={6} fill={C.glow} /></svg>
            <div>
              <Texto size={34} style={{fontFamily: F.display, fontWeight: 700}}>{A.puntos.length} con ubicación pública</Texto>
              <Mono size={17}>en catálogos abiertos · OpenStreetMap · Climate TRACE</Mono>
            </div>
          </div>
        </Aparece>
        <Aparece v={duda} dx={30} dy={0}>
          <div style={{display: "flex", alignItems: "center", gap: 16}}>
            <svg width={30} height={30}><circle cx={15} cy={15} r={11} fill="none" stroke="rgba(231,235,241,0.8)" strokeWidth={1.8} strokeDasharray="3 4" /><text x={15} y={20.5} textAnchor="middle" fontSize={15} fontWeight={700} fill="#fff" fontFamily="sans-serif">?</text></svg>
            <div>
              <Texto size={34} style={{fontFamily: F.display, fontWeight: 700}}>Muchos más, sin catalogar</Texto>
              <Mono size={17}>sin relevamiento formal ni inventario oficial de cuáles siguen activos</Mono>
            </div>
          </div>
        </Aparece>
      </div>
      <Creditos items={[["Imagen", "NASA GIBS · Blue Marble"], ["Puntos", "OpenStreetMap · Climate TRACE"]]} opacidad={interpolate(f, [10, 20], [0, 1], clamp)} />
    </AbsoluteFill>
  );
};

/* Transition: radar pulse that reveals the satellite image */
const Pulso: React.FC<{dur: number}> = ({dur}) => {
  const f = useCurrentFrame();
  const p = interpolate(f, [0, s(dur)], [0, 1], {...clamp, easing: Easing.inOut(Easing.cubic)});
  const cx = ANCHO * cxS2, cy = OFFSET_Y + ANCHO * cyS2;
  return (
    <AbsoluteFill>
      <div style={{position: "absolute", inset: 0, clipPath: `circle(${p * 1400}px at ${cx}px ${cy}px)`}}><Cuadro src="s2-norte3.jpg" escala={1.08} origen={[cxS2, cyS2]} /></div>
      <svg width={ANCHO} height={ALTO} style={{position: "absolute", inset: 0}}>
        {[0, 0.2].map((d, k) => <circle key={k} cx={cx} cy={cy} r={Math.max(0, p - d) * 1400} fill="none" stroke={k ? C.radar : "#bfefff"} strokeWidth={k ? 2 : 6} opacity={p > d ? 1 - (p - d) : 0} />)}
      </svg>
    </AbsoluteFill>
  );
};

/* 3 · Dumpsite + NISAR */
const DumpsiteNisar: React.FC<{t0: number; dur: number}> = ({t0, dur}) => {
  const f = useCurrentFrame();
  const e = useEntra();
  const at = (abs: number) => s(abs - t0);
  const n = s(dur);
  const salida = at(en("dumpsite", "plataforma"));
  const r0 = at(en("dumpsite", "radar")) - 4;
  const radar = interpolate(f, [r0, r0 + 20], [0, 1], {...clamp, easing: Easing.inOut(Easing.quad)});
  const escalaR = interpolate(f, [r0, n], [14 / 6, 1.08], {...clamp, easing: Easing.out(Easing.cubic)});
  const chips: [string, number][] = [["cada 12 días", at(en("dumpsite", "doce"))]];
  const pin = tras(salida) + 4;
  return (
    <AbsoluteFill style={{background: C.bg}}>
      <Cuadro src="s2-norte3.jpg" escala={interpolate(f, [0, r0], [1.08, 1], clamp)} origen={[cxS2, cyS2]} opacidad={1 - radar} />
      <div style={{opacity: radar}}>
        <Cuadro src="nisar-coherencia-amplia.png" escala={escalaR} origen={[cxNa, cyNa]}>
          <Poligono pts={n3.poligono_nisar_amplio as number[][]} relleno="rgba(255,165,61,0.12)" borde={C.glow} grosor={3} brillo={10} />
        </Cuadro>
      </div>
      <div style={{opacity: Math.min(1 - radar, interpolate(f, [pin, pin + 8], [0, 1], clamp))}}>
        <PinUbicacion x={ANCHO * cxS2} y={OFFSET_Y + ANCHO * cyS2 - 30} texto="Norte III · Buenos Aires" delay={pin} />
      </div>
      <div style={{position: "absolute", left: 0, top: 0, width: 1500, height: 640, background: "radial-gradient(1400px 600px at 0% 0%, rgba(5,8,12,0.92) 0%, rgba(5,8,12,0.5) 52%, rgba(5,8,12,0) 100%)", opacity: radar}} />
      <div style={{position: "absolute", left: 48, top: 180, opacity: radar}}>
        <Mono size={20} color={C.glow} style={{letterSpacing: 4}}>NASA–ISRO NISAR</Mono>
        <Texto size={62} style={{fontFamily: F.display, fontWeight: 700, lineHeight: 1, marginTop: 6}}>Lo que ve el radar sobre el basural</Texto>
        <div style={{display: "flex", gap: 26, marginTop: 14, fontFamily: F.sans, fontSize: 24, color: "#fff"}}>
          <span><span style={{display: "inline-block", width: 18, height: 18, borderRadius: 4, background: "#e6f6fb", marginRight: 8, verticalAlign: -2}} />suelo estable</span>
          <span><span style={{display: "inline-block", width: 18, height: 18, borderRadius: 4, background: "#0b1a26", border: "1px solid #5fc0dc", marginRight: 8, verticalAlign: -2}} />suelo que cambia</span>
        </div>
        <div style={{display: "flex", gap: 10, marginTop: 18}}>
          {chips.map(([c, d]) => <Pill key={c} v={e(d - 3, 14)}>{c}</Pill>)}
        </div>
      </div>
      <TituloSeccion titulo="Dumpsite" bajada="Una plataforma que sigue basurales desde el espacio" salida={salida} />
      <Creditos items={[radar < 0.5 ? OPTICO_ES : RADAR_ES]} />
    </AbsoluteFill>
  );
};

/* 4 · Insomnia: the dump site changes, coherence measures it, the index counts it, the map extends it */
const Insomnio: React.FC<{t0: number; dur: number}> = ({t0, dur}) => {
  const f = useCurrentFrame();
  const e = useEntra();
  const at = (abs: number) => s(abs - t0);
  const n = s(dur);
  const salida = 12;
  const aIni = tras(salida);
  const b0 = at(fr("coherencia").inicio), c0 = at(fr("mapa").inicio);
  const porImagen = Math.max(8, Math.floor((b0 - aIni - 8) / serie.imagenes.length));
  const idx = Math.min(serie.imagenes.length - 1, Math.max(0, Math.floor((f - aIni) / porImagen)));
  const fundido = interpolate((f - aIni) - idx * porImagen, [0, 6], [0, 1], clamp);
  const partA = interpolate(f, [aIni - 4, aIni + 6, b0 - 6, b0 + 4], [0, 1, 1, 0], clamp);
  const partB = interpolate(f, [b0, b0 + 8, c0 - 6, c0 + 4], [0, 1, 1, 0], clamp);
  // B · the bars come in with "coherencia"; the eyes, pass by pass, with "cambió más de lo que tiene alrededor"
  const barras = at(en("coherencia", "cuanto")) - 6;
  const ojos0 = at(en("insomnio", "cambio")) - 4, ojos1 = at(en("insomnio", "alrededor")) + 6;
  const paso = (ojos1 - ojos0) / pasadas.length;
  const visibles = Math.floor(interpolate(f, [ojos0, ojos1], [0, pasadas.length], clamp));
  const despiertos = pasadas.slice(0, visibles).filter((p) => p.despierto).length;
  const puntaje = e(at(en("insomnio", "indice")) - 4, 14);
  const c = cajaNorte3EnAmba();
  const ease = Easing.inOut(Easing.cubic);
  const vista = {cx: interpolate(f, [c0, c0 + 50], [c.cx, 0.55], {...clamp, easing: ease}), cy: interpolate(f, [c0, c0 + 50], [c.cy, 0.5], {...clamp, easing: ease}),
    zoom: zoomExp(f, [c0, c0 + 50], 1 / c.ancho, 1.25, Easing.inOut(Easing.poly(4))) * interpolate(f, [c0 + 50, n], [1, 1.08], clamp)};
  const mapa = interpolate(f, [c0 - 4, c0 + 8], [0, 1], clamp);
  const lado = 600, tile = 150;
  return (
    <AbsoluteFill style={{background: FONDO}}>
      <AbsoluteFill style={{opacity: partA}}>
        <div style={{position: "absolute", left: 300, top: 170, width: lado, height: lado, borderRadius: 18, overflow: "hidden", boxShadow: "0 30px 90px rgba(0,0,0,0.7)", border: "1px solid rgba(255,255,255,0.18)"}}>
          {idx > 0 && <Img src={staticFile(serie.imagenes[idx - 1].archivo)} style={{position: "absolute", inset: 0, width: "100%", height: "100%"}} />}
          <Img src={staticFile(serie.imagenes[idx].archivo)} style={{position: "absolute", inset: 0, width: "100%", height: "100%", opacity: fundido}} />
          <Poligono pts={serie.poligono} relleno="transparent" borde="rgba(255,165,61,0.9)" grosor={2.5} />
          <Texto size={48} style={{position: "absolute", left: 18, top: 14, fontFamily: F.display, fontWeight: 700}}>{fechaEs(serie.imagenes[idx].fecha)}</Texto>
        </div>
        <div style={{position: "absolute", left: 980, top: 190, width: 640}}>
          <Texto size={44} style={{fontFamily: F.display, fontWeight: 700}}><span style={{color: C.glow}}>Norte III,</span> {serie.imagenes.length} fechas de Sentinel-2</Texto>
          <Texto size={26} color="rgba(231,235,241,0.75)" style={{marginTop: 6}}>junio a octubre de 2026</Texto>
          <div style={{display: "grid", gridTemplateColumns: "repeat(3, 150px)", gap: 12, marginTop: 24}}>
            {serie.imagenes.map((im, k) => (
              <div key={im.fecha} style={{width: 150, height: 150, borderRadius: 10, overflow: "hidden", outline: k === idx ? `3px solid ${C.glow}` : "1px solid rgba(255,255,255,0.2)", opacity: k <= idx ? 1 : 0.35}}>
                <Img src={staticFile(im.archivo)} style={{width: "100%", height: "100%"}} />
              </div>
            ))}
          </div>
        </div>
      </AbsoluteFill>
      <AbsoluteFill style={{opacity: partB}}>
        <div style={{position: "absolute", left: 0, right: 0, top: 150, textAlign: "center"}}>
          <Texto size={58} style={{fontFamily: F.display, fontWeight: 700}}>Coherencia: cuánto se parece un lugar entre dos pasadas</Texto>
          <Texto size={28} color="rgba(231,235,241,0.8)" style={{marginTop: 6}}>1 · nada cambió &nbsp;&nbsp;→&nbsp;&nbsp; 0 · cambió todo</Texto>
        </div>
        <div style={{position: "absolute", top: 300, left: (ANCHO - pasadas.length * (tile + 16) + 16) / 2, display: "flex", gap: 16}}>
          {pasadas.map((p, k) => {
            const v = e(barras + k * 3, 13);
            const ojo = interpolate(f, [ojos0 + k * paso, ojos0 + k * paso + 6], [0, 1], clamp);
            const H = 120;
            return (
              <div key={p.fecha} style={{width: tile, height: 270, borderRadius: 14, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "flex-end", gap: 8, paddingBottom: 12,
                opacity: v, transform: `translateY(${(1 - v) * 40}px)`, background: `rgba(255,165,61,${0.04 + 0.1 * ojo})`, border: `2px solid rgba(255,165,61,${0.25 + 0.5 * ojo})`}}>
                <div style={{opacity: ojo, transform: `scale(${0.6 + 0.4 * ojo})`}}><Ojo despierto={p.despierto} tam={64} /></div>
                <svg width={90} height={H + 4}>
                  <rect x={14} y={H - p.anillo * H * v} width={24} height={p.anillo * H * v} rx={3} fill="rgba(95,192,220,0.75)" />
                  <rect x={52} y={H - p.sitio * H * v} width={24} height={p.sitio * H * v} rx={3} fill={C.glow} />
                </svg>
                <div style={{fontFamily: F.sans, fontWeight: 600, fontSize: 22, color: "#fff"}}>{fechaEs(p.fecha)}</div>
              </div>
            );
          })}
        </div>
        <div style={{position: "absolute", left: 0, right: 0, top: 590, display: "flex", justifyContent: "center", gap: 30, fontFamily: F.sans, fontSize: 22, color: "rgba(231,235,241,0.85)", opacity: e(barras + 10)}}>
          <span><span style={{display: "inline-block", width: 14, height: 14, background: "rgba(95,192,220,0.75)", borderRadius: 3, marginRight: 6}} />su entorno</span>
          <span><span style={{display: "inline-block", width: 14, height: 14, background: C.glow, borderRadius: 3, marginRight: 6}} />el basural: siempre más bajo</span>
        </div>
        <div style={{position: "absolute", left: 0, right: 0, top: 640, display: "flex", justifyContent: "center", alignItems: "center", gap: 80}}>
          <Texto size={38} style={{opacity: visibles > 0 ? 1 : 0}}>cambió más que su entorno en <b style={{color: C.glow, fontSize: 60}}>{despiertos}</b> de {pasadas.length} pasadas</Texto>
          <div style={{opacity: puntaje, transform: `scale(${0.7 + 0.3 * puntaje})`, textAlign: "center"}}>
            <div style={{fontFamily: F.display, fontWeight: 700, fontSize: 120, lineHeight: 0.9, color: C.glow, textShadow: "0 0 40px rgba(255,165,61,0.5)"}}>{Math.round((n3.insomnio as number) * 100)} %</div>
            <Texto size={24} color="rgba(231,235,241,0.9)">índice de insomnio · Norte III</Texto>
          </div>
        </div>
      </AbsoluteFill>
      {mapa > 0 && (
        <AbsoluteFill style={{opacity: mapa}}>
          <MapaAmba vista={vista}>{(px) => <path d={caminoPoligono(n3.poligono_amba as number[][], px)} fill="none" stroke={C.glow} strokeWidth={2} />}</MapaAmba>
          <div style={{position: "absolute", left: 0, top: 0, width: 1500, height: 600, background: "radial-gradient(1400px 560px at 0% 0%, rgba(5,8,12,0.9) 0%, rgba(5,8,12,0.4) 55%, rgba(5,8,12,0) 100%)"}} />
          <div style={{position: "absolute", left: 48, top: 180, opacity: interpolate(f, [Math.max(c0 + 18, at(en("mapa", "ejemplo")) - 8), Math.max(c0 + 30, at(en("mapa", "ejemplo")) + 4)], [0, 1], clamp)}}>
            <Mono size={20} color={C.glow} style={{letterSpacing: 4}}>EJEMPLO</Mono>
            <Texto size={58} style={{fontFamily: F.display, fontWeight: 700}}>El Gran Buenos Aires, píxel por píxel</Texto>
            <div style={{display: "flex", gap: 10, marginTop: 14}}>
              {([["sin agua (JRC)", "agua"], ["sin rutas", "rutas"], ["sin cultivos", "cultivos"]] as const).map(([c, w]) => (
                <Pill key={c} v={e(at(en("mapa", w)) - 3, 14)}>{c}</Pill>
              ))}
            </div>
          </div>
        </AbsoluteFill>
      )}
      <TituloSeccion titulo="Insomnio" bajada="Cuánto cambia el suelo, pasada tras pasada" salida={salida} />
      <Creditos items={[f < b0 ? OPTICO_ES : RADAR_ES]} />
    </AbsoluteFill>
  );
};

/* A site in Sentinel-2, date by date, with its outline */
const PanelSitio: React.FC<{id: string; f: number; desde: number; dibujo: number; color: string; cada?: number}> = ({id, f, desde, dibujo, color, cada = 14}) => {
  const x = CASOS.sitios[id];
  const k = Math.max(0, Math.floor((f - desde) / cada)) % x.fechas.length;
  const d = x.contorno.map(([a, b], i) => `${i ? "L" : "M"}${a},${b}`).join(" ") + " Z";
  return (
    <div style={{position: "absolute", inset: 0, borderRadius: 16, overflow: "hidden", boxShadow: "0 30px 90px rgba(0,0,0,0.7)", border: "1px solid rgba(255,255,255,0.2)"}}>
      {x.fechas.map((fe, i) => <Img key={fe} src={staticFile(`casos/${id}/${fe}.jpg`)} style={{position: "absolute", inset: 0, width: "100%", height: "100%", opacity: i === k ? 1 : 0}} />)}
      <svg viewBox={`0 0 ${x.lado} ${x.lado}`} style={{position: "absolute", inset: 0, width: "100%", height: "100%"}}>
        <path d={d} fill={color} fillOpacity={0.12 * dibujo} stroke={color} strokeWidth={4} strokeLinejoin="round" pathLength={1} strokeDasharray="1 1" strokeDashoffset={1 - dibujo}
          style={{filter: `drop-shadow(0 0 8px ${color})`}} />
      </svg>
      <div style={{position: "absolute", left: 14, top: 10, fontFamily: F.display, fontWeight: 700, fontSize: 36, color: "#fff", textShadow: "0 2px 8px #000"}}>{fechaEs(x.fechas[k])}</div>
    </div>
  );
};
// The radar's 15 comparisons: each cell lights up on its turn
const Comparaciones: React.FC<{f: number; desde: number; hasta: number; cambio: boolean; ancho: number}> = ({f, desde, hasta, cambio, ancho}) => {
  const n = 15, gap = 6, w = (ancho - gap * (n - 1)) / n;
  const color = cambio ? C.glow : C.radar;
  return (
    <div style={{display: "flex", gap}}>
      {Array.from({length: n}).map((_, k) => {
        const v = interpolate(f, [desde + ((hasta - desde) * k) / n, desde + ((hasta - desde) * k) / n + 5], [0, 1], clamp);
        return (
          <div key={k} style={{width: w, height: 40, borderRadius: 7, display: "flex", alignItems: "center", justifyContent: "center",
            border: `1.5px solid ${v > 0 ? color : "rgba(231,235,241,0.25)"}`, background: v > 0 ? `${color}${cambio ? "33" : "22"}` : "rgba(10,18,26,0.6)"}}>
            <div style={{opacity: v, transform: `scale(${0.5 + 0.5 * v})`}}><Ojo despierto={cambio} tam={w - 8} /></div>
          </div>
        );
      })}
    </div>
  );
};

/* 5 · Luján (closed, quiet) against González Catán (changes in every pair) */
const Casos: React.FC<{t0: number; dur: number}> = ({t0}) => {
  const f = useCurrentFrame();
  const e = useEntra();
  const at = (abs: number) => s(abs - t0);
  const salida = 6;
  const panelL = tras(salida);
  const dos = at(fr("norte3").inicio); // González Catán comes in
  const lado = 520, y = 200;
  const xL = 330, xC = 1070;
  const lCells: [number, number] = [at(en("lujan", "radar")) - 2, at(en("lujan", "comparaciones")) + 10];
  const cCells: [number, number] = [at(en("norte3", "catan")) - 4, at(en("norte3", "todas")) + 4];
  const cuentaL = Math.round(interpolate(f, lCells, [0, 15], clamp));
  const cuentaC = Math.round(interpolate(f, cCells, [0, 15], clamp));
  const vC = e(dos + 4, 16);
  const info = 1 - interpolate(f, [dos - 6, dos + 6], [0, 1], clamp);
  return (
    <AbsoluteFill style={{background: FONDO}}>
      {/* Luján */}
      <Aparece v={e(panelL - 2)} style={{position: "absolute", left: xL, top: 140, width: lado, display: "flex", alignItems: "baseline", justifyContent: "space-between"}}>
        <Texto size={42} style={{fontFamily: F.display, fontWeight: 700, color: C.radar}}>Basural de Luján</Texto>
        <Mono size={20} color={C.radar}>insomnio {Math.round(CASOS.sitios.lujan.insomnio * 100)} %</Mono>
      </Aparece>
      <div style={{position: "absolute", left: xL, top: y, width: lado, height: lado, opacity: e(panelL), transform: `scale(${0.94 + 0.06 * e(panelL)})`}}>
        <PanelSitio id="lujan" f={Math.min(f, dos)} desde={panelL} dibujo={interpolate(f, [panelL + 6, panelL + 36], [0, 1], {...clamp, easing: Easing.inOut(Easing.cubic)})} color={C.radar} cada={10} />
      </div>
      <div style={{position: "absolute", left: xL, top: y + lado + 20, opacity: f >= lCells[0] - 6 ? 1 : 0}}>
        <Comparaciones f={f} desde={lCells[0]} hasta={lCells[1]} cambio={false} ancho={lado} />
        <Texto size={30} style={{marginTop: 12}}>quieto en <b style={{color: C.radar}}>{cuentaL}</b> de 15 comparaciones</Texto>
      </div>
      {/* the Luján explanation takes Catán's place until Catán comes in */}
      <div style={{position: "absolute", left: xC, top: y + 20, width: 640, opacity: info}}>
        <Aparece v={e(at(en("lujan", "cerro")) - 4)}>
          <Mono size={20} color={C.radar} style={{letterSpacing: 3}}>ANUNCIO OFICIAL</Mono>
          <Texto size={50} style={{fontFamily: F.display, fontWeight: 700, marginTop: 4}}>Cerrado el 1 de julio de 2026</Texto>
        </Aparece>
        <Aparece v={e(lCells[0])} style={{marginTop: 40}}>
          <Mono size={20} color={C.radar} style={{letterSpacing: 3}}>RADAR NISAR · JULIO A OCTUBRE</Mono>
          <Texto size={50} style={{fontFamily: F.display, fontWeight: 700, marginTop: 4}}>Ninguna pasada lo encuentra cambiado</Texto>
        </Aparece>
      </div>
      {/* González Catán */}
      <div style={{opacity: vC, transform: `translateX(${(1 - vC) * 80}px)`}}>
        <div style={{position: "absolute", left: xC, top: 140, width: lado, display: "flex", alignItems: "baseline", justifyContent: "space-between"}}>
          <Texto size={42} style={{fontFamily: F.display, fontWeight: 700, color: C.glow}}>González Catán</Texto>
          <Mono size={20} color={C.glow}>insomnio {Math.round(CASOS.sitios["gonzalez-catan"].insomnio * 100)} %</Mono>
        </div>
        <div style={{position: "absolute", left: xC, top: y, width: lado, height: lado}}>
          <PanelSitio id="gonzalez-catan" f={f} desde={dos} dibujo={interpolate(f, [dos + 8, dos + 34], [0, 1], {...clamp, easing: Easing.inOut(Easing.cubic)})} color={C.glow} cada={10} />
        </div>
        <div style={{position: "absolute", left: xC, top: y + lado + 20, opacity: f >= cCells[0] - 6 ? 1 : 0}}>
          <Comparaciones f={f} desde={cCells[0]} hasta={cCells[1]} cambio ancho={lado} />
          <Texto size={30} style={{marginTop: 12}}>cambió en <b style={{color: C.glow}}>{cuentaC}</b> de 15 comparaciones</Texto>
        </div>
      </div>
      <TituloSeccion titulo="Casos reales" bajada="Mismo radar, dos historias" salida={salida} />
      <Creditos items={[["Óptico", "Sentinel-2 L2A · Copernicus, vía Planetary Computer"], ["Contornos", "OpenStreetMap"], RADAR_ES]} opacidad={e(panelL)} />
    </AbsoluteFill>
  );
};

/* 6 · The data: the radar says what changes, the catalog teaches what it is */
const FUENTES_CATALOGO: [string, string, string][] = [
  ["OpenStreetMap · Overture", "polígonos de rellenos y basurales", "openstreetmap"],
  ["Climate TRACE", "emisiones por sitio", "climate"],
  ["EPA LMOP", "agencia ambiental de EE. UU.", "agencia"],
  ["NASA EMIT", "plumas de metano", "plumas"],
];
const Datos: React.FC<{t0: number; dur: number}> = ({t0}) => {
  const f = useCurrentFrame();
  const e = useEntra();
  const at = (abs: number) => s(abs - t0);
  const salida = 8;
  const a0 = tras(salida);
  const b0 = at(en("catalogo", "para"));
  const partA = interpolate(f, [a0 - 4, a0 + 6, b0 - 8, b0 + 2], [0, 1, 1, 0], clamp);
  const partB = interpolate(f, [b0, b0 + 10], [0, 1], clamp);
  const cuenta = Math.round(entreno.total_catalogo * interpolate(f, [at(en("catalogo", "catalogo")), at(en("catalogo", "mundo")) + 10], [0, 1], {...clamp, easing: Easing.out(Easing.cubic)}));
  const ch = 112, cols = 7, gap = 8, yG = 222;
  const gridW = cols * ch + (cols - 1) * gap;
  const x0 = (ANCHO - (gridW + 90 + 640)) / 2;
  const xR = x0 + gridW + 90;
  const sumamos = at(en("catalogo", "sumamos")) - 4;
  const parecidos = [{t: "canteras", img: "chip-tres-febrero.jpg", w: "canteras"}, {t: "aeródromos", img: "chip-el-palomar.jpg", w: "aerodromos"}];
  return (
    <AbsoluteFill style={{background: FONDO}}>
      {/* A · a point that changes: what is it? */}
      <AbsoluteFill style={{opacity: partA}}>
        <div style={{position: "absolute", left: 430, top: 215, width: 560, height: 560}}>
          <PanelSitio id="gonzalez-catan" f={f} desde={a0} dibujo={interpolate(f, [a0, a0 + 24], [0, 1], clamp)} color={C.glow} cada={10} />
        </div>
        <div style={{position: "absolute", left: 1070, top: 340, display: "grid", gap: 40}}>
          <Aparece v={e(at(en("catalogo", "cambia")) - 6)} dx={-24} dy={0}>
            <Texto size={30} color="rgba(231,235,241,0.7)">¿Cambia en el tiempo?</Texto>
            <Texto size={54} style={{fontFamily: F.display, fontWeight: 700, color: C.radar}}>Sí · lo dice el radar</Texto>
          </Aparece>
          <Aparece v={e(at(en("catalogo", "que")) - 4)} dx={-24} dy={0}>
            <Texto size={30} color="rgba(231,235,241,0.7)">¿Qué es?</Texto>
            <Texto size={54} style={{fontFamily: F.display, fontWeight: 700, color: C.glow}}>El radar no lo sabe</Texto>
          </Aparece>
        </div>
      </AbsoluteFill>
      {/* B · the catalog */}
      <AbsoluteFill style={{opacity: partB}}>
        <div style={{position: "absolute", left: x0, top: yG, display: "grid", gridTemplateColumns: `repeat(${cols}, ${ch}px)`, gap}}>
          {entreno.muestras.slice(0, 28).map((m, k) => {
            const v = e(b0 + 4 + (k % 7) * 1.5 + Math.floor(k / 7) * 2, 14);
            return (
              <div key={m.archivo} style={{width: ch, height: ch, borderRadius: 9, overflow: "hidden", opacity: v, transform: `scale(${0.6 + 0.4 * v})`, position: "relative", border: "1px solid rgba(255,255,255,0.25)"}}>
                <Img src={staticFile(m.archivo)} style={{width: "100%", height: "100%"}} />
                <div style={{position: "absolute", left: 5, bottom: 3, fontFamily: F.mono, fontSize: 12, color: "#fff", textShadow: "0 1px 3px #000"}}>{m.pais}</div>
              </div>
            );
          })}
        </div>
        <div style={{position: "absolute", left: x0, top: yG + 4 * ch + 3 * gap + 30, opacity: e(sumamos)}}>
          <Texto size={28}>Y lugares que <b style={{color: C.radar}}>también cambian seguido</b>:</Texto>
          <div style={{display: "flex", gap: 18, marginTop: 12}}>
            {parecidos.map((p) => {
              const v = e(at(en("catalogo", p.w)) - 6);
              return (
                <Aparece key={p.t} v={v}>
                  <div style={{display: "flex", alignItems: "center", gap: 12, padding: "8px 20px 8px 8px", borderRadius: 14, border: "1px solid rgba(95,192,220,0.5)", background: "rgba(10,25,36,0.85)"}}>
                    <Img src={staticFile(p.img)} style={{width: 64, height: 64, borderRadius: 8}} /><Texto size={28}>{p.t}</Texto>
                  </div>
                </Aparece>
              );
            })}
          </div>
        </div>
        <div style={{position: "absolute", left: xR, top: yG + 20, width: 640}}>
          <div style={{fontFamily: F.display, fontWeight: 700, fontSize: 130, lineHeight: 0.9, color: C.glow, textShadow: "0 0 36px rgba(255,165,61,0.45)"}}>{cuenta.toLocaleString("es-AR")}</div>
          <Texto size={34}>basurales mapeados en todo el mundo</Texto>
          <div style={{display: "grid", gap: 14, marginTop: 34}}>
            {FUENTES_CATALOGO.map(([a, b, w]) => (
              <Aparece key={a} v={e(at(en("catalogo", w)) - 4)} dx={30} dy={0}>
                <div style={{display: "flex", alignItems: "center", gap: 14}}>
                  <Pill color="rgba(255,165,61,0.7)" size={19}>{a}</Pill><Texto size={22} color="rgba(231,235,241,0.75)">{b}</Texto>
                </div>
              </Aparece>
            ))}
          </div>
        </div>
      </AbsoluteFill>
      <TituloSeccion titulo="Los datos" bajada="El radar dice qué cambia, no qué es" salida={salida} />
      <Creditos items={f < b0 ? [["Óptico", "Sentinel-2 · Copernicus · EOX (CC BY-NC-SA)"]] : [["Catálogo", "OSM · Overture · Climate TRACE · EPA · NASA EMIT"]]} opacidad={e(a0)} />
    </AbsoluteFill>
  );
};

/* 7 · LightGBM: like in the English video, the image goes into the model and lands on "Basural" or "Otra cosa" */
const VARIABLES_ES: [string, string][] = [
  ["coherencia", "radar"], ["eco de radar", "radar"], ["infrarrojo · SWIR", "sentinel"], ["vegetación · NDVI", "vegetacion"],
  ["suelo desnudo · BSI", "suelo"], ["agua · NDWI", "agua"], ["forma", "forma"], ["tamaño", "forma"], ["entorno", "forma"],
];
const EJEMPLOS_ES = [
  {id: "norte3-disp", det: "clasificado como basural por el modelo", ok: true},
  {id: "el-palomar", det: "un aeródromo", ok: false},
  {id: "tres-febrero", det: "una cantera", ok: false},
];
const Modelo: React.FC<{t0: number; dur: number}> = ({t0, dur}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const e = useEntra();
  const at = (abs: number) => s(abs - t0);
  const n = s(dur);
  const salida = 22;
  const base = tras(salida);
  const cajaW = 720, cajaH = 400, cajaY = 290, trayW = 500;
  const cajaX = (ANCHO - (cajaW + 90 + trayW)) / 2;
  const salX = cajaX + cajaW + 90;
  const arboles0 = at(en("modelo", "cientos")) - 4;
  const corrige0 = at(en("modelo", "cada")), corrige1 = at(en("modelo", "anterior")) + 10;
  const activo = f >= corrige0 && f < corrige1 ? Math.floor(interpolate(f, [corrige0, corrige1], [0, 7], clamp)) : -1;
  const vars0 = at(en("modelo", "veintinueve")) - 4;
  const clasifica = at(en("modelo", "clasifica")) - 6;
  const intervalo = 11;
  const caja = e(base, 16);
  // on entry, the catalog images fly into the box: that's what it trains with
  const vuelo = interpolate(f, [base + 4, base + 30], [0, 1], {...clamp, easing: Easing.in(Easing.cubic)});
  return (
    <AbsoluteFill style={{background: FONDO_AZUL}}>
      {vuelo > 0 && vuelo < 1 && entreno.muestras.slice(0, 12).map((m, k) => {
        const x0 = -140 + (k % 4) * 30, y0 = 220 + k * 48;
        const x = x0 + (cajaX + cajaW / 2 - x0) * vuelo, y = y0 + (cajaY + cajaH / 2 - y0) * vuelo;
        return <Img key={m.archivo} src={staticFile(m.archivo)} style={{position: "absolute", left: x - 45, top: y - 45, width: 90, height: 90, borderRadius: 10, opacity: 1 - vuelo * 0.8, transform: `scale(${1 - vuelo * 0.7})`, border: "1px solid rgba(255,255,255,0.3)"}} />;
      })}
      <div style={{position: "absolute", left: cajaX, top: cajaY, width: cajaW, height: cajaH, borderRadius: 22, border: "2px solid rgba(191,239,255,0.55)", opacity: caja, transform: `scale(${0.95 + 0.05 * caja})`,
        background: "linear-gradient(160deg, rgba(95,192,220,0.18), rgba(10,20,30,0.88))", boxShadow: "0 0 60px rgba(95,192,220,0.28)"}}>
        <div style={{position: "absolute", left: 26, top: 16, fontFamily: F.display, fontWeight: 700, fontSize: 54, color: "#fff"}}>LightGBM</div>
        <Mono size={16} color="rgba(191,239,255,0.8)" style={{position: "absolute", right: 26, top: 34}}>árboles de decisión con boosting</Mono>
        <div style={{position: "absolute", left: 26, right: 26, top: 96}}>
          <Mono size={17} color={C.glow} style={{letterSpacing: 2, opacity: e(vars0)}}>29 VARIABLES POR MANCHA</Mono>
          <div style={{display: "flex", flexWrap: "wrap", gap: 8, marginTop: 10}}>
            {VARIABLES_ES.map(([x, w], k) => <Pill key={x} size={16} v={e(Math.max(vars0, at(en("modelo", w))) - 4 + (k % 2) * 3, 14)}>{x}</Pill>)}
            <Pill size={16} v={e(at(en("modelo", "forma")) + 6, 14)}>…</Pill>
          </div>
        </div>
        <div style={{position: "absolute", left: 26, right: 26, top: 268, display: "flex", alignItems: "center", gap: 14}}>
          {Array.from({length: 7}).map((_, k) => (
            <Arbol key={k} v={e(arboles0 + k * 4, 14)} color={k % 3 === 0 ? C.glow : "#5fc0dc"} activo={activo === k || (activo < 0 && f > corrige1 && Math.floor(f / 6) % 7 === k)} />
          ))}
          <span style={{fontFamily: F.mono, fontSize: 22, color: "#fff", opacity: e(arboles0 + 30)}}>… cientos</span>
        </div>
      </div>
      {/* the two outputs */}
      <AbsoluteFill style={{opacity: interpolate(f, [clasifica - 10, clasifica], [0, 1], clamp)}}>
        {[{t: "Basural", c: C.glow, y: cajaY}, {t: "Otra cosa", c: C.radar, y: cajaY + 210}].map((x) => (
          <div key={x.t} style={{position: "absolute", left: salX, top: x.y, width: trayW, height: 190, borderRadius: 16, border: `2px dashed ${x.c}`, background: "rgba(5,8,12,0.4)"}}>
            <div style={{position: "absolute", left: 18, top: 8, fontFamily: F.display, fontWeight: 700, fontSize: 38, color: x.c}}>{x.t}</div>
          </div>
        ))}
        <svg width={ANCHO} height={ALTO} style={{position: "absolute", inset: 0}}>
          <line x1={cajaX + cajaW} y1={cajaY + cajaH / 2} x2={salX} y2={cajaY + 95} stroke="rgba(255,165,61,0.6)" strokeWidth={3} />
          <line x1={cajaX + cajaW} y1={cajaY + cajaH / 2} x2={salX} y2={cajaY + 305} stroke="rgba(95,192,220,0.6)" strokeWidth={3} />
        </svg>
      </AbsoluteFill>
      {EJEMPLOS_ES.map((x, k) => {
        const inicio = clasifica - 14 + k * intervalo;
        const entra = spring({frame: f - inicio, fps, config: {damping: 16}});
        const cruza = interpolate(f, [inicio + 10, inicio + 22], [0, 1], {...clamp, easing: Easing.in(Easing.quad)});
        const sale = spring({frame: f - (inicio + 22), fps, config: {damping: 14}});
        const yIn = cajaY + 80 + k * 120;
        const xChip = interpolate(entra, [0, 1], [-200, cajaX - 100]) + cruza * 180;
        const otros = EJEMPLOS_ES.filter((y) => y.ok === x.ok).indexOf(x);
        return (
          <React.Fragment key={x.id}>
            {cruza < 1 && f >= inicio - 2 && (
              <div style={{position: "absolute", left: xChip - 60, top: yIn - 60, width: 120, height: 120, opacity: 1 - cruza, transform: `scale(${1 - cruza * 0.6})`,
                borderRadius: 12, overflow: "hidden", border: "2px solid rgba(255,255,255,0.4)", boxShadow: "0 10px 30px rgba(0,0,0,0.6)"}}>
                <Img src={staticFile(`chip-${x.id}.jpg`)} style={{width: "100%", height: "100%"}} />
              </div>
            )}
            {sale > 0.01 && (
              <div style={{position: "absolute", left: salX + 20 + otros * 240, top: (x.ok ? cajaY : cajaY + 210) + 64, display: "flex", alignItems: "center", gap: 12, opacity: sale, transform: `translateX(${(1 - sale) * -60}px)`}}>
                <Img src={staticFile(`chip-${x.id}.jpg`)} style={{width: 100, height: 100, borderRadius: 10, flexShrink: 0, border: `3px solid ${x.ok ? C.glow : "rgba(191,239,255,0.6)"}`, boxShadow: x.ok ? "0 0 26px rgba(255,165,61,0.55)" : undefined}} />
                <Texto size={19} color="rgba(231,235,241,0.85)" style={{width: x.ok ? 300 : 110}}>{x.det}</Texto>
              </div>
            )}
          </React.Fragment>
        );
      })}
      <TituloSeccion titulo="LightGBM" bajada="¿Basural u otra cosa?" salida={salida} />
      <Creditos items={[["Entrenamiento", "OSM · Climate TRACE · EPA · NASA EMIT"], OPTICO_ES, RADAR_ES]} opacidad={interpolate(f, [base, base + 10, n - 6, n], [0, 1, 1, 0], clamp)} />
    </AbsoluteFill>
  );
};

/* 8 · Results: the same world map as the international video (ingles/Final.tsx), tied to the voice:
   known catalog → regions run ("29 regiones") → possible new ("encontró 183") → the caveat */
const Resultados: React.FC<{t0: number; dur: number}> = ({t0, dur}) => {
  const at = (abs: number) => s(abs - t0);
  const salida = 14;
  const tx: TextosMundo = {
    ...MUNDO_EN,
    catalogo: (n) => `${n} basurales en catálogos públicos`, regiones: (n) => `${n} regiones corridas hasta ahora`,
    nuevos: ["posibles basurales nuevos,", "en ningún catálogo público"], nota: ["Clasificados como basural por el modelo · sin verificar en terreno.", "Falta correrlo en el resto del mundo."],
    titulo: "Resultados", bajada: "La Argentina y ciudades del mundo",
    cred: [["Imagen", "NASA GIBS · Blue Marble"], ["Basurales conocidos", "OpenStreetMap · Climate TRACE · EPA · NASA EMIT"]],
    locale: "es-AR", salida,
    t: {catalogo: tras(salida), regiones: at(en("argentina", "regiones")) - 8, nuevos: at(en("argentina", "encontro")) - 2, nota: at(en("argentina", "catalogo")) + 10},
  };
  return <EscenaMundo dur={dur} tx={tx} />;
};

/* 9 · The web, in a normal browser window, without crops */
const W_NAV = 1260, ESC = W_NAV / 1920, H_NAV = 1080 * ESC, X_NAV = (ANCHO - W_NAV) / 2, Y_NAV = 100, BARRA = 40;
const FONDO_WEB = "radial-gradient(ellipse at 50% 45%, #2a4258 0%, #142332 55%, #080e15 100%)";
const Resalte: React.FC<{r: Rect; v: number; pad?: number}> = ({r, v, pad = 8}) => (
  <div style={{position: "absolute", left: X_NAV + r[0] * ESC - pad, top: Y_NAV + BARRA + r[1] * ESC - pad, width: r[2] * ESC + 2 * pad, height: r[3] * ESC + 2 * pad,
    borderRadius: 12, border: `3px solid ${C.glow}`, boxShadow: `0 0 0 4000px rgba(5,8,12,${0.35 * v}), 0 0 30px ${C.glow}aa`, opacity: v, transform: `scale(${1.04 - 0.04 * v})`}} />
);
const Web: React.FC<{t0: number; dur: number}> = ({t0}) => {
  const f = useCurrentFrame();
  const e = useEntra();
  const at = (abs: number) => s(abs - t0);
  const salida = at(en("web", "web")) - 8;
  const nav = tras(salida);
  const clic = at(en("ficha", "lujan"));
  const tN3 = at(en("norte3_web", "norte")) - 4;
  const tLista = at(en("lista", "armamos")) - 4;
  const pasos: {img: string; desde: number}[] = [
    {img: "web/es-mapa.png", desde: 0},
    {img: "web/es-ficha-lujan.png", desde: clic + 4},
    {img: "web/es-ficha-norte3.png", desde: tN3},
    {img: "web/es-sitios.png", desde: tLista},
  ];
  const k = pasos.reduce((acc, p, i) => (f >= p.desde ? i : acc), 0);
  const fade = interpolate(f - pasos[k].desde, [0, 8], [0, 1], clamp);
  const vNav = e(nav, 18);
  // highlights: [rect, from, to]
  const R = RECTS;
  const resaltes: [Rect, number, number][] = [
    [[0, 0, 1500, 1080], at(en("ficha", "imagen")) - 2, at(en("ficha", "radar")) - 6],
    [R.lujan.crece, at(en("ficha", "radar")) - 4, at(fr("lujan_web").inicio)],
    [R.lujan.tag, at(en("lujan_web", "coinciden")) - 4, at(en("lujan_web", "radar")) - 4],
    [R.lujan.kpis, at(en("lujan_web", "radar")) - 4, tN3],
    [R.norte3.crece, at(en("norte3_web", "radar")) - 4, tLista],
    [R.sitios.lista, at(en("lista", "todos")) - 4, at(en("lista", "descargar")) - 6],
    [R.sitios.csv, at(en("lista", "descargar")) - 4, at(fr("lista").inicio + fr("lista").duracion) + 10],
  ];
  // the cursor goes to Luján and clicks
  const [lx, ly] = R.mapa.lujan;
  const c0 = at(en("ficha", "clic")) - 10;
  const mov = interpolate(f, [c0, clic - 4], [0, 1], {...clamp, easing: Easing.inOut(Easing.cubic)});
  const cx = X_NAV + interpolate(mov, [0, 1], [1300, lx]) * ESC, cy = Y_NAV + BARRA + interpolate(mov, [0, 1], [300, ly]) * ESC;
  const onda = interpolate(f, [clic - 4, clic + 10], [0, 1], clamp);
  return (
    <AbsoluteFill style={{background: FONDO_WEB}}>
      <div style={{position: "absolute", left: X_NAV, top: Y_NAV, width: W_NAV, height: H_NAV + BARRA, borderRadius: 14, overflow: "hidden",
        boxShadow: "0 30px 90px rgba(0,0,0,0.55), 0 0 0 1.5px rgba(255,255,255,0.35)", opacity: vNav, transform: `translateY(${(1 - vNav) * 60}px)`}}>
        <div style={{height: BARRA, background: "#1a222e", display: "flex", alignItems: "center", gap: 9, padding: "0 16px"}}>
          {["#ff5f57", "#febc2e", "#28c840"].map((c) => <span key={c} style={{width: 13, height: 13, borderRadius: 7, background: c}} />)}
          <span style={{marginLeft: 18, width: 480, height: 26, borderRadius: 13, background: "#0e141d", color: "#aab4c2", fontFamily: F.mono, fontSize: 15, display: "flex", alignItems: "center", paddingLeft: 14}}>{RESULTADOS.url}</span>
        </div>
        <div style={{position: "relative", width: W_NAV, height: H_NAV}}>
          {k > 0 && <Img src={staticFile(pasos[k - 1].img)} style={{position: "absolute", inset: 0, width: W_NAV, height: H_NAV}} />}
          <Img src={staticFile(pasos[k].img)} style={{position: "absolute", inset: 0, width: W_NAV, height: H_NAV, opacity: fade}} />
        </div>
      </div>
      {resaltes.map(([r, d, h], i) => {
        const v = Math.min(e(d, 16), interpolate(f, [h - 6, h], [1, 0], clamp));
        return v > 0.01 ? <Resalte key={i} r={r} v={v} pad={i === 0 ? 0 : 8} /> : null;
      })}
      {f >= c0 - 6 && f < clic + 16 && (
        <>
          <div style={{position: "absolute", left: cx - 30 * onda, top: cy - 30 * onda, width: 60 * onda, height: 60 * onda, borderRadius: "50%", border: `3px solid ${C.glow}`, opacity: 1 - onda}} />
          <svg width={34} height={40} viewBox="0 0 24 28" style={{position: "absolute", left: cx - 4, top: cy - 2, opacity: interpolate(f, [c0 - 6, c0, clic + 10, clic + 16], [0, 1, 1, 0], clamp), filter: "drop-shadow(0 3px 6px rgba(0,0,0,0.6))"}}>
            <path d="M2 2 L2 22 L7.5 17 L11 25 L14.5 23.5 L11 15.5 L18 15.5 Z" fill="#fff" stroke="#111" strokeWidth={1.5} strokeLinejoin="round" />
          </svg>
        </>
      )}
      <TituloSeccion titulo="La web" bajada={RESULTADOS.url} salida={salida} />
    </AbsoluteFill>
  );
};

/* 10 · Fuentes y links */
const FUENTES: [string, string, string][] = [
  ["NISAR GUNW y GCOV", "NASA / ISRO · ASF DAAC", "coherencia y eco de radar"],
  ["Sentinel-2 L2A", "ESA Copernicus · Planetary Computer", "imágenes ópticas"],
  ["NASA EMIT", "LP DAAC", "plumas de metano"],
  ["NASA GIBS", "Blue Marble", "mapa de fondo"],
  ["JRC Global Surface Water", "Comisión Europea", "máscara de agua"],
  ["OpenStreetMap · Overture", "ODbL", "contornos de rellenos"],
  ["Climate TRACE", "CC BY 4.0", "emisiones por sitio"],
  ["EPA LMOP", "dominio público", "rellenos de EE. UU."],
];
const Cierre: React.FC<{t0: number; dur: number}> = ({t0}) => {
  const f = useCurrentFrame();
  const e = useEntra();
  const at = (abs: number) => s(abs - t0);
  const tablaW = 1040, linksW = 520, gap = 90;
  const x0 = (ANCHO - (tablaW + gap + linksW)) / 2;
  const links = at(en("cierre", "codigo")) - 6;
  const cols = "320px 400px 1fr";
  return (
    <AbsoluteFill style={{background: FONDO}}>
      <div style={{position: "absolute", left: x0, top: 130, width: tablaW}}>
        <Aparece v={e(2)}><Texto size={56} style={{fontFamily: F.display, fontWeight: 700}}>Solo datos abiertos</Texto></Aparece>
        <div style={{marginTop: 22, borderTop: "1px solid rgba(231,235,241,0.18)"}}>
          {FUENTES.map(([a, b, c], k) => (
            <Aparece key={a} v={e(6 + k * 3, 16)} dx={-24} dy={0}>
              <div style={{display: "grid", gridTemplateColumns: cols, alignItems: "center", height: 54, borderBottom: "1px solid rgba(231,235,241,0.12)", whiteSpace: "nowrap"}}>
                <Texto size={24} style={{fontWeight: 600}}>{a}</Texto>
                <Mono size={18} color="rgba(191,239,255,0.85)">{b}</Mono>
                <Texto size={21} color="rgba(231,235,241,0.72)">{c}</Texto>
              </div>
            </Aparece>
          ))}
        </div>
        <Mono size={16} style={{marginTop: 18, opacity: e(34)}}>Contenido generado con IA: el clip inicial (Higgsfield), marcado en pantalla.</Mono>
      </div>
      <div style={{position: "absolute", left: x0 + tablaW + gap, top: 130, width: linksW}}>
        <Aparece v={e(links - 6)}><Texto size={34} style={{fontFamily: F.display, fontWeight: 700}}>Código, modelo y datos</Texto></Aparece>
        <div style={{display: "grid", gap: 18, marginTop: 22}}>
          {[{i: "▶", et: "Mapa en vivo", v: RESULTADOS.url, c: C.glow}, {i: "</>", et: "Código, modelo y datos", v: RESULTADOS.repo, c: C.radar}].map((x, k) => {
            const v = e(links + k * 8, 13);
            return (
              <div key={x.v} style={{padding: "16px 24px", borderRadius: 18, background: "rgba(10,18,26,0.92)", border: `2px solid ${x.c}`, boxShadow: `0 0 26px ${x.c}44`,
                opacity: v, transform: `translateX(${(1 - v) * 50}px)`}}>
                <div style={{display: "flex", alignItems: "center", gap: 10}}>
                  <span style={{fontFamily: F.mono, fontSize: 20, color: x.c}}>{x.i}</span><Texto size={20} color="rgba(231,235,241,0.7)">{x.et}</Texto>
                </div>
                <div style={{fontFamily: F.mono, fontSize: 27, color: "#fff", marginTop: 6, whiteSpace: "nowrap"}}>{x.v}</div>
              </div>
            );
          })}
        </div>
      </div>
    </AbsoluteFill>
  );
};

/* 11 · Dumpsite and the tagline */
const Lema: React.FC<{t0: number}> = ({t0}) => {
  const f = useCurrentFrame();
  const e = useEntra();
  const at = (abs: number) => s(abs - t0);
  const l0 = at(en("lema", "dumpsite")) - 4;
  const linea1 = at(en("lema", "un")) - 4, linea2 = at(en("lema", "pero")) - 4, despierto = at(en("lema", "despierto")) - 2;
  const letras = "DUMPSITE".split("");
  const brillo = e(despierto, 12);
  return (
    <AbsoluteFill style={{background: C.bg}}>
      <Img src={staticFile("nisar-coherencia-amplia.png")} style={{position: "absolute", left: -200, top: -620, width: 2320, height: 2320, filter: "blur(2px) brightness(0.25)", transform: `scale(${1 + f * 0.001})`}} />
      <AbsoluteFill style={{background: "radial-gradient(circle at 50% 46%, rgba(5,8,12,0) 0%, rgba(5,8,12,0.85) 62%)"}} />
      <div style={{position: "absolute", left: 0, right: 0, top: 250, display: "flex", justifyContent: "center", gap: 6}}>
        {letras.map((l, k) => {
          const v = e(l0 + k * 2.5, 11);
          return <span key={k} style={{display: "inline-block", fontFamily: F.display, fontWeight: 700, fontSize: 220, lineHeight: 1, color: C.glow, opacity: Math.min(1, v * 1.4),
            transform: `translateY(${(1 - v) * 110}px) scale(${1 + (1 - v) * 0.7})`, textShadow: "0 0 50px rgba(255,165,61,0.55)"}}>{l}</span>;
        })}
      </div>
      <div style={{position: "absolute", left: 0, right: 0, top: 520, textAlign: "center"}}>
        <Aparece v={e(linea1)}><Texto size={46}>Un basural se puede cerrar en los papeles,</Texto></Aparece>
        <Aparece v={e(linea2)} style={{marginTop: 10}}>
          <Texto size={46}>pero desde el espacio se ve si verdaderamente sigue <span style={{color: C.glow, textShadow: `0 0 ${30 * brillo}px rgba(255,165,61,${0.9 * brillo})`}}>despierto</span>.</Texto>
        </Aparece>
      </div>
      <div style={{position: "absolute", left: 0, right: 0, top: 700, textAlign: "center", fontFamily: F.mono, fontSize: 26, color: C.radar, opacity: e(despierto + 6)}}>{RESULTADOS.url}</div>
    </AbsoluteFill>
  );
};

/* 12 · We are Spaceship, thank you: the team photo as a Polaroid and the <=> logo (open = close) */
const Gracias: React.FC<{t0: number; dur: number}> = ({t0, dur}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const e = useEntra();
  const at = (abs: number) => s(abs - t0);
  const n = s(dur);
  const somos = at(en("equipo", "somos")) - 6;
  const gracias = at(en("equipo", "muchas")) - 4;
  // Polaroid: 4:3 photo with a white frame and a wide strip at the bottom, falls while rotating a little
  const fw = 640, fh = 480, borde = 22, pie = 92;
  const pw = fw + 2 * borde, ph = fh + borde + pie;
  const cae = spring({frame: f - 2, fps, config: {damping: 13, mass: 0.9}});
  const revela = interpolate(f, [10, 40], [0, 1], {...clamp, easing: Easing.out(Easing.cubic)}); // the photo "develops"
  const xP = 250, yP = 130;
  // logo: "<" and ">" come in from the sides and meet "=" in the middle
  const logo = spring({frame: f - somos, fps, config: {damping: 14}});
  const igual = spring({frame: f - somos - 8, fps, config: {damping: 10}});
  const xR = xP + pw + 130;
  return (
    <AbsoluteFill style={{background: FONDO, opacity: interpolate(f, [0, 8, n - 12, n], [0, 1, 1, 0], clamp)}}>
      <div style={{position: "absolute", left: xP, top: yP, width: pw, height: ph, background: "#f6f3ec", borderRadius: 4,
        boxShadow: "0 30px 80px rgba(0,0,0,0.65), 0 2px 0 rgba(255,255,255,0.4) inset",
        opacity: Math.min(1, cae * 1.5), transform: `translateY(${(1 - cae) * -140}px) rotate(${-3 - (1 - cae) * 8}deg)`}}>
        <div style={{position: "absolute", left: borde, top: borde, width: fw, height: fh, overflow: "hidden", background: "#1d2228"}}>
          {FOTO_EQUIPO ? (
            <Img src={staticFile(FOTO_EQUIPO)} style={{width: fw, height: fh, objectFit: "cover",
              filter: `brightness(${0.35 + 0.65 * revela}) saturate(${0.3 + 0.7 * revela}) sepia(${0.4 * (1 - revela)})`}} />
          ) : (
            <div style={{width: fw, height: fh, display: "flex", alignItems: "center", justifyContent: "center"}}><Mono size={20}>public/equipo.jpg</Mono></div>
          )}
        </div>
        <div style={{position: "absolute", left: 0, right: 0, bottom: 0, height: pie, display: "flex", alignItems: "center", justifyContent: "center",
          fontFamily: F.display, fontWeight: 600, fontSize: 38, letterSpacing: 1, color: "#2b2f36", opacity: revela}}>
          Space Apps · Buenos Aires 2026
        </div>
      </div>
      <div style={{position: "absolute", left: xR, top: 130, width: 1920 - xR - 80}}>
        <div style={{display: "flex", alignItems: "center", fontFamily: F.mono, fontWeight: 500, fontSize: 100, lineHeight: 1, color: C.glow, textShadow: "0 0 40px rgba(255,165,61,0.5)", height: 110}}>
          <span style={{display: "inline-block", opacity: logo, transform: `translateX(${(1 - logo) * -160}px)`}}>&lt;</span>
          <span style={{display: "inline-block", opacity: igual, transform: `scale(${igual})`}}>=</span>
          <span style={{display: "inline-block", opacity: logo, transform: `translateX(${(1 - logo) * 160}px)`}}>&gt;</span>
        </div>
        <Aparece v={e(somos + 10)} style={{marginTop: 8}}>
          <div style={{fontFamily: F.display, fontWeight: 700, fontSize: 110, lineHeight: 1.15, color: "#fff"}}>Spaceship</div>
        </Aparece>
        <div style={{display: "grid", gap: 2, marginTop: 14}}>
          {EQUIPO.map((nombre, k) => <Aparece key={nombre} v={e(somos + 18 + k * 3, 16)} dx={-16} dy={0}><Texto size={27} color="rgba(231,235,241,0.9)">{nombre}</Texto></Aparece>)}
        </div>
        <Aparece v={e(gracias, 12)} style={{marginTop: 22}}>
          <Texto size={68} style={{fontFamily: F.display, fontWeight: 700, color: C.glow}}>¡Muchas gracias!</Texto>
        </Aparece>
      </div>
      <div style={{position: "absolute", left: 0, right: 0, top: 815, textAlign: "center", fontFamily: F.mono, fontSize: 18, letterSpacing: 2, color: "rgba(231,235,241,0.6)", opacity: e(gracias + 10)}}>
        NASA SPACE APPS 2026 · DANCING WITH THE SARS · BUENOS AIRES
      </div>
    </AbsoluteFill>
  );
};

/* Composition */
export const DumpsiteLocal: React.FC = () => {
  const t = (id: string) => fr(id).inicio;
  const tramos: [string, number, number][] = [
    ["ia", 0, CLIP_IA],
    ["argentina", CLIP_IA, t("dumpsite") - 0.6],
    ["pulso", t("dumpsite") - 0.6, t("dumpsite")],
    ["dumpsite", t("dumpsite"), t("cambia")],
    ["insomnio", t("cambia"), t("lujan")],
    ["casos", t("lujan"), t("catalogo")],
    ["datos", t("catalogo"), t("modelo")],
    ["modelo", t("modelo"), t("argentina")],
    ["resultados", t("argentina"), t("web")],
    ["web", t("web"), t("cierre")],
    ["cierre", t("cierre"), t("lema")],
    ["lema", t("lema"), t("equipo")],
    ["gracias", t("equipo"), DURACION_LOCAL],
  ];
  const S = (id: string, el: (t0: number, dur: number) => React.ReactNode) => {
    const [, a, b] = tramos.find((y) => y[0] === id)!;
    return <Sequence key={id} from={s(a)} durationInFrames={Math.max(1, s(b) - s(a))} name={id}>{el(a, b - a)}</Sequence>;
  };
  return (
    <AbsoluteFill style={{background: C.bg}}>
      {S("ia", () => <ClipIA />)}
      {S("argentina", (a, d) => <Argentina t0={a} dur={d} />)}
      {S("pulso", (_, d) => <Pulso dur={d} />)}
      {S("dumpsite", (a, d) => <DumpsiteNisar t0={a} dur={d} />)}
      {S("insomnio", (a, d) => <Insomnio t0={a} dur={d} />)}
      {S("casos", (a, d) => <Casos t0={a} dur={d} />)}
      {S("datos", (a, d) => <Datos t0={a} dur={d} />)}
      {S("modelo", (a, d) => <Modelo t0={a} dur={d} />)}
      {S("resultados", (a, d) => <Resultados t0={a} dur={d} />)}
      {S("web", (a, d) => <Web t0={a} dur={d} />)}
      {S("cierre", (a, d) => <Cierre t0={a} dur={d} />)}
      {S("lema", (a) => <Lema t0={a} />)}
      {S("gracias", (a, d) => <Gracias t0={a} dur={d} />)}
      <Html5Audio src={staticFile(VOZ_ES.pista)} volume={(fr_) => interpolate(fr_, [s(DURACION_LOCAL) - 45, s(DURACION_LOCAL) - 2], [1, 0], clamp)} />
      <Subtitulos frases={VOZ_ES.frases} max={105} />
    </AbsoluteFill>
  );
};
