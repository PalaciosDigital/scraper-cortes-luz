"""Fuente MAE: "Mantenimientos de Contingencia" del Ministerio de Ambiente y Energía.

Página vigilada: https://www.ambienteyenergia.gob.ec/mantenimientoseedprogramados/
(redirige siempre, con 301, a la URL del mes vigente, p. ej. …seedprogramadosoct/:
por eso se vigila la URL sin el mes). Revisado 2026-10-17: la página agrupa, por
cada jornada de mantenimiento, un PDF por distribuidora (EEQ, ELEPCO, EEASA,
EERSSA, CentroSur…) más uno de mantenimientos de transmisión (subestaciones).

Formato de los PDFs "de distribución" (EEQ, ELEPCO, EEASA y similares):

- Encabezado con la fecha ("Sábado, 17 de octubre de 2026" o en mayúsculas).
- Una línea con la PROVINCIA en mayúsculas, sola.
- Por cada corte: "CANTÓN: <uno o varios cantones>" (también "CANTONES X Y Y"),
  seguido de las columnas ZONA DE MANTENIMIENTO(S) | SECTORES | TIPO DE
  TRABAJO | HORARIO. pdfplumber no arma bien la tabla (celdas vacías: el PDF
  está maquetado con cajas de texto, no con una tabla real), así que las filas
  se arman leyendo las palabras por su posición X, agrupadas en líneas.
- El horario siempre cae solo en su propia línea ("03:00 a 06:00", a veces con
  varias franjas separadas por "/"), así que se usa como fin de fila.

No cubre (caen a "formato desconocido" y piden revisión humana, ver
docs/FLUJO.md):

- El PDF de mantenimientos de transmisión/subestaciones (otra tabla, sin
  "sectores" por barrio: afecta a toda una subestación).
- PDFs escaneados sin texto (p. ej. EERSSA) — hace falta OCR, que el pipeline
  no tiene hoy (ver docs/PLAN.md).
"""
from __future__ import annotations

import re
from pathlib import Path

import pdfplumber

from ..texto import clave

_RE_FECHA = re.compile(r"\d{1,2}\s+de\s+[a-záéíóúñ]+(?:\s+de\s+\d{4})?", re.I)
_RE_HORARIO = re.compile(
    r"^\d{1,2}:\d{2}\s*a\s*\d{1,2}:\d{2}(\s*/\s*\d{1,2}:\d{2}\s*a\s*\d{1,2}:\d{2})*$", re.I)
# Los dos puntos son obligatorios: distinguen la etiqueta "CANTÓN: Quito" del
# texto de la zona, que a veces también empieza con "CANTÓN" (p. ej. "CANTÓN
# PELILEO REDONDEL DE LA HUAMBALEÑA", sin dos puntos).
_RE_CANTON_PREFIJO = re.compile(r"^cant[oó]n(?:es)?\s*:\s*", re.I)

_PALABRAS_ENCABEZADO = {"zona", "de", "mantenimiento", "mantenimientos", "sectores", "tipo", "trabajo", "horario"}

# Posición X (puntos) donde cambia de columna. Calibrado con los PDF de
# EEQ, ELEPCO, EEASA y Morona Santiago de octubre de 2026 (ver tests/fixtures).
X_ZONA_MAX = 280
X_SECTORES_MAX = 658


def _agrupar_lineas(palabras: list[dict], tolerancia: float = 3.0) -> list[list[dict]]:
    """Agrupa palabras de pdfplumber en líneas visuales por su coordenada `top`."""
    lineas: list[list[dict]] = []
    for p in sorted(palabras, key=lambda w: (w["top"], w["x0"])):
        if lineas and abs(p["top"] - lineas[-1][0]["top"]) <= tolerancia:
            lineas[-1].append(p)
        else:
            lineas.append([p])
    for linea in lineas:
        linea.sort(key=lambda w: w["x0"])
    return lineas


def _es_encabezado(linea: list[dict]) -> bool:
    """Línea compuesta solo por las etiquetas de columna (se repiten por cada corte)."""
    return all(clave(p["text"]) in _PALABRAS_ENCABEZADO for p in linea)


