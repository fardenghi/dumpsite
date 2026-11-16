// Ending of the international video: Argentina (results), the web with the links and Spaceship.
import React from "react";
import {AbsoluteFill, Easing, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig} from "remotion";
import {CIUDADES_AR, EQUIPO, RESULTADOS, RESULTADOS_AR} from "../compartido/data";
import {C, F} from "../compartido/theme";
import {Creditos, TituloSeccion} from "../compartido/components/Overlays";
import {clamp} from "../compartido/escenas/Escenas";
import casosJson from "../compartido/casos.json";

const A = (casosJson as unknown as {argentina: {puntos: [number, number][]; amba: [number, number]}}).argentina;

// Same projection as public/casos/argentina.jpg (MapLibre, center -58.5 / -39.5, zoom 3.75, 1920 × 1080; see capturas_mapa.mjs)
const MUNDO = 512 * 2 ** 3.75;
const merc = (lon: number, lat: number) => [((lon + 180) / 360) * MUNDO, ((1 - Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360)) / Math.PI) / 2) * MUNDO];
const [MX, MY] = merc(-58.5, -39.5);
const aPx = (lon: number, lat: number) => { const [x, y] = merc(lon, lat); return [x - MX + 960, y - MY + 540]; };

const mono = (size: number, color = "rgba(231,235,241,0.7)"): React.CSSProperties => ({fontFamily: F.mono, fontSize: size, color, letterSpacing: 1});
const cifra = (v: number | null) => (v == null ? "XX" : v.toLocaleString("en-US"));

/* Argentina: the already known sites (public catalogs) and the large cities where the model runs */
export const EscenaArgentina: React.FC<{dur: number}> = ({dur}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const n = dur * fps;
  const e = (desde: number, largo = 10) => interpolate(f, [desde, desde + largo], [0, 1], {...clamp, easing: Easing.out(Easing.cubic)});
  const dx = -360;
  const filas: [string, number | null, string, string][] = [
    ["found", RESULTADOS_AR.encontrados, "dumps classified by the model", C.radar],
    ["unregistered", RESULTADOS_AR.sinRegistro, "in no official registry", C.glow],
  ];
  return (
    <AbsoluteFill style={{background: C.bg, opacity: interpolate(f, [0, 5], [0, 1], clamp)}}>
      <div style={{position: "absolute", inset: 0, transform: `translateX(${dx}px) scale(${interpolate(f, [0, n], [1.0, 1.05], clamp)})`, transformOrigin: `${A.amba[0]}px ${A.amba[1]}px`}}>
        <Img src={staticFile("casos/argentina.jpg")} style={{width: 1920, height: 1080, filter: "brightness(0.72) saturate(0.85)"}} />
        <svg width={1920} height={1080} style={{position: "absolute", inset: 0}}>
          {/* known sites: those with a public location in open catalogs */}
          {A.puntos.map(([x, y], k) => {
            const v = e(2 + (k / A.puntos.length) * 12, 6);
            return v > 0.01 ? <circle key={k} cx={x} cy={y} r={4 * v} fill="rgba(231,235,241,0.85)" stroke={C.bg} strokeWidth={1.2} /> : null;
          })}
          {/* large cities where the model runs */}
          {CIUDADES_AR.map(([nombre, lon, lat], k) => {
            const [x, y] = aPx(lon, lat);
            const v = spring({frame: f - 12 - k * 1.5, fps, config: {damping: 12}});
            const pulso = ((f + k * 7) % 30) / 30;
            return (
              <g key={nombre} opacity={Math.min(1, v)}>
                <circle cx={x} cy={y} r={14 + pulso * 22} fill="none" stroke={C.glow} strokeWidth={2} opacity={(1 - pulso) * 0.8} />
                <circle cx={x} cy={y} r={16 * v} fill="rgba(255,165,61,0.18)" stroke={C.glow} strokeWidth={2.5} />
              </g>
            );
          })}
        </svg>
      </div>
      <AbsoluteFill style={{background: "linear-gradient(270deg, rgba(5,8,12,0.95) 0%, rgba(5,8,12,0.8) 40%, rgba(5,8,12,0) 62%)"}} />
      <div style={{position: "absolute", left: 1010, top: 230, width: 840}}>
        <div style={{display: "flex", gap: 28, opacity: e(10), ...mono(19)}}>
          <span><span style={{display: "inline-block", width: 12, height: 12, borderRadius: 6, background: "rgba(231,235,241,0.85)", marginRight: 8}} />known sites · public catalogs</span>
          <span><span style={{display: "inline-block", width: 14, height: 14, borderRadius: 7, border: `2px solid ${C.glow}`, background: "rgba(255,165,61,0.18)", marginRight: 8, verticalAlign: -2}} />major cities scanned</span>
        </div>
        {filas.map(([id, v, texto, color], k) => {
          const a = e(16 + k * 7, 12);
          return (
            <div key={id} style={{display: "flex", alignItems: "baseline", gap: 24, marginTop: k ? 6 : 34, opacity: a, transform: `translateY(${(1 - a) * 20}px)`}}>
              <div style={{fontFamily: F.display, fontWeight: 700, fontSize: 150, lineHeight: 1, color, textShadow: `0 0 36px ${color}66`, minWidth: 170}}>{cifra(v)}</div>
              <div style={{fontFamily: F.sans, fontSize: 36, color: "#fff", textShadow: "0 2px 6px #000"}}>{texto}</div>
            </div>
          );
        })}
        <div style={{marginTop: 30, opacity: e(30), ...mono(18, "rgba(231,235,241,0.6)")}}>
          Scope so far: Argentina's major cities + test regions worldwide.<br />The global run comes next.
        </div>
      </div>
      <TituloSeccion titulo="Results" bajada="Argentina's major cities" salida={4} />
      <Creditos items={[["Image", "NASA GIBS · Blue Marble"], ["Known sites", "OpenStreetMap · Climate TRACE"]]} opacidad={e(8)} />
    </AbsoluteFill>
  );
};

