import React from "react";
import {AbsoluteFill, Easing, Img, OffthreadVideo, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig} from "remotion";
import {ANCHO, ALTO, DATOS, EJEMPLOS_CNN, Par, RESULTADOS, fechaCorta} from "../data";
import {C, F} from "../theme";
import {AvisoIA, Creditos, Equipo, PinUbicacion, Placeholder, TituloSeccion} from "../components/Overlays";
import {MapaAmba, caminoPoligono, cajaNorte3EnAmba} from "../components/Mapa";

export const clamp = {extrapolateLeft: "clamp", extrapolateRight: "clamp"} as const;
export const n3 = DATOS.norte3;
// Sólo la órbita 10: una pasada cada 12 días (la 161 pasa un día antes y confundía las fechas).
export const pasadas = (n3.pares as Par[]).filter((p) => p.orbita === 10).sort((a, b) => a.fecha.localeCompare(b.fecha));
export const serie = DATOS.serie_s2 as {imagenes: {fecha: string; archivo: string}[]; poligono: number[][]};
export const entreno = DATOS.entreno as {total_catalogo: number; muestras: {archivo: string; pais: string}[]};
export const CRED_OPTICO: [string, string] = ["Optical", "Sentinel-2 · Copernicus"];
export const CRED_RADAR: [string, string] = ["Radar", "NASA–ISRO NISAR · ASF DAAC"];
export const zoomExp = (f: number, r: [number, number], de: number, a: number, easing = Easing.inOut(Easing.cubic)) =>
  Math.exp(interpolate(f, r, [Math.log(de), Math.log(a)], {...clamp, easing}));

export const OFFSET_Y = (ALTO - ANCHO) / 2;
export const centroide = (pts: number[][]) => [pts.reduce((s, p) => s + p[0], 0) / pts.length, pts.reduce((s, p) => s + p[1], 0) / pts.length];
export const [cxS2, cyS2] = centroide(n3.poligono_norm as number[][]);
export const [cxNa, cyNa] = centroide(n3.poligono_nisar_amplio as number[][]);
const pathNorm = (pts: number[][]) => pts.map(([x, y], i) => `${i ? "L" : "M"}${x},${y}`).join(" ") + " Z";

export const Cuadro: React.FC<{src: string; escala?: number; filtro?: string; opacidad?: number; origen?: [number, number]; children?: React.ReactNode}> =
  ({src, escala = 1, filtro, opacidad = 1, origen = [0.5, 0.5], children}) => (
    <div style={{position: "absolute", left: 0, top: OFFSET_Y, width: ANCHO, height: ANCHO, opacity: opacidad,
      transform: `scale(${escala})`, transformOrigin: `${origen[0] * 100}% ${origen[1] * 100}%`}}>
      <Img src={staticFile(src)} style={{width: "100%", height: "100%", filter: filtro}} />
      {children}
    </div>
  );

export const Poligono: React.FC<{pts: number[][]; relleno: string; borde: string; grosor?: number; brillo?: number}> = ({pts, relleno, borde, grosor = 3, brillo = 0}) => (
  <svg viewBox="0 0 1 1" preserveAspectRatio="none" style={{position: "absolute", inset: 0, width: "100%", height: "100%", overflow: "visible",
    filter: brillo ? `drop-shadow(0 0 ${brillo}px ${C.glow})` : undefined}}>
    <path d={pathNorm(pts)} fill={relleno} stroke={borde} strokeWidth={grosor} vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
  </svg>
);

/* ======================= 1 · IA ======================= */
export const EscenaIA: React.FC<{durTotal: number}> = ({durTotal}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const fin = durTotal * fps;
  const aviso = interpolate(f, [fin - 12, fin - 2], [1, 0], clamp);
  return (
    <AbsoluteFill style={{background: C.bg}}>
      {/* Clip de Higgsfield ya montado (satélite 1 s, nubes 1 s, basural 2,7 s = 4,73 s), ajustado al tramo. */}
      <OffthreadVideo src={staticFile("clip1-ai.mp4")} playbackRate={4.733 / durTotal} muted style={{width: ANCHO, height: ALTO, objectFit: "cover"}} />
      <AbsoluteFill style={{background: "radial-gradient(ellipse at center, rgba(0,0,0,0) 55%, rgba(0,0,0,0.45) 100%)"}} />
      <div style={{opacity: aviso}}><AvisoIA /></div>
      <Equipo dur={durTotal} />
    </AbsoluteFill>
  );
};

