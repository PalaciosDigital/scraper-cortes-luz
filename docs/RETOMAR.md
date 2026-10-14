# Retomar el proyecto (estado al 14 de octubre de 2026, tarde)

## Dónde vive

- **Repositorio (fuente de verdad):** `~/repos/scraper-cortes-luz`. Está fuera de iCloud y tiene git.
- La carpeta de iCloud `07_BUSCADOR_CORTES_DE_LUZ/02_PIPELINE` quedó como **copia antigua**: no editarla.

## Qué está listo

- **Scraper de CNEL** (`pipeline/fuentes/cnel.py`): probado con las emergencias de Santa Elena
  (marzo) y Esmeraldas (mayo) → 815 registros, sin descartes.
- **Vigilante** (`python -m pipeline.vigilar`): 14 páginas de CNEL, línea base en
  `data/vigilancia/estado.json`, un candidato y una aprobación. Ver `docs/FLUJO.md`.
- **Workflows**: `vigilar.yml` (cron cada hora de 6:00 a 22:00, commit de `data/`, issue) y `aprobar.yml` (botón).
- 52 tests (`pytest -q`).

## Modelo de publicación (como Mazar)

El buscador en Xalok lee
`https://raw.githubusercontent.com/<cuenta>/scraper-cortes-luz/main/data/cortes_luz_publicado.json`.
`config.yaml → vigilancia.publicacion: revision` (los datos nuevos esperan aprobación).

## CentroSur (primera fuente oficial, 2026-10-14)

- Tabla GeneXus de su extranet, leída por HTTP (`pipeline/fuentes/centrosur.py`). 65 filas, 8 ANU excluidos.
- **Bloqueante para publicar:** solo 2 de 57 cortes traen el cantón en el texto. Hay que completar
  `data/alimentadores_centrosur.csv` (21 alimentadores con direcciones de ejemplo).
- Pendiente de confirmar con CentroSur: significado de PRO / EMM / PAR / ANU.

## Siguientes pasos

1. Subir el repo a GitHub siguiendo `docs/GITHUB.md`. Falta definir la **cuenta** (¿la de Mazar, `tefaceli`?).
2. Buscador HTML (`01_HTML/PROTOTIPO.html`): `DATA_URL` → la URL de arriba, y después `/inyecta_a_Xalok`.
3. Completar `data/alimentadores_centrosur.csv` (cantón de cada alimentador).
4. Más subcentrales/distribuidoras: añadir a `config.yaml → vigilancia.paginas`; si el formato es nuevo,
   crear un módulo en `pipeline/fuentes/` + un fixture real + un test.

## Entorno

Mac Intel con Python 3.9: `pip install --only-binary=cryptography -r requirements.txt`. El venv va fuera de iCloud.
