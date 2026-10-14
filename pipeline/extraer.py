"""Extracción de tablas del PDF con pdfplumber.

El formato exacto del PDF aún no se conoce. Este extractor es genérico:
busca en cada tabla una fila de encabezados que coincida con los alias de
`config.yaml → columnas` y devuelve filas crudas como dicts {campo: texto}.
Ajusta los alias tras ejecutar `--inspeccionar`.
"""
from __future__ import annotations

from pathlib import Path

import pdfplumber

from .texto import clave


def inspeccionar(ruta_pdf: Path, max_filas: int = 6) -> str:
    """Resumen legible de las tablas del PDF para decidir cómo extraer."""
    lineas: list[str] = []
    with pdfplumber.open(ruta_pdf) as pdf:
        lineas.append(f"Páginas: {len(pdf.pages)}")
        for n, pagina in enumerate(pdf.pages, start=1):
            tablas = pagina.extract_tables()
            texto = (pagina.extract_text() or "").strip()
            lineas.append(f"\n=== Página {n}: {len(tablas)} tabla(s), {len(texto)} caracteres de texto")
            if not tablas and not texto:
                lineas.append("  Sin texto: probablemente escaneado → requiere OCR.")
            for t, tabla in enumerate(tablas, start=1):
                lineas.append(f"  -- Tabla {t}: {len(tabla)} filas x {len(tabla[0]) if tabla else 0} columnas")
                for fila in tabla[:max_filas]:
                    lineas.append("     | " + " | ".join((c or "").replace("\n", " ")[:30] for c in fila))
            if n >= 3:
                lineas.append(f"\n(Se muestran 3 de {len(pdf.pages)} páginas)")
                break
    return "\n".join(lineas)


def _mapear_encabezados(fila: list[str | None], alias: dict[str, list[str]]) -> dict[int, str] | None:
    """Si la fila parece de encabezados, devuelve {índice_columna: campo}."""
    mapa: dict[int, str] = {}
    for i, celda in enumerate(fila):
        k = clave(celda or "")
        if not k:
            continue
        for campo, nombres in alias.items():
            if k in {clave(x) for x in nombres}:
                mapa[i] = campo
                break
    # Exigimos al menos 3 columnas reconocidas para considerarla encabezado.
    return mapa if len(mapa) >= 3 else None


def extraer_filas(ruta_pdf: Path, alias: dict[str, list[str]]) -> list[dict[str, str]]:
    """Devuelve las filas crudas de todas las tablas reconocidas del PDF.

    Los encabezados detectados se reutilizan en páginas siguientes, porque
    muchos PDFs solo los repiten en la primera página.
    """
    filas: list[dict[str, str]] = []
    mapa_actual: dict[int, str] | None = None
    previo: dict[str, str] | None = None

    with pdfplumber.open(ruta_pdf) as pdf:
        for pagina in pdf.pages:
            for tabla in pagina.extract_tables():
                for fila in tabla:
                    posible = _mapear_encabezados(fila, alias)
                    if posible:
                        mapa_actual = posible
                        continue
                    if not mapa_actual or not any((c or "").strip() for c in fila):
                        continue
                    registro = {
                        campo: " ".join((fila[i] or "").split())
                        for i, campo in mapa_actual.items() if i < len(fila)
                    }
                    # Celdas combinadas: pdfplumber deja vacías las celdas
                    # verticalmente fusionadas; heredamos de la fila anterior.
                    if previo:
                        for campo in ("provincia", "canton", "fecha", "dia"):
                            if campo in registro and not registro[campo]:
                                registro[campo] = previo.get(campo, "")
                    filas.append(registro)
                    previo = registro
    return filas
