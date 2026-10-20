"""Descarga del PDF de origen."""
from __future__ import annotations

import hashlib
from pathlib import Path

import requests


def sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(65536), b""):
            h.update(bloque)
    return h.hexdigest()


def firma_remota(url: str, user_agent: str, timeout_s: int = 60) -> str | None:
    """ETag + Last-Modified + Content-Length del archivo, sin descargarlo (HEAD).

    Sirve para notar que reemplazaron un PDF conservando su nombre. None si el
    servidor no manda ninguna de esas cabeceras.
    """
    r = requests.head(url, headers={"User-Agent": user_agent}, timeout=timeout_s, allow_redirects=True)
    r.raise_for_status()
    partes = [r.headers.get(h, "") for h in ("ETag", "Last-Modified", "Content-Length")]
    return "|".join(partes) if any(partes) else None


def descargar_pdf(url: str, destino: Path, user_agent: str, timeout_s: int = 60) -> Path:
    """Descarga el PDF y verifica que realmente sea un PDF."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    r = requests.get(url, headers={"User-Agent": user_agent}, timeout=timeout_s)
    r.raise_for_status()
    if not r.content.startswith(b"%PDF"):
        tipo = r.headers.get("Content-Type", "?")
        raise ValueError(f"La URL no devolvió un PDF (Content-Type: {tipo}). "
                         "¿Cambió la página de la distribuidora?")
    destino.write_bytes(r.content)
    return destino
