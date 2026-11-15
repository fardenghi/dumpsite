import React from "react";
import {AbsoluteFill, Img, staticFile} from "remotion";
import {ANCHO, ALTO, DATOS} from "../data";

const mercY = (lat: number) => Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 180 / 2));

// Box [west, south, east, north] -> normalized 0..1 coordinates within the AMBA box.
export const normAmba = (lon: number, lat: number): [number, number] => {
  const [w, s, e, n] = DATOS.caja_amba as number[];
  return [(lon - w) / (e - w), (mercY(n) - mercY(lat)) / (mercY(n) - mercY(s))];
};

export const cajaNorte3EnAmba = () => {
  const [w, s, e, n] = DATOS.caja_norte3 as number[];
  const [x0, y0] = normAmba(w, n);
  const [x1, y1] = normAmba(e, s);
  return {x0, y0, x1, y1, cx: (x0 + x1) / 2, cy: (y0 + y1) / 2, ancho: x1 - x0};
};

// Real aspect ratio of the AMBA box (2800 x 2010 px in Web Mercator).
const RELACION = 2010 / 2800;

export type Vista = {cx: number; cy: number; zoom: number};

// zoom = 1 shows the whole AMBA across the width of the frame.
export const MapaAmba: React.FC<{vista: Vista; indice?: number; s2?: number; children?: (px: (x: number, y: number) => [number, number], escala: number) => React.ReactNode}> =
  ({vista, indice = 1, s2 = 1, children}) => {
    const w = ANCHO * vista.zoom;
    const h = w * RELACION;
    const left = ANCHO / 2 - vista.cx * w;
    const top = ALTO / 2 - vista.cy * h;
    const px = (x: number, y: number): [number, number] => [left + x * w, top + y * h];
    return (
      <AbsoluteFill style={{overflow: "hidden", background: "#05080c"}}>
        <Img src={staticFile("s2-amba.jpg")} style={{position: "absolute", left, top, width: w, height: h, opacity: s2,
          filter: "saturate(0.55) brightness(0.62)"}} />
        <Img src={staticFile("insomnio-amba.png")} style={{position: "absolute", left, top, width: w, height: h, opacity: indice,
          filter: vista.zoom > 6 ? "blur(3px)" : undefined}} />
        {children && (
          <svg width={ANCHO} height={ALTO} style={{position: "absolute", inset: 0}}>{children(px, vista.zoom)}</svg>
        )}
      </AbsoluteFill>
    );
  };

export const caminoPoligono = (pts: number[][], px: (x: number, y: number) => [number, number]) =>
  pts.map(([x, y], i) => {
    const [a, b] = px(x, y);
    return `${i ? "L" : "M"}${a.toFixed(1)},${b.toFixed(1)}`;
  }).join(" ") + " Z";
