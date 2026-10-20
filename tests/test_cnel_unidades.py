"""Fuente "Unidades de Negocio CNEL EP": PDFs reales de octubre de 2026."""
from pathlib import Path

from pipeline.fuentes.cnel_unidades import extraer_filas
from pipeline.normalizar import normalizar_todo
from tests.test_normalizar import CATALOGO

FIX = Path(__file__).resolve().parent / "fixtures"


def test_guayaquil_tres_cortes():
    filas = extraer_filas(FIX / "cnel_unidad_guayaquil_2026-10-17.pdf")
    assert len(filas) == 3
    assert [f["canton"] for f in filas] == ["Guayaquil", "Guayaquil", "Playas"]
    assert all(f["provincia"] == "Guayas" for f in filas)
    assert all(f["horario"] == "03:00 a 06:00" for f in filas)
    assert filas[0]["sectores"].startswith("Edificio River Front 1")


def test_guayas_los_rios_incluye_bloques_sin_canton():
    # Las páginas de CELEC Transelectric afectan a toda la provincia, sin
    # "cantón X": se usa la provincia también como cantón, no se pierde la fila.
    filas = extraer_filas(FIX / "cnel_unidad_guayas_los_rios_2026-10-17.pdf")
    assert len(filas) == 5
    assert [f["canton"] for f in filas][:2] == ["Samborondón", "Durán"]
    sin_canton_especifico = [f for f in filas if f["canton"] == f["provincia"]]
    assert len(sin_canton_especifico) == 3   # Guayas, Los Ríos, Manabi (CELEC)


def test_el_oro_cantones_de_otras_provincias():
    # La unidad "El Oro" también cubre cantones de Azuay y Guayas.
    filas = extraer_filas(FIX / "cnel_unidad_el_oro_2026-10-17.pdf")
    assert len(filas) == 5
    provincias = {f["provincia"] for f in filas}
    assert provincias == {"El Oro", "Azuay", "Guayas"}


def test_sucumbios_horario_con_h():
    # "De 03H00 a 06H00" (con H, no ":") en todos los bloques.
    filas = extraer_filas(FIX / "cnel_unidad_sucumbios_2026-10-17.pdf")
    assert len(filas) == 4
    assert all(f["horario"] == "03:00 a 06:00" for f in filas)
    assert filas[0]["canton"] == "Lago Agrio"


def test_normalizacion_completa_sin_descartes():
    for nombre in ("cnel_unidad_guayaquil_2026-10-17.pdf", "cnel_unidad_guayas_los_rios_2026-10-17.pdf",
                   "cnel_unidad_el_oro_2026-10-17.pdf", "cnel_unidad_sucumbios_2026-10-17.pdf"):
        regs, errs = normalizar_todo(extraer_filas(FIX / nombre), CATALOGO, "CNEL EP")
        assert errs == [], nombre
        assert regs, nombre
        assert all(r["fecha"] == "2026-10-17" for r in regs)
        assert all(r["distribuidora"] == "CNEL EP" for r in regs)


def test_drive_de_x_cantones_desde_los_sectores():
    # PDF de @CNEL_EP en X (Google Drive), 22 oct 2026: el encabezado solo dice
    # "Los Ríos"; los cantones van en los sectores ("Cantón Ventanas: …").
    filas = extraer_filas(FIX / "cnel_x_los_rios_2026-10-22.pdf")
    assert [(f["provincia"], f["canton"]) for f in filas] == [("Los Ríos", "Ventanas - Quinsaloma")]
    filas = extraer_filas(FIX / "cnel_x_manabi_2026-10-22.pdf")
    assert [(f["provincia"], f["canton"], f["horario"]) for f in filas] == [("Manabí", "Portoviejo", "03:00 a 06:00")]
