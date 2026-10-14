#!/usr/bin/env bash
# Descarga el prototipo y el JSON actuales para comparar y editar localmente.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p linea_base
BASE="https://primicias.s3.us-east-1.amazonaws.com"
curl -fsSL "$BASE/editorial/2026/gestio-diaria/octubre/maqueta-cortes-luz/PROTOTIPO.html" -o linea_base/PROTOTIPO.html
curl -fsSL "$BASE/editorial/2026/Cortes+de+Luz+2026/cortes_luz_mayo_junio_2026.json" -o linea_base/cortes_luz_mayo_junio_2026.json
python3 -c "import json;d=json.load(open('linea_base/cortes_luz_mayo_junio_2026.json'));print(f'{len(d)} registros en la línea base')"
echo "Listo: linea_base/"
