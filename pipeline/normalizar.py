"""Convierte filas crudas del PDF en registros del esquema."""
from __future__ import annotations

import csv
import re
from datetime import date, datetime
from pathlib import Path

from .texto import clave

DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7,
    "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}


class ErrorNormalizacion(ValueError):
    pass


# ---------- fechas y horas ----------

def normalizar_fecha(texto: str, anio_por_defecto: int | None = None) -> str:
    """Acepta 06/06/2026, 2026-06-06, 6-6-26, 'sábado 6 de junio de 2026', '6 de junio'."""
    t = clave(texto)
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", t)
    if m:
        a, mes, d = map(int, m.groups())
        return date(a, mes, d).isoformat()
    m = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", t)
    if m:
        d, mes, a = map(int, m.groups())
        a = a + 2000 if a < 100 else a
        return date(a, mes, d).isoformat()
    m = re.search(r"(\d{1,2}) de ([a-z]+)(?: de(?:l)? (\d{4}))?", t)
    if m and m.group(2) in MESES:
        a = int(m.group(3)) if m.group(3) else (anio_por_defecto or date.today().year)
        return date(a, MESES[m.group(2)], int(m.group(1))).isoformat()
    raise ErrorNormalizacion(f"Fecha no reconocida: {texto!r}")


def dia_semana(fecha_iso: str) -> str:
    return DIAS[datetime.strptime(fecha_iso, "%Y-%m-%d").weekday()]


def _hora(texto: str) -> str:
    m = re.fullmatch(r"(\d{1,2})(?:[:h.](\d{2}))?", texto.strip().lower().replace(" ", ""))
    if not m:
        raise ErrorNormalizacion(f"Hora no reconocida: {texto!r}")
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    if h > 24 or mi > 59:
        raise ErrorNormalizacion(f"Hora fuera de rango: {texto!r}")
    return f"{h % 24:02d}:{mi:02d}"


def normalizar_horario(texto: str = "", inicio: str = "", fin: str = "") -> str:
    """'09h00 - 13h00', '9:00 a 13:00', '09:00-13:00' o inicio/fin por separado → '09:00 a 13:00'."""
    if inicio and fin:
        return f"{_hora(inicio)} a {_hora(fin)}"
    partes = re.split(r"\s*(?:\ba\b|-|–|—|hasta)\s*", texto.strip().lower())
    partes = [p for p in partes if p]
    if len(partes) != 2:
        raise ErrorNormalizacion(f"Horario no reconocido: {texto!r}")
    return f"{_hora(partes[0])} a {_hora(partes[1])}"


# ---------- cantones y provincias ----------

Catalogo = dict[str, list[tuple[str, str]]]


def cargar_catalogo(ruta: Path) -> Catalogo:
    """CSV canton,provincia[,canton_oficial] → {clave(canton): [(canton_oficial, PROVINCIA), …]}.

    Es una lista porque hay cantones homónimos en provincias distintas
    (p. ej. Bolívar en Carchi y Manabí; Olmedo en Loja y Manabí).
    La columna opcional canton_oficial permite alias: "Macas" → "Morona".
    """
    catalogo: Catalogo = {}
    if not ruta.exists():
        return catalogo
    with open(ruta, encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            oficial = (fila.get("canton_oficial") or fila["canton"]).strip()
            entrada = (oficial, fila["provincia"].strip().upper())
            lista = catalogo.setdefault(clave(fila["canton"]), [])
            if entrada not in lista:
                lista.append(entrada)
    return catalogo


def separar_cantones(texto: str) -> list[str]:
    # Ningún cantón de Ecuador lleva guion, así que cualquier guion o raya separa:
    # "Samborondón - Daule", "Libertad-Salinas", "Santa Elena – Libertad" (CNEL).
    partes = re.split(r"\s*[-–—/,]\s*|\s+y\s+", texto.strip())
    return [p.strip() for p in partes if p.strip()]


def resolver_cantones(texto: str, catalogo: Catalogo,
                      provincia_pdf: str = "") -> list[tuple[str, str | None]]:
    """Devuelve [(canton_normalizado, provincia_o_None)]."""
    salida = []
    for c in separar_cantones(texto):
        opciones = catalogo.get(clave(c), [])
        if not opciones:
            salida.append((c, None))
            continue
        # Homónimos: preferir el que coincide con la provincia del PDF.
        elegido = next((o for o in opciones if clave(o[1]) == clave(provincia_pdf)), opciones[0])
        salida.append(elegido)
    return salida


# ---------- registro completo ----------

def normalizar_registro(crudo: dict[str, str], catalogo: Catalogo,
                        distribuidora: str | None = None,
                        anio_por_defecto: int | None = None) -> dict:
    fecha = normalizar_fecha(crudo.get("fecha", ""), anio_por_defecto)
    horario = normalizar_horario(crudo.get("horario", ""), crudo.get("hora_inicio", ""), crudo.get("hora_fin", ""))

    canton_txt = crudo.get("canton", "").strip()
    prov_pdf = crudo.get("provincia", "").strip().upper()
    resueltos = resolver_cantones(canton_txt, catalogo, prov_pdf)
    prov_catalogo = resueltos[0][1] if resueltos else None
    provincia = prov_catalogo or prov_pdf

    alimentador = crudo.get("alimentador", "").strip()
    registro = {
        "provincia": provincia,
        "canton": canton_txt,
        "alimentador": alimentador,
        "fecha": fecha,
        "dia": dia_semana(fecha),
        "horario": horario,
        "tipo_trabajo": crudo.get("tipo_trabajo", "").strip(),
        "zona_cortes": (crudo.get("zona_cortes") or alimentador).strip(),
        "sectores": crudo.get("sectores", "").strip(),
        "cantones": [c for c, _ in resueltos] or [canton_txt],
    }
    if prov_pdf and prov_catalogo and clave(prov_pdf) != clave(prov_catalogo):
        registro["provincia_original"] = prov_pdf
    if distribuidora:
        registro["distribuidora"] = distribuidora
    return registro


def normalizar_todo(crudos: list[dict[str, str]], catalogo, distribuidora=None):
    """Devuelve (registros, errores). Los errores no detienen el resto."""
    registros, errores = [], []
    for i, c in enumerate(crudos):
        try:
            registros.append(normalizar_registro(c, catalogo, distribuidora))
        except ErrorNormalizacion as e:
            errores.append(f"Fila {i + 1}: {e}")
    # Duplicados exactos (PDFs que repiten filas entre páginas).
    vistos, unicos = set(), []
    for r in registros:
        k = (r["canton"], r["alimentador"], r["fecha"], r["horario"], r["sectores"])
        if k not in vistos:
            vistos.add(k)
            unicos.append(r)
    unicos.sort(key=lambda r: (r["fecha"], r["provincia"], r["canton"], r["horario"]))
    return unicos, errores
