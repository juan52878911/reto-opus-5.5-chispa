#!/usr/bin/env bash
# Imprime en stdout un tar.gz con runtime/l1/ (código, tests y testdata; sin el .chispa-l1 ni aws/).
# Los tests dorados solo leen runtime/l1/testdata, así que model/sondeo/ no hace falta.
# Uso: bash runtime/l1/aws/empaquetar.sh > codigo.tgz
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../../.."
find runtime/l1 -type f -not -path 'runtime/l1/aws/*' -not -name '*.chispa-l1' -not -name '*.test' \
  -not -path '*/__pycache__/*' | LC_ALL=C sort | tar -czf - -T -
