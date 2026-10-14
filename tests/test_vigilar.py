"""Flujo de vigilancia con un sitio falso (sin red) y PDFs reales de CNEL."""
import json
import shutil
from pathlib import Path

import pytest

from pipeline import vigilar
from pipeline.fuentes import cnel
from pipeline.main import cargar_config

FIX = Path(__file__).resolve().parent / "fixtures"
URL = "https://cnel.test/trabajos-programados/"
VACIA = "<div>Por el momento no contamos con Trabajos Programados</div>"


class SitioFalso:
    """Simula la página vigilada: qué PDFs lista y qué HTML devuelve."""

    def __init__(self):
        self.pdfs: list[dict] = []
        self.html = VACIA

    def publicar(self, fixture: str):
        self.pdfs.insert(0, {"url": f"https://cnel.test/{fixture}", "titulo": ""})
        self.html = "<h3>Cronogramas</h3>"

    def listar(self, url, ua, patron, timeout, max_paginas=20, htmls=None):
        if htmls is not None:
            htmls.append(self.html)
        return list(self.pdfs)


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    sitio = SitioFalso()
    cfg = cargar_config()
    cfg["vigilancia"] = {"estado": str(tmp_path / "estado.json"), "paginas": [{
        "id": "prueba", "tipo": "cnel_emergentes", "url": URL, "provincia": "SANTA ELENA",
        "distribuidora": "CNEL EP Santa Elena", "texto_vacio": "no contamos con Trabajos Programados"}]}
    monkeypatch.setattr(vigilar, "cargar_config", lambda: cfg)
    monkeypatch.setattr(vigilar, "CARPETA", tmp_path / "vigilancia")
    monkeypatch.setattr(vigilar, "DATOS", tmp_path / "vigilancia")
    monkeypatch.setattr(cnel, "listar_pdfs", sitio.listar)
    monkeypatch.setattr(vigilar, "descargar_pdf",
                        lambda url, destino, *a: (destino.parent.mkdir(parents=True, exist_ok=True),
                                                  shutil.copy(FIX / url.rsplit("/", 1)[-1], destino)))

    def correr(hoy, *extra):
        return vigilar.main(["--hoy", hoy, "--estado", str(tmp_path / "estado.json"), *extra])

    correr.cfg = cfg
    return sitio, correr, tmp_path / "vigilancia"


def test_primera_pasada_es_linea_base(entorno):
    sitio, correr, carpeta = entorno
    sitio.publicar("cnel_santa_elena_2026-03-21.pdf")       # ya existía antes de vigilar
    assert correr("2026-03-21") == vigilar.SIN_NOVEDADES
    assert not (carpeta / "cortes_luz_vigentes.json").exists()


def test_pdf_nuevo_genera_vigentes(entorno):
    sitio, correr, carpeta = entorno
    assert correr("2026-03-20") == vigilar.SIN_NOVEDADES    # línea base: página vacía
    sitio.publicar("cnel_santa_elena_2026-03-21.pdf")
    assert correr("2026-03-20") == vigilar.DATOS_NUEVOS
    datos = json.loads((carpeta / "cortes_luz_vigentes.json").read_text(encoding="utf-8"))
    assert len(datos) == 47 and {r["fecha"] for r in datos} == {"2026-03-21"}
    assert correr("2026-03-20") == vigilar.SIN_NOVEDADES    # segunda pasada: nada que hacer


def test_formato_desconocido_pide_revision(entorno):
    sitio, correr, carpeta = entorno
    correr("2026-03-20")
    sitio.publicar("formato_desconocido.pdf")
    assert correr("2026-03-20") == vigilar.REVISION
    assert "ningún extractor reconoce" in (carpeta / "alerta.md").read_text(encoding="utf-8")


def test_desaparece_aviso_de_pagina_vacia(entorno):
    sitio, correr, carpeta = entorno
    correr("2026-03-20")
    sitio.html = "<p>Cortes en Guayaquil: ver imagen</p>"   # publicaron sin PDF
    assert correr("2026-03-20") == vigilar.REVISION
    assert "desapareció" in (carpeta / "alerta.md").read_text(encoding="utf-8")


