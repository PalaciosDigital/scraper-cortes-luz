# Fuente @CNEL_EP en X (enlaces a Google Drive)

Desde octubre de 2026, @CNEL_EP publica en X los cronogramas de mantenimiento por unidad de negocio
como **PDF públicos de Google Drive**, enlazados con bit.ly. A veces llegan antes que a la página del
Ministerio de Ambiente y Energía. Ejemplo: post del 20 oct 2026 (10:19 Ecuador) con «UN Los Ríos» y
«UN Manabí» para el jueves 22.

## Reparto del trabajo

| Paso | Quién | Dónde |
|---|---|---|
| Revisar la cuenta y anotar los PDF nuevos | Claude, **cada hora**, desde el Chrome de Diego (Claude in Chrome) | `data/enlaces_cnel_x.csv` |
| Descargar, extraer, avisar | el pipeline (GitHub Actions, cada hora 6–22) | página `cnel-x-drive` en `config.yaml` |
| Aprobar la publicación | Diego (botón «Aprobar publicación») | issue de GitHub |

X no se puede leer sin iniciar sesión, por eso la revisión depende de que el Mac y Chrome de Diego estén
abiertos y la sesión de Claude activa. Los PDF ya anotados se procesan solos aunque eso falle.
**No** usar espejos no oficiales ni trucos para leer X sin sesión.

## Procedimiento de cada revisión

1. `git pull --ff-only` en `~/repos/scraper-cortes-luz`.
2. Abrir https://x.com/CNEL_EP en una pestaña nueva y leer los posts más recientes (hasta llegar a los
   ya anotados en el CSV o, como mucho, ~2 días atrás).
3. Quedarse con los posts que anuncian **mantenimientos / cortes programados** con enlaces. La vista de la
   cuenta corta el texto: abrir el post (`/status/<id>`) para ver todos los enlaces.
4. Resolver cada enlace (bit.ly → `drive.google.com/file/d/<ID>/view`) con `curl -sIL -o /dev/null
   -w '%{url_effective}'`. Anotar solo los que lleven a Drive (o a un PDF).
5. Si el `drive_id` no está en el CSV, agregar una fila:
   `drive_id,archivo,unidad,post,publicado` (archivo = nombre del PDF según `content-disposition`;
   publicado = fecha del post en UTC, `AAAA-MM-DDTHH:MMZ`).
6. Probar el PDF con el extractor (`pipeline/fuentes/cnel_unidades.py`). Si sale 0 filas o un cantón raro,
   avisar a Diego antes de subir.
7. `pytest -q` y `git push`. La siguiente corrida de GitHub lo procesa y abre el aviso de aprobación.
8. Cerrar la pestaña. Si no hubo nada nuevo, no se hace commit.

## Detalles técnicos

- Descarga directa: `https://drive.google.com/uc?export=download&id=<ID>` (sin sesión, devuelve el PDF).
- La verificación de reemplazos (HEAD: Last-Modified + tamaño) también cubre Drive: si CNEL sube una
  versión nueva sobre el mismo enlace, se reprocesa.
- La página `cnel-x-drive` no tiene línea base: todo lo anotado en el CSV se procesa en la primera pasada.
- Es `prioridad: true`, como las páginas del Ministerio (misma fuente oficial).
