// Video para el jurado local de Buenos Aires: hasta 3 minutos, en castellano, mismo estilo que el internacional.
// Cifras: idea-basurales-nisar/context/README.md, idea/indice-final.md, data/basurales (catálogo), insomnes-web seed/veredictos.json. Ver guion-es.json.
// Cada escena arranca cuando arranca su frase en voz-es.json: si cambia la voz, las escenas se reacomodan solas (ver video/VOZ-GRABADA.md).
import React from "react";
import {AbsoluteFill, Easing, Html5Audio, Img, OffthreadVideo, Sequence, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig} from "remotion";
import {ALTO, ANCHO, DATOS, FPS, RESULTADOS, fechaCorta} from "../compartido/data";
import {C, F} from "../compartido/theme";
import {AvisoIA, Creditos, Equipo, PinUbicacion, Subtitulos, TituloSeccion} from "../compartido/components/Overlays";
import {MapaAmba, caminoPoligono, cajaNorte3EnAmba} from "../compartido/components/Mapa";
import {Arbol, Cuadro, Navegador, OFFSET_Y, Ojo, Poligono, clamp, cxNa, cxS2, cyNa, cyS2, entreno, n3, pasadas, serie, zoomExp} from "../compartido/escenas/Escenas";
import voz from "./voz-es.json";

type Frase = {id: string; archivo: string; inicio: number; duracion: number; texto: string};
const VOZ_ES = voz as {duracion_video: number; frases: Frase[]};
export const DURACION_LOCAL = VOZ_ES.duracion_video;
const fr = (id: string) => VOZ_ES.frases.find((x) => x.id === id)!;
// segundos desde el inicio de la frase en que empieza un fragmento (proporcional a los caracteres)
const dentro = (id: string, desde: string) => {
  const x = fr(id);
  return Math.max(0, (x.texto.indexOf(desde) / x.texto.length) * x.duracion);
};
const s = (seg: number) => Math.round(seg * FPS);

const RADAR_ES: [string, string] = ["Radar", "NASA–ISRO NISAR · ASF DAAC"];
const OPTICO_ES: [string, string] = ["Óptico", "Sentinel-2 · Copernicus"];
const CLIP_IA = 4.733;

const Texto: React.FC<{children: React.ReactNode; size?: number; color?: string; style?: React.CSSProperties}> = ({children, size = 30, color = "#fff", style}) => (
  <div style={{fontFamily: F.sans, fontSize: size, color, textShadow: "0 2px 8px rgba(0,0,0,0.9)", ...style}}>{children}</div>
);
const Pill: React.FC<{children: React.ReactNode; color?: string; v?: number}> = ({children, color = "rgba(95,192,220,0.55)", v = 1}) => (
  <span style={{display: "inline-block", opacity: v, transform: `translateY(${(1 - v) * 12}px)`, fontFamily: F.mono, fontSize: 18, color: "#e7f6fb",
    padding: "6px 14px", borderRadius: 999, border: `1px solid ${color}`, background: "rgba(10,25,36,0.8)", whiteSpace: "nowrap"}}>{children}</span>
);
const Grande: React.FC<{valor: string; color: string; texto: string; nota?: string; v: number}> = ({valor, color, texto, nota, v}) => (
  <div style={{opacity: Math.min(1, v * 1.6), transform: `translateY(${(1 - v) * 24}px)`}}>
    <div style={{fontFamily: F.display, fontWeight: 700, fontSize: 170, lineHeight: 0.9, color, textShadow: `0 0 40px ${color}55, 0 4px 14px rgba(0,0,0,0.8)`}}>{valor}</div>
    <Texto size={36}>{texto}</Texto>
    {nota && <div style={{fontFamily: F.mono, fontSize: 18, color: "rgba(231,235,241,0.6)", marginTop: 6}}>{nota}</div>}
  </div>
);

/* 1 · Problema (sobre el final del clip de IA, en cámara lenta) */
const Problema: React.FC<{dur: number; t2: number}> = ({dur, t2}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const n = dur * fps;
  const a = spring({frame: f - s(t2) - 4, fps, config: {damping: 16}});
  const b = spring({frame: f - s(t2) - s(5.2), fps, config: {damping: 16}});
  return (
    <AbsoluteFill style={{background: C.bg}}>
      <OffthreadVideo src={staticFile("clip1-ai.mp4")} startFrom={s(3.9)} playbackRate={0.7 / dur} muted style={{width: ANCHO, height: ALTO, objectFit: "cover", filter: "brightness(0.55)"}} />
      <AbsoluteFill style={{background: "linear-gradient(90deg, rgba(5,8,12,0.88) 0%, rgba(5,8,12,0.55) 55%, rgba(5,8,12,0.2) 100%)"}} />
      <div style={{position: "absolute", left: 100, top: 170, display: "grid", gap: 60}}>
        <Grande v={a} valor="≈ 5.000" color={C.glow} texto="basurales a cielo abierto en Argentina" nota="estimación del Ministerio de Ambiente · no sale de un relevamiento formal" />
        <Grande v={b} valor="0" color={C.radar} texto="inventarios oficiales abiertos con coordenadas" nota="no hay forma pública de saber dónde están ni cuáles siguen activos" />
      </div>
      <div style={{opacity: interpolate(f, [n - 10, n], [1, 0], clamp)}}><AvisoIA texto="Imagen generada con IA" /></div>
    </AbsoluteFill>
  );
};

/* Transición: pulso de radar que revela la imagen satelital */
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