/* ======================= Transición: pulso de radar que revela el satélite ======================= */
export const Transicion: React.FC<{dur: number}> = ({dur}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const p = interpolate(f, [0, dur * fps], [0, 1], {...clamp, easing: Easing.inOut(Easing.cubic)});
  const cx = ANCHO * cxS2;
  const cy = OFFSET_Y + ANCHO * cyS2;
  const anillos = [0, 0.18, 0.36].map((d) => Math.max(0, p - d));
  return (
    <AbsoluteFill>
      <div style={{position: "absolute", inset: 0, clipPath: `circle(${p * 1400}px at ${cx}px ${cy}px)`}}>
        <Cuadro src="s2-norte3.jpg" escala={1.08} origen={[cxS2, cyS2]} />
        <AbsoluteFill style={{opacity: 1 - p, backgroundImage: "linear-gradient(rgba(95,192,220,0.35) 1px, transparent 1px), linear-gradient(90deg, rgba(95,192,220,0.35) 1px, transparent 1px)",
          backgroundSize: "48px 48px", mixBlendMode: "screen"}} />
        <AbsoluteFill style={{background: `rgba(95,192,220,${0.35 * (1 - p)})`, mixBlendMode: "color"}} />
      </div>
      <svg width={ANCHO} height={ALTO} style={{position: "absolute", inset: 0}}>
        {anillos.map((a, k) => (
          <circle key={k} cx={cx} cy={cy} r={a * 1400} fill="none" stroke={k === 0 ? "#bfefff" : C.radar} strokeWidth={k === 0 ? 6 : 2}
            opacity={a > 0 ? (1 - a) * (k === 0 ? 1 : 0.6) : 0} style={{filter: "drop-shadow(0 0 12px #5fc0dc)"}} />
        ))}
      </svg>
    </AbsoluteFill>
  );
};

/* ======================= 2 · Dumpsite + NISAR ======================= */
export const EscenaNisar: React.FC<{dur: number}> = ({dur}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const n = dur * fps;
  const r0 = Math.round(n * 0.42); // cuando la voz llega a "NASA's NISAR radar"
  const escalaS2 = interpolate(f, [0, r0], [1.08, 1.0], clamp);
  const radar = interpolate(f, [r0, r0 + 18], [0, 1], {...clamp, easing: Easing.inOut(Easing.quad)});
  const escalaR = interpolate(f, [r0, n], [14 / 6, 1.1], {...clamp, easing: Easing.out(Easing.cubic)});
  return (
    <AbsoluteFill style={{background: C.bg}}>
      <Cuadro src="s2-norte3.jpg" escala={escalaS2} origen={[cxS2, cyS2]} opacidad={1 - radar} />
      <div style={{opacity: radar}}>
        <Cuadro src="nisar-coherencia-amplia.png" escala={escalaR} origen={[cxNa, cyNa]}>
          <Poligono pts={n3.poligono_nisar_amplio as number[][]} relleno="rgba(255,165,61,0.12)" borde={C.glow} grosor={3} brillo={10} />
        </Cuadro>
      </div>
      <div style={{opacity: Math.min(1 - radar, interpolate(f, [30, 40], [0, 1], clamp))}}>
        <PinUbicacion x={ANCHO * cxS2} y={OFFSET_Y + ANCHO * cyS2 - 30} texto={RESULTADOS.region} delay={30} />
      </div>
      <div style={{position: "absolute", left: 0, top: 0, width: 1250, height: 320, background: "radial-gradient(ellipse at 0% 0%, rgba(5,8,12,0.9) 0%, rgba(5,8,12,0.5) 50%, rgba(5,8,12,0) 78%)", opacity: radar}} />
      <div style={{position: "absolute", left: 48, top: 178, opacity: radar, fontFamily: F.sans, color: "#fff", textShadow: "0 2px 8px rgba(0,0,0,0.95)"}}>
        <div style={{fontFamily: F.mono, fontSize: 20, letterSpacing: 4, color: C.glow}}>NASA–ISRO NISAR · L-BAND RADAR · EVERY 12 DAYS</div>
        <div style={{fontFamily: F.display, fontWeight: 700, fontSize: 62, lineHeight: 1, marginTop: 6}}>What the radar sees over the dump</div>
        <div style={{display: "flex", gap: 26, marginTop: 14, fontSize: 24, alignItems: "center"}}>
          <span><span style={{display: "inline-block", width: 18, height: 18, borderRadius: 4, background: "#e6f6fb", marginRight: 8, verticalAlign: -2}} />stable ground</span>
          <span><span style={{display: "inline-block", width: 18, height: 18, borderRadius: 4, background: "#0b1a26", border: "1px solid #5fc0dc", marginRight: 8, verticalAlign: -2}} />changing ground</span>
        </div>
      </div>
      <TituloSeccion titulo="Dumpsite" bajada="A platform that tracks dump sites from space" salida={30} />
      <Creditos items={[radar < 0.5 ? CRED_OPTICO : CRED_RADAR]} />
    </AbsoluteFill>
  );
};

