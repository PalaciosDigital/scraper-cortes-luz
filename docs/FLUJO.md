# Flujo automático: de la página de la distribuidora al buscador

La fuente oficial definitiva es incierta, así que el pipeline **vigila páginas
candidatas** y actúa cuando aparece algo. Comando: `python -m pipeline.vigilar`.

```
 cada hora (6:00–22:00)
        │
        ▼
 ┌──────────────┐   14 páginas de CNEL (config.yaml → vigilancia.paginas)
 │ 1. Vigilar   │   · Trabajos programados × 11 unidades (?unidad=guayaquil…)
 └──────┬───────┘   · Emergentes Santa Elena · Emergentes Esmeraldas · CENACE
        │
        ▼
 ┌──────────────┐   ¿PDF que no estaba en la línea base?
 │ 2. Detectar  │   ¿Desapareció "no contamos con Trabajos Programados" sin PDF?
 └──────┬───────┘   ¿La página no responde?
        │
        ▼
 ┌──────────────┐   extractor CNEL → si no saca filas, extractor genérico
 │ 3. Procesar  │   → si tampoco: "formato desconocido" (revisión humana)
 └──────┬───────┘
        │
        ▼
 ┌──────────────┐   une todos los PDFs procesados, solo fechas de hoy en adelante,
 │ 4. Armar     │   deduplica (el PDF más nuevo gana, salvo la fuente prioritaria,
 └──────┬───────┘   que siempre gana) y valida con validar.py
        │
        ▼
 ┌──────────────┐   local: salida/vigilancia/cortes_luz_vigentes.json
 │ 5. Publicar  │   candidato: data/cortes_luz_vigentes.json (commit al repo)
 │              │   publicado: data/cortes_luz_publicado.json ← lo lee el buscador
 └──────┬───────┘
        │
        ▼
 ┌──────────────┐   alerta.md + código de salida → notificación del Mac o issue de GitHub
 │ 6. Avisar    │   (en GitHub: issue + botón «Aprobar publicación»)
 └──────────────┘
```

## Qué significa cada aviso

| Código | Aviso | Qué hacer |
|---|---|---|
| 0 | (ninguno) | Nada. También se usa cuando solo se retiraron cortes vencidos. |
| 10 | **Datos nuevos** | Revisar el issue y `data/cortes_luz_vigentes.json`; pulsar «Aprobar publicación». |
| 20 | **Revisión necesaria** | Formato de PDF desconocido, filas descartadas, página cambiada sin PDF, página caída o ya no quedan cortes vigentes. |
| 2 | Error | Fallo general. Mirar el log de la ejecución en Actions. |

## Decisiones de diseño

- **Línea base**: la primera vez que se vigila una página se registran sus PDFs
  existentes sin procesarlos. Así no se publican cortes viejos (marzo, mayo).
- **Nunca se vacía el JSON solo**: si se acaban los cortes vigentes, se avisa
  (código 20) y una persona decide si retirar el buscador.
- **Retirar cortes vencidos no avisa**: el JSON se recalcula cada pasada.
- **La regla de "caída máxima" no se aplica aquí**: el total baja cada día por
  vencimiento. Los cambios de formato se detectan PDF por PDF.
- **Solo PDFs del propio dominio**: el pie de CNEL enlaza documentos de otros sitios.

## Fuente prioritaria (Ministerio de Ambiente y Energía)

Confirmada por Diego el 2026-10-17: es la fuente oficial. Página vigilada
`mae-mantenimientos` (`config.yaml`, extractor `pipeline/fuentes/mae.py`), con
`prioridad: true`. Agrupa un PDF por distribuidora (EEQ, ELEPCO, EEASA,
EERSSA, CentroSur…) más uno de subestaciones/transmisión.

- **Qué significa `prioridad: true`**: en el paso 4 (Armar), si esta página
  tiene algún corte para un cantón y fecha dados, los cortes de las DEMÁS
  páginas para ese mismo cantón y fecha se descartan por completo —aunque el
  texto de sectores no coincida—, en vez de aplicar la regla general de "el
  PDF más nuevo gana". Ver `armar_vigentes` y `paginas_prioritarias` en
  `pipeline/vigilar.py`.
