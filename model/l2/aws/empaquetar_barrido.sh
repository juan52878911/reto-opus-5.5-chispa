#!/usr/bin/env bash
# El tar.gz de empaquetar.sh más lo que necesita barrido.sh (G.8b): model/cascada/ (L1 con prototipos, sin tests ni resultados) y, con
# --fixtures (prueba en seco), el fixture de JevBench.
# Uso: bash model/l2/aws/empaquetar_barrido.sh [--fixtures] > codigo.tgz
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../../.."
tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT
bash model/l2/aws/empaquetar.sh "$@" | gunzip > "$tmp"
extra=$(find model/cascada -maxdepth 1 -type f -name '*.py')
[ "${1:-}" = --fixtures ] && extra="$extra
$(find model/evaluacion/tests/fixtures/jevbench -type f)"
printf '%s\n' "$extra" | LC_ALL=C sort -u | tar -rf "$tmp" -T -
gzip -c "$tmp"