/* 2 · Dumpsite + NISAR */
const DumpsiteNisar: React.FC<{dur: number; tNisar: number}> = ({dur, tNisar}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const n = dur * fps;
  const r0 = s(tNisar);
  const radar = interpolate(f, [r0, r0 + 20], [0, 1], {...clamp, easing: Easing.inOut(Easing.quad)});
  const escalaR = interpolate(f, [r0, n], [14 / 6, 1.08], {...clamp, easing: Easing.out(Easing.cubic)});
  const chips = ["cada 12 días", "de día y de noche", "a través de las nubes", "radar banda L"];
  return (
    <AbsoluteFill style={{background: C.bg}}>
      <Cuadro src="s2-norte3.jpg" escala={interpolate(f, [0, r0], [1.08, 1], clamp)} origen={[cxS2, cyS2]} opacidad={1 - radar} />
      <div style={{opacity: radar}}>
        <Cuadro src="nisar-coherencia-amplia.png" escala={escalaR} origen={[cxNa, cyNa]}>
          <Poligono pts={n3.poligono_nisar_amplio as number[][]} relleno="rgba(255,165,61,0.12)" borde={C.glow} grosor={3} brillo={10} />
        </Cuadro>
      </div>
      <div style={{opacity: Math.min(1 - radar, interpolate(f, [s(4), s(4.5)], [0, 1], clamp))}}>
        <PinUbicacion x={ANCHO * cxS2} y={OFFSET_Y + ANCHO * cyS2 - 30} texto="Buenos Aires, Argentina" delay={s(4)} />
      </div>
      <div style={{position: "absolute", left: 0, top: 0, width: 1300, height: 380, background: "radial-gradient(ellipse at 0% 0%, rgba(5,8,12,0.92) 0%, rgba(5,8,12,0.5) 52%, rgba(5,8,12,0) 78%)", opacity: radar}} />
      <div style={{position: "absolute", left: 48, top: 178, opacity: radar}}>
        <div style={{fontFamily: F.mono, fontSize: 20, letterSpacing: 4, color: C.glow}}>NASA–ISRO NISAR · RADAR DE APERTURA SINTÉTICA</div>
        <Texto size={62} style={{fontFamily: F.display, fontWeight: 700, lineHeight: 1, marginTop: 6}}>Lo que ve el radar sobre el basural</Texto>
        <div style={{display: "flex", gap: 26, marginTop: 14, fontFamily: F.sans, fontSize: 24, color: "#fff"}}>
          <span><span style={{display: "inline-block", width: 18, height: 18, borderRadius: 4, background: "#e6f6fb", marginRight: 8, verticalAlign: -2}} />suelo estable</span>
          <span><span style={{display: "inline-block", width: 18, height: 18, borderRadius: 4, background: "#0b1a26", border: "1px solid #5fc0dc", marginRight: 8, verticalAlign: -2}} />suelo que cambia</span>
        </div>
        <div style={{display: "flex", gap: 10, marginTop: 18}}>
          {chips.map((c, k) => <Pill key={c} v={spring({frame: f - r0 - 20 - k * 6, fps, config: {damping: 14}})}>{c}</Pill>)}
        </div>
      </div>
      <TituloSeccion titulo="Dumpsite" bajada="Una plataforma que sigue basurales desde el espacio" salida={s(2.2)} />
      <Creditos items={[radar < 0.5 ? OPTICO_ES : RADAR_ES]} />
    </AbsoluteFill>
  );
};

