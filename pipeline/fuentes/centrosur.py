"""Fuente CentroSur (Azuay, Cañar, Morona Santiago): tabla de trabajos programados.

Cómo publica CentroSur (revisado 2026-10-14):

- https://www.centrosur.gob.ec/trabajos-programados/ incrusta un iframe de su
  extranet: https://extranet.centrosur.gob.ec/PartesDiario/gob.ec.webtrabajosprogramados
- Es una app GeneXus. Por defecto muestra de hoy a hoy+3 días, 10 filas por página.
  Se lee con HTTP simple y el User-Agent honesto de config.yaml (no con un
  navegador: el sitio bloquea "HeadlessChrome" y no se debe esquivar ese bloqueo):
    1. GET de la página → cookies de sesión + GXState (tokens) + rango de fechas.
    2. Un POST AJAX igual al del botón «Sig» de la página, pero pidiendo 100 filas
       por página y la primera página: llega toda la tabla en una respuesta.
  Si GeneXus cambia sus tokens o la forma de la respuesta, leer_tabla lanza
  RuntimeError y la vigilancia avisa (código 20) en lugar de publicar.
- No es un PDF: es una "foto" de lo programado que cambia a diario. Cada pasada
  reemplaza la foto anterior (ver pipeline/vigilar.py, páginas tipo tabla).

Columnas (nombre GeneXus → contenido):
  0 CONNRO     número de consignación
  1 CONZFE     fecha dd/mm/aa
  2 CONALIO    alimentador (p. ej. 0500080V01)
  3 CONZON     zona / dirección (mayúsculas y minúsculas)
  4 CONZONPUB  zona publicada (MAYÚSCULAS; es la que ve el público)
  5 CONZHI     hora inicio
  6 CONZHF     hora fin
  7 CONPCA     descripción del trabajo
  8 CONMOTTAB  motivo (p. ej. MANTENIMIENTO PREVENTIVO BV)
  9 CONESA     VAL
 10 CONEST     Activo / Deshabilitado
 11 CONTMA     PRO / EMM / PAR / ANU (ANU se interpreta como anulado: se excluye)

No hay columna de cantón ni provincia. El cantón sale, en este orden, de:
  1. el texto: "… CANTÓN SANTA ISABEL" en la dirección o la descripción;
  2. data/alimentadores_centrosur.csv (alimentador → cantón, se llena poco a poco);
  3. si no hay nada: el corte queda pendiente y el aviso pide asignar ese alimentador.
No se adivina por nombres sueltos ("Santiago", "El Pan" aparecen en nombres de calles).
"""
from __future__ import annotations

import csv
import html
import json
import re
import time
from pathlib import Path

import requests

from ..texto import clave

COLUMNAS = 12
_RE_CANTON = re.compile(r"\bcant[oó]n\s+(.{2,60})", re.I)
SIGLAS = {"BV", "MV", "AV", "BT", "MT", "AT", "S/E"}


# ---------- lectura (HTTP) ----------

# Identificador del evento AJAX en la URL. Es fijo (igual en sesiones distintas);
# si cambia, el POST falla y la vigilancia lo avisa.
EVENTO_AJAX = "8722e2ea52fd44f599d35d1534485d8e7ca2d469a29afec3fb85c695423920e1"
FILAS_POR_PAGINA = 100


def _estado_gx(html_pagina: str) -> dict:
    m = re.search(r"name=\"GXState\" value='(.*?)'(?=\s*/?>)", html_pagina, re.S)
    if not m:
        raise RuntimeError("CentroSur: la página ya no trae GXState (¿cambió la aplicación?).")
    return json.loads(html.unescape(m.group(1)))


def _fecha_gx(ddmmaa: str) -> str:
    """'14/10/26' → '2026/10/14 00:00:00' (formato de los parámetros AJAX)."""
    d, m, a = ddmmaa.split("/")
    return f"20{a}/{m}/{d} 00:00:00" if len(a) == 2 else f"{a}/{m}/{d} 00:00:00"


