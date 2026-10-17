# Hoja de ruta

Marca las casillas a medida que avances. El agente puede actualizar este archivo.

## Fase 0 — Preparación

- [x] Definir la URL del PDF de origen: resuelto el 2026-10-17 con la fuente
      oficial del Ministerio de Ambiente y Energía (un PDF por distribuidora,
      no uno nacional consolidado), vigilada como `mae-mantenimientos` con
      `prioridad: true`. Ver `docs/FLUJO.md → Fuente prioritaria`. La ruta
      `fuente.pdf_url`/`fuente.pdfs` de esta sección queda sin usar: el flujo
      real es el de vigilancia (`pipeline/vigilar.py`), no `pipeline/main.py`.
- [ ] Descargar la línea base: `bash scripts/descargar_linea_base.sh`.
- [ ] Guardar un PDF real de ejemplo en `tests/fixtures/ejemplo.pdf`.
- [ ] Completar `data/cantones_ecuador.csv` con el catálogo oficial del INEC
      (División Político Administrativa, 221 cantones).

## Fase 1 — Extracción local

- [ ] `python -m pipeline.main --inspeccionar --pdf tests/fixtures/ejemplo.pdf`
- [ ] Ajustar `config.yaml → columnas` con los encabezados reales del PDF.
- [ ] Ejecutar `--local` y comparar contra el JSON de mayo-junio
      (mismo número de registros para el mismo PDF, mismos campos).
- [ ] Si el PDF es escaneado: añadir OCR (`ocrmypdf` antes de pdfplumber).
- [ ] Si las tablas son irregulares: evaluar extracción asistida con la API de
      Claude (una página → JSON con el esquema). Dejarlo como respaldo, no como
      camino principal.

## Fase 2 — Calidad de datos

- [ ] Corregir provincia por cantón y guardar `provincia_original`.
- [ ] Separar cantones múltiples en `cantones: [...]`.
- [ ] Normalizar tildes y mayúsculas contra el catálogo.
- [ ] Tests para cada caso de `CLAUDE.md → Problemas conocidos`.

## Fase 3 — Infraestructura AWS (descartada: se publica en GitHub como Mazar)

- [ ] Aplicar CORS al bucket:
      `aws s3api put-bucket-cors --bucket primicias --cors-configuration file://infra/cors.json`
- [ ] Crear usuario IAM `pipeline-cortes-luz` con `infra/iam-policy.json`
      (solo escribe en la carpeta de cortes de luz).
- [ ] Probar publicación a staging desde local.

## Fase 4 — Buscador

- [ ] Cambiar `DATA_URL` a `cortes_luz_actual.json` (ver `frontend/cambios-prototipo.md`).
- [ ] Cambiar el respaldo: si la copia embebida está vencida, mostrar aviso
      en lugar de horarios viejos.
- [ ] Aprovechar `cantones[]` en el filtro de cantón.
- [ ] Verificar en Xalok (preview) que el fetch vivo funciona sin caer al respaldo.

## Fase 5 — Automatización

Flujo de vigilancia implementado (`pipeline/vigilar.py`, ver `docs/FLUJO.md`).
Línea base de las 14 páginas de CNEL registrada el 2026-10-14.

- [x] Vigilancia de páginas candidatas con línea base y avisos por código de salida.
- [x] Simulacro con PDFs reales de marzo 2026 (tests/test_vigilar.py).
- [x] Elegido: GitHub Actions con commit de `data/` (modelo Mazar). Botón de aprobación.
- [ ] Crear el repositorio y activarlo (`docs/GITHUB.md`).
- [ ] Buscador: `DATA_URL` → raw.githubusercontent.com/…/data/cortes_luz_publicado.json.

- [ ] Notificación cuando la validación falle (issue automático en GitHub o correo).
- [ ] Periodo de prueba en staging con aprobación humana (Diego / estadígrafo).
- [ ] Pasar a `modo: produccion`.

## Ideas para después

- Página interna de estado: última actualización, registros por provincia, alertas.
- Detectar cortes eliminados o reprogramados entre versiones (diff del histórico).
- Varias distribuidoras con un extractor por formato.
