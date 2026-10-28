#!/usr/bin/env bash
# Imprime en stdout el tar.gz con lo que necesita la instancia de AWS (ver arranque.sh): model/l2/ (sin tests), el conversor
# model/datos/ (sin tests ni fixtures, salvo con --fixtures para la prueba en seco), el arnés model/evaluacion/, el listón
# (model/liston/ y model/etiquetado/acuerdo.py), las filas de T1.4 las cifras de model/lineas_base/resultados.json y la lista de ficheros de meta (conversion-20261027.json).
# Uso: bash model/l2/aws/empaquetar.sh [--fixtures] > codigo.tgz
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../../.."
FIX=(-not -path '*/fixtures/*'); [ "${1:-}" = --fixtures ] && FIX=()
{
  echo model/__init__.py
  find model/l2 -type f \( -name '*.py' -o -name '*.sh' \) -not -path '*/tests/*' -not -path '*/__pycache__/*'
  find model/datos -type f \( -name '*.py' -o -name '*.md' -o -name '*.json*' -o -name '*.csv' -o -name '*.parquet' \) -not -path '*/tests/*' "${FIX[@]}" -not -path '*/__pycache__/*'
  find model/liston -type f -name '*.py' -not -path '*/tests/*' -not -path '*/__pycache__/*'
  echo model/etiquetado/__init__.py
  echo model/etiquetado/acuerdo.py
  find model/evaluacion -maxdepth 1 -type f -name '*.py'
  echo model/herramientas/train.jsonl
  echo model/herramientas/test.jsonl
  echo model/lineas_base/resultados.json
  echo model/meta/resultados/conversion-20261027.json
} | LC_ALL=C sort -u | tar -czf - -T -
