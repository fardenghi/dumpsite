// Datos reales, precalculados. `seed/sitios.json` lo escribe el pipeline del índice de insomnio
// (motor/pipeline_insomnio.py indice) con la forma exacta de `Sitio[]`:
// 15 pares de NISAR (GUNW, 80 m) sobre el AMBA, contornos de OpenStreetMap y registro con fuente.
// No se edita a mano: se regenera con ese comando.
import base from './seed/sitios.json'
import type { Sitio } from './types'

export const SITIOS = base as unknown as Sitio[]
