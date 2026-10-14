# Correr el scraper en servidores propios (producción)

En **PRE** el scraper corre en GitHub Actions y el buscador lee el JSON desde
raw.githubusercontent.com (ver `docs/GITHUB.md`). En **producción** corre en
servidores de PRIMICIAS. El código es el mismo: Python + una tarea programada.
GitHub solo aporta el cron, el commit de `data/` y los issues; aquí se reemplazan
por cron, un directorio servido por web y las alertas del equipo.

## Requisitos

- Python 3.9 o superior, salida a internet hacia `cnelep.gob.ec` y `extranet.centrosur.gob.ec`.
- `pip install -r requirements.txt` (pdfplumber, requests, PyYAML, jsonschema; boto3 solo para la ruta antigua a S3).
- Un directorio persistente para `data/`: es el estado (línea base de CNEL, fotos de CentroSur,
  tabla de alimentadores). **No se borra entre ejecuciones.**

## Ejecución

```bash
cd /ruta/scraper-cortes-luz
python -m pipeline.vigilar          # una pasada; cron cada 3 h entre 6:00 y 22:00 (America/Guayaquil)
```

Crontab de ejemplo (hora local de Ecuador):

```
0 6,9,12,15,18,21 * * *  cd /ruta/scraper-cortes-luz && .venv/bin/python -m pipeline.vigilar >> salida/vigilancia/registro.log 2>&1; /ruta/avisar.sh $?
```

Una sola ejecución a la vez (por ejemplo, `flock -n /tmp/cortes.lock …`): la pasada y la aprobación
escriben los mismos archivos.

## Qué produce

| Archivo | Uso |
|---|---|
| `data/cortes_luz_publicado.json` | **Lo que lee el buscador.** Servirlo por HTTPS. |
| `data/cortes_luz_vigentes.json` | Candidato pendiente de aprobación (modo `revision`). |
| `data/vigilancia/estado.json`, `data/vigilancia/registros/` | Estado interno. No servir. |
| `data/alimentadores_centrosur.csv` | Alimentador → cantón. Lo completa una persona. |
| `salida/vigilancia/alerta.md` | Texto del aviso de la última pasada (Markdown). |

## Servir el JSON al buscador

El buscador en Xalok (www.primicias.ec) hace `fetch` al JSON: el servidor debe enviar CORS.
Ejemplo nginx:

```nginx
location = /datos/cortes_luz.json {
    alias /ruta/scraper-cortes-luz/data/cortes_luz_publicado.json;
    add_header Access-Control-Allow-Origin "https://www.primicias.ec" always;
    add_header Cache-Control "public, max-age=300" always;
    default_type application/json;
}
```

Luego, en el HTML del buscador, `DATA_URL` apunta a esa URL (en PRE apunta a raw.githubusercontent.com).

## Avisos (códigos de salida)

| Código | Significado | Acción sugerida |
|---|---|---|
| 0 | Sin novedades (o solo se retiraron cortes vencidos) | Nada |
| 10 | Datos nuevos: candidato listo | Avisar al editor para aprobar |
| 20 | Revisión: formato desconocido, alimentadores sin cantón, página caída, validación fallida | Avisar con `alerta.md` |
| 2 | Error general | Alerta técnica |

El aviso puede ir por correo, Slack o lo que use el equipo; el contenido es `salida/vigilancia/alerta.md`.

## Aprobación

```bash
python -m pipeline.vigilar --aprobar    # copia el candidato a cortes_luz_publicado.json
```

En PRE es el botón «Aprobar publicación» de GitHub. En producción puede ser este comando, un
botón en una herramienta interna, o `publicacion: directa` en `config.yaml` cuando el flujo
sea confiable.

## Ediciones manuales

- `config.yaml`: páginas vigiladas, modo de publicación, user agent.
- `data/alimentadores_centrosur.csv`: completar `canton` y `provincia`.

Si se edita en el servidor, conviene llevar esos cambios también al repositorio (y viceversa).

## Notas de cortesía con las fuentes

- User agent honesto (`config.yaml → fuente.user_agent`). CentroSur bloquea navegadores sin
  interfaz: **no cambiar el user agent para parecer un navegador**.
- Ritmo bajo: una visita por página cada 3 horas; los PDFs ya vistos no se descargan otra vez.
