"""Utilidades de texto compartidas."""
from __future__ import annotations

import re
import unicodedata


def sin_tildes(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def clave(s: str) -> str:
    """Forma comparable: sin tildes, minúsculas, espacios simples."""
    return re.sub(r"\s+", " ", sin_tildes(s).lower()).strip(" .:")
