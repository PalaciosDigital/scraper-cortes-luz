# Retomar el proyecto (estado al 14 de octubre de 2026)

## Dónde vive

- **Repositorio (fuente de verdad):** `~/repos/scraper-cortes-luz`. Está fuera de iCloud y tiene git.
- La carpeta de iCloud `07_BUSCADOR_CORTES_DE_LUZ/02_PIPELINE` quedó como **copia antigua**: no editarla.

## Qué está listo

- **Scraper de CNEL** (`pipeline/fuentes/cnel.py`): probado con las emergencias de Santa Elena
  (marzo) y Esmeraldas (mayo) → 815 registros, sin descartes.
- **Vigilante** (`python -m pipeline.vigilar`): 14 páginas de CNEL, línea base en
  `data/vigilancia/estado.json`, un candidato y una aprobación. Ver `docs/FLUJO.md`.
- **Workflows**: `vigilar.yml` (cron cada 3 h, commit de `data/`, issue) y `aprobar.yml` (botón).
- 45 tests (`pytest -q`).

## Modelo de publicación (como Mazar)

El buscador en Xalok lee
`https://raw.githubusercontent.com/<cuenta>/scraper-cortes-luz/main/data/cortes_luz_publicado.json`.
`config.yaml → vigilancia.publicacion: revision` (los datos nuevos esperan aprobación).

## Siguientes pasos

1. Subir el repo a GitHub siguiendo `docs/GITHUB.md`. Falta definir la **cuenta** (¿la de Mazar, `tefaceli`?).
2. Buscador HTML (`01_HTML/PROTOTIPO.html`): `DATA_URL` → la URL de arriba, y después `/inyecta_a_Xalok`.
3. **Link oficial con todas las subcentrales** → añadirlo a `config.yaml → vigilancia.paginas`,
   `python -m pipeline.scrapear --listar`, inspeccionar un PDF real, guardar un fixture + test.

## Entorno

Mac Intel con Python 3.9: `pip install --only-binary=cryptography -r requirements.txt`. El venv va fuera de iCloud.