/* The web: the map with everything that was run, and the links */
export const EscenaWeb: React.FC<{dur: number; inicioLinks: number}> = ({dur, inicioLinks}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const n = dur * fps;
  const tL = inicioLinks * fps;
  const entra = spring({frame: f, fps, config: {damping: 18}});
  const links = [
    {icono: "▶", etiqueta: "Live map", valor: RESULTADOS.url, color: C.glow},
    {icono: "</>", etiqueta: "Code + model", valor: RESULTADOS.repo, color: C.radar},
  ];
  return (
    <AbsoluteFill style={{background: "radial-gradient(ellipse at 40% 55%, #13202d 0%, #05080c 72%)", opacity: interpolate(f, [n - 6, n], [1, 0], clamp)}}>
      {/* flat, large browser: the whole map capture, without the tilt of the Navegador in the other scenes */}
      <div style={{position: "absolute", left: 70, top: 150, width: 1180, borderRadius: 14, overflow: "hidden", background: "#0e141d",
        boxShadow: "0 40px 120px rgba(0,0,0,0.7), 0 0 0 1px rgba(255,255,255,0.12)", opacity: entra, transform: `translateY(${(1 - entra) * 60}px) scale(${0.96 + 0.04 * entra})`}}>
        <div style={{height: 38, background: "#1a222e", display: "flex", alignItems: "center", gap: 9, padding: "0 16px"}}>
          {["#ff5f57", "#febc2e", "#28c840"].map((c) => <span key={c} style={{width: 12, height: 12, borderRadius: 6, background: c}} />)}
          <span style={{marginLeft: 18, flex: 1, height: 22, borderRadius: 11, background: "#0e141d", color: "#8e99a8", fontFamily: F.mono, fontSize: 14,
            display: "flex", alignItems: "center", paddingLeft: 12}}>{RESULTADOS.url}</span>
        </div>
        <Img src={staticFile("web/en-mapa-mundo.png")} style={{display: "block", width: 1180}} />
      </div>
      <div style={{position: "absolute", right: 60, top: 560, display: "grid", gap: 14, justifyItems: "end"}}>
        {links.map((l, k) => {
          const v = spring({frame: f - tL - k * 4, fps, config: {damping: 13}});
          return (
            <div key={l.valor} style={{display: "flex", alignItems: "center", gap: 16, padding: "14px 26px", borderRadius: 999, background: "rgba(10,18,26,0.92)",
              border: `2px solid ${l.color}`, boxShadow: `0 0 30px ${l.color}55`, opacity: v, transform: `translateX(${(1 - v) * 80}px) scale(${0.9 + 0.1 * v})`}}>
              <span style={{fontFamily: F.mono, fontSize: 26, color: l.color}}>{l.icono}</span>
              <span style={{fontFamily: F.sans, fontSize: 22, color: "rgba(231,235,241,0.7)"}}>{l.etiqueta}</span>
              <span style={{fontFamily: F.mono, fontSize: 32, color: "#fff"}}>{l.valor}</span>
            </div>
          );
        })}
      </div>
      <div style={{position: "absolute", right: 60, top: 400, textAlign: "right", width: 560, fontFamily: F.display, fontWeight: 700, fontSize: 64, color: "#fff",
        textShadow: "0 2px 10px #000", opacity: interpolate(f, [2, 10], [0, 1], clamp)}}>
        Implemented <span style={{color: C.glow}}>&amp;</span> open
      </div>
    </AbsoluteFill>
  );
};

