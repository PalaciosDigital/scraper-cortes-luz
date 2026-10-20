"""Vigilancia de fuentes: detecta cronogramas nuevos y arma el JSON de cortes vigentes.

Pensado para correr cada pocas horas en GitHub Actions, como el scraper de Mazar:
el workflow hace commit de data/ y el buscador en Xalok lee
data/cortes_luz_publicado.json desde raw.githubusercontent.com (CORS abierto).
La URL definitiva de la fuente oficial es incierta, así que se vigilan varias
páginas candidatas (config.yaml → vigilancia.paginas) y se avisa cuando:

- aparece un PDF nuevo (se procesa solo si su formato es conocido);
- desaparece el texto de "página vacía" (p. ej. publicaron en otro formato);
- una página deja de responder.

    python -m pipeline.vigilar                         # una pasada real
    python -m pipeline.vigilar --aprobar               # publica el candidato pendiente
    python -m pipeline.vigilar --simular 3 --hoy 2026-03-19 --estado /tmp/e.json   # simulacro

Primera pasada sobre una página: registra lo que ya existe como línea base y
no lo procesa (no queremos publicar cortes viejos). --simular N deja fuera de
la línea base los N PDFs más recientes de cada página para ensayar el flujo.

Códigos de salida: 0 = sin novedades · 10 = datos nuevos listos · 20 = requiere
revisión humana · 2 = error general.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from . import extraer as extractor_generico
from .descargar import descargar_pdf, firma_remota, sha256
from .fuentes import centrosur, cnel, cnel_unidades, mae
from .main import RAIZ, SALIDA, cargar_config, cargar_env
from .normalizar import cargar_catalogo, normalizar_todo
from .texto import clave
from .validar import validar

SIN_NOVEDADES, DATOS_NUEVOS, REVISION, ERROR = 0, 10, 20, 2
CARPETA = SALIDA / "vigilancia"      # PDFs descargados y alerta.md (no se suben al repo)
DATOS = RAIZ / "data"                 # estado, registros y JSON (sí se suben: los lee el buscador)
EXTRACTORES = {"cnel_emergentes": cnel, "mae_mantenimientos": mae, "cnel_unidades": cnel_unidades}
# Fuentes "tabla": no publican PDFs sino una foto de lo programado que cambia a diario.
# Cada pasada reemplaza la foto anterior; no hay línea base (lo que muestran está vigente).
TABLAS = {"centrosur_tabla": centrosur}
# GitHub Actions corre en UTC: sin esto, desde las 19:00 de Ecuador ya es "mañana"
# y los cortes del día se retiraban del buscador antes de terminar.
ZONA = ZoneInfo("America/Guayaquil")


def hoy_ecuador(ahora: datetime | None = None) -> date:
    return (ahora or datetime.now(ZONA)).astimezone(ZONA).date()


# ---------- configuración ----------

def expandir_paginas(cfg_vig: dict) -> list[dict]:
    """Expande las entradas con `unidades` (una URL por unidad de negocio).

    unidades: {slug: [nombre, provincia]}; la provincia es solo una pista,
    el catálogo de cantones manda.
    """
    paginas = []
    for p in cfg_vig.get("paginas", []):
        if "unidades" not in p:
            paginas.append(p)
            continue
        for slug, (nombre, provincia) in p["unidades"].items():
            q = {k: v for k, v in p.items() if k != "unidades"}
            q.update(id=f"{p['id']}-{slug}", url=p["url"].format(unidad=slug), provincia=provincia,
                     distribuidora=f"{p.get('distribuidora', '')} {nombre}".strip())
            paginas.append(q)
    return paginas


# ---------- estado ----------

def cargar_estado(ruta: Path) -> dict:
    if ruta.exists():
        return json.loads(ruta.read_text(encoding="utf-8"))
    return {"paginas": {}, "dataset_sha256": None}


def guardar_estado(ruta: Path, estado: dict) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(estado, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------- procesamiento de un PDF ----------

def procesar_pdf(ruta: Path, pagina: dict, titulo: str, cfg: dict, catalogo) -> dict:
    """Prueba el extractor de la página y, si no saca nada, el genérico.

    Devuelve {formato, registros, descartes, crudos}. formato = 'desconocido'
    si ningún extractor reconoce la tabla.
    """
    intentos = []
    mod = EXTRACTORES.get(pagina.get("tipo"))
    if mod:
        intentos.append((pagina["tipo"], lambda: mod.extraer_filas(ruta, pagina.get("provincia", ""), titulo)))
    intentos.append(("generico", lambda: extractor_generico.extraer_filas(ruta, cfg["columnas"])))

    for nombre, fn in intentos:
        try:
            crudos = fn()
        except Exception:                            # PDF corrupto, escaneado, etc.: probar el siguiente
            crudos = []
        if crudos:
            regs, errs = normalizar_todo(crudos, catalogo, pagina.get("distribuidora"))
            if regs:
                return {"formato": nombre, "registros": regs, "descartes": errs, "crudos": len(crudos)}
    return {"formato": "desconocido", "registros": [], "descartes": [], "crudos": 0}


def registrar_pdf(ruta: Path, p: dict, pagina: dict, cfg: dict, catalogo, hoy: date, resumen: dict,
                  reemplazo: bool = False) -> dict:
    """Procesa un PDF descargado, guarda sus registros y devuelve su entrada para el estado."""
    r = procesar_pdf(ruta, pagina, p["titulo"], cfg, catalogo)
    huella = sha256(ruta)
    info = {"estado": "ok" if r["registros"] else "formato_desconocido", "formato": r["formato"],
            "sha256": huella, "visto_en": hoy.isoformat(), "titulo": p["titulo"],
            "registros": len(r["registros"]), "descartes": len(r["descartes"])}
    if reemplazo:
        info["reemplazado_en"] = hoy.isoformat()
    nota = " (reemplazó a una versión anterior con el mismo nombre)" if reemplazo else ""
    if r["registros"]:
        destino = DATOS / "vigilancia" / "registros" / f"{huella}.json"
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(json.dumps(r["registros"], ensure_ascii=False), encoding="utf-8")
        fechas = sorted(x["fecha"] for x in r["registros"])
        resumen["nuevos"].append(f"{pagina['id']}: {ruta.name}{nota} → {len(r['registros'])} registros "
                                 f"({fechas[0]} → {fechas[-1]}, formato {r['formato']})")
        if r["descartes"]:
            resumen["revision"].append(f"{pagina['id']}: {ruta.name} tuvo {len(r['descartes'])} filas "
                                       f"descartadas: " + "; ".join(r["descartes"][:5]))
    else:
        muestra = extractor_generico.inspeccionar(ruta).splitlines()[:12]
        resumen["revision"].append(
            f"{pagina['id']}: {p['url']}{nota} tiene un formato que ningún extractor reconoce. "
            "Inspección:\n```\n" + "\n".join(muestra) + "\n```")
    return info


# ---------- pasada ----------

def registrar_alimentadores(ruta: Path, pendientes: dict[str, list[str]]) -> list[str]:
    """Añade al CSV los alimentadores nuevos sin cantón (con direcciones de ejemplo).

    Devuelve los que se añadieron en esta pasada. Una persona completa la columna
    canton (y provincia) desde la web de GitHub; desde la pasada siguiente se publican.
    """
    import csv
    filas = list(csv.DictReader(open(ruta, encoding="utf-8"))) if ruta.exists() else []
    conocidos = {f["alimentador"].strip().upper() for f in filas}
    nuevos = sorted(a for a in pendientes if a not in conocidos)
    if nuevos:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        escribir_cabecera = not ruta.exists() or ruta.stat().st_size == 0
        with open(ruta, "a", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            if escribir_cabecera:
                w.writerow(["alimentador", "canton", "provincia", "ejemplos"])
            for a in nuevos:
                w.writerow([a, "", "", " | ".join(pendientes[a][:3])])
    return nuevos


def procesar_tabla(pagina: dict, cfg: dict, catalogo, ep: dict, hoy: date, resumen: dict) -> None:
    """Lee una fuente tipo tabla (CentroSur) y reemplaza su foto en data/vigilancia/registros/."""
    mod = TABLAS[pagina["tipo"]]
    ua, timeout = cfg["fuente"]["user_agent"], cfg["fuente"].get("timeout_s", 60)
    try:
        filas = mod.leer_tabla(pagina["url"], ua, timeout)
    except requests.RequestException as e:
        resumen["errores"].append(f"{pagina['id']}: no se pudo leer {pagina['url']} ({e})")
        return
    except RuntimeError as e:                         # la aplicación de la fuente cambió
        resumen["revision"].append(f"{pagina['id']}: {e} Revisa {pagina.get('pagina_publica', pagina['url'])}")
        return

    ruta_alim = RAIZ / pagina["alimentadores"]
    crudos, pendientes, excluidas = mod.a_crudos(filas, mod.cargar_alimentadores(ruta_alim), catalogo,
                                                 tuple(pagina.get("excluir_estados", ["ANU"])))
    regs, errs = normalizar_todo(crudos, catalogo, pagina.get("distribuidora"))
    huella = hashlib.sha256(json.dumps(regs, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    previo = next(iter(ep["pdfs"].values()), {})
    ep["inicializada"] = True

    nuevos_alim = registrar_alimentadores(ruta_alim, pendientes)
    sin_canton = sum(len(v) for v in pendientes.values())
    if nuevos_alim:
        resumen["revision"].append(
            f"{pagina['id']}: {len(nuevos_alim)} alimentador(es) nuevo(s) sin cantón. Complétalos en "
            f"`{pagina['alimentadores']}` (columna canton y provincia): " + ", ".join(nuevos_alim))
    if errs:
        resumen["revision"].append(f"{pagina['id']}: {len(errs)} filas descartadas: " + "; ".join(errs[:5]))

    if huella == previo.get("sha256"):
        return
    destino = DATOS / "vigilancia" / "registros" / f"{huella}.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(regs, ensure_ascii=False), encoding="utf-8")
    if previo.get("sha256") and previo["sha256"] != huella:   # la foto anterior ya no sirve
        (DATOS / "vigilancia" / "registros" / f"{previo['sha256']}.json").unlink(missing_ok=True)
    ep["pdfs"] = {pagina["url"]: {"estado": "ok", "formato": pagina["tipo"], "sha256": huella,
                                  "visto_en": hoy.isoformat(), "registros": len(regs),
                                  "filas_fuente": len(filas), "excluidas": excluidas, "sin_canton": sin_canton}}
    fechas = sorted(r["fecha"] for r in regs)
    rango = f"{fechas[0]} → {fechas[-1]}" if fechas else "sin fechas"
    resumen["nuevos"].append(
        f"{pagina['id']}: tabla actualizada → {len(regs)} cortes publicables ({rango}); "
        f"{excluidas} excluidos por estado; {sin_canton} sin cantón en {len(pendientes)} alimentador(es)")


def vigilar(cfg: dict, estado: dict, hoy: date, simular: int = 0, solo: str | None = None) -> dict:
    """Recorre las páginas y actualiza `estado`. Devuelve el resumen de la pasada."""
    ua, timeout = cfg["fuente"]["user_agent"], cfg["fuente"].get("timeout_s", 60)
    catalogo = cargar_catalogo(RAIZ / "data" / "cantones_ecuador.csv")
    resumen = {"nuevos": [], "revision": [], "linea_base": [], "errores": []}

    for pagina in expandir_paginas(cfg["vigilancia"]):
        if solo and not pagina["id"].startswith(solo):
            continue
        ep = estado["paginas"].setdefault(pagina["id"], {"pdfs": {}, "inicializada": False, "vacia": None})
        if pagina.get("tipo") in TABLAS:
            procesar_tabla(pagina, cfg, catalogo, ep, hoy, resumen)
            continue
        htmls: list[str] = []
        try:
            pdfs = cnel.listar_pdfs(pagina["url"], ua, pagina.get("patron_pdf", "."), timeout, htmls=htmls)
        except requests.RequestException as e:
            resumen["errores"].append(f"{pagina['id']}: no se pudo leer {pagina['url']} ({e})")
            continue

        if not ep["inicializada"]:
            base = pdfs[simular:] if simular else pdfs
            for p in base:
                ep["pdfs"][p["url"]] = {"estado": "linea_base", "visto_en": hoy.isoformat()}
            ep["inicializada"] = True
            resumen["linea_base"].append(f"{pagina['id']}: {len(base)} PDF(s) existentes registrados")

        nuevos = [p for p in pdfs if p["url"] not in ep["pdfs"]]

        # ¿Desapareció el aviso de "no hay trabajos" sin que llegara un PDF?
        # Puede significar que publicaron en otro formato (imagen, tabla HTML).
        if pagina.get("texto_vacio"):
            vacia = any(clave(pagina["texto_vacio"]) in clave(h) for h in htmls)
            if ep["vacia"] is True and not vacia and not nuevos:
                resumen["revision"].append(
                    f"{pagina['id']}: desapareció «{pagina['texto_vacio']}» y no hay PDF nuevo. "
                    f"Revisa la página: {pagina['url']}")
            ep["vacia"] = vacia

        for p in nuevos:
            ruta = CARPETA / "pdfs" / pagina["id"] / p["url"].rsplit("/", 1)[-1]
            try:
                if not ruta.exists():
                    descargar_pdf(p["url"], ruta, ua, timeout)
            except (requests.RequestException, ValueError) as e:
                resumen["errores"].append(f"{pagina['id']}: no se pudo descargar {p['url']} ({e})")
                continue
            ep["pdfs"][p["url"]] = registrar_pdf(ruta, p, pagina, cfg, catalogo, hoy, resumen)

        # ¿Reemplazaron algún PDF ya conocido conservando su nombre? Un HEAD por PDF
        # listado: si cambia la firma (ETag, fecha, tamaño) se descarga y, si el
        # contenido es otro, se procesa como nuevo. La primera vez solo se anota la firma.
        for p in pdfs:
            info = ep["pdfs"].get(p["url"])
            if info is None:                          # falló su descarga: se reintenta como nuevo
                continue
            try:
                firma = firma_remota(p["url"], ua, timeout)
            except requests.RequestException:
                continue                              # se reintenta en la próxima pasada
            if firma is None or info.get("firma") == firma:
                continue
            if "firma" not in info:
                info["firma"] = firma
                continue
            ruta = CARPETA / "pdfs" / pagina["id"] / p["url"].rsplit("/", 1)[-1]
            try:
                descargar_pdf(p["url"], ruta, ua, timeout)
            except (requests.RequestException, ValueError) as e:
                resumen["errores"].append(f"{pagina['id']}: cambió {p['url']} pero no se pudo descargar ({e})")
                continue
            if sha256(ruta) == info.get("sha256"):    # misma versión (p. ej. el servidor tocó la fecha)
                info["firma"] = firma
                continue
            anterior = info.get("sha256")
            nuevo = registrar_pdf(ruta, p, pagina, cfg, catalogo, hoy, resumen, reemplazo=True)
            nuevo["firma"] = firma
            ep["pdfs"][p["url"]] = nuevo
            if anterior and anterior != nuevo["sha256"]:
                (DATOS / "vigilancia" / "registros" / f"{anterior}.json").unlink(missing_ok=True)
    return resumen


def paginas_prioritarias(cfg_vig: dict) -> set[str]:
    """IDs de página (ya expandidos) marcados `prioridad: true` en config.yaml.

    Hoy, el Ministerio de Ambiente y Energía (mae-mantenimientos): es la fuente
    oficial, así que sus cortes mandan sobre los de las demás páginas para el
    mismo cantón y fecha (ver `armar_vigentes`).
    """
    return {p["id"] for p in expandir_paginas(cfg_vig) if p.get("prioridad")}


def armar_vigentes(estado: dict, hoy: date, dias_futuro: int,
                   prioritarias: frozenset[str] = frozenset()) -> list[dict]:
    """Une los registros de todos los PDFs procesados con fecha de hoy en adelante.

    Si una página prioritaria (`prioridad: true`) tiene algún corte para un
    cantón y fecha dados, los cortes de las DEMÁS páginas para ese mismo
    cantón y fecha se descartan por completo — aunque el texto de sectores no
    coincida —, porque se la considera la fuente oficial y no tendría sentido
    mostrar dos versiones distintas del mismo corte.
    """
    tope = (hoy + timedelta(days=dias_futuro)).isoformat()

    def registros_de(pagina_id: str):
        ep = estado["paginas"].get(pagina_id, {})
        for info in ep.get("pdfs", {}).values():
            if info.get("estado") != "ok":
                continue
            ruta = DATOS / "vigilancia" / "registros" / f"{info['sha256']}.json"
            if not ruta.exists():
                continue
            for r in json.loads(ruta.read_text(encoding="utf-8")):
                if hoy.isoformat() <= r["fecha"] <= tope:
                    yield info["visto_en"], r

    claves_prioritarias = {(r["canton"], r["fecha"])
                           for pid in prioritarias for _, r in registros_de(pid)}

    vistos, salida = set(), []
    todas = [(pid, visto_en, r) for pid in estado["paginas"] for visto_en, r in registros_de(pid)]
    # Recorremos del PDF más nuevo al más viejo: si un PDF "-NUEVO" reemplaza a otro,
    # la versión más reciente gana en la deduplicación.
    for pid, _visto_en, r in sorted(todas, key=lambda t: t[1], reverse=True):
        if pid not in prioritarias and (r["canton"], r["fecha"]) in claves_prioritarias:
            continue
        k = (r["canton"], r["fecha"], r["horario"], r["sectores"])
        if k not in vistos:
            vistos.add(k)
            salida.append(r)
    return sorted(salida, key=lambda r: (r["fecha"], r["provincia"], r["canton"], r["horario"]))


def escribir_alerta(resumen: dict, vigentes: list, res, codigo: int, destino: str) -> str:
    titulo = {SIN_NOVEDADES: "Sin novedades", DATOS_NUEVOS: "Datos nuevos listos",
              REVISION: "Requiere revisión humana", ERROR: "Error"}[codigo]
    lineas = [f"# Cortes de luz · {titulo}", f"_{datetime.now(ZONA):%Y-%m-%d %H:%M} (Ecuador)_", "",
              f"- Cortes vigentes: **{len(vigentes)}**"]
    if vigentes:
        lineas.append(f"- Rango: {vigentes[0]['fecha']} → {vigentes[-1]['fecha']}")
    if destino:
        lineas.append(f"- Resultado: {destino}")
    for clave_, nombre in (("nuevos", "Fuentes con datos nuevos"), ("revision", "Para revisar"),
                           ("errores", "Errores de lectura"), ("linea_base", "Línea base registrada")):
        if resumen[clave_]:
            lineas += ["", f"## {nombre}", *[f"- {x}" for x in resumen[clave_]]]
    if res and res.errores:
        lineas += ["", "## Validación fallida (no se publicó)", *[f"- {e}" for e in res.errores[:20]]]
    if res and res.advertencias:
        lineas += ["", "## Advertencias de validación", *[f"- {a}" for a in res.advertencias]]
    return "\n".join(lineas)


def aprobar() -> bool:
    """Copia el candidato (cortes_luz_vigentes.json) al JSON que lee el buscador."""
    candidato = DATOS / "cortes_luz_vigentes.json"
    if not candidato.exists():
        return False
    (DATOS / "cortes_luz_publicado.json").write_bytes(candidato.read_bytes())
    return True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Vigila las fuentes y arma el JSON de cortes vigentes")
    ap.add_argument("--aprobar", action="store_true",
                    help="Solo publicar el candidato pendiente (botón «Aprobar» de GitHub)")
    ap.add_argument("--estado", type=Path, help="Ruta del archivo de estado (por defecto, el de config.yaml)")
    ap.add_argument("--hoy", type=date.fromisoformat, help="Fecha de referencia (simulacros)")
    ap.add_argument("--simular", type=int, default=0, metavar="N",
                    help="En la primera pasada, tratar como nuevos los N PDFs más recientes")
    ap.add_argument("--solo", help="Vigilar solo las páginas cuyo id empieza así")
    args = ap.parse_args(argv)

    cargar_env()
    cfg = cargar_config()
    hoy = args.hoy or hoy_ecuador()
    ruta_estado = args.estado or (RAIZ / cfg["vigilancia"]["estado"])
    estado = cargar_estado(ruta_estado)
    # revision: los datos nuevos esperan aprobación humana · directa: se publican solos.
    directa = cfg["vigilancia"].get("publicacion", "revision") == "directa"

    if args.aprobar:
        if not aprobar():
            print("No hay candidato que aprobar (data/cortes_luz_vigentes.json no existe).", file=sys.stderr)
            return ERROR
        estado["pendiente_aprobacion"] = False
        guardar_estado(ruta_estado, estado)
        print("Publicado: data/cortes_luz_publicado.json")
        return SIN_NOVEDADES

    resumen = vigilar(cfg, estado, hoy, args.simular, args.solo)
    vigentes = armar_vigentes(estado, hoy, cfg["validacion"].get("dias_futuro_max", 60),
                              paginas_prioritarias(cfg["vigilancia"]))
    huella = hashlib.sha256(json.dumps(vigentes, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    cambio = huella != estado.get("dataset_sha256")

    res, destino = None, ""
    codigo = REVISION if resumen["revision"] or resumen["errores"] else SIN_NOVEDADES
    if cambio and vigentes:
        # Sin `anterior`: el total baja solo cada día al vencer cortes, así que la regla
        # de caída máxima no sirve aquí. Los cambios de formato se detectan por PDF.
        res = validar(vigentes, cfg["validacion"], hoy=hoy)
        if res.ok:
            DATOS.mkdir(parents=True, exist_ok=True)
            local = DATOS / "cortes_luz_vigentes.json"
            local.write_text(json.dumps(vigentes, ensure_ascii=False, indent=1), encoding="utf-8")
            estado.update(dataset_sha256=huella, dataset_registros=len(vigentes))
            # Solo se avisa si entró un PDF nuevo; retirar cortes vencidos se publica en silencio.
            if resumen["nuevos"]:
                codigo = max(codigo, DATOS_NUEVOS)    # REVISION (20) prevalece sobre DATOS_NUEVOS (10)

            # ¿Se publica ya? Nunca con algo por revisar. Con datos nuevos, solo en modo directa.
            # Si solo vencieron cortes, sí, salvo que haya un candidato anterior esperando aprobación
            # (si no, se colaría sin que nadie lo apruebe).
            if codigo == DATOS_NUEVOS and not directa:
                estado["pendiente_aprobacion"] = True
                destino = "candidato en data/cortes_luz_vigentes.json · pendiente de aprobación"
            elif codigo == DATOS_NUEVOS or (codigo == SIN_NOVEDADES and not estado.get("pendiente_aprobacion")):
                aprobar()
                destino = "publicado en data/cortes_luz_publicado.json"
            else:
                destino = "candidato en data/cortes_luz_vigentes.json · pendiente de aprobación"
        elif huella != estado.get("rechazado_sha256"):
            # Avisar una sola vez por candidato rechazado (no en cada pasada).
            estado["rechazado_sha256"] = huella
            codigo = REVISION
    elif cambio and not vigentes and estado.get("dataset_registros"):
        # Se acabaron los cortes vigentes. No vaciamos el JSON publicado sin una persona.
        resumen["revision"].append("Ya no quedan cortes vigentes. El JSON publicado no se tocó: "
                                   "decide si se vacía o se retira el buscador.")
        estado.update(dataset_sha256=huella, dataset_registros=0)
        codigo = REVISION

    guardar_estado(ruta_estado, estado)
    texto = escribir_alerta(resumen, vigentes, res, codigo, destino)
    CARPETA.mkdir(parents=True, exist_ok=True)
    (CARPETA / "alerta.md").write_text(texto, encoding="utf-8")
    print(texto)
    return codigo


if __name__ == "__main__":
    sys.exit(main())
