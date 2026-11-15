import React from "react";
import {AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig} from "remotion";
import {EQUIPO, FRASES as FRASES_EN, MOSTRAR_PLACEHOLDERS} from "../data";
import {C, F} from "../theme";

const clamp = {extrapolateLeft: "clamp", extrapolateRight: "clamp"} as const;

/* Subtítulos integrados: sin caja, palabra por palabra al ritmo de la voz, con sombra suave. */
type FraseSub = {inicio: number; duracion: number; texto: string};
// Parte una frase larga en bloques de hasta `max` caracteres, cortando preferentemente después de una coma o un punto.
const bloques = (texto: string, max: number) => {
  const palabras = texto.split(" ");
  const out: string[][] = [[]];
  let largo = 0;
  palabras.forEach((p, k) => {
    const actual = out[out.length - 1];
    actual.push(p);
    largo += p.length + 1;
    const resto = palabras.slice(k + 1).join(" ").length;
    const corteNatural = /[,.]$/.test(p) && largo > max * 0.45;
    if (resto > 0 && (largo >= max || corteNatural) && resto > 12) {
      out.push([]);
      largo = 0;
    }
  });
  return out;
};

export const Subtitulos: React.FC<{frases?: FraseSub[]; max?: number}> = ({frases: FRASES_P, max = 10000}) => {
  const FRASES = FRASES_P ?? FRASES_EN;
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = frame / fps;
  const i = FRASES.findIndex((fr, k) => t >= fr.inicio - 0.1 && t < (FRASES[k + 1]?.inicio ?? fr.inicio + fr.duracion + 3) - 0.15);
  if (i < 0) return null;
  const fr = FRASES[i];
  const total = fr.texto.length;
  // qué bloque se está diciendo ahora: el último cuyo comienzo ya pasó
  const partes = bloques(fr.texto, max);
  let desde = 0, elegido = 0, inicioBloque = 0;
  partes.forEach((b, k) => {
    const tb = fr.inicio + (desde / total) * fr.duracion;
    if (t >= tb - 0.08) { elegido = k; inicioBloque = desde; }
    desde += b.join(" ").length + 1;
  });
  const palabras = partes[elegido];
  let acumulado = inicioBloque;
  const salida = interpolate(t, [fr.inicio + fr.duracion + 0.25, fr.inicio + fr.duracion + 0.6], [1, 0], clamp);
  return (
    <AbsoluteFill style={{justifyContent: "flex-end", alignItems: "center", paddingBottom: 92, pointerEvents: "none"}}>
      {/* degradado suave detrás del texto: se lee sobre fondos claros (la web) sin parecer una caja */}
      <div style={{position: "absolute", left: 0, right: 0, bottom: 0, height: 330, opacity: salida,
        background: "linear-gradient(to top, rgba(5,8,12,0.88) 0%, rgba(5,8,12,0.6) 45%, rgba(5,8,12,0) 100%)"}} />
      <div style={{position: "relative", maxWidth: 1560, textAlign: "center", fontFamily: F.sans, fontWeight: 600, fontSize: 46, lineHeight: 1.25,
        letterSpacing: 0.2, color: "#fff", opacity: salida,
        textShadow: "0 2px 3px rgba(0,0,0,0.85), 0 0 24px rgba(0,0,0,0.65), 0 0 60px rgba(0,0,0,0.45)"}}>
        {palabras.map((p, k) => {
          // cada palabra aparece cuando la voz llega a ella (proporcional a los caracteres)
          const tPalabra = fr.inicio + (acumulado / total) * fr.duracion;
          acumulado += p.length + 1;
          const v = interpolate(t, [tPalabra - 0.05, tPalabra + 0.15], [0, 1], clamp);
          return (
            <span key={k} style={{display: "inline-block", marginRight: "0.28em", opacity: 0.25 + 0.75 * v,
              transform: `translateY(${(1 - v) * 6}px)`}}>{p}</span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

/* Aviso de contenido generado con IA: visible todo el clip, discreto y prolijo. */
export const AvisoIA: React.FC<{texto?: string}> = ({texto = "AI-generated imagery"}) => (
  <div style={{position: "absolute", right: 40, bottom: 40, display: "flex", alignItems: "center", gap: 10,
    padding: "9px 16px 9px 12px", borderRadius: 999, background: "rgba(8,12,18,0.42)", backdropFilter: "blur(10px)",
    border: "1px solid rgba(255,255,255,0.28)", color: "rgba(255,255,255,0.92)", fontFamily: F.sans, fontSize: 20, letterSpacing: 1.6,
    textTransform: "uppercase", fontWeight: 500}}>
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M12 2l2.2 6.6L21 11l-6.8 2.4L12 20l-2.2-6.6L3 11l6.8-2.4z" fill="rgba(255,255,255,0.9)" />
    </svg>
    {texto}
  </div>
);

/* Integrantes del equipo: abajo a la derecha, arriba del aviso de IA y por encima de la zona de subtítulos.
   La guía oficial sugiere presentar al equipo al principio del video. No se dicen en voz alta. */
export const Equipo: React.FC<{titulo?: string; dur: number}> = ({titulo = "Team", dur}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const n = dur * fps;
  const v = interpolate(f, [8, 20, n - 12, n - 2], [0, 1, 1, 0], clamp);
  return (
    <div style={{position: "absolute", right: 40, bottom: 236, opacity: v, transform: `translateY(${(1 - Math.min(1, f / 20)) * 10}px)`,
      padding: "14px 20px", borderRadius: 16, background: "rgba(8,12,18,0.5)", backdropFilter: "blur(10px)", border: "1px solid rgba(255,255,255,0.22)",
      textAlign: "right", textShadow: "0 1px 3px rgba(0,0,0,0.8)"}}>
      <div style={{fontFamily: F.mono, fontSize: 15, letterSpacing: 3, textTransform: "uppercase", color: C.glow, marginBottom: 6}}>{titulo}</div>
      {EQUIPO.map((nombre) => (
        <div key={nombre} style={{fontFamily: F.sans, fontWeight: 500, fontSize: 21, lineHeight: 1.35, color: "rgba(255,255,255,0.94)"}}>{nombre}</div>
      ))}
    </div>
  );
};

/* Créditos de la imagen en pantalla, como ficha técnica chiquita. */
export const Creditos: React.FC<{items: [string, string][]; opacidad?: number}> = ({items, opacidad = 1}) => (
  <div style={{position: "absolute", left: 40, bottom: 34, display: "flex", gap: 22, opacity: opacidad, fontFamily: F.mono, fontSize: 15,
    color: "rgba(231,235,241,0.78)", textShadow: "0 1px 3px rgba(0,0,0,0.9)"}}>
    {items.map(([etiqueta, valor]) => (
      <span key={etiqueta}><span style={{color: C.glow, letterSpacing: 2, textTransform: "uppercase", marginRight: 8}}>{etiqueta}</span>{valor}</span>
    ))}
  </div>
);

export const Placeholder: React.FC<{texto: string}> = ({texto}) => {
  if (!MOSTRAR_PLACEHOLDERS) return null;
  return (
    <div style={{position: "absolute", right: 28, top: 24, fontFamily: F.mono, fontSize: 14, color: "#ffd2a8", padding: "4px 10px",
      borderRadius: 4, border: "1px dashed rgba(255,122,26,0.8)", background: "rgba(40,18,4,0.6)", zIndex: 60}}>
      PLACEHOLDER · {texto}
    </div>
  );
};

/* Título de sección: entra grande al centro y se acomoda arriba a la izquierda. */
export const TituloSeccion: React.FC<{numero?: string; titulo: string; bajada?: string; salida?: number}> = ({numero, titulo, bajada, salida = 26}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const entra = spring({frame, fps, config: {damping: 16, mass: 0.7}});
  const mueve = interpolate(frame, [salida, salida + 18], [0, 1], {...clamp, easing: Easing.inOut(Easing.cubic)});
  const escala = interpolate(mueve, [0, 1], [1, 0.36]);
  const x = interpolate(mueve, [0, 1], [960, 48]);
  const y = interpolate(mueve, [0, 1], [500, 46]);
  const fondo = interpolate(mueve, [0, 0.6], [0.55, 0], clamp);
  return (
    <>
      <AbsoluteFill style={{background: `rgba(5,8,12,${fondo * entra})`, pointerEvents: "none"}} />
      <div style={{position: "absolute", left: x, top: y, transform: `translate(${-50 * (1 - mueve)}%, ${-50 * (1 - mueve)}%) scale(${escala})`,
        transformOrigin: "0 0", textAlign: mueve > 0.5 ? "left" : "center", opacity: entra}}>
        {numero && (
          <div style={{fontFamily: F.mono, fontSize: 34, letterSpacing: 10, color: C.glow, textTransform: "uppercase",
            transform: `translateY(${(1 - entra) * 20}px)`}}>{numero}</div>
        )}
        <div style={{fontFamily: F.display, fontWeight: 700, fontSize: 200, lineHeight: 0.95, color: C.ink, letterSpacing: 2,
          textShadow: "0 6px 40px rgba(0,0,0,0.6)", whiteSpace: "nowrap", transform: `translateY(${(1 - entra) * 40}px)`}}>{titulo}</div>
        {bajada && (
          <div style={{fontFamily: F.sans, fontSize: 40, color: "rgba(231,235,241,0.85)", marginTop: 12, opacity: interpolate(frame, [8, 18], [0, 1], clamp)}}>
            {bajada}
          </div>
        )}
      </div>
    </>
  );
};

/* Pin de ubicación que cae con rebote y deja un pulso. */
export const PinUbicacion: React.FC<{x: number; y: number; texto: string; delay?: number}> = ({x, y, texto, delay = 0}) => {
  const frame = useCurrentFrame() - delay;
  const {fps} = useVideoConfig();
  const cae = spring({frame, fps, config: {damping: 9, mass: 0.6}});
  const pulso = (Math.max(0, frame) % 36) / 36;
  const etiqueta = interpolate(frame, [10, 20], [0, 1], clamp);
  return (
    <div style={{position: "absolute", left: x, top: y, opacity: frame < 0 ? 0 : 1}}>
      <div style={{position: "absolute", left: -40, top: -40, width: 80, height: 80, borderRadius: 40, border: `3px solid ${C.glow}`,
        transform: `scale(${0.3 + pulso * 1.4})`, opacity: (1 - pulso) * 0.8}} />
      <svg width="54" height="70" viewBox="0 0 24 31" style={{position: "absolute", left: -27, top: -70 + (1 - cae) * -120}}>
        <path d="M12 0C5.4 0 0 5.2 0 11.7 0 20.5 12 31 12 31s12-10.5 12-19.3C24 5.2 18.6 0 12 0z" fill={C.glow} />
        <circle cx="12" cy="11.5" r="4.5" fill="#1b0e02" />
      </svg>
      <div style={{position: "absolute", left: 40, top: -62, opacity: etiqueta, transform: `translateX(${(1 - etiqueta) * -14}px)`,
        whiteSpace: "nowrap", fontFamily: F.sans, fontWeight: 600, fontSize: 34, color: "#fff",
        textShadow: "0 2px 4px rgba(0,0,0,0.9), 0 0 22px rgba(0,0,0,0.7)"}}>{texto}</div>
    </div>
  );
};
