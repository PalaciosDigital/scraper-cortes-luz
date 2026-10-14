"""Reglas de calidad. Si hay errores, el pipeline NO publica."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from jsonschema import Draft202012Validator

ESQUEMA = Path(__file__).resolve().parent.parent / "schema" / "cortes_luz.schema.json"


@dataclass
class Resultado:
    errores: list[str] = field(default_factory=list)
    advertencias: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errores


def validar(registros: list[dict], reglas: dict, anterior: int | None = None,
            hoy: date | None = None) -> Resultado:
    res = Resultado()
    hoy = hoy or date.today()

    if len(registros) < reglas.get("min_registros", 1):
        res.errores.append(f"Solo {len(registros)} registros (mínimo {reglas.get('min_registros')}).")

    if anterior:
        caida = 100 * (anterior - len(registros)) / anterior
        if caida > reglas.get("caida_maxima_pct", 100):
            res.errores.append(f"Los registros cayeron {caida:.0f} % ({anterior} → {len(registros)}). "
                               "Posible cambio de formato del PDF.")

    validador = Draft202012Validator(json.loads(ESQUEMA.read_text(encoding="utf-8")))
    for i, r in enumerate(registros):
        for e in validador.iter_errors(r):
            res.errores.append(f"Registro {i + 1} ({r.get('canton', '?')}): {e.message}")

    minimo = hoy - timedelta(days=reglas.get("dias_pasado_max", 7))
    maximo = hoy + timedelta(days=reglas.get("dias_futuro_max", 60))
    fuera = [r for r in registros if not (minimo.isoformat() <= r.get("fecha", "") <= maximo.isoformat())]
    if fuera and len(fuera) == len(registros):
        res.errores.append(f"Ninguna fecha está entre {minimo} y {maximo}: ¿el PDF está desactualizado?")
    elif fuera:
        res.advertencias.append(f"{len(fuera)} registros con fechas fuera de rango.")

    sin_prov = sorted({r["canton"] for r in registros if "provincia_original" in r})
    if sin_prov:
        res.advertencias.append("Provincia corregida por catálogo en: " + ", ".join(sin_prov))

    return res
