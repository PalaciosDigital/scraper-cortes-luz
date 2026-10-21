"""Fuente CentroSur: tabla real del 14 de octubre de 2026 (65 filas, 8 ANU)."""
import csv
import json
from pathlib import Path

import pytest

from pipeline import vigilar
from pipeline.fuentes import centrosur
from pipeline.fuentes.centrosur import _titulo, a_crudos, canton_en_texto, limpiar_sectores
from pipeline.main import cargar_config
from tests.test_normalizar import CATALOGO

FIX = Path(__file__).resolve().parent / "fixtures"
FILAS = json.loads((FIX / "centrosur_2026-10-14.json").read_text(encoding="utf-8"))


def test_fixture_tiene_la_forma_esperada():
    assert len(FILAS) == 65 and all(len(f) == centrosur.COLUMNAS for f in FILAS)


def test_excluye_anulados_y_separa_pendientes():
    crudos, pendientes, excluidas = a_crudos(FILAS, {}, CATALOGO)
    assert excluidas == 8                                   # los ANU
    assert {c["canton"] for c in crudos} == {"Santa Isabel", "Saraguro"}
    assert len(pendientes) == 21                            # alimentadores sin cantón
    assert all(c["estado_origen"] in {"PRO", "EMM", "PAR"} for c in crudos)


def test_canton_solo_con_nombre_oficial_tras_la_palabra_canton():
    assert canton_en_texto("Sector. Malapamba, Cantón Santa Isabel", CATALOGO) == ("Santa Isabel", "AZUAY")
    assert canton_en_texto("SUMAIPAMBA, CANTÓN SARAGURO", CATALOGO) == ("Saraguro", "LOJA")
    # Sin la palabra «cantón» no se adivina (Santiago, El Pan… son también nombres de calles).
    assert canton_en_texto("Calle Santiago y El Pan", CATALOGO) == ("", "")
    # No arrastra el resto de la frase.
    assert canton_en_texto("cantón Santa Isabel cambio de poste siniestrado", CATALOGO)[0] == "Santa Isabel"


def test_calles_con_nombre_de_canton_no_cuentan():
    # Esquinas reales de Cuenca (tabla de CentroSur, 21 y 22 de octubre de 2026).
    for esquina in ("Cantón Samborondón y 1ero de Mayo", "Cantón Girón y Cantón Paute",
                    "Cantón Gualaceo y Cantón Paute", "CANTON CHUNCHI Y CANTON MONTUFAR",
                    "Avellaneda y Cantón Paute"):
        assert canton_en_texto(esquina, CATALOGO) == ("", ""), esquina
    # Las referencias de lugar siguen valiendo.
    assert canton_en_texto("sector Quillosisa, Parroquia Abdón Calderón, Cantón Santa Isabel",
                           CATALOGO)[0] == "Santa Isabel"
    assert canton_en_texto("Sector San José. Cantón Santa Isabel", CATALOGO)[0] == "Santa Isabel"


def test_esquina_usa_el_canton_del_alimentador():
    filas = [["1", "21/10/26", "0500050V10", "Cantón Samborondón y 1ero de Mayo", "", "13:00", "17:00",
              "Cambio de transformador", "MANTENIMIENTO", "VAL", "A", "PRO"]]
    crudos, pendientes, _ = a_crudos(filas, {"0500050V10": ("Cuenca", "AZUAY")}, CATALOGO)
    assert [c["canton"] for c in crudos] == ["Cuenca"] and not pendientes


def test_tabla_de_alimentadores_y_el_texto_manda():
    alim = {"0500080V01": ("Cuenca", "AZUAY"), "0500140V01": ("Santa Isabel", "AZUAY")}
    crudos, pendientes, _ = a_crudos(FILAS, alim, CATALOGO)
    assert "0500080V01" not in pendientes
    assert any(c["alimentador"] == "0500080V01" and c["canton"] == "Cuenca" for c in crudos)
    # 0500140V01 sirve a Santa Isabel y a Saraguro: el texto «Cantón Saraguro» gana a la tabla.
    assert {c["canton"] for c in crudos if c["alimentador"] == "0500140V01"} >= {"Saraguro", "Santa Isabel"}


def test_titulo_y_limpieza():
    assert _titulo("CAMBIO DE POSTE BV") == "Cambio de poste BV"
    assert _titulo("MEJORA DE REDES BV_MV") == "Mejora de redes BV_MV"
    assert _titulo("OPTIMIZACION DE TRAFO                ") == "Optimizacion de trafo"


