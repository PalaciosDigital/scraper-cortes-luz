"""Fuente CNEL EP: páginas de "Trabajos emergentes" en cnelep.gob.ec.

Cómo publica CNEL (revisado 2026-10-14):

- Página WordPress estática, sin JavaScript para cargar los PDFs.
- Santa Elena (/trabajos-emergentes/): cada PDF va en un `.doc-card` con un
  `<h3>` "Planificación de horarios y sectores – 21 de marzo de 2026" y un
  enlace `.btn-descargar`. Paginación en /page/2/, /page/3/…
- Esmeraldas (/trabajos-emergentes-esmeraldas/): los enlaces envuelven un
  banner de imagen, sin título ni paginación.
- PDFs en /wp-content/uploads/AAAA/MM/CRONOGRAMA-DD.MM.AA.pdf (el nombre no es
  consistente: también "STE-EDITABLE-CORTE-5-MARZO.pdf").

Formato del PDF (igual en ambas unidades):

- Una página por franja horaria. Tabla de 2 columnas: CANTÓN | "SECTORES 11:00 a 13:00".
  El horario va dentro del encabezado de la segunda columna.
- La fecha va en el texto de la página: "Fecha: 21 de Marzo de 2026".
- El motivo va en el texto: "…debido a afectación de autotransformador en …".
- No hay alimentador, provincia ni tipo de trabajo por fila.
- Con la tolerancia por defecto pdfplumber pega palabras ("ManantialdeChanduy");
  text_x_tolerance=1 las separa bien.
"""
from __future__ import annotations

import html
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import pdfplumber
import requests

from ..texto import clave

AJUSTES_TABLA = {"text_x_tolerance": 1}

_RE_H3 = re.compile(r"<h3[^>]*>(.*?)</h3>", re.S | re.I)
_RE_PDF = re.compile(r"""<a\s[^>]*href=["']([^"']+\.pdf)["']""", re.I)
_RE_SIGUIENTE = re.compile(r"""class=["']next page-numbers["'][^>]*href=["']([^"']+)["']"""
                           r"""|href=["']([^"']+)["'][^>]*class=["']next page-numbers["']""", re.I)
_RE_FECHA = re.compile(r"Fecha\s*:\s*([^\n]+)", re.I)
_RE_MOTIVO = re.compile(r"debido a\s+(.+?)(?:\.\s|\.$|\n[A-ZÁÉÍÓÚÑ]{4,})", re.I | re.S)


# ---------- listado (HTML) ----------

def _texto_html(fragmento: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragmento)).split())


def parsear_listado(pagina_html: str, base_url: str, patron: str) -> tuple[list[dict], str | None]:
    """Devuelve ([{url, titulo}], url_pagina_siguiente).

    Empareja cada PDF con el último <h3> que lo precede (Santa Elena). Si no hay
    <h3> previo (Esmeraldas), el título queda vacío y la fecha sale del PDF.
    `patron` filtra por nombre de archivo para descartar PDFs del menú
    (p. ej. el Plan Estratégico).
    """
    filtro = re.compile(patron, re.I)
    eventos = [(m.start(), "h3", _texto_html(m.group(1))) for m in _RE_H3.finditer(pagina_html)]
    eventos += [(m.start(), "pdf", urljoin(base_url, html.unescape(m.group(1))))
                for m in _RE_PDF.finditer(pagina_html)]
    eventos.sort()

    dominio = urlparse(base_url).netloc
    vistos, salida, titulo = set(), [], ""
    for _, tipo, valor in eventos:
        if tipo == "h3":
            titulo = valor
            continue
        nombre = valor.rsplit("/", 1)[-1]
        # Solo PDFs del propio sitio: el pie enlaza documentos de otros dominios.
        if urlparse(valor).netloc != dominio or not filtro.search(nombre) or valor in vistos:
            continue
        vistos.add(valor)
        salida.append({"url": valor, "titulo": titulo})
        titulo = ""

    m = _RE_SIGUIENTE.search(pagina_html)
    siguiente = urljoin(base_url, html.unescape(m.group(1) or m.group(2))) if m else None
    return salida, siguiente


