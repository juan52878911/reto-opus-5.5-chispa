#!/usr/bin/env bash
# Imprime en stdout el tar.gz que necesita e2e.sh: server/, runtime/l1, runtime/tok, format/chispa3, el SDK de Python
# (con el entrenador de Go), los pedazos de model/ que usan chispa train, model.l2 y chispa_eval, las cifras de T2.2c y
# gomod-proxy/ (la caché de módulos de kindling, que no está en un proxy público).
# Portable (GNU y bsdtar): sin -C junto a -T ni -printf; se prepara un directorio y se empaqueta con tar -C sin -T.
# Uso: bash server/deploy/aws/empaquetar_e2e.sh [--fixtures] > codigo.tgz     (--fixtures: model/datos con sus fixtures, para la prueba en seco)
set -euo pipefail
cd "$(dirname "$0")/../../.."
GOMODCACHE=${GOMODCACHE:-$(go env GOMODCACHE)}
KIND=$GOMODCACHE/cache/download/github.com/juan52878911/kindling
[ -d "$KIND/@v" ] || { echo "falta $KIND/@v (go mod download en server/)" >&2; exit 1; }
FIXARGS=(-not -path '*/fixtures/*'); [ "${1:-}" = --fixtures ] && FIXARGS=()
T=$(mktemp -d)
LISTA=$T.lista
trap 'rm -rf "$T" "$LISTA"' EXIT
{
  find server runtime/l1 runtime/tok format/chispa3 sdk/python/chispa -type f -size -1025k \
    -not -name '*.pyc' -not -name '*.so' -not -path '*/__pycache__/*' -not -path 'runtime/l1/aws/*' -not -path 'server/deploy/aws/resultados/*'
  echo sdk/python/pyproject.toml
  echo model/__init__.py
  find model/l2 -type f \( -name '*.py' -o -name '*.sh' \) -not -path '*/tests/*' -not -path '*/__pycache__/*'
  find model/l2/empaquetar_go -type f -size -1025k
  find model/l2/tests/fixtures_conjunta -type f -size -1025k
  find model/datos -type f \( -name '*.py' -o -name '*.md' -o -name '*.json*' -o -name '*.csv' -o -name '*.parquet' \) \
    -not -path '*/tests/*' -not -path '*/__pycache__/*' ${FIXARGS[@]+"${FIXARGS[@]}"}
  find model/evaluacion -maxdepth 1 -type f -name '*.py'
  find model/lineas_base -maxdepth 1 -type f \( -name '__init__.py' -o -name 'correr.py' \)
  find model/cascada -maxdepth 1 -type f \( -name '__init__.py' -o -name 'cascada.py' -o -name 'capas.py' -o -name 'informe.py' \)
  echo model/bench/vocab-podado-e5-small.json
  echo model/herramientas/train.jsonl
  echo model/herramientas/test.jsonl
  echo model/lineas_base/resultados.json
  echo model/l2/resultados/t22c-conjunta/resultados.json
} | LC_ALL=C sort -u > "$LISTA"
# un fichero de la lista que no exista hace fallar tar (set -e)
tar -cf - -T "$LISTA" | tar -xf - -C "$T"
mkdir -p "$T/gomod-proxy/github.com/juan52878911"
cp -R "$KIND" "$T/gomod-proxy/github.com/juan52878911/"
find "$T/gomod-proxy" -name '*.lock' -exec rm -f {} +
tar -czf - -C "$T" .
