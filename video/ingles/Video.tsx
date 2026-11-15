import React from "react";
import {AbsoluteFill, Html5Audio, Sequence, staticFile} from "remotion";
import {ESCENAS, FPS, FRASES} from "../compartido/data";
import {C} from "../compartido/theme";
import {Subtitulos} from "../compartido/components/Overlays";
import {EscenaIA, EscenaInsomnia, EscenaNisar, EscenaRed, EscenaResultados, Transicion} from "../compartido/escenas/Escenas";

const s = (seg: number) => Math.round(seg * FPS);
const tramo = (e: {desde: number; hasta: number}) => ({from: s(e.desde), durationInFrames: Math.max(1, s(e.hasta) - s(e.desde))});
const dur = (e: {desde: number; hasta: number}) => e.hasta - e.desde;

// Segundos (desde el inicio de la frase) en que empieza una parte, proporcional a los caracteres.
const inicioDe = (id: string, desde: string) => {
  const fr = FRASES.find((x) => x.id === id)!;
  return (fr.texto.indexOf(desde) / fr.texto.length) * fr.duracion;
};

export const DumpsiteIntl: React.FC = () => {
  const iaTotal = {desde: ESCENAS.ia.desde, hasta: ESCENAS.transicion.hasta};
  return (
    <AbsoluteFill style={{background: C.bg}}>
      <Sequence {...tramo(iaTotal)} name="1 · IA (Higgsfield)"><EscenaIA durTotal={dur(iaTotal)} /></Sequence>
      <Sequence {...tramo(ESCENAS.transicion)} name="Transición radar"><Transicion dur={dur(ESCENAS.transicion)} /></Sequence>
      <Sequence {...tramo(ESCENAS.nisar)} name="2 · NISAR"><EscenaNisar dur={dur(ESCENAS.nisar)} /></Sequence>
      <Sequence {...tramo(ESCENAS.insomnia)} name="3 · Insomnia">
        <EscenaInsomnia dur={dur(ESCENAS.insomnia)} inicioParte2={inicioDe("insomnia", "active dumps")} />
      </Sequence>
      <Sequence {...tramo(ESCENAS.red)} name="4 · Red neuronal">
        <EscenaRed dur={dur(ESCENAS.red)} inicioParte2={dur(ESCENAS.red) * 0.4} />
      </Sequence>
      <Sequence {...tramo(ESCENAS.resultados)} name="5 · Dumpsite"><EscenaResultados dur={dur(ESCENAS.resultados)} inicioLinks={inicioDe("resultados", "at the links")} /></Sequence>
      {FRASES.map((l) => (
        <Sequence key={l.archivo} from={s(l.inicio)} durationInFrames={s(l.duracion) + 3} name={`voz · ${l.id}`}>
          <Html5Audio src={staticFile(l.archivo)} />
        </Sequence>
      ))}
      <Subtitulos />
    </AbsoluteFill>
  );
};
