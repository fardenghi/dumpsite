# data/

Datos curados y livianos que usa el equipo. Los pesados (por ejemplo, los `.h5` de NISAR) no van acá ni al repo.

## basurales/
Catálogo de basurales y rellenos del mundo, armado el 14/11/2026 por `idea-basurales-nisar/herramientas/curar_basurales.py`. El objetivo es encontrar sitios que **en teoría están cerrados pero en la práctica siguen activos**.

| Archivo | Qué tiene |
|---|---|
| `basurales_mundo.json` (57 MB) | 66.981 sitios: 1.225 abiertos, 3.579 cerrados, 31 contradictorios y 62.146 sin estado conocido. 64.492 tienen área |
| `basurales_cerrados.json` | Solo los cerrados o en disputa, ordenados por `puntaje_sospecha` |
| `casos_curados_argentina.json` | 7 casos de Buenos Aires curados a mano (Luján, Norte III, González Catán, Ensenada, San Pedro, Navarro, Nueve de Julio) con notas y documentos, más los inventarios argentinos relacionados |

### Estructura
Cada archivo tiene `meta` (fuentes con licencia y cita, criterios, advertencias y conteos) y `sitios`. Cada sitio trae:
- `id`, `nombre`, `pais`, `lat`, `lon`, `tipo`
- `estado`: `abierto`, `cerrado`, `contradictorio` o `desconocido`, más `estados_por_fuente` con el motivo que da cada fuente
- `fecha_apertura`, `fecha_cierre`
- `area_m2`, `area_ha` y `area_origen`, que dice de qué fuente sale el área
- `operador`, `residuos`, `emisiones_climate_trace`
- `plumas_metano_emit` y `ultima_pluma_emit`
- `senales_cerrado_pero_activo`, con el tipo, el detalle y el peso de cada señal, y `puntaje_sospecha`
- `fuentes`: cada registro original con su `fuente`, `id_fuente`, `url` y sus datos, más las plumas de EMIT con su granulo y fecha

### Fuentes (citar todas)
| Clave | Fuente | Licencia |
|---|---|---|
| `osm` / `overture` | OpenStreetMap, con los polígonos sacados de Overture Maps release 2026-10-21.0 (`base/land_use`, `class=landfill`) | ODbL 1.0, © colaboradores de OpenStreetMap |
| `climate_trace` | Climate TRACE, subsector solid-waste-disposal, API v6 | CC BY 4.0 |
| `epa_lmop` | U.S. EPA LMOP Landfill and Project Database (2024-09) | Dominio público |
| `nasa_emit` | NASA EMIT L2B CH4PLM v002, doi:10.5067/EMIT/EMITL2BCH4PLM.002 | Sin restricciones |
| `curado_manual` | Notas y documentos citados en cada caso | La de cada fuente |

### Advertencias
- OSM casi nunca dice si un basural está activo, por eso la mayoría queda en `desconocido`.
- El metano no prueba actividad: un relleno cerrado emite durante décadas.
- Las señales sirven para priorizar qué mirar con NISAR. No son acusaciones: hablar de "señal compatible con actividad".
- Los sitios que solo están en OSM no traen país.

### Regenerar
Bajar las fuentes a un directorio (Overture con DuckDB, Climate TRACE por su API, el `.xlsx` de LMOP y los metadatos de EMIT por CMR) y correr:
```bash
cd idea-basurales-nisar/herramientas
python curar_basurales.py <dir_descargas> ../../data/basurales
```
