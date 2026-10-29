#!/usr/bin/env bash
# El tar.gz de empaquetar.sh más lo que necesita general.sh (G.8): model/meta/ (conversores y muestreo, sin tests), el comparador
# model/evaluacion/aws/comparar_g8.py y, con --fixtures (prueba en seco), el fixture de JevBench.
# Uso: bash model/l2/aws/empaquetar_general.sh [--fixtures] > codigo.tgz
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../../.."
tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT
bash model/l2/aws/empaquetar.sh "$@" | gunzip > "$tmp"
extra=$(find model/meta -type f -name '*.py' -not -path '*/tests/*' -not -path '*/__pycache__/*'; echo model/evaluacion/aws/comparar_g8.py)
[ "${1:-}" = --fixtures ] && extra="$extra
$(find model/evaluacion/tests/fixtures/jevbench -type f)"
printf '%s\n' "$extra" | LC_ALL=C sort -u | tar -rf "$tmp" -T -
gzip -c "$tmp"
