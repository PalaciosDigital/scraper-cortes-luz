from datetime import date

from pipeline.validar import validar

REGLAS = {"min_registros": 2, "caida_maxima_pct": 70, "dias_pasado_max": 7, "dias_futuro_max": 60}
HOY = date(2026, 6, 1)


def reg(**kw):
    base = {"provincia": "AZUAY", "canton": "Cuenca", "alimentador": "A", "fecha": "2026-06-06",
            "dia": "Sábado", "horario": "09:00 a 13:00", "tipo_trabajo": "x", "zona_cortes": "A",
            "sectores": "Turi", "cantones": ["Cuenca"]}
    base.update(kw)
    return base


def test_valido():
    assert validar([reg(), reg()], REGLAS, hoy=HOY).ok


def test_pocos_registros():
    assert not validar([reg()], REGLAS, hoy=HOY).ok


def test_caida_brusca():
    res = validar([reg(), reg()], REGLAS, anterior=100, hoy=HOY)
    assert not res.ok and "cayeron" in res.errores[0]


def test_esquema_horario_malo():
    res = validar([reg(), reg(horario="9 a 13")], REGLAS, hoy=HOY)
    assert not res.ok


def test_campo_desconocido_rechazado():
    assert not validar([reg(), reg(extra=1)], REGLAS, hoy=HOY).ok


def test_pdf_viejo():
    res = validar([reg(fecha="2025-01-01"), reg(fecha="2025-01-02")], REGLAS, hoy=HOY)
    assert not res.ok and "desactualizado" in res.errores[0]
