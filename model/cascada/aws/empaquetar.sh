#!/usr/bin/env bash
# Imprime en stdout el tar.gz con lo que necesita la instancia de AWS (ver arranque.sh): model/cascada/ (sin tests, resultados ni
# el verificador de Go), el conversor model/datos/ (sin tests ni fixtures), el arnés model/evaluacion/, model/lineas_base/ (correr.py y
# resultados.json, las cifras del listón) y las filas de herramientas (model/herramientas/train.jsonl y test.jsonl).
# Con --fixtures incluye también model/datos/fixtures (prueba en seco).
# Portable (GNU tar y bsdtar): find y tar sin opciones de GNU, y sin -C combinado con -T.
# Uso: bash model/cascada/aws/empaquetar.sh [--fixtures] > codigo.tgz
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../../.."
CON_FIX=0; [ "${1:-}" = --fixtures ] && CON_FIX=1
{
  echo model/__init__.py
  find model/cascada -type f \( -name '*.py' -o -name '*.sh' \) -not -path '*/tests/*' -not -path '*/__pycache__/*' -not -path '*/resultados/*'
  if [ "$CON_FIX" = 1 ]; then
    find model/datos -type f \( -name '*.py' -o -name '*.md' -o -name '*.json*' -o -name '*.csv' -o -name '*.parquet' \) -not -path '*/tests/*' -not -path '*/__pycache__/*'
  else
    find model/datos -type f \( -name '*.py' -o -name '*.md' -o -name '*.json*' -o -name '*.csv' -o -name '*.parquet' \) -not -path '*/tests/*' -not -path '*/fixtures/*' -not -path '*/__pycache__/*'
  fi
  find model/evaluacion -maxdepth 1 -type f -name '*.py'
  echo model/lineas_base/__init__.py
  echo model/lineas_base/correr.py
  echo model/lineas_base/resultados.json
  echo model/herramientas/train.jsonl
  echo model/herramientas/test.jsonl
} | LC_ALL=C sort -u | tar -czf - -T -
