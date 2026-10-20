"""Flujo de vigilancia con un sitio falso (sin red) y PDFs reales de CNEL."""
from __future__ import annotations

import json
import shutil
from datetime import date, datetime, timezone
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
        self.archivos: dict[str, str] = {}     # URL → fixture que se sirve (para reemplazos)
        self.firmas: dict[str, str] = {}       # URL → firma HEAD (ETag|Last-Modified|tamaño)

    def reemplazar(self, nombre: str, fixture: str, firma: str):
        """Sube otro contenido con el mismo nombre de archivo."""
        url = f"https://cnel.test/{nombre}"
        self.archivos[url], self.firmas[url] = fixture, firma

    def publicar(self, fixture: str, nombre: str | None = None, firma: str = "v1"):
        url = f"https://cnel.test/{nombre or fixture}"
        self.pdfs.insert(0, {"url": url, "titulo": ""})
        self.archivos[url], self.firmas[url] = fixture, firma
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
                                                  shutil.copy(FIX / sitio.archivos[url], destino)))
    monkeypatch.setattr(vigilar, "firma_remota", lambda url, *a: sitio.firmas.get(url))

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


def test_paginas_prioritarias_lee_config():
    cfg_vig = {"paginas": [{"id": "mae-mantenimientos", "prioridad": True}, {"id": "centrosur"}]}
    assert vigilar.paginas_prioritarias(cfg_vig) == {"mae-mantenimientos"}


def test_fuente_prioritaria_reemplaza_a_las_demas_en_su_canton_y_fecha(tmp_path, monkeypatch):
    # El Ministerio (prioritaria) y CNEL reportan el mismo cantón+fecha con
    # sectores distintos: debe ganar el Ministerio, no "el PDF más nuevo".
    monkeypatch.setattr(vigilar, "DATOS", tmp_path)
    registros = tmp_path / "vigilancia" / "registros"
    registros.mkdir(parents=True)
    (registros / "mae.json").write_text(json.dumps([
        {"canton": "Quito", "provincia": "PICHINCHA", "fecha": "2026-10-20",
         "horario": "03:00 a 06:00", "sectores": "Versión del Ministerio"},
    ]), encoding="utf-8")
    (registros / "cnel.json").write_text(json.dumps([
        {"canton": "Quito", "provincia": "PICHINCHA", "fecha": "2026-10-20",
         "horario": "03:00 a 06:00", "sectores": "Versión de CNEL (texto distinto)"},
        {"canton": "Cuenca", "provincia": "AZUAY", "fecha": "2026-10-21",
         "horario": "08:00 a 10:00", "sectores": "Corte que solo reporta CNEL"},
    ]), encoding="utf-8")
    estado = {"paginas": {
        "mae-mantenimientos": {"pdfs": {"a": {"estado": "ok", "sha256": "mae", "visto_en": "2026-10-17T00:00"}}},
        # "visto_en" más reciente que el del Ministerio: sin prioridad, ganaría por recencia.
        "cnel-guayaquil": {"pdfs": {"b": {"estado": "ok", "sha256": "cnel", "visto_en": "2026-10-17T05:00"}}},
    }}

    vigentes = vigilar.armar_vigentes(estado, date(2026, 10, 17), 60, frozenset({"mae-mantenimientos"}))

    quito = [r for r in vigentes if r["canton"] == "Quito"]
    assert len(quito) == 1
    assert quito[0]["sectores"] == "Versión del Ministerio"
    # Un cantón/fecha que el Ministerio no cubre: la otra fuente se conserva.
    assert any(r["canton"] == "Cuenca" and r["sectores"] == "Corte que solo reporta CNEL" for r in vigentes)


