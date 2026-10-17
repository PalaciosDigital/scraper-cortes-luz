"""Fuente MAE: PDFs reales de "Mantenimientos de Contingencia" (17 de octubre de 2026)."""
from pathlib import Path

from pipeline.fuentes.mae import extraer_filas
from pipeline.normalizar import normalizar_todo
from tests.test_normalizar import CATALOGO

FIX = Path(__file__).resolve().parent / "fixtures"


def test_eeq_dos_zonas_sin_repetir_canton():
    # "CANTÓN: Quito" aparece una sola vez para dos zonas (SANGOLQUÍ y TUMBACO):
    # el encabezado de columnas que se repite entre ellas debe separar las filas.
    filas = extraer_filas(FIX / "mae_eeq_2026-10-17.pdf")
    assert len(filas) == 2
    assert [f["zona_cortes"] for f in filas] == ["SANGOLQUÍ", "TUMBACO"]
    assert all(f["canton"] == "Quito" for f in filas)
    assert all(f["horario"] == "03:00 a 06:00" for f in filas)
    assert filas[0]["sectores"] == "VÍA AMAGUAÑA, SAN JUAN, SAN LUIS"
    assert filas[0]["tipo_trabajo"] == "MANTENIMIENTO PERIÓDICO"


def test_elepco_tres_cortes_mismo_canton():
    filas = extraer_filas(FIX / "mae_elepco_2026-10-17.pdf")
    assert len(filas) == 3
    assert [f["canton"] for f in filas] == ["Latacunga", "La Maná", "La Maná"]
    assert all(f["provincia"] == "COTOPAXI" for f in filas)


def test_eeasa_canton_repetido_sin_colon_no_se_confunde_con_etiqueta():
    # La zona de dos de los cortes es literalmente "CANTÓN PELILEO" (sin ":"):
    # no debe interpretarse como una nueva etiqueta "CANTÓN: …".
    filas = extraer_filas(FIX / "mae_eeasa_2026-10-17.pdf")
    cantones = [f["canton"] for f in filas]
    assert cantones.count("PELILEO") == 2
    assert "PELILEO-PATATE" in cantones
    assert "TENA" in cantones
    assert all(f["zona_cortes"] for f in filas) and all(f["sectores"] for f in filas)


def test_eerssa_escaneado_no_devuelve_filas():
    # Sin texto (PDF escaneado): cae a "formato desconocido" en vigilar.py, no revienta aquí.
    assert extraer_filas(FIX / "mae_eerssa_escaneado_2026-10-17.pdf") == []


def test_normalizacion_completa_sin_descartes():
    for nombre in ("mae_eeq_2026-10-17.pdf", "mae_elepco_2026-10-17.pdf",
                   "mae_eeasa_2026-10-17.pdf", "mae_morona_santiago_2026-10-17.pdf"):
        regs, errs = normalizar_todo(extraer_filas(FIX / nombre), CATALOGO, "Ministerio de Ambiente y Energía")
        assert errs == [], nombre
        assert regs, nombre
        assert all(r["fecha"] == "2026-10-17" for r in regs)
        assert all(r["distribuidora"] == "Ministerio de Ambiente y Energía" for r in regs)