/* 3 · Insomnio: cambia, coherencia, mapa */
const Insomnio: React.FC<{dur: number; tB: number; tC: number}> = ({dur, tB, tC}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const n = dur * fps;
  const b0 = s(tB), c0 = s(tC);
  const aIni = 16;
  const porImagen = Math.max(8, Math.floor((b0 - aIni - 8) / serie.imagenes.length));
  const idx = Math.min(serie.imagenes.length - 1, Math.max(0, Math.floor((f - aIni) / porImagen)));
  const fundido = interpolate((f - aIni) - idx * porImagen, [0, 6], [0, 1], clamp);
  const partA = interpolate(f, [aIni - 4, aIni + 6, b0 - 6, b0 + 4], [0, 1, 1, 0], clamp);
  const partB = interpolate(f, [b0, b0 + 8, c0 - 6, c0 + 4], [0, 1, 1, 0], clamp);
  const bIni = b0 + s(2.5);
  const paso = 7;
  const visibles = Math.floor(interpolate(f, [bIni, bIni + paso * pasadas.length], [0, pasadas.length], clamp));
  const despiertos = pasadas.slice(0, visibles).filter((p) => p.despierto).length;
  const puntaje = spring({frame: f - (bIni + paso * pasadas.length + 10), fps, config: {damping: 14}});
  const c = cajaNorte3EnAmba();
  const ease = Easing.inOut(Easing.cubic);
  const vista = {cx: interpolate(f, [c0, c0 + 50], [c.cx, 0.55], {...clamp, easing: ease}), cy: interpolate(f, [c0, c0 + 50], [c.cy, 0.5], {...clamp, easing: ease}),
    zoom: zoomExp(f, [c0, c0 + 50], 1 / c.ancho, 1.25, Easing.inOut(Easing.poly(4))) * interpolate(f, [c0 + 50, n], [1, 1.08], clamp)};
  const mapa = interpolate(f, [c0 - 4, c0 + 8], [0, 1], clamp);
  const lado = 640, tile = 132;
  return (
    <AbsoluteFill style={{background: "radial-gradient(ellipse at 50% 45%, #0d1824 0%, #05080c 70%)"}}>
      <AbsoluteFill style={{opacity: partA}}>
        <div style={{position: "absolute", left: 960 - lado / 2 - 120, top: 140, width: lado, height: lado, borderRadius: 18, overflow: "hidden", boxShadow: "0 30px 90px rgba(0,0,0,0.7)", border: "1px solid rgba(255,255,255,0.18)"}}>
          {idx > 0 && <Img src={staticFile(serie.imagenes[idx - 1].archivo)} style={{position: "absolute", inset: 0, width: "100%", height: "100%"}} />}
          <Img src={staticFile(serie.imagenes[idx].archivo)} style={{position: "absolute", inset: 0, width: "100%", height: "100%", opacity: fundido}} />
          <Poligono pts={serie.poligono} relleno="transparent" borde="rgba(255,165,61,0.9)" grosor={2.5} />
          <Texto size={48} style={{position: "absolute", left: 18, top: 14, fontFamily: F.display, fontWeight: 700}}>{fechaCorta(serie.imagenes[idx].fecha).replace("Jun", "jun").replace("Aug", "ago").replace("Sep", "sep").replace("Oct", "oct").replace("Jul", "jul")}</Texto>
        </div>
        <div style={{position: "absolute", left: 960 + lado / 2 - 80, top: 170, width: 420}}>
          <Texto size={34}><b style={{color: C.glow}}>Mismo basural,</b><br />{serie.imagenes.length} fechas.</Texto>
          <Texto size={24} color="rgba(231,235,241,0.75)" style={{marginTop: 8}}>Imágenes Sentinel-2 reales de Norte III, entre junio y octubre de 2026.</Texto>
        </div>
        <div style={{position: "absolute", left: 960 + lado / 2 - 80, top: 420, display: "grid", gridTemplateColumns: "repeat(3, 104px)", gap: 10}}>
          {serie.imagenes.map((im, k) => (
            <div key={im.fecha} style={{width: 104, height: 104, borderRadius: 8, overflow: "hidden", outline: k === idx ? `3px solid ${C.glow}` : "1px solid rgba(255,255,255,0.2)", opacity: k <= idx ? 1 : 0.35}}>
              <Img src={staticFile(im.archivo)} style={{width: "100%", height: "100%"}} />
            </div>
          ))}
        </div>
      </AbsoluteFill>
      <AbsoluteFill style={{opacity: partB}}>
        <div style={{position: "absolute", left: 0, right: 0, top: 170, textAlign: "center"}}>
          <Texto size={58} style={{fontFamily: F.display, fontWeight: 700}}>Coherencia = qué tan parecidas son dos pasadas</Texto>
          <Texto size={28} color="rgba(231,235,241,0.8)" style={{marginTop: 6}}>1 · nada cambió &nbsp;&nbsp;→&nbsp;&nbsp; 0 · cambió todo</Texto>
        </div>
        <div style={{position: "absolute", top: 330, left: (ANCHO - pasadas.length * (tile + 16)) / 2, display: "flex", gap: 16}}>
          {pasadas.map((p, k) => {
            const v = spring({frame: f - bIni - k * paso, fps, config: {damping: 13, mass: 0.5}});
            const H = 110;
            return (
              <div key={p.fecha} style={{width: tile, height: 250, borderRadius: 14, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "flex-end", gap: 8, paddingBottom: 12,
                opacity: v, transform: `translateY(${(1 - v) * 40}px)`, background: "rgba(255,165,61,0.12)", border: "2px solid rgba(255,165,61,0.7)"}}>
                <Ojo despierto={p.despierto} tam={64} />
                <svg width={90} height={H + 4}>
                  <rect x={14} y={H - p.anillo * H * v} width={24} height={p.anillo * H * v} rx={3} fill="rgba(95,192,220,0.75)" />
                  <rect x={52} y={H - p.sitio * H * v} width={24} height={p.sitio * H * v} rx={3} fill={C.glow} />
                </svg>
                <div style={{fontFamily: F.sans, fontWeight: 600, fontSize: 22, color: "#fff"}}>{fechaCorta(p.fecha).replace("Jul", "jul").replace("Aug", "ago").replace("Sep", "sep").replace("Oct", "oct")}</div>
              </div>
            );
          })}
        </div>
        <div style={{position: "absolute", left: 0, right: 0, top: 596, display: "flex", justifyContent: "center", gap: 30, fontFamily: F.sans, fontSize: 22, color: "rgba(231,235,241,0.85)"}}>
          <span><span style={{display: "inline-block", width: 14, height: 14, background: "rgba(95,192,220,0.75)", borderRadius: 3, marginRight: 6}} />entorno</span>
          <span><span style={{display: "inline-block", width: 14, height: 14, background: C.glow, borderRadius: 3, marginRight: 6}} />el basural, siempre más bajo</span>
        </div>
        <div style={{position: "absolute", left: 0, right: 0, top: 640, display: "flex", justifyContent: "center", alignItems: "center", gap: 70}}>
          <Texto size={38} style={{opacity: visibles > 0 ? 1 : 0}}>inquieto en <b style={{color: C.glow, fontSize: 60}}>{despiertos}</b> de {pasadas.length} pasadas</Texto>
          <div style={{opacity: puntaje, transform: `scale(${0.7 + 0.3 * puntaje})`, textAlign: "center"}}>
            <div style={{fontFamily: F.display, fontWeight: 700, fontSize: 130, lineHeight: 0.9, color: C.glow, textShadow: "0 0 40px rgba(255,165,61,0.5)"}}>{(n3.insomnio as number).toFixed(2).replace(".", ",")}</div>
            <Texto size={24} color="rgba(231,235,241,0.9)">índice de insomnio · Norte III</Texto>
          </div>
        </div>
      </AbsoluteFill>
      {mapa > 0 && (
        <AbsoluteFill style={{opacity: mapa}}>
          <MapaAmba vista={vista}>{(px) => <path d={caminoPoligono(n3.poligono_amba as number[][], px)} fill="none" stroke={C.glow} strokeWidth={2} />}</MapaAmba>
          <div style={{position: "absolute", left: 0, top: 0, width: 1250, height: 330, background: "radial-gradient(ellipse at 0% 0%, rgba(5,8,12,0.9) 0%, rgba(5,8,12,0.4) 55%, rgba(5,8,12,0) 80%)"}} />
          <div style={{position: "absolute", left: 48, top: 150, opacity: interpolate(f, [c0 + 18, c0 + 30], [0, 1], clamp)}}>
            <Texto size={58} style={{fontFamily: F.display, fontWeight: 700}}>Todo el Gran Buenos Aires, píxel por píxel</Texto>
            <div style={{display: "flex", gap: 10, marginTop: 14}}>
              {["219 manchas candidatas", "sin agua (JRC)", "sin rutas ni arroyos", "sin cultivos estacionales"].map((c, k) => (
                <Pill key={c} color={k === 0 ? "rgba(255,165,61,0.8)" : undefined} v={spring({frame: f - c0 - 30 - k * 6, fps, config: {damping: 14}})}>{c}</Pill>
              ))}
            </div>
          </div>
        </AbsoluteFill>
      )}
      <TituloSeccion titulo="Insomnio" bajada="Cuánto cambia el suelo, pasada tras pasada" salida={14} />
      <Creditos items={[f < b0 ? OPTICO_ES : RADAR_ES]} />
    </AbsoluteFill>
  );
};