def leer_tabla(url: str, user_agent: str, timeout_s: int = 60) -> list[list[str]]:
    """Devuelve todas las filas de la tabla, 12 celdas cada una (texto crudo)."""
    s = requests.Session()
    s.headers["User-Agent"] = user_agent
    r = s.get(url, timeout=timeout_s)
    r.raise_for_status()
    st = _estado_gx(r.text)
    rango = [re.search(rf'id="{c}"[^>]*value="([^"]+)"', r.text) for c in ("vINICIOCONZFE", "vFINCONZFE")]
    if not all(rango):
        raise RuntimeError("CentroSur: no se encontró el rango de fechas en la página.")
    try:
        cabeceras = {"GxAjaxRequest": "1", "Content-Type": "application/json",
                     "AJAX_SECURITY_TOKEN": st["AJAX_SECURITY_TOKEN"],
                     "X-GXAUTH-TOKEN": st["GX_AUTH_WEBTRABAJOSPROGRAMADOS"]}
        cuerpo = {"MPage": False, "cmpCtx": "",
                  "parms": ["0", "0", str(FILAS_POR_PAGINA), 1, False,
                            _fecha_gx(rango[0].group(1)), _fecha_gx(rango[1].group(1)),
                            "webTrabajosProgramados", *[""] * 10, "First"],
                  "hsh": [{"hsh": st["gxhash_vPGMNAME"], "row": ""}],
                  "objClass": "webtrabajosprogramados", "pkgName": "gob.ec",
                  "events": ["GRIDPAGINATIONBAR.CHANGEPAGE"],
                  "grids": {"Grid": {"id": 30, "lastRow": 10, "pRow": ""}}}
    except KeyError as e:
        raise RuntimeError(f"CentroSur: falta el token {e} en GXState (¿cambió la aplicación?).")

    filas, primero = [], 0
    while True:                                       # normalmente una sola vuelta (≤ 100 cortes)
        cuerpo["parms"][0] = str(primero)
        u = f"{url}?{EVENTO_AJAX},gx-no-cache={int(time.time() * 1000)}"
        p = s.post(u, data=json.dumps(cuerpo), headers=cabeceras, timeout=timeout_s)
        p.raise_for_status()
        try:
            j = p.json()
            grid = j["gxGrids"][0]
            n = int(grid.get("Count") or 0)
            pagina = [[str(prop[-1]) for prop in grid[str(i)]["Props"]] for i in range(n)]
        except (ValueError, KeyError, IndexError, TypeError) as e:
            raise RuntimeError(f"CentroSur: respuesta AJAX con otra forma ({e!r}).")
        if any(len(f) != COLUMNAS for f in pagina):
            raise RuntimeError(f"CentroSur cambió la tabla: filas de {len(pagina[0])} columnas "
                               f"(se esperaban {COLUMNAS}).")
        filas += pagina
        if j.get("gxHiddens", {}).get("GRID_nEOF") == "1" or n < FILAS_POR_PAGINA or len(filas) > 2000:
            break
        primero += FILAS_POR_PAGINA
        cuerpo["parms"][-1] = "Next"
    return filas


# ---------- filas → crudos ----------

def cargar_alimentadores(ruta: Path) -> dict[str, tuple[str, str]]:
    """CSV alimentador,canton,provincia → {ALIMENTADOR: (canton, PROVINCIA)}."""
    tabla: dict[str, tuple[str, str]] = {}
    if ruta.exists():
        with open(ruta, encoding="utf-8") as f:
            for fila in csv.DictReader(f):
                if fila.get("alimentador") and fila.get("canton"):
                    tabla[fila["alimentador"].strip().upper()] = (fila["canton"].strip(),
                                                                 (fila.get("provincia") or "").strip().upper())
    return tabla


def canton_en_texto(texto: str, catalogo: dict) -> tuple[str, str]:
    """'… Cantón Santa Isabel' → ('Santa Isabel', 'AZUAY') si el nombre está en el catálogo.

    Solo acepta nombres oficiales del catálogo que sigan a la palabra «cantón»
    (el más largo que coincida), para no arrastrar el resto de la frase.
    """
    for m in _RE_CANTON.finditer(texto or ""):
        tras = clave(m.group(1))
        mejor = max((k for k in catalogo if tras == k or tras.startswith(k + " ") or tras.startswith(k + ",")
                     or tras.startswith(k + ".")), key=len, default=None)
        if mejor:
            return catalogo[mejor][0]
    return "", ""


def _limpio(s: str) -> str:
    s = re.sub(r"[\x00-\x1f]", " ", str(s or ""))     # CentroSur trae \x1a y saltos de línea
    return " ".join(s.split()).strip(" -.,")


def _titulo(s: str) -> str:
    """'CAMBIO DE POSTE BV' → 'Cambio de poste BV' (las siglas técnicas quedan en mayúsculas)."""
    salida = []
    for i, p in enumerate(_limpio(s).split()):
        if p.upper() in SIGLAS or "_" in p:
            salida.append(p.upper())
        else:
            salida.append(p.capitalize() if i == 0 else p.lower())
    return " ".join(salida)


def a_crudos(filas: list[list[str]], alimentadores: dict, catalogo: dict,
             excluir: tuple[str, ...] = ("ANU",)):
    """Devuelve (crudos, pendientes, excluidas).

    pendientes: {alimentador: [direcciones de ejemplo]} sin cantón conocido.
    """
    crudos, pendientes, excluidas = [], {}, 0
    for f in filas:
        nro, fecha, alim, zona, zona_pub, ini, fin, desc, motivo, _esa, est, tma = [_limpio(c) for c in f]
        # CONEST llega como "A"/"D" por HTTP y como "Activo"/"Deshabilitado" en pantalla.
        if tma.upper() in excluir or clave(est) in ("d", "deshabilitado"):
            excluidas += 1
            continue
        alim = alim.upper()
        # CONZON viene en mayúsculas y minúsculas; CONZONPUB, todo en mayúsculas.
        sectores = zona or zona_pub
        # Cada campo por separado: unirlos haría que el cantón arrastre la descripción.
        canton, provincia = canton_en_texto(zona, catalogo)
        if not canton:
            canton, provincia = canton_en_texto(desc, catalogo)
        if not canton and alim in alimentadores:
            canton, provincia = alimentadores[alim]
        if not canton:
            pendientes.setdefault(alim, [])
            if sectores not in pendientes[alim]:
                pendientes[alim].append(sectores)
            continue
        crudos.append({
            "provincia": provincia,
            "canton": canton,
            "alimentador": alim,
            "fecha": fecha,
            "hora_inicio": ini,
            "hora_fin": fin,
            "tipo_trabajo": _titulo(motivo),
            "zona_cortes": alim,
            "sectores": sectores,
            "consignacion": nro,
            "estado_origen": tma.upper(),
        })
    return crudos, pendientes, excluidas