/* ======================= 3 · Insomnia ======================= */
export const Ojo: React.FC<{despierto: boolean; tam: number}> = ({despierto, tam}) => (
  <svg width={tam} height={tam * 0.62} viewBox="0 0 100 62">
    {despierto ? (
      <>
        <path d="M4 31 C 24 4, 76 4, 96 31 C 76 58, 24 58, 4 31 Z" fill="rgba(255,165,61,0.15)" stroke={C.glow} strokeWidth="5" />
        <circle cx="50" cy="31" r="14" fill={C.glow} />
        <circle cx="55" cy="26" r="4" fill="#fff" opacity="0.85" />
      </>
    ) : (
      <path d="M6 26 C 26 50, 74 50, 94 26" fill="none" stroke={C.radar} strokeWidth="5" strokeLinecap="round" />
    )}
  </svg>
);

export const EscenaInsomnia: React.FC<{dur: number; inicioParte2: number}> = ({dur, inicioParte2}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const n = dur * fps;
  const t2 = inicioParte2 * fps; // "So first, our Insomnia score..."
  const zIni = n - 78;

  // Parte A: el mismo basural en seis fechas (Sentinel-2 real), una tras otra
  const aIni = 18;
  const porImagen = Math.max(8, Math.floor((t2 - aIni - 6) / serie.imagenes.length));
  const idx = Math.min(serie.imagenes.length - 1, Math.max(0, Math.floor((f - aIni) / porImagen)));
  const local = (f - aIni) - idx * porImagen;
  const fundido = interpolate(local, [0, 5], [0, 1], clamp);
  const partA = interpolate(f, [aIni - 4, aIni + 6, t2 - 6, t2 + 4], [0, 1, 1, 0], clamp);

  // Parte B: una pasada de radar cada 12 días y el puntaje
  const bIni = t2 + 2;
  const paso = 5;
  const visibles = Math.floor(interpolate(f, [bIni + 10, bIni + 10 + paso * pasadas.length], [0, pasadas.length], clamp));
  const despiertos = pasadas.slice(0, visibles).filter((p) => p.despierto).length;
  const puntaje = spring({frame: f - (bIni + 10 + paso * pasadas.length + 6), fps, config: {damping: 14}});
  const partB = interpolate(f, [t2, t2 + 8, zIni - 6, zIni + 4], [0, 1, 1, 0], clamp);

  // Parte C: el mismo cálculo en todo Buenos Aires
  const c = cajaNorte3EnAmba();
  const ease = Easing.inOut(Easing.cubic);
  const vista = {cx: interpolate(f, [zIni, zIni + 44], [c.cx, 0.55], {...clamp, easing: ease}), cy: interpolate(f, [zIni, zIni + 44], [c.cy, 0.5], {...clamp, easing: ease}),
    zoom: zoomExp(f, [zIni, zIni + 44], 1 / c.ancho, 1.25, Easing.inOut(Easing.poly(4))) * interpolate(f, [zIni + 44, n], [1, 1.06], clamp)};
  const mapa = interpolate(f, [zIni - 4, zIni + 8], [0, 1], clamp);

  const lado = 640;
  const tile = 132;
  return (
    <AbsoluteFill style={{background: "radial-gradient(ellipse at 50% 45%, #0d1824 0%, #05080c 70%)"}}>
      {/* A · Sentinel-2 en distintas fechas */}
      <AbsoluteFill style={{opacity: partA}}>
        <div style={{position: "absolute", left: 960 - lado / 2 - 120, top: 140, width: lado, height: lado, borderRadius: 18, overflow: "hidden",
          boxShadow: "0 30px 90px rgba(0,0,0,0.7)", border: "1px solid rgba(255,255,255,0.18)"}}>
          {idx > 0 && <Img src={staticFile(serie.imagenes[idx - 1].archivo)} style={{position: "absolute", inset: 0, width: "100%", height: "100%"}} />}
          <Img src={staticFile(serie.imagenes[idx].archivo)} style={{position: "absolute", inset: 0, width: "100%", height: "100%", opacity: fundido}} />
          <Poligono pts={serie.poligono} relleno="transparent" borde="rgba(255,165,61,0.9)" grosor={2.5} />
          <div style={{position: "absolute", left: 18, top: 14, fontFamily: F.display, fontWeight: 700, fontSize: 48, color: "#fff", textShadow: "0 2px 8px #000"}}>
            {fechaCorta(serie.imagenes[idx].fecha)}
          </div>
        </div>
        <div style={{position: "absolute", left: 960 + lado / 2 - 80, top: 170, width: 380, fontFamily: F.sans, fontSize: 30, color: "#fff", lineHeight: 1.3,
          textShadow: "0 2px 8px #000"}}>
          <b style={{color: C.glow}}>Same dump,</b><br />{serie.imagenes.length} dates.<br />
          <span style={{fontSize: 22, color: "rgba(231,235,241,0.7)"}}>Trucks and machines reshape it every week.</span>
        </div>
        <div style={{position: "absolute", left: 960 + lado / 2 - 80, top: 400, display: "grid", gridTemplateColumns: "repeat(3, 104px)", gap: 10}}>
          {serie.imagenes.map((im, k) => (
            <div key={im.fecha} style={{width: 104, height: 104, borderRadius: 8, overflow: "hidden",
              outline: k === idx ? `3px solid ${C.glow}` : "1px solid rgba(255,255,255,0.2)", opacity: k <= idx ? 1 : 0.35}}>
              <Img src={staticFile(im.archivo)} style={{width: "100%", height: "100%"}} />
            </div>
          ))}
        </div>
      </AbsoluteFill>

      {/* B · coherencia, pasada tras pasada (valores reales del sitio y su entorno) */}
      <AbsoluteFill style={{opacity: partB}}>
        <div style={{position: "absolute", left: 0, right: 0, top: 170, textAlign: "center", fontFamily: F.sans, color: "#fff", textShadow: "0 2px 8px #000"}}>
          <div style={{fontFamily: F.display, fontWeight: 700, fontSize: 60}}>Radar coherence = how alike two passes look</div>
          <div style={{fontSize: 28, marginTop: 6, color: "rgba(231,235,241,0.8)"}}>1 · nothing changed &nbsp;&nbsp;→&nbsp;&nbsp; 0 · everything changed</div>
        </div>
        <div style={{position: "absolute", top: 330, left: (ANCHO - pasadas.length * (tile + 16)) / 2, display: "flex", gap: 16}}>
          {pasadas.map((p, k) => {
            const v = spring({frame: f - bIni - 10 - k * paso, fps, config: {damping: 13, mass: 0.5}});
            const H = 110;
            return (
              <div key={p.fecha} style={{width: tile, height: 250, borderRadius: 14, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "flex-end",
                gap: 8, paddingBottom: 12, opacity: v, transform: `translateY(${(1 - v) * 40}px)`,
                background: p.despierto ? "rgba(255,165,61,0.12)" : "rgba(95,192,220,0.1)", border: `2px solid ${p.despierto ? "rgba(255,165,61,0.7)" : "rgba(95,192,220,0.6)"}`}}>
                <Ojo despierto={p.despierto} tam={64} />
                <svg width={90} height={H + 4}>
                  <rect x={14} y={H - p.anillo * H * v} width={24} height={p.anillo * H * v} rx={3} fill="rgba(95,192,220,0.75)" />
                  <rect x={52} y={H - p.sitio * H * v} width={24} height={p.sitio * H * v} rx={3} fill={C.glow} />
                </svg>
                <div style={{fontFamily: F.sans, fontWeight: 600, fontSize: 22, color: "#fff"}}>{fechaCorta(p.fecha)}</div>
              </div>
            );
          })}
        </div>
        <div style={{position: "absolute", left: 0, right: 0, top: 596, display: "flex", justifyContent: "center", gap: 30, fontFamily: F.sans, fontSize: 22,
          color: "rgba(231,235,241,0.85)"}}>
          <span><span style={{display: "inline-block", width: 14, height: 14, background: "rgba(95,192,220,0.75)", borderRadius: 3, marginRight: 6}} />surroundings</span>
          <span><span style={{display: "inline-block", width: 14, height: 14, background: C.glow, borderRadius: 3, marginRight: 6}} />the dump: always lower</span>
        </div>
        <div style={{position: "absolute", left: 0, right: 0, top: 640, display: "flex", justifyContent: "center", alignItems: "center", gap: 70,
          fontFamily: F.sans, color: "#fff", textShadow: "0 2px 8px #000"}}>
          <div style={{fontSize: 38, opacity: visibles > 0 ? 1 : 0}}>
            restless in <b style={{color: C.glow, fontSize: 60}}>{despiertos}</b> of {pasadas.length} passes
          </div>
          <div style={{opacity: puntaje, transform: `scale(${0.7 + 0.3 * puntaje})`, textAlign: "center"}}>
            <div style={{fontFamily: F.display, fontWeight: 700, fontSize: 130, lineHeight: 0.9, color: C.glow, textShadow: "0 0 40px rgba(255,165,61,0.5)"}}>
              {(n3.insomnio as number).toFixed(2)}
            </div>
            <div style={{fontSize: 24, color: "rgba(231,235,241,0.9)"}}>Insomnia score · high = likely dump</div>
          </div>
        </div>
      </AbsoluteFill>

      {/* C · todo Buenos Aires */}
      {mapa > 0 && (
        <AbsoluteFill style={{opacity: mapa}}>
          <MapaAmba vista={vista}>
            {(px) => <path d={caminoPoligono(n3.poligono_amba as number[][], px)} fill="none" stroke={C.glow} strokeWidth={2} />}
          </MapaAmba>
          <div style={{position: "absolute", left: 48, top: 150, fontFamily: F.display, fontWeight: 700, fontSize: 58, color: "#fff", textShadow: "0 2px 8px #000",
            opacity: interpolate(f, [zIni + 14, zIni + 26], [0, 1], clamp)}}>
            Every pixel of Buenos Aires, scored
          </div>
        </AbsoluteFill>
      )}
      <TituloSeccion titulo="Insomnia" bajada="How often the ground keeps changing" salida={16} />
      <Creditos items={[f < t2 ? CRED_OPTICO : CRED_RADAR]} />
    </AbsoluteFill>
  );
};