/* 4 · Casos reales en la web: Luján, Norte III, González Catán */
const Casos: React.FC<{dur: number; t2: number}> = ({dur, t2}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const n = dur * fps;
  const corte = s(t2) + s(1.6);
  const fichas = [
    {img: "web/es-ficha-lujan.png", desde: 0, hasta: s(t2), nombre: "Basural de Luján", lineas: ["cerrado el 1 de julio de 2026", "quieto en las 15 pasadas", "insomnio 0 %"], color: C.radar},
    {img: "web/es-ficha-norte3.png", desde: s(t2), hasta: corte, nombre: "Norte III (CEAMSE)", lineas: ["relleno activo", "insomnio 86 %"], color: C.glow},
    {img: "web/es-ficha-catan.png", desde: corte, hasta: n + 1, nombre: "González Catán", lineas: ["sin registro abierto", "insomnio 100 %"], color: C.glow},
  ];
  const k = fichas.findIndex((x) => f >= x.desde && f < x.hasta);
  const x = fichas[Math.max(0, k)];
  const v = spring({frame: f - x.desde, fps, config: {damping: 16}});
  return (
    <AbsoluteFill style={{background: "radial-gradient(ellipse at 40% 55%, #13202d 0%, #05080c 72%)"}}>
      <div style={{position: "absolute", left: 90, top: 190, width: 1180, height: 664, borderRadius: 16, overflow: "hidden", boxShadow: "0 40px 120px rgba(0,0,0,0.7), 0 0 0 1px rgba(255,255,255,0.12)",
        transform: `perspective(1800px) rotateY(${6 - 4 * v}deg) scale(${0.97 + 0.03 * v})`}}>
        <div style={{height: 36, background: "#1a222e", display: "flex", alignItems: "center", gap: 8, padding: "0 14px"}}>
          {["#ff5f57", "#febc2e", "#28c840"].map((c) => <span key={c} style={{width: 12, height: 12, borderRadius: 6, background: c}} />)}
          <span style={{marginLeft: 14, fontFamily: F.mono, fontSize: 14, color: "#8e99a8"}}>{RESULTADOS.url}</span>
        </div>
        {fichas.map((y, i) => <Img key={y.img} src={staticFile(y.img)} style={{position: "absolute", top: 36, left: 0, width: 1180, opacity: i === k ? Math.min(1, v * 1.5) : 0}} />)}
      </div>
      <div style={{position: "absolute", left: 1330, top: 240, width: 520, opacity: Math.min(1, v * 1.5), transform: `translateX(${(1 - v) * 40}px)`}}>
        <Texto size={58} style={{fontFamily: F.display, fontWeight: 700, color: x.color}}>{x.nombre}</Texto>
        {x.lineas.map((l) => <Texto key={l} size={32} style={{marginTop: 10}}>{l}</Texto>)}
      </div>
      <TituloSeccion titulo="Casos reales" bajada="Lo que dice el registro contra lo que ve el radar" salida={14} />
      <Creditos items={[RADAR_ES, OPTICO_ES]} />
    </AbsoluteFill>
  );
};

/* 5 · Datos: catálogo mundial y lo que se le parece */
const Datos: React.FC<{dur: number; t2: number}> = ({dur, t2}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const b0 = s(t2);
  const cuenta = Math.round(entreno.total_catalogo * interpolate(f, [24, s(5)], [0, 1], {...clamp, easing: Easing.out(Easing.cubic)}));
  const fuentes = [["OpenStreetMap · Overture", "polígonos de rellenos"], ["Climate TRACE", "emisiones por sitio"], ["EPA LMOP (EE. UU.)", "rellenos registrados"], ["NASA EMIT", "plumas de metano"]];
  const parecidos = [{t: "canteras", img: "chip-tres-febrero.jpg"}, {t: "aeródromos", img: "chip-el-palomar.jpg"}, {t: "campos de golf"}, {t: "parques"}];
  const ch = 98, cols = 7;
  return (
    <AbsoluteFill style={{background: "radial-gradient(ellipse at 45% 55%, #0d1a26 0%, #05080c 70%)"}}>
      <div style={{position: "absolute", left: 90, top: 190, display: "grid", gridTemplateColumns: `repeat(${cols}, ${ch}px)`, gap: 9, opacity: interpolate(f, [b0, b0 + 12], [1, 0.25], clamp)}}>
        {entreno.muestras.slice(0, 28).map((m, k) => {
          const v = spring({frame: f - 14 - (k % 7) * 1.5 - Math.floor(k / 7) * 2, fps, config: {damping: 14, mass: 0.5}});
          return (
            <div key={m.archivo} style={{width: ch, height: ch, borderRadius: 9, overflow: "hidden", opacity: v, transform: `scale(${0.6 + 0.4 * v})`, position: "relative", border: "1px solid rgba(255,255,255,0.25)"}}>
              <Img src={staticFile(m.archivo)} style={{width: "100%", height: "100%"}} />
              <div style={{position: "absolute", left: 5, bottom: 3, fontFamily: F.mono, fontSize: 12, color: "#fff", textShadow: "0 1px 3px #000"}}>{m.pais}</div>
            </div>
          );
        })}
      </div>
      <div style={{position: "absolute", left: 1030, top: 190, width: 820}}>
        <div style={{fontFamily: F.display, fontWeight: 700, fontSize: 120, lineHeight: 0.9, color: C.glow, textShadow: "0 0 36px rgba(255,165,61,0.45)"}}>{cuenta.toLocaleString("es-AR")}</div>
        <Texto size={34}>basurales mapeados en todo el mundo</Texto>
        <div style={{display: "grid", gap: 10, marginTop: 24}}>
          {fuentes.map(([a, b], k) => {
            const v = spring({frame: f - s(2.5) - k * 8, fps, config: {damping: 14}});
            return <div key={a} style={{display: "flex", alignItems: "center", gap: 14, opacity: v, transform: `translateX(${(1 - v) * 30}px)`}}>
              <Pill color="rgba(255,165,61,0.7)">{a}</Pill><Texto size={22} color="rgba(231,235,241,0.75)">{b}</Texto></div>;
          })}
        </div>
      </div>
      <div style={{position: "absolute", left: 90, right: 70, top: 655, opacity: interpolate(f, [b0, b0 + 10], [0, 1], clamp)}}>
        <Texto size={34}>Y ejemplos de <b style={{color: C.radar}}>lo que se le parece</b>, de OpenStreetMap</Texto>
        <div style={{display: "flex", gap: 22, marginTop: 14}}>
          {parecidos.map((p, k) => {
            const v = spring({frame: f - b0 - 6 - k * 6, fps, config: {damping: 14}});
            return (
              <div key={p.t} style={{display: "flex", alignItems: "center", gap: 12, opacity: v, transform: `translateY(${(1 - v) * 20}px)`, padding: "8px 18px 8px 8px", borderRadius: 14,
                border: "1px solid rgba(95,192,220,0.5)", background: "rgba(10,25,36,0.8)"}}>
                {p.img ? <Img src={staticFile(p.img)} style={{width: 70, height: 70, borderRadius: 8}} /> : <div style={{width: 8}} />}
                <Texto size={28}>{p.t}</Texto>
              </div>
            );
          })}
        </div>
      </div>
      <TituloSeccion titulo="Los datos" bajada="Con qué aprende a reconocer un basural" salida={14} />
      <Creditos items={[["Catálogo", "OSM · Overture · Climate TRACE · EPA · NASA EMIT"]]} />
    </AbsoluteFill>
  );
};

