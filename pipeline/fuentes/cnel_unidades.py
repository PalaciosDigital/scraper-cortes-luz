"""Fuente "Unidades de Negocio CNEL EP" del Ministerio de Ambiente y Energía.

Página vigilada: https://www.ambienteyenergia.gob.ec/unidades-de-negocio-cnel-ep-2/
Un PDF por unidad de negocio de CNEL (Guayaquil, El Oro, Los Ríos, Guayas-Los
Ríos, Esmeraldas, Milagro, Manabí, Sucumbíos…). Revisado 2026-10-17: mismo
"branding" que `pipeline/fuentes/mae.py` (Mantenimientos de Contingencia), pero
un formato de texto distinto — por párrafos, no por columnas:

    PROVINCIA HORARIO
    <Provincia>, cantón <Cantón> TIPO DE TRABAJO: De 03H00 a 06H00
    <tipo de trabajo, una o varias líneas>
    SECTORES
    <sectores, una o varias líneas>

Variantes reales vistas en los 8 PDF de octubre de 2026:

- "TIPO DE TRABAJO:" a veces va en su propia línea, ANTES de la línea del
  cantón, en vez de pegado a ella.
- Algunos bloques no traen cantón, solo la provincia entera (p. ej. un
  mantenimiento de CELEC que afecta a toda la provincia).
- El horario usa "03H00" (con H), no "03:00".
- Rara vez el nombre del cantón se corta en dos líneas ("cantones Cascales y"
  / "Gonzao Pizarro …"): la segunda línea se pierde del cantón y se cuela en
  el tipo de trabajo (no se intenta recomponer; es un solo caso en 8 PDF).

pdfplumber ya extrae el texto en el orden correcto (no hace falta leer por
posición X como en mae.py), así que se analiza línea por línea. Para páginas
sin texto (escaneadas) se usa OCR (Tesseract) sobre el texto completo, no
por palabra: aquí no hay columnas que reescalar.
"""
from __future__ import annotations

import re
from pathlib import Path

import pdfplumber
import pytesseract

_RE_FECHA = re.compile(r"\d{1,2}\s+de\s+[a-záéíóúñ]+(?:\s+de\s+\d{4})?", re.I)
_RE_HORARIO = re.compile(r"[Dd]e\s+(\d{1,2})[Hh](\d{2})\s*a\s*(\d{1,2})[Hh](\d{2})")
_RE_TIPO_LABEL = re.compile(r"TIPO DE TRABAJO:\s*", re.I)
_RE_PROVINCIA_CANTON = re.compile(r"^(?P<provincia>.+?),?\s*cant(?:ón|ones)\s+(?P<canton>.+)$", re.I)

_OCR_DPI = 300


def _texto_pagina(pagina) -> str:
    texto = pagina.extract_text(x_tolerance=1) or ""
    if texto.strip():
        return texto
    imagen = pagina.to_image(resolution=_OCR_DPI).original   # página escaneada: OCR
    return pytesseract.image_to_string(imagen, lang="spa")


def extraer_filas(ruta_pdf: Path, provincia: str = "", fecha_respaldo: str = "") -> list[dict[str, str]]:
    """Filas crudas {provincia, canton, fecha, horario, tipo_trabajo, sectores}."""
    filas: list[dict[str, str]] = []
    fecha = fecha_respaldo

    with pdfplumber.open(ruta_pdf) as pdf:
        for pagina in pdf.pages:
            texto_pagina = _texto_pagina(pagina)
            m = _RE_FECHA.search(texto_pagina)
            if m:
                fecha = m.group(0)

            lineas = [l.strip() for l in texto_pagina.split("\n") if l.strip()]
            i = 0
            while i < len(lineas):
                if lineas[i] != "PROVINCIA HORARIO":
                    i += 1
                    continue
                i += 1
                if i < len(lineas) and lineas[i] == "TIPO DE TRABAJO:":
                    i += 1   # etiqueta sola antes del cantón: el tipo real viene después

                canton_txt, tipo_txt, horario = "", [], None
                while i < len(lineas) and horario is None:
                    linea = lineas[i]
                    i += 1
                    m_hora = _RE_HORARIO.search(linea)
                    if not m_hora:
                        canton_txt = f"{canton_txt} {linea}".strip()
                        continue
                    horario = f"{m_hora.group(1)}:{m_hora.group(2)} a {m_hora.group(3)}:{m_hora.group(4)}"
                    antes = _RE_TIPO_LABEL.sub(" ", linea[:m_hora.start()])
                    canton_txt = f"{canton_txt} {antes}".strip()
                    despues = linea[m_hora.end():].strip()
                    if despues:
                        tipo_txt.append(despues)
                if horario is None:
                    continue   # "PROVINCIA HORARIO" sin bloque completo detrás (no visto, por seguridad)

                while i < len(lineas) and lineas[i] != "SECTORES":
                    tipo_txt.append(lineas[i])
                    i += 1
                if i < len(lineas):
                    i += 1   # saltar "SECTORES"
                sectores_txt = []
                while i < len(lineas) and lineas[i] != "PROVINCIA HORARIO":
                    sectores_txt.append(lineas[i])
                    i += 1

                m_pc = _RE_PROVINCIA_CANTON.match(canton_txt)
                if m_pc:
                    provincia_fila, canton_fila = m_pc["provincia"].strip(), m_pc["canton"].strip()
                else:
                    # Bloque sin "cantón X" (afecta a toda la provincia): se usa la
                    # provincia también como cantón para no dejar la fila sin cantón.
                    provincia_fila = canton_fila = canton_txt

                filas.append({
                    "provincia": provincia_fila or provincia,
                    "canton": canton_fila,
                    "fecha": fecha,
                    "horario": horario,
                    "tipo_trabajo": " ".join(tipo_txt),
                    "sectores": " ".join(sectores_txt),
                })
    return filas