/* ======================= 4 · Modelo: LightGBM entrenado con miles de basurales mapeados ======================= */
// De cada imagen se calculan variables (vegetación, suelo desnudo, agua, infrarrojo, radar): eso es lo que aprende el modelo.
const VARIABLES = ["vegetation · NDVI", "bare soil · BSI", "water · NDWI", "infrared · SWIR", "radar coherence"];

export const Arbol: React.FC<{v: number; color: string; activo: boolean}> = ({v, color, activo}) => (
  <svg width={70} height={76} viewBox="0 0 86 92" style={{opacity: v, transform: `translateY(${(1 - v) * 14}px)`}}>
    {[[43, 10, 22, 40], [43, 10, 64, 40], [22, 40, 10, 74], [22, 40, 32, 74], [64, 40, 54, 74], [64, 40, 76, 74]].map(([x1, y1, x2, y2], k) => (
      <line key={k} x1={x1} y1={y1} x2={x2} y2={y2} stroke={activo ? "#fff" : "rgba(191,239,255,0.55)"} strokeWidth={2.2} />
    ))}
    {[[43, 10], [22, 40], [64, 40]].map(([x, y], k) => <circle key={k} cx={x} cy={y} r={6} fill="#0d1a26" stroke={activo ? C.glow : "#bfefff"} strokeWidth={2} />)}
    {[10, 32, 54, 76].map((x, k) => <rect key={k} x={x - 6} y={74} width={12} height={12} rx={3} fill={color} />)}
  </svg>
);

