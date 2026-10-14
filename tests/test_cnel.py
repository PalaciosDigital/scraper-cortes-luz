"""Fuente CNEL EP: listado HTML y PDFs reales de Santa Elena (marzo 2026)."""
from pathlib import Path

from pipeline.fuentes.cnel import extraer_filas, parsear_listado
from pipeline.normalizar import normalizar_todo
from tests.test_normalizar import CATALOGO

FIX = Path(__file__).resolve().parent / "fixtures"
BASE = "https://www.cnelep.gob.ec/trabajos-emergentes/"

# Fragmento reducido del HTML real: menú con un PDF que no es cronograma,
# dos doc-cards (una con &#8211;) y la paginación.
LISTADO = """
<li class="menu-item"><a href="https://www.cnelep.gob.ec/wp-content/uploads/2026/02/Plan-Estratégico-CNEL-EP-2025-2029-1.pdf">Plan</a></li>
<div class="doc-card"><div class="doc-details"><p>FECHA PROGRAMADA</p>
  <h3>Planificación de horarios y sectores – 21 de marzo de 2026</h3></div>
  <a href="https://www.cnelep.gob.ec/wp-content/uploads/2026/03/CRONOGRAMA-21.03.26.pdf" class="btn-descargar">Descargar PDF</a></div>
<div class="doc-card"><div class="doc-details">
  <h3>Planificación de horarios y sectores &#8211; 4 de marzo de 2026</h3></div>
  <a href="/wp-content/uploads/2026/03/STE-EDITABLE-CORTE-4-MARZO-1.pdf" class="btn-descargar">Descargar PDF</a></div>
<footer><a href="https://www.gobiernoelectronico.gob.ec/wp-content/uploads/2019/07/Acuerdo-012-2019.pdf">Acuerdo</a></footer>
<span class='page-numbers current'>1</span>
<a class="next page-numbers" href="https://www.cnelep.gob.ec/trabajos-emergentes/page/2/">›</a>
"""


def test_listado_filtra_menu_y_empareja_titulos():
    # Con el patrón abierto que usa la vigilancia: fuera el menú y el PDF de otro dominio.
    pdfs, siguiente = parsear_listado(LISTADO, BASE, "^(?!.*plan-estrat)")
    assert [p["url"].rsplit("/", 1)[-1] for p in pdfs] == [
        "CRONOGRAMA-21.03.26.pdf", "STE-EDITABLE-CORTE-4-MARZO-1.pdf"]
    assert pdfs[0]["titulo"].endswith("21 de marzo de 2026")
    assert pdfs[1]["titulo"].endswith("4 de marzo de 2026")          # entidad HTML resuelta
    assert pdfs[1]["url"].startswith("https://www.cnelep.gob.ec/")     # enlace relativo resuelto
    assert siguiente == BASE + "page/2/"


def test_listado_sin_titulos_ni_paginacion():
    # Esmeraldas: el enlace envuelve un banner, no hay <h3> ni paginación.
    url = "https://www.cnelep.gob.ec/wp-content/uploads/2026/05/CRONOGRAMA-19.5.26.pdf"
    html = f'<p><a href="{url}"><img src="18.jpg"></a></p>'
    pdfs, siguiente = parsear_listado(html, BASE, "cronograma")
    assert pdfs == [{"url": url, "titulo": ""}]
    assert siguiente is None


def test_pdf_formato_estandar():
    filas = extraer_filas(FIX / "cnel_santa_elena_2026-03-21.pdf", "SANTA ELENA")
    assert len(filas) == 47
    f = filas[0]
    assert f["fecha"] == "21 de Marzo de 2026"
    assert f["horario"] == "11:00 a 13:00"
    assert f["canton"] == "Santa Elena"
    # text_x_tolerance=1: palabras separadas, no "ManantialdeChanduy".
    assert f["sectores"].startswith("Manantial de Chanduy, Puerto de Chanduy")
    assert f["tipo_trabajo"].startswith("Afectación de autotransformador")


def test_pdf_variante_detalle():
    # Primera columna "DETALLE" y horario "SECTORES - 00:00 a 04:00".
    filas = extraer_filas(FIX / "cnel_santa_elena_2026-03-16_detalle.pdf", "SANTA ELENA")
    assert filas[0]["horario"] == "00:00 a 04:00"
    assert not any(clave in f["canton"].lower() for f in filas for clave in ("detalle", "corporación"))


def test_pdf_doble_franja_se_separa():
    filas = extraer_filas(FIX / "cnel_santa_elena_2026-03-09_doble_franja.pdf", "SANTA ELENA")
    horarios = {f["horario"] for f in filas}
    assert "11:00 a 12:00" in horarios and "22:00 a 23:00" in horarios
    assert not any("/" in h for h in horarios)


def test_normalizacion_completa_sin_descartes():
    for nombre in ("cnel_santa_elena_2026-03-21.pdf", "cnel_santa_elena_2026-03-16_detalle.pdf",
                   "cnel_santa_elena_2026-03-09_doble_franja.pdf"):
        regs, errs = normalizar_todo(extraer_filas(FIX / nombre, "SANTA ELENA"), CATALOGO, "CNEL EP Santa Elena")
        assert errs == [], nombre
        assert all(r["provincia"] == "SANTA ELENA" for r in regs)
        assert all(r["distribuidora"] == "CNEL EP Santa Elena" for r in regs)
