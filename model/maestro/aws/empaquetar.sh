#!/usr/bin/env bash
# Imprime en stdout el tar.gz con lo mínimo que necesita la instancia de AWS (ver arranque.sh): model/maestro/ (sin
# tests), el conversor model/datos/ (sin tests ni fixtures), model/evaluacion/metricas.py (ECE) y las filas de T1.4
# (model/herramientas/train.jsonl y test.jsonl). Uso: bash model/maestro/aws/empaquetar.sh > codigo.tgz
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../../.."
{
  echo model/__init__.py
  find model/maestro -type f \( -name '*.py' -o -name '*.sh' \) -not -path '*/tests/*' -not -path '*/__pycache__/*'
  find model/datos -type f \( -name '*.py' -o -name '*.md' \) -not -path '*/tests/*' -not -path '*/fixtures/*' -not -path '*/__pycache__/*'
  echo model/evaluacion/__init__.py
  echo model/evaluacion/metricas.py
  echo model/herramientas/train.jsonl
  echo model/herramientas/test.jsonl
} | LC_ALL=C sort | tar -czf - -T -