export const EscenaRed: React.FC<{dur: number; inicioParte2: number}> = ({dur, inicioParte2}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const n = dur * fps;
  const t2 = inicioParte2 * fps;
  // A · el muro de basurales mapeados (imágenes reales del catálogo del equipo)
  const muro = interpolate(f, [14, 22, t2 - 12, t2], [0, 1, 1, 0], clamp);
  const colapso = interpolate(f, [t2 - 16, t2], [0, 1], {...clamp, easing: Easing.in(Easing.cubic)});
  const cuenta = Math.round(entreno.total_catalogo * interpolate(f, [20, t2 - 20], [0, 1], {...clamp, easing: Easing.out(Easing.cubic)}));
  const ch = 132;
  const cols = 7;
  const x0 = 960 - (cols * (ch + 10)) / 2;
  // B · el modelo: imágenes → variables → árboles → clasificador
  const modelo = interpolate(f, [t2 - 12, t2 + 2], [0, 1], clamp);
  // bloque centrado: caja (640) + espacio (70) + salidas (540) = 1250 px
  const cajaW = 640, cajaY = 330, cajaH = 330;
  const cajaX = (ANCHO - (cajaW + 70 + 540)) / 2;
  const salX = cajaX + cajaW + 70;
  const intervalo = 13;
  const t0 = t2 + 4;
  return (
    <AbsoluteFill style={{background: "radial-gradient(ellipse at 45% 55%, #0d1a26 0%, #05080c 70%)"}}>
      <AbsoluteFill style={{opacity: muro}}>
        <div style={{position: "absolute", left: x0, top: 150, display: "grid", gridTemplateColumns: `repeat(${cols}, ${ch}px)`, gap: 10}}>
          {entreno.muestras.slice(0, 28).map((m, k) => {
            const v = spring({frame: f - 16 - (k % 7) * 1.5 - Math.floor(k / 7) * 2, fps, config: {damping: 14, mass: 0.5}});
            const dx = (cajaX + cajaW / 2 - (x0 + (k % cols) * (ch + 10) + ch / 2)) * colapso;
            const dy = (cajaY + cajaH / 2 - (150 + Math.floor(k / cols) * (ch + 10) + ch / 2)) * colapso;
            return (
              <div key={m.archivo} style={{width: ch, height: ch, borderRadius: 10, overflow: "hidden", opacity: v * (1 - colapso * 0.7), position: "relative",
                transform: `translate(${dx}px, ${dy}px) scale(${(0.6 + 0.4 * v) * (1 - colapso * 0.85)})`, border: "1px solid rgba(255,255,255,0.25)",
                boxShadow: "0 8px 24px rgba(0,0,0,0.5)"}}>
                <Img src={staticFile(m.archivo)} style={{width: "100%", height: "100%"}} />
                <div style={{position: "absolute", left: 6, bottom: 4, fontFamily: F.mono, fontSize: 13, color: "#fff", textShadow: "0 1px 3px #000"}}>{m.pais}</div>
              </div>
            );
          })}
        </div>
        <div style={{position: "absolute", left: 0, right: 0, top: 735, textAlign: "center", fontFamily: F.sans, color: "#fff", textShadow: "0 2px 8px #000", opacity: 1 - colapso}}>
          <span style={{fontFamily: F.display, fontWeight: 700, fontSize: 64, color: C.glow}}>{cuenta.toLocaleString("en-US")}</span>
          <span style={{fontSize: 32, marginLeft: 16}}>mapped dumps worldwide · training data</span>
        </div>
      </AbsoluteFill>

      <AbsoluteFill style={{opacity: modelo}}>
        {/* la caja del modelo */}
        <div style={{position: "absolute", left: cajaX, top: cajaY, width: cajaW, height: cajaH, borderRadius: 22, border: "2px solid rgba(191,239,255,0.55)",
          background: "linear-gradient(160deg, rgba(95,192,220,0.16), rgba(10,20,30,0.85))", boxShadow: "0 0 50px rgba(95,192,220,0.25)"}}>
          <div style={{position: "absolute", left: 24, top: 16, fontFamily: F.display, fontWeight: 700, fontSize: 52, color: "#fff"}}>LightGBM</div>
          <div style={{position: "absolute", right: 24, top: 30, fontFamily: F.mono, fontSize: 16, color: "rgba(191,239,255,0.8)"}}>gradient-boosted decision trees</div>
          <div style={{position: "absolute", left: 24, right: 24, top: 92, display: "flex", flexWrap: "wrap", gap: 8}}>
            {VARIABLES.map((v, k) => {
              const s = spring({frame: f - t2 - k * 3, fps, config: {damping: 14}});
              return <span key={v} style={{opacity: s, fontFamily: F.mono, fontSize: 15, color: "#cfefff", padding: "4px 10px", borderRadius: 999,
                border: "1px solid rgba(95,192,220,0.5)", background: "rgba(10,25,36,0.8)"}}>{v}</span>;
            })}
          </div>
          <div style={{position: "absolute", left: 24, right: 24, top: 190, display: "flex", alignItems: "center", gap: 2}}>
            {Array.from({length: 6}).map((_, k) => (
              <React.Fragment key={k}>
                <Arbol v={spring({frame: f - t2 - 6 - k * 3, fps, config: {damping: 14}})} color={k % 3 === 0 ? C.glow : "#5fc0dc"} activo={Math.floor(f / 5) % 6 === k} />
                {k < 5 && <span style={{fontFamily: F.mono, fontSize: 22, color: "rgba(231,235,241,0.5)"}}>+</span>}
              </React.Fragment>
            ))}
            <span style={{fontFamily: F.mono, fontSize: 22, color: "#fff", marginLeft: 8}}>… × 300</span>
          </div>
        </div>
        {/* el clasificador: dos salidas */}
        {[{t: "Dump", c: C.glow, y: 300}, {t: "Something else", c: C.radar, y: 520}].map((s) => (
          <div key={s.t} style={{position: "absolute", left: salX, top: s.y, width: 540, height: 190, borderRadius: 16, border: `2px dashed ${s.c}`,
            background: "rgba(5,8,12,0.4)"}}>
            <div style={{position: "absolute", left: 18, top: 8, fontFamily: F.display, fontWeight: 700, fontSize: 38, color: s.c}}>{s.t}</div>
          </div>
        ))}
        <svg width={ANCHO} height={ALTO} style={{position: "absolute", inset: 0}}>
          <line x1={cajaX + cajaW} y1={cajaY + cajaH / 2} x2={salX} y2={395} stroke="rgba(255,165,61,0.6)" strokeWidth={3} />
          <line x1={cajaX + cajaW} y1={cajaY + cajaH / 2} x2={salX} y2={615} stroke="rgba(95,192,220,0.6)" strokeWidth={3} />
        </svg>
      </AbsoluteFill>

      {/* ejemplos: entran al modelo y caen en su salida */}
      {EJEMPLOS_CNN.map((e, k) => {
        const inicio = t0 + k * intervalo;
        const entra = spring({frame: f - inicio, fps, config: {damping: 16}});
        const cruza = interpolate(f, [inicio + 10, inicio + 22], [0, 1], {...clamp, easing: Easing.in(Easing.quad)});
        const sale = spring({frame: f - (inicio + 22), fps, config: {damping: 14}});
        const yIn = 360 + k * 140;
        const xChip = interpolate(entra, [0, 1], [-200, cajaX - 110]) + cruza * 170;
        const slot = e.basural ? 300 : 520;
        const otros = EJEMPLOS_CNN.filter((x) => x.basural === e.basural).indexOf(e);
        return (
          <React.Fragment key={e.id}>
            {cruza < 1 && f >= inicio - 2 && (
              <div style={{position: "absolute", left: xChip - 60, top: yIn - 60, width: 120, height: 120, opacity: 1 - cruza, transform: `scale(${1 - cruza * 0.6})`,
                borderRadius: 12, overflow: "hidden", border: "2px solid rgba(255,255,255,0.4)", boxShadow: "0 10px 30px rgba(0,0,0,0.6)"}}>
                <Img src={staticFile(`chip-${e.id}.jpg`)} style={{width: "100%", height: "100%"}} />
              </div>
            )}
            {sale > 0.01 && (
              <div style={{position: "absolute", left: salX + 20 + otros * 262, top: slot + 66, display: "flex", alignItems: "center", gap: 12,
                opacity: sale, transform: `translateX(${(1 - sale) * -60}px)`}}>
                <div style={{width: 100, height: 100, borderRadius: 10, overflow: "hidden", flexShrink: 0, border: `3px solid ${e.basural ? C.glow : "rgba(191,239,255,0.6)"}`,
                  boxShadow: e.basural ? "0 0 26px rgba(255,165,61,0.55)" : undefined}}>
                  <Img src={staticFile(`chip-${e.id}.jpg`)} style={{width: "100%", height: "100%"}} />
                </div>
                <div style={{fontFamily: F.sans, fontSize: 19, color: "rgba(231,235,241,0.85)", width: 120}}>{e.detalle}</div>
              </div>
            )}
          </React.Fragment>
        );
      })}
      <TituloSeccion titulo="LightGBM" bajada="Dump, or something else?" salida={12} />
      <Creditos items={[["Training", "OpenStreetMap · Climate TRACE · EPA · NASA EMIT"], CRED_OPTICO]} opacidad={interpolate(f, [22, 32], [0, 1], clamp)} />
    </AbsoluteFill>
  );
};