def listar_pdfs(url: str, user_agent: str, patron: str, timeout_s: int = 60,
                max_paginas: int = 20, htmls: list[str] | None = None) -> list[dict]:
    """Recorre el listado y su paginación. Orden: el del sitio (más reciente primero).

    Si se pasa `htmls`, se le añade el HTML de cada página leída (para la vigilancia).
    """
    pdfs, visitadas = [], set()
    while url and url not in visitadas and len(visitadas) < max_paginas:
        visitadas.add(url)
        r = requests.get(url, headers={"User-Agent": user_agent}, timeout=timeout_s)
        r.raise_for_status()
        if htmls is not None:
            htmls.append(r.text)
        encontrados, url = parsear_listado(r.text, url, patron)
        conocidos = {p["url"] for p in pdfs}
        pdfs += [p for p in encontrados if p["url"] not in conocidos]
    return pdfs


# ---------- PDF ----------

def _limpiar(celda: str | None) -> str:
    return " ".join((celda or "").split())


def _horario_de_encabezado(fila: list[str | None]) -> str | None:
    """'SECTORES 11:00 a 13:00' o 'SECTORES - 00:00 a 04:00' → '… a …'.

    None si la fila no es encabezado. La primera columna se llama "CANTÓN" o,
    en algunos PDFs (16 de marzo), "DETALLE".
    """
    celdas = [_limpiar(c) for c in fila]
    if not celdas or clave(celdas[0]) not in ("canton", "detalle"):
        return None
    for c in celdas[1:]:
        m = re.match(r"sectores\s*[-–:]?\s*(.*)", c, re.I)
        if m:
            return m.group(1).strip()
    return ""


def _franjas(horario: str) -> list[str]:
    """'11:00 a 12:00 / 22:00 a 23:00' → dos franjas (un registro por franja)."""
    return [h.strip() for h in re.split(r"\s*/\s*|\s+y\s+", horario) if h.strip()] or [horario]


def extraer_filas(ruta_pdf: Path, provincia: str = "", fecha_respaldo: str = "") -> list[dict[str, str]]:
    """Filas crudas {provincia, canton, fecha, horario, tipo_trabajo, sectores}.

    La fecha y el horario se heredan entre páginas si una página no los trae
    (tabla partida en dos páginas sin encabezado repetido).
    """
    filas: list[dict[str, str]] = []
    fecha, horario, motivo, canton_prev = fecha_respaldo, "", "", ""

    with pdfplumber.open(ruta_pdf) as pdf:
        for pagina in pdf.pages:
            texto = pagina.extract_text(x_tolerance=1) or ""
            m = _RE_FECHA.search(texto)
            if m:
                fecha = m.group(1).strip()
            m = _RE_MOTIVO.search(texto)
            if m:
                motivo = " ".join(m.group(1).split())
                motivo = motivo[0].upper() + motivo[1:]

            for tabla in pagina.extract_tables(AJUSTES_TABLA):
                for fila in tabla:
                    h = _horario_de_encabezado(fila)
                    if h is not None:
                        horario = h or horario
                        continue
                    celdas = [_limpiar(c) for c in fila]
                    if len(celdas) < 2 or not any(celdas):
                        continue
                    canton = celdas[0] or canton_prev   # celdas combinadas verticalmente
                    sectores = " ".join(c for c in celdas[1:] if c).rstrip(".")
                    if not sectores:
                        continue
                    for franja in _franjas(horario):
                        filas.append({
                            "provincia": provincia,
                            "canton": canton.title(),
                            "fecha": fecha,
                            "horario": franja,
                            "tipo_trabajo": motivo,
                            "sectores": sectores,
                        })
                    canton_prev = canton
    return filas