def test_cortes_vencidos_y_fin(entorno):
    sitio, correr, carpeta = entorno
    correr("2026-03-15")
    sitio.publicar("cnel_santa_elena_2026-03-16_detalle.pdf")
    sitio.publicar("cnel_santa_elena_2026-03-21.pdf")
    assert correr("2026-03-15") == vigilar.DATOS_NUEVOS
    # Vence el 16 de marzo: se republica sin avisar.
    assert correr("2026-03-18") == vigilar.SIN_NOVEDADES
    datos = json.loads((carpeta / "cortes_luz_vigentes.json").read_text(encoding="utf-8"))
    assert {r["fecha"] for r in datos} == {"2026-03-21"}
    # Ya no queda nada vigente: se pide decisión humana y no se vacía el JSON.
    assert correr("2026-03-25") == vigilar.REVISION
    assert (carpeta / "cortes_luz_vigentes.json").exists()


def test_expandir_unidades():
    paginas = vigilar.expandir_paginas({"paginas": [{
        "id": "cnel-programados", "url": "https://x/?unidad={unidad}", "distribuidora": "CNEL EP",
        "unidades": {"guayaquil": ["Guayaquil", "GUAYAS"]}}]})
    assert paginas == [{"id": "cnel-programados-guayaquil", "url": "https://x/?unidad=guayaquil",
                        "distribuidora": "CNEL EP Guayaquil", "provincia": "GUAYAS"}]


def _fechas(ruta):
    return {r["fecha"] for r in json.loads(ruta.read_text(encoding="utf-8"))}


def test_revision_espera_aprobacion(entorno):
    sitio, correr, carpeta = entorno
    publicado = carpeta / "cortes_luz_publicado.json"
    correr("2026-03-15")
    sitio.publicar("cnel_santa_elena_2026-03-16_detalle.pdf")
    sitio.publicar("cnel_santa_elena_2026-03-21.pdf")
    assert correr("2026-03-15") == vigilar.DATOS_NUEVOS
    assert not publicado.exists()                       # el buscador aún no lo ve
    # Vencen cortes con un candidato pendiente: NO se cuela al publicado.
    assert correr("2026-03-18") == vigilar.SIN_NOVEDADES
    assert not publicado.exists()
    # Aprobación (botón de GitHub).
    assert correr("2026-03-18", "--aprobar") == vigilar.SIN_NOVEDADES
    assert _fechas(publicado) == {"2026-03-21"}


def test_vencidos_se_publican_solos_tras_aprobar(entorno):
    sitio, correr, carpeta = entorno
    publicado = carpeta / "cortes_luz_publicado.json"
    correr("2026-03-15")
    sitio.publicar("cnel_santa_elena_2026-03-16_detalle.pdf")
    sitio.publicar("cnel_santa_elena_2026-03-21.pdf")
    correr("2026-03-15")
    correr("2026-03-15", "--aprobar")
    assert _fechas(publicado) == {"2026-03-16", "2026-03-21"}
    assert correr("2026-03-18") == vigilar.SIN_NOVEDADES
    assert _fechas(publicado) == {"2026-03-21"}         # sin aprobación: solo retiró lo vencido


def test_modo_directa_publica_sin_esperar(entorno):
    sitio, correr, carpeta = entorno
    correr.cfg["vigilancia"]["publicacion"] = "directa"
    correr("2026-03-20")
    sitio.publicar("cnel_santa_elena_2026-03-21.pdf")
    assert correr("2026-03-20") == vigilar.DATOS_NUEVOS
    assert _fechas(carpeta / "cortes_luz_publicado.json") == {"2026-03-21"}


def test_formato_desconocido_no_publica(entorno):
    sitio, correr, carpeta = entorno
    correr.cfg["vigilancia"]["publicacion"] = "directa"
    correr("2026-03-20")
    sitio.publicar("cnel_santa_elena_2026-03-21.pdf")
    sitio.publicar("formato_desconocido.pdf")           # llega junto a uno bueno
    assert correr("2026-03-20") == vigilar.REVISION
    assert not (carpeta / "cortes_luz_publicado.json").exists()
