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
- El horario ("03:00 a 06:00", a veces con varias franjas separadas por "/")
  casi siempre cae solo en su propia línea, pero a veces queda pegado a otro
  texto (sobre todo en páginas con OCR): se busca el patrón "HH:MM a HH:MM"
  dentro de cada línea, no solo como línea completa.

Algunas distribuidoras (p. ej. EERSSA) exportan el mismo PDF como imagen, sin
texto: se les aplica OCR (Tesseract, vía `pytesseract`) antes de repetir el
mismo análisis por posición. Necesita el binario `tesseract` instalado (en Mac,
`brew install tesseract tesseract-lang`; en CI, `apt-get install tesseract-ocr
tesseract-ocr-spa`, ya en `.github/workflows/vigilar.yml`); si no está, esa
página cae a "formato desconocido" igual que antes (ver `vigilar.procesar_pdf`,
que ya atrapa cualquier excepción del extractor).

No cubre (cae a "formato desconocido" y pide revisión humana, ver
docs/FLUJO.md): el PDF de mantenimientos de transmisión/subestaciones, que es
otra tabla sin "sectores" por barrio (afecta a toda una subestación).
"""
from __future__ import annotations

import re
from pathlib import Path

import pdfplumber
import pytesseract

from ..texto import clave

_RE_FECHA = re.compile(r"\d{1,2}\s+de\s+[a-záéíóúñ]+(?:\s+de\s+\d{4})?", re.I)
_RE_HORA = re.compile(r"^\d{1,2}:\d{2}$")
# Los dos puntos son obligatorios: distinguen la etiqueta "CANTÓN: Quito" del
# texto de la zona, que a veces también empieza con "CANTÓN" (p. ej. "CANTÓN
# PELILEO REDONDEL DE LA HUAMBALEÑA", sin dos puntos).
_RE_CANTON_PREFIJO = re.compile(r"^cant[oó]n(?:es)?\s*:\s*", re.I)

_PALABRAS_ENCABEZADO = {"zona", "de", "mantenimiento", "mantenimientos", "sectores", "tipo", "trabajo", "horario"}

# Posición X (puntos) donde cambia de columna, usada hasta que se vea un
# encabezado real en la página (ver `_limites_de_encabezado`). Calibrado con
# los PDF de EEQ, ELEPCO, EEASA y Morona Santiago de octubre de 2026 (ver
# tests/fixtures). Los PDF con OCR (EERSSA) vienen a otra escala: sus límites
# se recalculan por página a partir de las etiquetas SECTORES/TIPO.
X_ZONA_MAX = 280
X_SECTORES_MAX = 658


# x0 (puntos) de la etiqueta SECTORES en los PDF con texto nativo (EEQ, ELEPCO,
# EEASA, Morona Santiago): varía poco entre ellos (328-336). Sirve de referencia
# para escalar X_ZONA_MAX/X_SECTORES_MAX en páginas con OCR, que vienen a otra
# escala (el "TIPO" de la cabecera no sirve de referencia: su x0 cae encima de
# donde ya empiezan datos de la columna SECTORES, muy ajustado).
_X_SECTORES_REFERENCIA = 328.0


def _escala_de_encabezado(linea: list[dict]) -> float | None:
    """Factor para reescalar los límites de columna, a partir de la etiqueta
    SECTORES de esta línea de encabezado (o None si la línea no la trae)."""
    x_sectores = next((p["x0"] for p in linea if clave(p["text"]) == "sectores"), None)
    return x_sectores / _X_SECTORES_REFERENCIA if x_sectores else None


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


def _es_provincia(linea: list[dict], texto: str, limite_zona: float = X_ZONA_MAX) -> bool:
    """Línea corta, en mayúsculas, a la izquierda: nombre de provincia suelto.

    `limite_zona` debe ser el límite de columna YA REESCALADO de la página
    (en páginas con OCR, el fijo X_ZONA_MAX corresponde a otra escala y deja
    pasar datos reales de la columna SECTORES, como "CELICA CANTÓN CELICA").
    """
    if not linea or len(linea) > 3 or any(p["x0"] >= limite_zona for p in linea):
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


def _extraer_horarios(linea: list[dict]) -> tuple[list[str], list[dict]]:
    """Saca los tramos "HH:MM a HH:MM" de la línea (en cualquier posición, no
    solo si ocupan toda la línea: a veces quedan pegados a la zona o al
    cantón, sobre todo en páginas con OCR) y devuelve (horarios, el resto de
    palabras, para seguir repartiéndolas por columna)."""
    horarios: list[str] = []
    resto: list[dict] = []
    i = 0
    while i < len(linea):
        siguientes = linea[i:i + 3]
        if (len(siguientes) == 3 and _RE_HORA.match(siguientes[0]["text"])
                and siguientes[1]["text"].strip(".,").lower() in ("a", "-", "–")
                and _RE_HORA.match(siguientes[2]["text"])):
            horarios.append(f'{siguientes[0]["text"]} a {siguientes[2]["text"]}')
            i += 3
            continue
        resto.append(linea[i])
        i += 1
    return horarios, resto


# A 200 DPI, Tesseract se come el horario (el texto blanco sobre fondo de
# color) en algunos de los cortes de una misma página; a 300 los reconoce todos
# (probado con tests/fixtures/mae_eerssa_escaneado_2026-10-17.pdf).
_OCR_DPI = 300


def _ocr_pagina(pagina) -> tuple[list[dict], str]:
    """OCR de una página sin texto: mismas claves {text, x0, top} que pdfplumber,
    convertidas de píxeles (a `_OCR_DPI`) a puntos PDF. La escala resultante no
    coincide exactamente con la de los PDF con texto nativo (depende de cómo se
    exportó la imagen): los límites de columna se reescalan aparte, ver
    `_escala_de_encabezado`."""
    imagen = pagina.to_image(resolution=_OCR_DPI).original
    datos = pytesseract.image_to_data(imagen, lang="spa", output_type=pytesseract.Output.DICT)
    escala = 72 / _OCR_DPI
    palabras = [{"text": t, "x0": datos["left"][i] * escala, "top": datos["top"][i] * escala}
               for i, t in enumerate(datos["text"]) if t.strip()]
    return palabras, " ".join(p["text"] for p in palabras)


def _palabras_y_texto(pagina) -> tuple[list[dict], str, bool]:
    """Devuelve (palabras, texto, es_ocr)."""
    palabras = pagina.extract_words(x_tolerance=1, use_text_flow=False)
    if palabras:
        return palabras, pagina.extract_text(x_tolerance=1) or "", False
    palabras, texto = _ocr_pagina(pagina)   # página sin texto (escaneada): OCR
    return palabras, texto, True


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
            palabras_pagina, texto_pagina, es_ocr = _palabras_y_texto(pagina)
            m = _RE_FECHA.search(texto_pagina)
            if m:
                fecha = m.group(0)

            provincia_actual, canton_actual = provincia, ""
            en_bloque = False   # True tras el primer "CANTÓN:", aunque venga sin nombre
            x_zona_max, x_sectores_max = X_ZONA_MAX, X_SECTORES_MAX
            zona: list[str] = []
            sectores: list[str] = []
            tipo: list[str] = []
            horarios: list[str] = []

            def cerrar() -> None:
                nonlocal zona, sectores, tipo, horarios
                # Si "CANTÓN:"/"CANTONES:" quedó sin nombre (p. ej. el PDF de EERSSA,
                # cuando hay más de uno, deja la etiqueta vacía y repite la lista en la
                # zona), se usa la zona como cantón: mejor un texto sin resolver en el
                # catálogo que perder la fila entera.
                canton_fila = canton_actual or " ".join(zona)
                if canton_fila and horarios and (zona or sectores or tipo):
                    for h in horarios:
                        for franja in _franjas(h):
                            filas.append({
                                "provincia": provincia_actual,
                                "canton": canton_fila,
                                "fecha": fecha,
                                "horario": franja,
                                "tipo_trabajo": " ".join(tipo),
                                "zona_cortes": " ".join(zona),
                                "sectores": " ".join(sectores),
                            })
                zona, sectores, tipo, horarios = [], [], [], []

            for linea in _agrupar_lineas(palabras_pagina):
                texto_linea = " ".join(p["text"] for p in linea).strip()
                if not texto_linea:
                    continue
                if _es_encabezado(linea):
                    # El encabezado de columnas se repite antes de cada corte, incluso
                    # cuando el cantón no cambia (p. ej. dos zonas bajo "CANTÓN: Quito"):
                    # también cierra la fila en curso. En páginas con OCR, de paso
                    # reescala los límites de columna (ver _escala_de_encabezado).
                    cerrar()
                    if es_ocr:
                        escala = _escala_de_encabezado(linea)
                        if escala:
                            x_zona_max = X_ZONA_MAX * escala
                            x_sectores_max = X_SECTORES_MAX * escala
                    continue
                if _es_provincia(linea, texto_linea, x_zona_max):
                    cerrar()
                    provincia_actual, canton_actual, en_bloque = texto_linea, "", False
                    continue
                if _RE_CANTON_PREFIJO.match(texto_linea):
                    cerrar()
                    canton_actual = _quitar_cola_encabezado(
                        _RE_CANTON_PREFIJO.sub("", texto_linea, count=1).strip())
                    en_bloque = True   # aunque "CANTÓN:"/"CANTONES:" venga sin nombre
                    continue
                horas, linea = _extraer_horarios(linea)
                horarios.extend(horas)
                if not linea or not en_bloque:
                    continue   # texto antes del primer "CANTÓN:" (título, fecha…)
                for p in linea:
                    if p["x0"] < x_zona_max:
                        zona.append(p["text"])
                    elif p["x0"] < x_sectores_max:
                        sectores.append(p["text"])
                    else:
                        tipo.append(p["text"])
            cerrar()
    return filas