/* ======================= 5 · Dumpsite: resultados sobre la web ======================= */
export const Navegador: React.FC<{src: string; f: number}> = ({src, f}) => {
  const {fps} = useVideoConfig();
  const entra = spring({frame: f, fps, config: {damping: 18}});
  const giro = interpolate(f, [0, 120], [14, 6], clamp);
  const scroll = 0;
  return (
    <div style={{position: "absolute", left: 690, top: 560, width: 1060, height: 600,
      transform: `translate(-50%, -50%) perspective(1800px) rotateX(${giro * 0.6}deg) rotateY(${giro}deg) translateY(${(1 - entra) * 260}px)`,
      opacity: entra, borderRadius: 16, overflow: "hidden", boxShadow: "0 40px 120px rgba(0,0,0,0.7), 0 0 0 1px rgba(255,255,255,0.12)", background: "#f4f1ea"}}>
      <div style={{height: 40, background: "#1a222e", display: "flex", alignItems: "center", gap: 9, padding: "0 16px"}}>
        {["#ff5f57", "#febc2e", "#28c840"].map((c) => <span key={c} style={{width: 13, height: 13, borderRadius: 7, background: c}} />)}
        <span style={{marginLeft: 18, flex: 1, height: 24, borderRadius: 12, background: "#0e141d", color: "#8e99a8", fontFamily: F.mono, fontSize: 14,
          display: "flex", alignItems: "center", paddingLeft: 12}}>{RESULTADOS.url}</span>
      </div>
      <Img src={staticFile(src)} style={{width: 1060, transform: `translateY(${scroll}px)`}} />
    </div>
  );
};

