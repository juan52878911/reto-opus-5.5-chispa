#!/usr/bin/env bash
# Imprime en stdout un tar.gz con lo mínimo que necesita la instancia de AWS (ver arranque.sh):
# el código de model/bench/ (sin work/ ni resultados), model/evaluacion/ (sin tests) y model/sondeo/.
# Uso: bash model/bench/aws/empaquetar.sh > codigo.tgz
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../../.."
{
  echo model/__init__.py
  find model/bench -type f \( -name '*.py' -o -name '*.sh' -o -name '*.json' \) -not -path '*/work/*' -not -path '*/__pycache__/*'
  find model/evaluacion -type f -name '*.py' -not -path '*/tests/*' -not -path '*/__pycache__/*'
  find model/sondeo -type f \( -name '*.jsonl' -o -name '*.py' -o -name SHA256 \) -not -path '*/__pycache__/*'
} | LC_ALL=C sort | tar -czf - -T -
