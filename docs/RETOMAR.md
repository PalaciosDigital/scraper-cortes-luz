# Retomar el proyecto (estado al 15 de octubre de 2026)

## Dónde vive

- **Repositorio:** https://github.com/PalaciosDigital/scraper-cortes-luz (público). Copia local: `~/repos/scraper-cortes-luz`.
- La carpeta de iCloud `07_BUSCADOR_CORTES_DE_LUZ/02_PIPELINE` es una **copia antigua**: no editarla.
- Entornos: **PRE = GitHub** (funciona, confirmado por Diego). **Producción = servidores del equipo de
  desarrollo** (guía: `docs/SERVIDOR.md`).

## Qué funciona

- **Fuentes:** CentroSur (tabla GeneXus por HTTP, `pipeline/fuentes/centrosur.py`) y 14 páginas de CNEL
  vigiladas (`pipeline/fuentes/cnel.py`; hoy sin cronogramas vigentes).
- **CentroSur:** `data/alimentadores_centrosur.csv` está completo (21 alimentadores). Salen 54 cortes
  (Cuenca, Azogues, El Tambo, Santa Isabel, Pucará, Saraguro).
- **Workflows:** `vigilar.yml` corre **cada hora** de 6:07 a 22:07 en Ecuador (cron `7 0-3,11-23 * * *`),
  hace commit de `data/` y deja los avisos en un único issue. `aprobar.yml` es el botón de aprobación.
  Primera publicación aprobada el 2026-10-14.
- **Buscador PRE:** `07_BUSCADOR_CORTES_DE_LUZ/01_HTML/PROTOTIPO_PRE.html` lee
  `data/cortes_luz_publicado.json` desde raw.githubusercontent.com. `PROTOTIPO.html` es la base de diseño:
  sus cambios se replican en _PRE, nunca al revés.
- 52 tests (`pytest -q`).

## Novedades del 15 de octubre

- 4 alimentadores nuevos con cantón: 0500020S05, 0500030V01, 0500040V06 → Cuenca; 0500140V04 (El Manzano) → **Nabón**
  (la subestación no basta para deducir el cantón).
- Los avisos del issue mencionan a @DiegoPalacios1 (variable de repo `AVISAR` para cambiarlo) para que GitHub notifique.
- 15:09 UTC: candidato de 35 cortes (15 → 18 oct) **pendiente de aprobación**.
- GitHub atrasa o se salta corridas del cron horario; en producción, los servidores del equipo.

## Acuerdos

- Claude integra links nuevos de fuentes y hace push directo (credenciales en el llavero de macOS):
  `git pull` antes de editar y `pytest` antes del push.
- Aprobar publicaciones es siempre humano. `publicacion: revision` hasta que Diego pida `directa`.
- La frecuencia puede cambiar: Diego avisará.

## Pendientes

1. **Links nuevos de fuentes** (los traerá Diego): revisar formato → `config.yaml` o un extractor nuevo + fixture + test.
2. **Limpieza de sectores de CentroSur** (ofrecida, sin respuesta): quitar códigos de poste (`P#13055`) y el
   «Cantón X», pasar las MAYÚSCULAS a formato normal y evitar que las comas partan un sector.
3. ~~Códigos CentroSur~~ (resuelto 2026-10-15, significados aportados por Diego, no oficiales): PRO = programado,
   PAR = parcial (ramal o sector), EMM = emergencia o trabajo técnico → se publican; ANU = anulado → se excluye.
4. Probar en un borrador real de Xalok (1440 / 992 / 767), decidir si se ve el footer del sitio y mover a
   producción en los servidores del equipo.

## Entorno

Mac Intel con Python 3.9: `pip install --only-binary=cryptography -r requirements.txt`. El venv va fuera de iCloud.