/* 6 · Modelo: LightGBM */
const VARIABLES_ES = ["vegetación · NDVI", "suelo desnudo · BSI", "agua · NDWI", "infrarrojo · SWIR", "coherencia de radar", "forma de la mancha"];
const GRUPOS_ES = [{n: "radar NISAR", k: 12, c: "#5fc0dc"}, {n: "ópticas Sentinel-2", k: 11, c: "#9ad17a"}, {n: "de forma", k: 3, c: "#d7b4ff"}, {n: "del entorno", k: 3, c: "#ffd29a"}];
const CIUDADES = ["Ciudad de México", "Delhi", "Los Ángeles", "Ponce", "Yakarta", "Maryland", "New Hampshire", "Nueva York", "Ohio"];

const Modelo: React.FC<{dur: number; t2: number; t3: number}> = ({dur, t2, t3}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const n = dur * fps;
  const b0 = s(t2), c0 = s(t3);
  const cajaW = 640, cajaY = 290, cajaH = 350;
  const cajaX = (ANCHO - (cajaW + 70 + 540)) / 2;
  const salX = cajaX + cajaW + 70;
  const ejemplos = [{id: "norte3-disp", clase: "Basural", det: "clasificado por el modelo", ok: true}, {id: "el-palomar", clase: "Otra cosa", det: "un aeródromo", ok: false}, {id: "tres-febrero", clase: "Otra cosa", det: "una cantera", ok: false}];
  const val = interpolate(f, [c0 - 4, c0 + 8], [0, 1], clamp);
  const ciudadActiva = Math.floor((f - c0) / 9) % CIUDADES.length;
  return (
    <AbsoluteFill style={{background: "radial-gradient(ellipse at 45% 55%, #0d1a26 0%, #05080c 70%)"}}>
      {/* 29 variables */}
      <div style={{position: "absolute", left: 0, right: 0, top: 170, display: "flex", justifyContent: "center", gap: 18, opacity: interpolate(f, [14, 24], [0, 1], clamp)}}>
        <Texto size={34}><b style={{color: C.glow}}>29 variables</b> por mancha</Texto>
        {GRUPOS_ES.map((g, k) => {
          const v = spring({frame: f - 22 - k * 5, fps, config: {damping: 14}});
          return <div key={g.n} style={{display: "flex", alignItems: "center", gap: 8, opacity: v}}>
            <div style={{width: g.k * 14, height: 22, borderRadius: 5, background: g.c}} /><Texto size={22}><b>{g.k}</b> {g.n}</Texto></div>;
        })}
      </div>
      <div style={{position: "absolute", left: cajaX, top: cajaY, width: cajaW, height: cajaH, borderRadius: 22, border: "2px solid rgba(191,239,255,0.55)",
        background: "linear-gradient(160deg, rgba(95,192,220,0.16), rgba(10,20,30,0.85))", boxShadow: "0 0 50px rgba(95,192,220,0.25)", opacity: 1 - val * 0.75}}>
        <div style={{position: "absolute", left: 24, top: 16, fontFamily: F.display, fontWeight: 700, fontSize: 52, color: "#fff"}}>LightGBM</div>
        <div style={{position: "absolute", right: 24, top: 30, fontFamily: F.mono, fontSize: 16, color: "rgba(191,239,255,0.8)"}}>árboles de decisión con boosting</div>
        <div style={{position: "absolute", left: 24, right: 24, top: 92, display: "flex", flexWrap: "wrap", gap: 8}}>
          {VARIABLES_ES.map((x, k) => <Pill key={x} v={spring({frame: f - 30 - k * 4, fps, config: {damping: 14}})}>{x}</Pill>)}
        </div>
        <div style={{position: "absolute", left: 24, right: 24, top: 236, display: "flex", alignItems: "center", gap: 2}}>
          {Array.from({length: 6}).map((_, k) => (
            <React.Fragment key={k}>
              <Arbol v={spring({frame: f - b0 - k * 5, fps, config: {damping: 14}})} color={k % 3 === 0 ? C.glow : "#5fc0dc"} activo={f > b0 && Math.floor(f / 5) % 6 === k} />
              {k < 5 && <span style={{fontFamily: F.mono, fontSize: 22, color: "rgba(231,235,241,0.5)"}}>+</span>}
            </React.Fragment>
          ))}
          <span style={{fontFamily: F.mono, fontSize: 22, color: "#fff", marginLeft: 8, opacity: interpolate(f, [b0 + 30, b0 + 40], [0, 1], clamp)}}>… × 300</span>
        </div>
      </div>
      <AbsoluteFill style={{opacity: interpolate(f, [b0 + 20, b0 + 32], [0, 1], clamp) * (1 - val * 0.75)}}>
        {[{t: "Basural", c: C.glow, y: 270}, {t: "Otra cosa", c: C.radar, y: 490}].map((x) => (
          <div key={x.t} style={{position: "absolute", left: salX, top: x.y, width: 540, height: 190, borderRadius: 16, border: `2px dashed ${x.c}`, background: "rgba(5,8,12,0.4)"}}>
            <div style={{position: "absolute", left: 18, top: 8, fontFamily: F.display, fontWeight: 700, fontSize: 38, color: x.c}}>{x.t}</div>
          </div>
        ))}
        {ejemplos.map((e, k) => {
          const inicio = b0 + 26 + k * 16;
          const sale = spring({frame: f - inicio, fps, config: {damping: 14}});
          const otros = ejemplos.filter((x) => x.ok === e.ok).indexOf(e);
          return sale > 0.01 ? (
            <div key={e.id} style={{position: "absolute", left: salX + 20 + otros * 262, top: (e.ok ? 270 : 490) + 66, display: "flex", alignItems: "center", gap: 12, opacity: sale, transform: `translateX(${(1 - sale) * -60}px)`}}>
              <Img src={staticFile(`chip-${e.id}.jpg`)} style={{width: 100, height: 100, borderRadius: 10, border: `3px solid ${e.ok ? C.glow : "rgba(191,239,255,0.6)"}`}} />
              <Texto size={19} color="rgba(231,235,241,0.85)" style={{width: 120}}>{e.det}</Texto>
            </div>
          ) : null;
        })}
      </AbsoluteFill>
      {/* validación por ciudad */}
      <div style={{position: "absolute", left: 0, right: 0, top: 660, textAlign: "center", opacity: val}}>
        <Texto size={34}>Validación: se deja <b style={{color: C.glow}}>una ciudad entera afuera</b> y se predice esa</Texto>
        <div style={{display: "flex", justifyContent: "center", flexWrap: "wrap", gap: 10, marginTop: 14}}>
          {CIUDADES.map((cname, k) => (
            <span key={cname} style={{fontFamily: F.sans, fontSize: 20, padding: "6px 14px", borderRadius: 999,
              border: `1px solid ${k === ciudadActiva ? C.glow : "rgba(95,192,220,0.45)"}`, color: k === ciudadActiva ? "#05080c" : "#e7f6fb",
              background: k === ciudadActiva ? C.glow : "rgba(10,25,36,0.8)"}}>{k === ciudadActiva ? `prueba · ${cname}` : cname}</span>
          ))}
        </div>
      </div>
      <TituloSeccion titulo="LightGBM" bajada="¿Basural u otra cosa?" salida={12} />
      <Creditos items={[OPTICO_ES, RADAR_ES]} opacidad={interpolate(f, [20, 30, n - 6, n], [0, 1, 1, 0], clamp)} />
    </AbsoluteFill>
  );
};