export const Cifra: React.FC<{valor: number; desde: number; f: number; color: string; texto: string; grande?: boolean; signo?: string}> = ({valor, desde, f, color, texto, grande, signo = ""}) => {
  const v = interpolate(f, [desde, desde + 14], [0, 1], {...clamp, easing: Easing.out(Easing.cubic)});
  if (v <= 0) return null;
  return (
    <div style={{opacity: Math.min(1, v * 2), transform: `translateY(${(1 - v) * 20}px)`}}>
      <div style={{fontFamily: F.display, fontWeight: 700, fontSize: grande ? 190 : 110, lineHeight: 0.9, color, textShadow: `0 0 36px ${color}66, 0 4px 14px rgba(0,0,0,0.8)`}}>
        {signo}{Math.round(valor * v).toLocaleString("en-US")}
      </div>
      <div style={{fontFamily: F.sans, fontSize: grande ? 34 : 28, color: "#fff", textShadow: "0 2px 6px #000"}}>{texto}</div>
    </div>
  );
};

export const EscenaResultados: React.FC<{dur: number; inicioLinks: number}> = ({dur, inicioLinks}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const tL = inicioLinks * fps;
  const web = 22;
  const links = [
    {icono: "▶", etiqueta: "Live map", valor: RESULTADOS.url, color: C.glow},
    {icono: "</>", etiqueta: "Code + model", valor: RESULTADOS.repo, color: C.radar},
  ];
  return (
    <AbsoluteFill style={{background: "radial-gradient(ellipse at 40% 55%, #13202d 0%, #05080c 72%)"}}>
      {f >= web && <Navegador src="web/inicio.png" f={f - web} />}
      <div style={{position: "absolute", right: 80, top: 190, display: "grid", gap: 20, textAlign: "right"}}>
        <Cifra valor={RESULTADOS.encontrados} desde={4} f={f} color={C.radar} texto="cataloged dumps still active on radar" />
        <Cifra valor={RESULTADOS.sinRegistro} desde={16} f={f} color={C.glow} texto="listed as closed, yet still active" grande />
        <div style={{fontFamily: F.mono, fontSize: 15, color: "rgba(231,235,241,0.55)"}}>10 regions · signal compatible with activity, not yet verified on site</div>
      </div>
      <div style={{position: "absolute", right: 70, top: 655, textAlign: "right", fontFamily: F.sans, fontSize: 26, color: "#fff", textShadow: "0 2px 8px #000",
        opacity: interpolate(f, [tL - 4, tL + 6], [0, 1], clamp)}}>
        Everything here is implemented. <b style={{color: C.glow}}>Check it yourself:</b>
      </div>
      <div style={{position: "absolute", right: 70, top: 700, display: "grid", gap: 14, justifyItems: "end"}}>
        {links.map((l, k) => {
          const v = spring({frame: f - tL - k * 6, fps, config: {damping: 13}});
          return (
            <div key={l.valor} style={{display: "flex", alignItems: "center", gap: 16, padding: "14px 26px", borderRadius: 999, background: "rgba(10,18,26,0.9)",
              border: `2px solid ${l.color}`, boxShadow: `0 0 30px ${l.color}55`, opacity: v, transform: `translateX(${(1 - v) * 80}px) scale(${0.9 + 0.1 * v})`}}>
              <span style={{fontFamily: F.mono, fontSize: 26, color: l.color}}>{l.icono}</span>
              <span style={{fontFamily: F.sans, fontSize: 22, color: "rgba(231,235,241,0.7)"}}>{l.etiqueta}</span>
              <span style={{fontFamily: F.mono, fontSize: 32, color: "#fff"}}>{l.valor}</span>
            </div>
          );
        })}
      </div>
      <div style={{position: "absolute", left: 0, right: 0, top: 36, textAlign: "right", paddingRight: 40, fontFamily: F.mono, fontSize: 16, color: "rgba(231,235,241,0.55)",
        letterSpacing: 2, opacity: interpolate(f, [tL, tL + 10], [0, 1], clamp)}}>
        NASA SPACE APPS 2026 · DANCING WITH THE SARS
      </div>
      <TituloSeccion titulo="Results" bajada="10 regions on 3 continents" salida={18} />
      <Placeholder texto="cifras y URLs de ejemplo" />
    </AbsoluteFill>
  );
};
