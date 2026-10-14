from pathlib import Path

import pytest

from pipeline.normalizar import (
    ErrorNormalizacion, cargar_catalogo, dia_semana, normalizar_fecha,
    normalizar_horario, normalizar_registro, normalizar_todo, separar_cantones,
)

CATALOGO = cargar_catalogo(Path(__file__).resolve().parent.parent / "data" / "cantones_ecuador.csv")


@pytest.mark.parametrize("entrada,esperado", [
    ("2026-06-06", "2026-06-06"),
    ("06/06/2026", "2026-06-06"),
    ("6-6-26", "2026-06-06"),
    ("Sábado, 6 de junio de 2026", "2026-06-06"),
    ("6 de junio del 2026", "2026-06-06"),
])
def test_fechas(entrada, esperado):
    assert normalizar_fecha(entrada) == esperado


def test_fecha_sin_anio_usa_defecto():
    assert normalizar_fecha("7 de junio", anio_por_defecto=2026) == "2026-06-07"


def test_fecha_invalida():
    with pytest.raises(ErrorNormalizacion):
        normalizar_fecha("pronto")


def test_dia_se_calcula():
    assert dia_semana("2026-06-06") == "Sábado"


@pytest.mark.parametrize("entrada,esperado", [
    ("09:00 a 13:00", "09:00 a 13:00"),
    ("09h00 - 13h00", "09:00 a 13:00"),
    ("9:00-13:00", "09:00 a 13:00"),
    ("23:00 a 01:00", "23:00 a 01:00"),
    ("08:30 hasta 12:30", "08:30 a 12:30"),
])
def test_horarios(entrada, esperado):
    assert normalizar_horario(entrada) == esperado


def test_horario_inicio_fin_separados():
    assert normalizar_horario(inicio="6h00", fin="8h30") == "06:00 a 08:30"


def test_separar_cantones():
    assert separar_cantones("Echeandía / Las Naves / Guaranda") == ["Echeandía", "Las Naves", "Guaranda"]
    assert separar_cantones("Samborondón - Daule - Colimes") == ["Samborondón", "Daule", "Colimes"]
    # Variantes de CNEL Santa Elena: guion sin espacios, guion a un lado y raya.
    assert separar_cantones("Libertad-Salinas") == ["Libertad", "Salinas"]
    assert separar_cantones("Libertad- Salinas") == ["Libertad", "Salinas"]
    assert separar_cantones("Santa Elena – Libertad") == ["Santa Elena", "Libertad"]
    assert separar_cantones("Cuenca") == ["Cuenca"]


def _crudo(**kw):
    base = {"provincia": "AZUAY", "canton": "Cuenca", "alimentador": "0823: Turi",
            "fecha": "06/06/2026", "horario": "09h00 - 13h00",
            "tipo_trabajo": "Mantenimiento", "sectores": "Turi, Patamaba"}
    base.update(kw)
    return base


def test_registro_conserva_campos_originales():
    r = normalizar_registro(_crudo(), CATALOGO)
    for campo in ("provincia", "canton", "alimentador", "fecha", "dia", "horario",
                  "tipo_trabajo", "zona_cortes", "sectores"):
        assert campo in r
    assert r["zona_cortes"] == r["alimentador"]  # se rellena si falta
    assert "provincia_original" not in r


@pytest.mark.parametrize("prov_pdf,canton,prov_ok,canton_ok", [
    ("AZUAY", "Macas", "MORONA SANTIAGO", "Morona"),
    ("SUCUMBÍOS", "Joya de los Sachas", "ORELLANA", "La Joya de los Sachas"),
    ("SUCUMBÍOS", "Francisco de Orellana", "ORELLANA", "Francisco de Orellana"),
    ("GUAYAS", "Buena Fe", "LOS RÍOS", "Buena Fe"),
    ("EL ORO", "Balao", "GUAYAS", "Balao"),
])
def test_corrige_provincia_por_canton(prov_pdf, canton, prov_ok, canton_ok):
    r = normalizar_registro(_crudo(provincia=prov_pdf, canton=canton), CATALOGO)
    assert r["provincia"] == prov_ok
    assert r["provincia_original"] == prov_pdf
    assert r["cantones"] == [canton_ok]
    assert r["canton"] == canton  # el texto original no se toca


def test_cantones_multiples_y_grafia():
    r = normalizar_registro(_crudo(provincia="ESMERALDAS", canton="Quininde"), CATALOGO)
    assert r["cantones"] == ["Quinindé"]
    r = normalizar_registro(_crudo(provincia="GUAYAS", canton="Samborondón - Salitre - Daule"), CATALOGO)
    assert r["cantones"] == ["Samborondón", "Salitre", "Daule"]


def test_normalizar_todo_descarta_duplicados_y_reporta_errores():
    crudos = [_crudo(), _crudo(), _crudo(fecha="sin fecha")]
    regs, errs = normalizar_todo(crudos, CATALOGO)
    assert len(regs) == 1
    assert len(errs) == 1 and "Fila 3" in errs[0]
