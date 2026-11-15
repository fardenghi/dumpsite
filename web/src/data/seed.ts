// Real, precomputed data. `seed/sitios.json` is written by the insomnia index pipeline
// (motor/pipeline_insomnio.py indice) with the exact shape of `Sitio[]`:
// 15 NISAR pairs (GUNW, 80 m) over the AMBA, OpenStreetMap outlines and the registry with its source.
// Not edited by hand: regenerate it with that command.
import base from './seed/sitios.json'
import type { Sitio } from './types'

export const SITIOS = base as unknown as Sitio[]