def test_pdf_reemplazado_con_el_mismo_nombre_se_reprocesa(entorno):
    sitio, correr, carpeta = entorno
    correr("2026-03-15")
    sitio.publicar("cnel_santa_elena_2026-03-16_detalle.pdf", nombre="cronograma.pdf")
    assert correr("2026-03-15") == vigilar.DATOS_NUEVOS
    correr("2026-03-15", "--aprobar")
    assert correr("2026-03-15") == vigilar.SIN_NOVEDADES          # misma firma: nada que hacer
    sitio.reemplazar("cronograma.pdf", "cnel_santa_elena_2026-03-21.pdf", firma="v2")
    assert correr("2026-03-15") == vigilar.DATOS_NUEVOS
    datos = json.loads((carpeta / "cortes_luz_vigentes.json").read_text(encoding="utf-8"))
    assert {r["fecha"] for r in datos} == {"2026-03-21"}          # la versión vieja ya no cuenta
    assert "mismo nombre" in (carpeta / "alerta.md").read_text(encoding="utf-8")


def test_firma_cambia_pero_contenido_igual_no_avisa(entorno):
    sitio, correr, carpeta = entorno
    correr("2026-03-20")
    sitio.publicar("cnel_santa_elena_2026-03-21.pdf")
    correr("2026-03-20")
    correr("2026-03-20", "--aprobar")
    sitio.firmas["https://cnel.test/cnel_santa_elena_2026-03-21.pdf"] = "v2"   # solo cambió la fecha
    assert correr("2026-03-20") == vigilar.SIN_NOVEDADES


def test_hoy_es_la_fecha_de_ecuador_no_la_de_utc():
    # 00:51 UTC del 18 de octubre = 19:51 del 17 en Ecuador: los cortes del 17 siguen vigentes.
    assert vigilar.hoy_ecuador(datetime(2026, 10, 18, 0, 51, tzinfo=timezone.utc)) == date(2026, 10, 17)
    assert vigilar.hoy_ecuador(datetime(2026, 10, 18, 5, 0, tzinfo=timezone.utc)) == date(2026, 10, 18)


def test_lista_de_enlaces_de_drive_se_procesa_sin_linea_base(tmp_path, monkeypatch):
    """Página tipo `lista` (enlaces de @CNEL_EP anotados a mano): entra todo en la primera pasada."""
    lista = tmp_path / "enlaces.csv"
    lista.write_text("drive_id,archivo,unidad,post,publicado\n"
                     "ABC123,1 LOS RIOS.pdf,Los Ríos,https://x.com/CNEL_EP/status/1,2026-10-20T15:19Z\n",
                     encoding="utf-8")
    cfg = cargar_config()
    cfg["vigilancia"] = {"estado": str(tmp_path / "estado.json"), "paginas": [{
        "id": "cnel-x-drive", "tipo": "cnel_unidades", "lista": str(lista), "url": "https://x.com/CNEL_EP",
        "distribuidora": "CNEL EP", "prioridad": True}]}
    cfg["validacion"]["min_registros"] = 1                 # el PDF de prueba trae un solo corte
    monkeypatch.setattr(vigilar, "cargar_config", lambda: cfg)
    monkeypatch.setattr(vigilar, "CARPETA", tmp_path / "vigilancia")
    monkeypatch.setattr(vigilar, "DATOS", tmp_path / "vigilancia")
    monkeypatch.setattr(vigilar, "firma_remota", lambda url, *a: "v1")
    descargas = []

    def descargar(url, destino, *a):
        descargas.append(url)
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(FIX / "cnel_x_los_rios_2026-10-22.pdf", destino)

    monkeypatch.setattr(vigilar, "descargar_pdf", descargar)
    assert vigilar.main(["--hoy", "2026-10-20", "--estado", str(tmp_path / "estado.json")]) == vigilar.DATOS_NUEVOS
    assert descargas == ["https://drive.google.com/uc?export=download&id=ABC123"]
    datos = json.loads((tmp_path / "vigilancia" / "cortes_luz_vigentes.json").read_text(encoding="utf-8"))
    assert [(r["canton"], r["cantones"], r["fecha"]) for r in datos] == [
        ("Ventanas - Quinsaloma", ["Ventanas", "Quinsaloma"], "2026-10-22")]
