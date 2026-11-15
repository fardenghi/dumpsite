import React from "react";
import {Composition} from "remotion";
import {ALTO, ANCHO, DURACION_S, FPS} from "./data";
import {DumpsiteIntl} from "../ingles/Video";
import {DURACION_LOCAL, DumpsiteLocal} from "../espanol/Local";

export const RemotionRoot: React.FC = () => (
  <>
    <Composition id="DumpsiteIntl" component={DumpsiteIntl} durationInFrames={Math.round(DURACION_S * FPS)} fps={FPS} width={ANCHO} height={ALTO} />
    <Composition id="DumpsiteLocal" component={DumpsiteLocal} durationInFrames={Math.round(DURACION_LOCAL * FPS)} fps={FPS} width={ANCHO} height={ALTO} />
  </>
);