/* 7 · Resultados reales (índice cruzado con catálogos) */
const REGIONES = ["Buenos Aires", "Los Ángeles", "Ciudad de México", "Delhi", "Yakarta", "Ponce", "Ohio", "Maryland", "New Hampshire", "Nueva York"];
const Resultados: React.FC<{dur: number}> = () => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const a = spring({frame: f - 10, fps, config: {damping: 15}});
  const b = spring({frame: f - s(4.2), fps, config: {damping: 15}});
  return (
    <AbsoluteFill style={{background: "radial-gradient(ellipse at 50% 50%, #13202d 0%, #05080c 72%)"}}>
      <div style={{position: "absolute", left: 0, right: 0, top: 200, display: "flex", justifyContent: "center", gap: 160, textAlign: "center"}}>
        <Grande v={a} valor="42" color={C.radar} texto="basurales de catálogo, activos en el radar" />
        <Grande v={b} valor="13" color={C.glow} texto="figuran cerrados y siguen activos" />
      </div>
      <div style={{position: "absolute", left: 0, right: 0, top: 560, textAlign: "center"}}>
        <div style={{display: "flex", justifyContent: "center", flexWrap: "wrap", gap: 10, maxWidth: 1500, margin: "0 auto"}}>
          {REGIONES.map((r, k) => <Pill key={r} v={spring({frame: f - 20 - k * 3, fps, config: {damping: 14}})}>{r}</Pill>)}
        </div>
        <div style={{fontFamily: F.mono, fontSize: 18, color: "rgba(231,235,241,0.6)", marginTop: 18}}>10 regiones · índice de insomnio cruzado con los catálogos · señal compatible con actividad, sin verificar en terreno</div>
      </div>
      <TituloSeccion titulo="Resultados" bajada="Diez regiones de tres continentes" salida={12} />
    </AbsoluteFill>
  );
};

