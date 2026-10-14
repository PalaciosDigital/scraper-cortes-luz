"""Prototipo de scraper: listado web de la distribuidora → PDFs → JSON local.

Solo trabaja en local (salida/). No lee ni escribe en S3.

    python -m pipeline.scrapear --listar                    # qué PDFs hay en cada fuente
    python -m pipeline.scrapear                             # todas las fuentes de config.yaml
    python -m pipeline.scrapear --fuente cnel-santa-elena --max-pdfs 3
    python -m pipeline.scrapear --historico                 # no exige fechas recientes

Códigos de salida: 0 = OK, 1 = validación fallida, 2 = error.
"""
from __future__ import annotations

import argparse
import json
import sys

from .descargar import descargar_pdf, sha256
from .fuentes import cnel
from .main import SALIDA, RAIZ, cargar_config, reporte
from .normalizar import ErrorNormalizacion, cargar_catalogo, normalizar_fecha, normalizar_todo
from .texto import clave
from .validar import validar

EXTRACTORES = {"cnel_emergentes": cnel}


def _fecha_de_titulo(titulo: str) -> str:
    try:
        return normalizar_fecha(titulo)
    except ErrorNormalizacion:
        return ""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Scraper de cronogramas de cortes (prototipo, solo local)")
    ap.add_argument("--fuente", help="id de config.yaml → fuentes_web (por defecto, todas)")
    ap.add_argument("--listar", action="store_true", help="Solo listar los PDFs encontrados")
    ap.add_argument("--max-pdfs", type=int, help="Procesar solo los N más recientes de cada fuente")
    ap.add_argument("--historico", action="store_true",
                    help="Desactiva la ventana de fechas de la validación (para PDFs viejos)")
    args = ap.parse_args(argv)

    cfg = cargar_config()
    ua = cfg["fuente"]["user_agent"]
    timeout = cfg["fuente"].get("timeout_s", 60)
    fuentes = [f for f in cfg.get("fuentes_web", []) if not args.fuente or f["id"] == args.fuente]
    if not fuentes:
        print("No hay fuentes en config.yaml → fuentes_web (o el --fuente no existe).", file=sys.stderr)
        return 2

    catalogo = cargar_catalogo(RAIZ / "data" / "cantones_ecuador.csv")
    registros, errores_norm, hashes = [], [], []

    for f in fuentes:
        mod = EXTRACTORES[f["tipo"]]
        pdfs = mod.listar_pdfs(f["url"], ua, f.get("patron_pdf", "."), timeout)
        print(f"\n[{f['id']}] {len(pdfs)} PDF(s) en {f['url']}")
        if args.listar:
            for p in pdfs:
                print(f"  - {p['titulo'] or '(sin título)'}\n    {p['url']}")
            continue

        carpeta = SALIDA / "fuentes" / f["id"]
        for p in pdfs[: args.max_pdfs]:
            ruta = carpeta / p["url"].rsplit("/", 1)[-1]
            if not ruta.exists():                      # caché: los PDFs publicados no cambian de nombre
                descargar_pdf(p["url"], ruta, ua, timeout)
            hashes.append(sha256(ruta))
            crudos = mod.extraer_filas(ruta, f.get("provincia", ""), _fecha_de_titulo(p["titulo"]))
            regs, errs = normalizar_todo(crudos, catalogo, f.get("distribuidora"))
            print(f"  {ruta.name}: {len(crudos)} filas → {len(regs)} registros"
                  + (f", {len(errs)} descartadas" if errs else ""))
            registros += regs
            errores_norm += [f"{ruta.name} · {e}" for e in errs]

    if args.listar:
        return 0

    # La misma fila puede aparecer en dos PDFs (reemplazos "-NUEVO"): deduplicar global.
    vistos, unicos = set(), []
    for r in registros:
        k = (r["canton"], r["fecha"], r["horario"], r["sectores"])
        if k not in vistos:
            vistos.add(k)
            unicos.append(r)
    registros = sorted(unicos, key=lambda r: (r["fecha"], r["provincia"], r["canton"], r["horario"]))

    reglas = dict(cfg["validacion"])
    if args.historico:
        reglas.update(dias_pasado_max=36500, dias_futuro_max=36500)
    res = validar(registros, reglas)
    desconocidos = sorted({c for r in registros for c in r["cantones"] if clave(c) not in catalogo})
    if desconocidos:
        res.advertencias.append("Cantones no encontrados en el catálogo: " + ", ".join(desconocidos))

    nombre = args.fuente or "fuentes_web"
    salida_json = SALIDA / f"{nombre}.json"
    salida_json.write_text(json.dumps(registros, ensure_ascii=False, indent=1), encoding="utf-8")
    texto = reporte(registros, errores_norm, res, hashes)
    (SALIDA / f"{nombre}_reporte.md").write_text(texto, encoding="utf-8")
    print("\n" + texto)
    print(f"\nResultado en {salida_json}")
    return 0 if res.ok else 1


if __name__ == "__main__":
    sys.exit(main())
