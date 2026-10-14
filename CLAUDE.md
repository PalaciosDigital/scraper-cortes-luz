# Buscador de cortes de luz — PRIMICIAS

Contexto para el agente de terminal. Léelo completo antes de tocar código.

## Qué es este proyecto

Un buscador interactivo de cortes de luz programados en Ecuador, publicado como
"elemento interactivo" dentro de un artículo de PRIMICIAS (CMS Xalok). El lector
elige provincia → cantón → sector y ve fecha y horario del corte.

- Prototipo publicado: https://primicias.s3.us-east-1.amazonaws.com/editorial/2026/gestio-diaria/octubre/maqueta-cortes-luz/PROTOTIPO.html
- JSON actual: https://primicias.s3.us-east-1.amazonaws.com/editorial/2026/Cortes+de+Luz+2026/cortes_luz_mayo_junio_2026.json
- Audiencia ~90 % móvil: cualquier cambio de interfaz es mobile-first.

Este repositorio contiene **el pipeline que mantiene actualizados los datos**:
descarga el PDF de la distribuidora → extrae tablas → normaliza → valida →
publica el JSON **en este mismo repositorio de GitHub** (modelo del scraper de
Mazar, `tefaceli/scraper-mazar`). El HTML del buscador vive en Xalok, no aquí.

## Cómo carga datos el buscador (importante)

El script del buscador (raíz `#pcl-app`) hace esto:

1. `DATA_URL` apunta a `https://raw.githubusercontent.com/<cuenta>/<repo>/main/data/cortes_luz_publicado.json`.
2. `fetch(DATA_URL, {cache: 'no-cache'})` con timeout de 2,5 s.
3. Si falla, usa `var DATA = [...]`, una copia embebida en el propio script (solo respaldo).

raw.githubusercontent.com envía `access-control-allow-origin: *` (el bucket S3
no), así que el fetch funciona dentro de Xalok. GitHub cachea 5 minutos.

Restricción de Xalok: el sanitizador elimina HTML dentro de strings JS. El
prototipo construye el DOM con `createElement`, nunca `innerHTML`. Mantén esa regla.

## Esquema de cada registro

Ver `schema/cortes_luz.schema.json` (fuente de verdad) y `docs/esquema.md`.

```json
{ "provincia": "AZUAY", "canton": "Cuenca", "alimentador": "0823: Turi Sector Patamaba",
  "fecha": "2026-06-06", "dia": "Sábado", "horario": "09:00 a 13:00",
  "tipo_trabajo": "Modificación de redes de medio voltaje",
  "zona_cortes": "0823: Turi Sector Patamaba",
  "sectores": "Vía 5 esquinas Punta Corral - Patapamba, Vía a Patapamba, Subida a El Verde" }
```

Los nueve campos actuales **no se renombran ni se eliminan**: el buscador
publicado depende de ellos. Se pueden **añadir** campos nuevos (p. ej.
`cantones`, `distribuidora`, `provincia_original`).

## Problemas conocidos en los datos de origen

Detectados en el JSON de mayo-junio (107 registros):

- `provincia` refleja la zona de servicio de la distribuidora, no la provincia
  política. Ejemplos: Macas → AZUAY, Joya de los Sachas y Francisco de Orellana →
  SUCUMBÍOS, Buena Fe → GUAYAS, Balao → EL ORO. Se corrige con
  `data/cantones_ecuador.csv` y se conserva el valor original en `provincia_original`.
- `canton` puede traer varios cantones: "Samborondón - Daule - Colimes - Balzar…",
  "Echeandía / Las Naves / Guaranda". Se separan en `cantones: [...]`.
- `zona_cortes` difiere de `alimentador` en 26 de 107 registros. No es un error,
  pero no asumas que son iguales.
- Horarios pueden cruzar medianoche ("23:00 a 01:00").
- Grafías sin tilde ("Quininde"). Normaliza contra el catálogo de cantones.

## Arquitectura del pipeline

```
pipeline/
  main.py         orquestador (CLI)
  descargar.py    baja el PDF y calcula SHA-256
  extraer.py      pdfplumber → filas crudas (con modo --inspeccionar)
  normalizar.py   filas crudas → registros del esquema
  validar.py      reglas de calidad; si falla, NO se publica
  publicar.py     sube a S3 (ruta antigua de main.py; el flujo actual no la usa)
  vigilar.py      vigilancia de páginas + candidato + aprobación (el flujo actual)
  fuentes/        un extractor por fuente web (cnel.py)
```

Datos versionados en `data/` (los escribe GitHub Actions; no editarlos a mano):

- `data/cortes_luz_publicado.json` ← lo que lee el buscador
- `data/cortes_luz_vigentes.json`  ← candidato pendiente de aprobación
- `data/vigilancia/estado.json`    ← línea base: PDFs ya vistos por página
- `data/vigilancia/registros/`     ← registros extraídos de cada PDF (por SHA-256)

## Reglas para el agente

- **Nunca** escribas `data/cortes_luz_publicado.json` sin pasar `validar.py`.
- `vigilancia.publicacion` está en `revision`: los datos nuevos esperan el botón
  «Aprobar publicación». No lo cambies a `directa` sin que Diego lo pida.
- No borres `data/vigilancia/estado.json`: sin él, la siguiente pasada registra
  todo como línea base y no procesa lo que haya vigente.
- No subas credenciales al repo.
- Antes de cambiar `extraer.py`, ejecuta `python -m pipeline.main --inspeccionar`
  sobre un PDF real y mira la estructura de las tablas.
- Cada cambio en normalización o validación lleva un test en `tests/`.
- Ejecuta `pytest -q` antes de dar una tarea por terminada.
- Respuestas y comentarios de código en español.

## Comandos útiles

```bash
pip install -r requirements.txt
python -m pipeline.main --inspeccionar --pdf ruta/al.pdf   # ver tablas del PDF
python -m pipeline.main --local --pdf ruta/al.pdf           # todo el flujo, sin subir a S3
python -m pipeline.main                                     # descarga + publica en staging
python -m pipeline.main --produccion                        # publica en el JSON vivo
pytest -q
bash scripts/descargar_linea_base.sh                        # baja JSON y prototipo actuales
python -m pipeline.scrapear --listar                        # PDFs publicados en cada fuente web
python -m pipeline.scrapear --historico                     # prototipo scraper, solo local
python -m pipeline.vigilar                                  # una pasada de vigilancia (ver docs/FLUJO.md)
python -m pipeline.vigilar --aprobar                        # publica el candidato pendiente
```

Flujo automático completo, códigos de salida y cómo añadir una fuente: `docs/FLUJO.md`.
Puesta en marcha en GitHub: `docs/GITHUB.md`.

Fuentes web (`config.yaml → fuentes_web`, extractores en `pipeline/fuentes/`):
CNEL EP publica cronogramas emergentes de Santa Elena y Esmeraldas en páginas
WordPress estáticas; el formato del PDF está documentado en `pipeline/fuentes/cnel.py`.
"Trabajos programados" de CNEL estaba vacío al 2026-10-14.


## Pendientes

La hoja de ruta con casillas está en `docs/PLAN.md`. Lo más urgente:
**falta la URL del PDF de origen** (`config.yaml → fuente.pdf_url`).
