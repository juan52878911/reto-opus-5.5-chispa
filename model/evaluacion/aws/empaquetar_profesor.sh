#!/usr/bin/env bash
# El tar.gz de model/l2/aws/empaquetar.sh (model/l2, model/datos, model/evaluacion/*.py…) más model/meta/{__init__,muestreo}.py, que
# profesor.py necesita para leer la lista fuera.json, y, con --fixtures (prueba en seco), el fixture de JevBench.
# Uso: bash model/evaluacion/aws/empaquetar_profesor.sh [--fixtures] > codigo.tgz
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../../.."
tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT
bash model/l2/aws/empaquetar.sh "$@" | gunzip > "$tmp"
extra="model/meta/__init__.py
model/meta/muestreo.py"
[ "${1:-}" = --fixtures ] && extra="$extra
$(find model/evaluacion/tests/fixtures/jevbench -type f)"
printf '%s\n' "$extra" | LC_ALL=C sort -u | tar -rf "$tmp" -T -
gzip -c "$tmp"
