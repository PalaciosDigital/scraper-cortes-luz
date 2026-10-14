# Scraper de cortes de luz · PRIMICIAS

Mantiene actualizado el buscador de cortes de luz de PRIMICIAS (en Xalok), con el
mismo modelo que el scraper de Mazar:

**páginas de CNEL y CentroSur → GitHub Actions cada hora → `data/cortes_luz_publicado.json` → buscador en Xalok**

El buscador lee el JSON desde:

```
https://raw.githubusercontent.com/<cuenta>/<repo>/main/data/cortes_luz_publicado.json
```

## Cómo funciona

1. `pipeline/vigilar.py` revisa las páginas de `config.yaml → vigilancia.paginas`.
2. Si aparece un PDF nuevo, lo extrae, normaliza y valida.
3. Deja un **candidato** en `data/cortes_luz_vigentes.json` y abre un issue.
4. Una persona revisa y pulsa **Actions → Aprobar publicación → Run workflow**.
5. El candidato pasa a `data/cortes_luz_publicado.json`, y el buscador lo muestra en ≤ 5 min.

Detalle del flujo, avisos y reglas: [`docs/FLUJO.md`](docs/FLUJO.md).
Puesta en marcha en GitHub: [`docs/GITHUB.md`](docs/GITHUB.md).
Producción en servidores propios: [`docs/SERVIDOR.md`](docs/SERVIDOR.md).

## Cambiar la fuente

Edita `config.yaml → vigilancia.paginas` (se puede hacer desde la web de GitHub).
Si el PDF de la página nueva tiene otro formato, el issue lo avisa
("formato desconocido") y hace falta un extractor en `pipeline/fuentes/`.

## Trabajar en local

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install --only-binary=cryptography -r requirements.txt
pytest -q
python -m pipeline.scrapear --listar        # qué PDFs hay en cada página
python -m pipeline.vigilar                   # una pasada (escribe data/: no hagas commit de eso a mano)
```

## Estructura

```
config.yaml               páginas vigiladas, columnas, reglas de validación, modo de publicación
pipeline/vigilar.py       vigilancia + candidato + aprobación
pipeline/fuentes/cnel.py  listado y extractor de los PDFs de CNEL
pipeline/fuentes/centrosur.py  tabla GeneXus de CentroSur (HTTP)
data/alimentadores_centrosur.csv  alimentador → cantón (se completa a mano)
pipeline/                 descargar → extraer → normalizar → validar
data/                     estado y JSON versionados (los escribe GitHub Actions)
data/cantones_ecuador.csv catálogo cantón → provincia
tests/                    pytest + PDFs reales de CNEL
.github/workflows/        vigilar.yml (cron) y aprobar.yml (botón)
docs/                     FLUJO, GITHUB, PLAN, esquema
```