def test_limpieza_de_sectores():
    # Textos reales de CentroSur (14 y 21 de octubre de 2026). El buscador parte los sectores por coma.
    casos = {
        "RIO MALACATUS Y AYAPUNGO P#20953": "Rio Malacatus y Ayapungo",
        "HUAGRA HUMA Y RIO CUTUCU P#456665R5": "Huagra Huma y Rio Cutucu",
        "sector Quillosisa, Parroquia Abdón Calderón, Cantón Santa Isabel":
            "Sector Quillosisa - Parroquia Abdón Calderón",
        "Sector. Huascachaca, cantón Santa Isabel": "Sector Huascachaca",
        "Sector San José. Cantón Santa Isabel": "Sector San José",
        "Mayancela, Centro": "Mayancela - Centro",
        "VÍA NULTI - EL ARENAL Y CALLE DE LOS JADES": "Vía Nulti - El Arenal y Calle de los Jades",
        "AV 10 DE AGOSTO Y AV 27 DE FEBRERO": "Av. 10 de Agosto y Av. 27 de Febrero",
        "- MIRADOR EL CALVARIO": "Mirador El Calvario",
        "SALIDA DEL ALIMENTADOR 0721 EN RICAURTE": "Salida del Alimentador 0721 en Ricaurte",
        "cuchucun": "Cuchucun",
        # Las esquinas con nombre de cantón son calles: se quedan.
        "Cantón Samborondón y 1ero de Mayo": "Cantón Samborondón y 1ero de Mayo",
        "CANTON CHUNCHI Y CANTON MONTUFAR": "Canton Chunchi y Canton Montufar",
        # Texto ya en mayúsculas y minúsculas: no se toca.
        "1ero de Mayo y Calle S/N (una cuadra antes de Felipe II)":
            "1ero de Mayo y Calle S/N (una cuadra antes de Felipe II)",
    }
    for crudo, limpio in casos.items():
        assert limpiar_sectores(crudo, CATALOGO) == limpio, crudo
    crudos, _, _ = a_crudos(FILAS, {}, CATALOGO)
    assert all("," not in c["sectores"] and "P#" not in c["sectores"] for c in crudos)


# ---------- integración con la vigilancia ----------

@pytest.fixture
def entorno(tmp_path, monkeypatch):
    cfg = cargar_config()
    alim = tmp_path / "alimentadores.csv"
    alim.write_text("alimentador,canton,provincia,ejemplos\n", encoding="utf-8")
    cfg["vigilancia"] = {"estado": str(tmp_path / "estado.json"), "paginas": [{
        "id": "centrosur", "tipo": "centrosur_tabla", "url": "https://centrosur.test/tabla",
        "distribuidora": "CentroSur", "excluir_estados": ["ANU"], "alimentadores": str(alim)}]}
    monkeypatch.setattr(vigilar, "cargar_config", lambda: cfg)
    monkeypatch.setattr(vigilar, "CARPETA", tmp_path / "v")
    monkeypatch.setattr(vigilar, "DATOS", tmp_path / "v")
    fuente = {"filas": FILAS}
    monkeypatch.setattr(centrosur, "leer_tabla", lambda url, ua, timeout: fuente["filas"])

    def correr(hoy="2026-10-14"):
        return vigilar.main(["--hoy", hoy, "--estado", str(tmp_path / "estado.json")])

    return correr, alim, fuente, tmp_path / "v"


def _completar(alim: Path, asignar: dict):
    filas = list(csv.DictReader(open(alim, encoding="utf-8")))
    for f in filas:
        if f["alimentador"] in asignar:
            f["canton"], f["provincia"] = asignar[f["alimentador"]]
    with open(alim, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["alimentador", "canton", "provincia", "ejemplos"])
        w.writeheader()
        w.writerows(filas)


def test_flujo_centrosur(entorno):
    correr, alim, fuente, carpeta = entorno
    # 1) Primera pasada: sin línea base (la tabla está vigente). Pide asignar 21 alimentadores.
    assert correr() == vigilar.REVISION
    filas_csv = list(csv.DictReader(open(alim, encoding="utf-8")))
    assert len(filas_csv) == 21 and all(f["canton"] == "" and f["ejemplos"] for f in filas_csv)
    # Solo 2 cortes traen «Cantón X»: menos del mínimo (5), no se publica nada.
    assert not (carpeta / "cortes_luz_vigentes.json").exists()
    assert "mínimo 5" in (carpeta / "alerta.md").read_text(encoding="utf-8")
    # 2) Misma tabla, sin cambios: no se repite ningún aviso.
    assert correr() == vigilar.SIN_NOVEDADES
    # 3) Se asigna un alimentador (8 cortes) en el CSV: entran sus cortes, sin pedir nada nuevo.
    _completar(alim, {"0500080V01": ("Cuenca", "AZUAY")})
    assert correr() == vigilar.DATOS_NUEVOS
    datos = json.loads((carpeta / "cortes_luz_vigentes.json").read_text(encoding="utf-8"))
    assert any(r["canton"] == "Cuenca" for r in datos)
    # 4) La foto se reemplaza: si CentroSur anula todo, no quedan cortes de esa fuente.
    fuente["filas"] = [f[:11] + ["ANU"] for f in FILAS]
    assert correr() == vigilar.REVISION                      # «ya no quedan cortes vigentes»


def test_cambio_de_aplicacion_pide_revision(entorno, monkeypatch):
    correr, *_ = entorno

    def roto(*a):
        raise RuntimeError("CentroSur: falta el token 'AJAX_SECURITY_TOKEN' en GXState.")

    monkeypatch.setattr(centrosur, "leer_tabla", roto)
    assert correr() == vigilar.REVISION