/* 8 · Recorrido por la web */
const Web: React.FC<{dur: number}> = ({dur}) => {
  const f = useCurrentFrame();
  const n = dur * FPS;
  const pasos = [
    {img: "web/es-mapa-indice.png", t: "El mapa del índice de insomnio"},
    {img: "web/es-ficha-norte3.png", t: "La ficha de cada sitio, con su curva de coherencia"},
    {img: "web/es-sitios.png", t: "La lista con el registro oficial"},
    {img: "web/es-modelo.png", t: "Cómo decide el modelo"},
  ];
  const tramo = n / pasos.length;
  const k = Math.min(pasos.length - 1, Math.floor(f / tramo));
  const local = f - k * tramo;
  const fade = interpolate(local, [0, 8], [0, 1], clamp);
  const zoom = interpolate(local, [0, tramo], [1, 1.06], clamp);
  return (
    <AbsoluteFill style={{background: "radial-gradient(ellipse at 50% 55%, #13202d 0%, #05080c 72%)"}}>
      <div style={{position: "absolute", left: 160, top: 180, width: 1600, height: 900 * (1600 / 1600) * 0.5625 + 36, borderRadius: 16, overflow: "hidden",
        boxShadow: "0 40px 120px rgba(0,0,0,0.7), 0 0 0 1px rgba(255,255,255,0.12)"}}>
        <div style={{height: 36, background: "#1a222e", display: "flex", alignItems: "center", gap: 8, padding: "0 14px", position: "relative", zIndex: 2}}>
          {["#ff5f57", "#febc2e", "#28c840"].map((c) => <span key={c} style={{width: 12, height: 12, borderRadius: 6, background: c}} />)}
          <span style={{marginLeft: 14, fontFamily: F.mono, fontSize: 14, color: "#8e99a8"}}>{RESULTADOS.url}</span>
        </div>
        <div style={{position: "absolute", top: 36, left: 0, width: 1600, height: 900, overflow: "hidden"}}>
          {k > 0 && <Img src={staticFile(pasos[k - 1].img)} style={{position: "absolute", width: 1600, height: 900}} />}
          <Img src={staticFile(pasos[k].img)} style={{position: "absolute", width: 1600, height: 900, opacity: fade, transform: `scale(${zoom})`, transformOrigin: "50% 40%"}} />
        </div>
      </div>
      <div style={{position: "absolute", left: 160, top: 120, display: "flex", gap: 12}}>
        {pasos.map((p, i) => (
          <span key={p.img} style={{fontFamily: F.sans, fontSize: 22, padding: "6px 16px", borderRadius: 999, border: `1px solid ${i === k ? C.glow : "rgba(231,235,241,0.3)"}`,
            color: i === k ? "#05080c" : "rgba(231,235,241,0.8)", background: i === k ? C.glow : "rgba(10,18,26,0.8)"}}>{p.t}</span>
        ))}
      </div>
      <TituloSeccion titulo="La web" bajada={RESULTADOS.url} salida={12} />
    </AbsoluteFill>
  );
};

