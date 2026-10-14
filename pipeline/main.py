"""Orquestador del pipeline.

Códigos de salida: 0 = publicado o sin cambios, 1 = validación fallida, 2 = error.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import yaml

from .descargar import descargar_pdf, sha256
from .extraer import extraer_filas, inspeccionar
from .normalizar import cargar_catalogo, normalizar_todo
from .texto import clave
from .validar import validar

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "salida"


def cargar_env() -> None:
    """Carga .env (si existe) sin dependencias extra. No pisa variables ya definidas."""
    import os
    ruta = RAIZ / ".env"
    if not ruta.exists():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        if "=" in linea and not linea.lstrip().startswith("#"):
            k, v = linea.split("=", 1)
            if v.strip():
                os.environ.setdefault(k.strip(), v.strip())


def cargar_config() -> dict:
    return yaml.safe_load((RAIZ / "config.yaml").read_text(encoding="utf-8"))


def fuentes(cfg: dict) -> list[dict]:
    f = cfg["fuente"]
    lista = list(f.get("pdfs") or [])
    if f.get("pdf_url"):
        lista.insert(0, {"url": f["pdf_url"], "distribuidora": None})
    return lista


def reporte(registros, errores_norm, res, hashes) -> str:
    por_prov = Counter(r["provincia"] for r in registros)
    fechas = sorted(r["fecha"] for r in registros)
    lineas = [
        f"# Reporte {datetime.now():%Y-%m-%d %H:%M}",
        f"- Registros: **{len(registros)}**",
        f"- Rango: {fechas[0]} → {fechas[-1]}" if fechas else "- Rango: (vacío)",
        f"- PDFs: {', '.join(h[:12] for h in hashes)}",
        f"- Validación: {'OK' if res.ok else 'FALLIDA'}",
        "", "## Por provincia", *[f"- {p}: {n}" for p, n in por_prov.most_common()],
    ]
    if res.errores:
        lineas += ["", "## Errores", *[f"- {e}" for e in res.errores[:50]]]
    if errores_norm:
        lineas += ["", "## Filas descartadas al normalizar", *[f"- {e}" for e in errores_norm[:50]]]
    if res.advertencias:
        lineas += ["", "## Advertencias", *[f"- {a}" for a in res.advertencias]]
    return "\n".join(lineas)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Pipeline de cortes de luz PRIMICIAS")
    ap.add_argument("--pdf", type=Path, help="Usar un PDF local en lugar de descargar")
    ap.add_argument("--inspeccionar", action="store_true", help="Solo mostrar las tablas del PDF")
    ap.add_argument("--local", action="store_true", help="No leer ni escribir en S3")
    ap.add_argument("--produccion", action="store_true", help="Publicar en el JSON vivo")
    ap.add_argument("--forzar", action="store_true", help="Procesar aunque el PDF no haya cambiado")
    args = ap.parse_args(argv)

    cargar_env()
    cfg = cargar_config()
    SALIDA.mkdir(exist_ok=True)

    # 1. Obtener PDF(s)
    if args.pdf:
        pdfs = [(args.pdf, None, str(args.pdf))]
    else:
        lista = fuentes(cfg)
        if not lista:
            print("Falta la URL del PDF en config.yaml (fuente.pdf_url).", file=sys.stderr)
            return 2
        pdfs = []
        for i, f in enumerate(lista):
            ruta = descargar_pdf(f["url"], SALIDA / f"fuente_{i}.pdf", cfg["fuente"]["user_agent"],
                                 cfg["fuente"].get("timeout_s", 60))
            pdfs.append((ruta, f.get("distribuidora"), f["url"]))

    if args.inspeccionar:
        for ruta, _, _ in pdfs:
            print(inspeccionar(ruta))
        return 0

    hashes = [sha256(r) for r, _, _ in pdfs]
    huella = "+".join(hashes)

    # 2. ¿Cambió algo?
    s3 = None
    estado_prev = None
    produccion = args.produccion or cfg.get("modo") == "produccion"
    if not args.local:
        from .publicar import S3
        s3 = S3(cfg["s3"])
        estado_prev = s3.leer_json(cfg["s3"]["estado"])
        if estado_prev and estado_prev.get("pdf_sha256") == huella and not args.forzar:
            print("El PDF no cambió desde la última publicación. Nada que hacer.")
            return 0

    # 3. Extraer y normalizar
    catalogo = cargar_catalogo(RAIZ / "data" / "cantones_ecuador.csv")
    registros, errores_norm = [], []
    for ruta, distribuidora, _ in pdfs:
        crudos = extraer_filas(ruta, cfg["columnas"])
        regs, errs = normalizar_todo(crudos, catalogo, distribuidora)
        registros += regs
        errores_norm += errs

    # 4. Validar
    res = validar(registros, cfg["validacion"], anterior=(estado_prev or {}).get("registros"))
    if catalogo:
        desconocidos = sorted({c for r in registros for c in r["cantones"] if clave(c) not in catalogo})
        if desconocidos:
            res.advertencias.append("Cantones no encontrados en el catálogo: " + ", ".join(desconocidos))
    else:
        res.advertencias.append("data/cantones_ecuador.csv vacío: no se corrigieron provincias.")

    (SALIDA / "cortes_luz.json").write_text(json.dumps(registros, ensure_ascii=False, indent=1), encoding="utf-8")
    texto = reporte(registros, errores_norm, res, hashes)
    (SALIDA / "reporte.md").write_text(texto, encoding="utf-8")
    print(texto)

    if not res.ok:
        print("\nValidación fallida: no se publica.", file=sys.stderr)
        return 1

    # 5. Publicar
    if args.local:
        print(f"\nModo local: resultado en {SALIDA / 'cortes_luz.json'}")
        return 0

    fechas = sorted(r["fecha"] for r in registros)
    estado = {
        "pdf_sha256": huella,
        "pdf_url": [u for _, _, u in pdfs],
        "procesado_en": datetime.now().astimezone().isoformat(timespec="seconds"),
        "registros": len(registros),
        "desde": fechas[0], "hasta": fechas[-1],
        "advertencias": res.advertencias,
    }
    urls = s3.publicar(registros, estado, produccion)
    print(f"\nPublicado en {'PRODUCCIÓN' if produccion else 'staging'}: {urls['destino']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
