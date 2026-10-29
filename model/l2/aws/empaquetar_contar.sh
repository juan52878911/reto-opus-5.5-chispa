#!/usr/bin/env bash
# El tar.gz de empaquetar.sh más model/meta/ (sin tests ni resultados; tasksource-instruct se convierte en la instancia) para contar_noul.sh.
# Uso: bash model/l2/aws/empaquetar_contar.sh [--fixtures] > codigo.tgz
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../../.."
tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT
bash model/l2/aws/empaquetar.sh "$@" | gunzip > "$tmp"
extra=$(find model/meta -maxdepth 1 -type f -name '*.py')
[ "${1:-}" = --fixtures ] && extra="$extra
$(find model/evaluacion/tests/fixtures/jevbench -type f)"
printf '%s\n' "$extra" | LC_ALL=C sort -u | tar -rf "$tmp" -T -
gzip -c "$tmp"