/* 9 · Fuentes y cierre */
const FUENTES = [
  ["NISAR GUNW y GCOV", "NASA / ISRO · vía ASF DAAC", "coherencia y eco de radar"],
  ["Sentinel-2 L2A", "ESA Copernicus · Planetary Computer · EOX", "imágenes ópticas e índices"],
  ["JRC Global Surface Water", "Comisión Europea", "máscara de agua"],
  ["OpenStreetMap · Overture Maps", "ODbL", "polígonos de rellenos y de lo que se les parece"],
  ["Climate TRACE", "CC BY 4.0", "emisiones por sitio"],
  ["EPA LMOP", "dominio público", "rellenos registrados en EE. UU."],
  ["NASA EMIT", "LP DAAC", "plumas de metano"],
];
const Cierre: React.FC<{dur: number; tLema: number}> = ({dur, tLema}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const n = dur * fps;
  const l0 = s(tLema);
  const fin = interpolate(f, [l0 - 6, l0 + 8], [0, 1], clamp);
  const letras = "DUMPSITE".split("");
  return (
    <AbsoluteFill style={{background: "radial-gradient(ellipse at 50% 50%, #0f1b27 0%, #05080c 72%)"}}>
      <AbsoluteFill style={{opacity: 1 - fin}}>
        <div style={{position: "absolute", left: 90, top: 170}}>
          <Texto size={44} style={{fontFamily: F.display, fontWeight: 700}}>Solo datos abiertos</Texto>
          <div style={{display: "grid", gap: 10, marginTop: 16}}>
            {FUENTES.map(([a, b, c], k) => {
              const v = spring({frame: f - 8 - k * 4, fps, config: {damping: 15}});
              return <div key={a} style={{display: "grid", gridTemplateColumns: "330px 390px 360px", gap: 16, alignItems: "baseline", opacity: v, transform: `translateX(${(1 - v) * -30}px)`}}>
                <Texto size={24} style={{fontWeight: 600}}>{a}</Texto><Texto size={18} color="rgba(191,239,255,0.8)" style={{fontFamily: F.mono}}>{b}</Texto><Texto size={20} color="rgba(231,235,241,0.7)">{c}</Texto></div>;
            })}
          </div>
          <div style={{fontFamily: F.mono, fontSize: 16, color: "rgba(231,235,241,0.55)", marginTop: 18}}>Contenido generado con IA: clip inicial (Higgsfield) y voz sintética (Azure AI Speech).</div>
        </div>
        <div style={{position: "absolute", right: 80, top: 230, display: "grid", gap: 16, justifyItems: "end"}}>
          <Texto size={28}>Código, modelo y datos, publicados</Texto>
          {[{i: "▶", e: "Mapa en vivo", v: RESULTADOS.url, c: C.glow}, {i: "</>", e: "Código y modelo", v: RESULTADOS.repo, c: C.radar}].map((x, k) => {
            const v = spring({frame: f - 20 - k * 8, fps, config: {damping: 13}});
            return <div key={x.v} style={{display: "flex", alignItems: "center", gap: 14, padding: "12px 24px", borderRadius: 999, background: "rgba(10,18,26,0.9)", border: `2px solid ${x.c}`,
              boxShadow: `0 0 26px ${x.c}55`, opacity: v, transform: `translateX(${(1 - v) * 60}px)`}}>
              <span style={{fontFamily: F.mono, fontSize: 24, color: x.c}}>{x.i}</span><Texto size={20} color="rgba(231,235,241,0.7)">{x.e}</Texto>
              <span style={{fontFamily: F.mono, fontSize: 28, color: "#fff"}}>{x.v}</span></div>;
          })}
        </div>
      </AbsoluteFill>
      <AbsoluteFill style={{opacity: fin}}>
        <Img src={staticFile("nisar-coherencia-amplia.png")} style={{position: "absolute", left: -200, top: -620, width: 2320, height: 2320, filter: "blur(2px) brightness(0.25)", transform: `scale(${1 + (f - l0) * 0.001})`}} />
        <AbsoluteFill style={{background: "radial-gradient(circle at 50% 46%, rgba(5,8,12,0) 0%, rgba(5,8,12,0.85) 62%)"}} />
        <div style={{position: "absolute", left: 0, right: 0, top: 330, display: "flex", justifyContent: "center", gap: 6}}>
          {letras.map((l, k) => {
            const v = spring({frame: f - l0 - k * 2.5, fps, config: {damping: 11, mass: 0.7}});
            return <span key={k} style={{display: "inline-block", fontFamily: F.display, fontWeight: 700, fontSize: 220, lineHeight: 1, color: C.glow, opacity: Math.min(1, v * 1.4),
              transform: `translateY(${(1 - v) * 110}px) scale(${1 + (1 - v) * 0.7})`, textShadow: "0 0 50px rgba(255,165,61,0.55)"}}>{l}</span>;
          })}
        </div>
        <Texto size={46} style={{position: "absolute", left: 0, right: 0, top: 590, textAlign: "center", opacity: interpolate(f, [l0 + 20, l0 + 32], [0, 1], clamp)}}>Los basurales que el radar nunca ve quietos</Texto>
        <div style={{position: "absolute", left: 0, right: 0, top: 680, textAlign: "center", fontFamily: F.mono, fontSize: 26, color: C.radar, opacity: interpolate(f, [l0 + 30, l0 + 40], [0, 1], clamp)}}>
          {RESULTADOS.url} · {RESULTADOS.repo}
        </div>
        <div style={{position: "absolute", left: 0, right: 0, bottom: 40, textAlign: "center", fontFamily: F.mono, fontSize: 18, letterSpacing: 2, color: "rgba(231,235,241,0.6)",
          opacity: interpolate(f, [l0 + 36, n], [0, 1], clamp)}}>NASA SPACE APPS 2026 · DANCING WITH THE SARS · BUENOS AIRES</div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

/* Composición */
export const DumpsiteLocal: React.FC = () => {
  const t = (id: string) => fr(id).inicio;
  const tramos: [string, number, number][] = [
    ["ia", 0, CLIP_IA],
    ["problema", CLIP_IA, t("dumpsite") - 0.6],
    ["pulso", t("dumpsite") - 0.6, t("dumpsite")],
    ["dumpsite", t("dumpsite"), t("cambia")],
    ["insomnio", t("cambia"), t("casos")],
    ["casos", t("casos"), t("datos")],
    ["datos", t("datos"), t("modelo")],
    ["modelo", t("modelo"), t("resultados")],
    ["resultados", t("resultados"), t("web")],
    ["web", t("web"), t("cierre")],
    ["cierre", t("cierre"), DURACION_LOCAL],
  ];
  const seq = (id: string) => {
    const x = tramos.find((y) => y[0] === id)!;
    return {from: s(x[1]), durationInFrames: Math.max(1, s(x[2]) - s(x[1])), name: id, dur: x[2] - x[1]};
  };
  const S = (id: string, el: (dur: number) => React.ReactNode) => {
    const q = seq(id);
    return <Sequence key={id} from={q.from} durationInFrames={q.durationInFrames} name={q.name}>{el(q.dur)}</Sequence>;
  };
  return (
    <AbsoluteFill style={{background: C.bg}}>
      {S("ia", () => (
        <AbsoluteFill><OffthreadVideo src={staticFile("clip1-ai.mp4")} muted style={{width: ANCHO, height: ALTO, objectFit: "cover"}} /><AvisoIA texto="Imagen generada con IA" /><Equipo titulo="Equipo · NASA Space Apps 2026" dur={CLIP_IA} /></AbsoluteFill>
      ))}
      {S("problema", (d) => <Problema dur={d} t2={fr("problema").inicio + dentro("problema", "En Argentina") - CLIP_IA} />)}
      {S("pulso", (d) => <Pulso dur={d} />)}
      {S("dumpsite", (d) => <DumpsiteNisar dur={d} tNisar={dentro("dumpsite", "NISAR toma")} />)}
      {S("insomnio", (d) => <Insomnio dur={d} tB={t("coherencia") - t("cambia")} tC={t("mapa") - t("cambia")} />)}
      {S("casos", (d) => <Casos dur={d} t2={dentro("casos", "Norte Tres")} />)}
      {S("datos", (d) => <Datos dur={d} t2={dentro("datos", "Y le sumamos")} />)}
      {S("modelo", (d) => <Modelo dur={d} t2={dentro("modelo", "Cientos de")} t3={dentro("modelo", "Y lo validamos")} />)}
      {S("resultados", (d) => <Resultados dur={d} />)}
      {S("web", (d) => <Web dur={d} />)}
      {S("cierre", (d) => <Cierre dur={d} tLema={dentro("cierre", "Dumpsite")} />)}
      {VOZ_ES.frases.map((l) => (
        <Sequence key={l.archivo} from={s(l.inicio)} durationInFrames={s(l.duracion) + 3} name={`voz · ${l.id}`}><Html5Audio src={staticFile(l.archivo)} /></Sequence>
      ))}
      <Subtitulos frases={VOZ_ES.frases} max={105} />
    </AbsoluteFill>
  );
};