def _es_provincia(linea: list[dict], texto: str) -> bool:
    """Línea corta, en mayúsculas, a la izquierda: nombre de provincia suelto."""
    if not linea or len(linea) > 3 or any(p["x0"] >= X_ZONA_MAX for p in linea):
        return False
    return bool(re.fullmatch(r"[A-ZÁÉÍÓÚÑ ]+", texto))


def _quitar_cola_encabezado(texto: str) -> str:
    """A veces la línea "CANTÓN: X" queda pegada a un fragmento de encabezado
    de la fila siguiente (p. ej. "SUCÚA Y LOGROÑO TIPO DE TRABAJO"): se recorta
    la cola de palabras de encabezado."""
    palabras = texto.split()
    while palabras and clave(palabras[-1]) in _PALABRAS_ENCABEZADO:
        palabras.pop()
    return " ".join(palabras)


def _franjas(horario: str) -> list[str]:
    return [h.strip() for h in horario.split("/") if h.strip()] or [horario]


def extraer_filas(ruta_pdf: Path, provincia: str = "", fecha_respaldo: str = "") -> list[dict[str, str]]:
    """Filas crudas {provincia, canton, fecha, horario, tipo_trabajo, zona_cortes, sectores}.

    La fecha se lee del propio PDF (hereda entre páginas si una no la trae).
    Cada bloque "CANTÓN: …" es una fila (a veces el mismo cantón se repite
    para varios cortes seguidos). El horario no tiene una posición fija
    dentro del bloque (queda centrado verticalmente junto a zona/sectores/tipo,
    que suelen ocupar varias líneas): se recoge por su propio patrón de texto
    en vez de por posición, y la fila se cierra al siguiente "CANTÓN:", la
    siguiente provincia o el fin de la página.
    """
    filas: list[dict[str, str]] = []
    fecha = fecha_respaldo

    with pdfplumber.open(ruta_pdf) as pdf:
        for pagina in pdf.pages:
            texto_pagina = pagina.extract_text(x_tolerance=1) or ""
            m = _RE_FECHA.search(texto_pagina)
            if m:
                fecha = m.group(0)

            provincia_actual, canton_actual = provincia, ""
            zona: list[str] = []
            sectores: list[str] = []
            tipo: list[str] = []
            horarios: list[str] = []

            def cerrar() -> None:
                nonlocal zona, sectores, tipo, horarios
                if canton_actual and horarios and (zona or sectores or tipo):
                    for h in horarios:
                        for franja in _franjas(h):
                            filas.append({
                                "provincia": provincia_actual,
                                "canton": canton_actual,
                                "fecha": fecha,
                                "horario": franja,
                                "tipo_trabajo": " ".join(tipo),
                                "zona_cortes": " ".join(zona),
                                "sectores": " ".join(sectores),
                            })
                zona, sectores, tipo, horarios = [], [], [], []

            for linea in _agrupar_lineas(pagina.extract_words(x_tolerance=1, use_text_flow=False)):
                texto_linea = " ".join(p["text"] for p in linea).strip()
                if not texto_linea:
                    continue
                if _es_encabezado(linea):
                    # El encabezado de columnas se repite antes de cada corte, incluso
                    # cuando el cantón no cambia (p. ej. dos zonas bajo "CANTÓN: Quito"):
                    # también cierra la fila en curso.
                    cerrar()
                    continue
                if _es_provincia(linea, texto_linea):
                    cerrar()
                    provincia_actual, canton_actual = texto_linea, ""
                    continue
                if _RE_CANTON_PREFIJO.match(texto_linea):
                    cerrar()
                    canton_actual = _quitar_cola_encabezado(
                        _RE_CANTON_PREFIJO.sub("", texto_linea, count=1).strip())
                    continue
                if _RE_HORARIO.match(texto_linea):
                    horarios.append(texto_linea)
                    continue
                if not canton_actual:
                    continue   # texto antes del primer "CANTÓN:" (título, fecha…)
                for p in linea:
                    if p["x0"] < X_ZONA_MAX:
                        zona.append(p["text"])
                    elif p["x0"] < X_SECTORES_MAX:
                        sectores.append(p["text"])
                    else:
                        tipo.append(p["text"])
            cerrar()
    return filas
