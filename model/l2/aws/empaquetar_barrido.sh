#!/usr/bin/env bash
# El tar.gz de empaquetar.sh más lo que necesita barrido.sh (G.8b): model/cascada/ (L1 con prototipos, sin tests ni resultados) y, con
# --fixtures (prueba en seco), el fixture de JevBench. Para el .chispa score: model/l2/empaquetar_go, format/chispa3 (sin tests) y
# gomod-proxy/ (kindling del GOMODCACHE local, que no está en un proxy público).
# Uso: bash model/l2/aws/empaquetar_barrido.sh [--fixtures] > codigo.tgz
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../../.."
tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT
bash model/l2/aws/empaquetar.sh "$@" | gunzip > "$tmp"
extra=$(find model/cascada -maxdepth 1 -type f -name '*.py'; ls model/bench/torre/datos_g7.py model/bench/vocab-podado-e5-small.json)
[ "${1:-}" = --fixtures ] && extra="$extra
$(find model/evaluacion/tests/fixtures/jevbench -type f)"
extra="$extra
$(find model/l2/empaquetar_go format/chispa3 -type f \( -name '*.go' -o -name go.mod -o -name go.sum \) -not -name '*_test.go')"
printf '%s\n' "$extra" | LC_ALL=C sort -u | tar -rf "$tmp" -T -
KIND=$(go env GOMODCACHE)/cache/download/github.com/juan52878911/kindling
if [ -d "$KIND/@v" ]; then
  T=$(mktemp -d); trap 'rm -rf "$tmp" "$T"' EXIT
  mkdir -p "$T/gomod-proxy/github.com/juan52878911"; cp -R "$KIND" "$T/gomod-proxy/github.com/juan52878911/"
  find "$T/gomod-proxy" -name '*.lock' -exec rm -f {} +
  tar -rf "$tmp" -C "$T" gomod-proxy
else echo "aviso: sin $KIND/@v; el .chispa score necesitará acceso a kindling" >&2; fi
gzip -c "$tmp"