- **PDFs escaneados (p. ej. EERSSA)**: desde el 2026-10-17 se procesan con OCR
  (Tesseract, vía `pytesseract`; necesita el paquete `tesseract-ocr` del
  sistema, ya instalado en `vigilar.yml`). No es perfecto: en el PDF de
  prueba reconoce 6 de 7 cortes (al otro, Tesseract le lee mal la insignia
  de horario) — revisa igual el candidato antes de aprobar.
- **No cubre**: el PDF de subestaciones (sin "sectores" por barrio) no tiene
  extractor → cae a "formato desconocido" (revisión humana).
- La URL vigilada (sin el mes) redirige siempre, con 301, a la del mes
  vigente —por eso no hace falta actualizarla cada mes.

Misma fuente oficial, segunda página: `cnel-unidades` (agregada el 2026-10-17
a pedido de Diego), un PDF por unidad de negocio de CNEL (Guayaquil, El Oro,
Los Ríos, Guayas-Los Ríos, Esmeraldas, Milagro, Manabí, Sucumbíos…). También
`prioridad: true`. Formato de texto distinto al de `mae-mantenimientos` (por
párrafos, sin columnas: "PROVINCIA HORARIO" / cantón + horario / tipo de
trabajo / SECTORES) — extractor aparte, `pipeline/fuentes/cnel_unidades.py`.
URL estable, sin redirección mensual.

## Si aparece otra fuente nueva

1. Si es otra página de CNEL: añadirla a `vigilancia.paginas` (mismo `tipo`).
2. Si es otra distribuidora o formato: crear `pipeline/fuentes/<nombre>.py` con
   `listar_pdfs()` y `extraer_filas()`, registrarlo en `EXTRACTORES` de
   `pipeline/vigilar.py`, guardar un PDF real en `tests/fixtures/` y escribir su test.
3. Si publican imágenes o posts en redes: el aviso de "página cambiada" lo
   detecta, pero hace falta OCR o extracción asistida (ver `docs/PLAN.md`, fase 1).

## Fuentes tipo tabla (CentroSur)

CentroSur no publica PDFs: su página incrusta una tabla GeneXus con lo programado
de hoy a hoy+3 días. Se lee por HTTP con el user agent honesto de `config.yaml`
(el sitio bloquea navegadores sin interfaz y **no se debe esquivar ese bloqueo**).
Detalle técnico en `pipeline/fuentes/centrosur.py`.

- Cada pasada **reemplaza la foto** anterior; no hay línea base.
- Se excluyen los estados de `excluir_estados` (ANU = anulado, por confirmar con CentroSur).
- **Cantón**: 1) "Cantón X" en la dirección o la descripción (solo nombres del
  catálogo); 2) `data/alimentadores_centrosur.csv`; 3) si no hay nada, el corte
  no se publica y el alimentador se añade al CSV con el cantón vacío y direcciones
  de ejemplo. Una persona completa `canton` y `provincia` desde la web de GitHub.
- Un mismo alimentador puede servir a dos cantones (0500140V01: Santa Isabel y
  Saraguro); por eso el texto manda sobre la tabla.
- Si GeneXus cambia sus tokens o la forma de la respuesta → aviso de revisión (código 20).

## Publicación y aprobación

`config.yaml → vigilancia.publicacion`:

- `revision` (actual): los datos nuevos quedan como candidato y el issue pide
  aprobar. Retirar cortes vencidos se publica solo, **salvo** si hay un
  candidato esperando (si no, se colaría sin aprobación).
- `directa`: los datos nuevos válidos se publican sin esperar. Nunca se publica
  con código 20.

## Dónde corre

GitHub Actions (`.github/workflows/vigilar.yml` y `aprobar.yml`). Puesta en marcha
paso a paso: `docs/GITHUB.md`.

## Simulacro

```bash
python -m pipeline.vigilar --estado /tmp/e.json --solo cnel-emergentes --simular 3 --hoy 2026-03-19
python -m pipeline.vigilar --estado /tmp/e.json --solo cnel-emergentes --hoy 2026-03-21
```

`--simular N` deja fuera de la línea base los N PDFs más recientes de cada
página; `--hoy` fija la fecha de referencia.