/* Spaceship: the team photo as a Polaroid, the <=> logo and the names by last name. No spoken text. */
export const EscenaEquipo: React.FC<{dur: number}> = ({dur}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const n = dur * fps;
  const e = (desde: number, largo = 8) => interpolate(f, [desde, desde + largo], [0, 1], {...clamp, easing: Easing.out(Easing.cubic)});
  const fw = 640, fh = 480, borde = 22, pie = 92;
  const pw = fw + 2 * borde, ph = fh + borde + pie;
  const cae = spring({frame: f, fps, config: {damping: 14, mass: 0.7}});
  const revela = interpolate(f, [2, 14], [0, 1], {...clamp, easing: Easing.out(Easing.cubic)});
  const xP = 200, yP = 150;
  const logo = spring({frame: f - 1, fps, config: {damping: 14}});
  const igual = spring({frame: f - 4, fps, config: {damping: 10}});
  const xR = xP + pw + 130;
  return (
    <AbsoluteFill style={{background: "radial-gradient(ellipse at 50% 45%, #13202d 0%, #05080c 75%)", opacity: interpolate(f, [0, 5, n - 4, n], [0, 1, 1, 0.9], clamp)}}>
      <div style={{position: "absolute", left: xP, top: yP, width: pw, height: ph, background: "#f6f3ec", borderRadius: 4,
        boxShadow: "0 30px 80px rgba(0,0,0,0.65)", opacity: Math.min(1, cae * 1.5), transform: `translateY(${(1 - cae) * -120}px) rotate(${-3 - (1 - cae) * 8}deg)`}}>
        <div style={{position: "absolute", left: borde, top: borde, width: fw, height: fh, overflow: "hidden", background: "#1d2228"}}>
          <Img src={staticFile("equipo.jpg")} style={{width: fw, height: fh, objectFit: "cover",
            filter: `brightness(${0.35 + 0.65 * revela}) saturate(${0.3 + 0.7 * revela}) sepia(${0.4 * (1 - revela)})`}} />
        </div>
        <div style={{position: "absolute", left: 0, right: 0, bottom: 0, height: pie, display: "flex", alignItems: "center", justifyContent: "center",
          fontFamily: F.display, fontWeight: 600, fontSize: 38, letterSpacing: 1, color: "#2b2f36", opacity: revela}}>
          Space Apps · Buenos Aires 2026
        </div>
      </div>
      <div style={{position: "absolute", left: xR, top: 120, width: 1920 - xR - 60}}>
        <div style={{display: "flex", alignItems: "center", fontFamily: F.mono, fontWeight: 500, fontSize: 100, lineHeight: 1, color: C.glow, textShadow: "0 0 40px rgba(255,165,61,0.5)", height: 110}}>
          <span style={{display: "inline-block", opacity: logo, transform: `translateX(${(1 - logo) * -160}px)`}}>&lt;</span>
          <span style={{display: "inline-block", opacity: igual, transform: `scale(${igual})`}}>=</span>
          <span style={{display: "inline-block", opacity: logo, transform: `translateX(${(1 - logo) * 160}px)`}}>&gt;</span>
        </div>
        <div style={{marginTop: 8, opacity: e(3, 6), transform: `translateY(${(1 - e(3, 6)) * 16}px)`, fontFamily: F.display, fontWeight: 700, fontSize: 96, lineHeight: 1.15, color: "#fff"}}>Spaceship</div>
        <div style={{display: "grid", gap: 2, marginTop: 14}}>
          {EQUIPO.map((nombre, k) => (
            <div key={nombre} style={{opacity: e(5 + k, 6), transform: `translateX(${(1 - e(5 + k, 6)) * -16}px)`, fontFamily: F.sans, fontSize: 27, color: "rgba(231,235,241,0.92)"}}>{nombre}</div>
          ))}
        </div>
        <LinksFinal v={e(8, 6)} />
      </div>
      <div style={{position: "absolute", left: 0, right: 0, top: 860, textAlign: "center", fontFamily: F.mono, fontSize: 18, letterSpacing: 2, color: "rgba(231,235,241,0.6)", opacity: e(14)}}>
        NASA SPACE APPS 2026 · DANCING WITH THE SARS · BUENOS AIRES
      </div>
    </AbsoluteFill>
  );
};

/* The links in the final image, so the jury can copy them calmly */
const LinksFinal: React.FC<{v: number}> = ({v}) => (
  <div style={{display: "grid", gap: 12, marginTop: 30, opacity: v, transform: `translateY(${(1 - v) * 14}px)`}}>
    {[{icono: "▶", valor: RESULTADOS.url, color: C.glow}, {icono: "</>", valor: RESULTADOS.repo, color: C.radar}].map((l) => (
      <div key={l.valor} style={{display: "flex", alignItems: "center", gap: 14, padding: "10px 22px", borderRadius: 999, width: "fit-content",
        background: "rgba(10,18,26,0.92)", border: `2px solid ${l.color}`, boxShadow: `0 0 24px ${l.color}44`}}>
        <span style={{fontFamily: F.mono, fontSize: 22, color: l.color}}>{l.icono}</span>
        <span style={{fontFamily: F.mono, fontSize: 28, color: "#fff"}}>{l.valor}</span>
      </div>
    ))}
  </div>
);
