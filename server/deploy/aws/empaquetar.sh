#!/usr/bin/env bash
# Imprime en stdout un tar.gz con lo que necesita la instancia de AWS (ver arranque.sh): server/, runtime/l1/ y
# format/chispa3/ (los `replace` de server/go.mod los exigen), el Dockerfile en server/deploy/ y gomod-proxy/,
# la caché de módulos de kindling (está en la caché de Go de esta máquina, no se puede bajar de un proxy público).
# Sin ficheros .chispa de más de 1 MB ni binarios. Uso: bash server/deploy/aws/empaquetar.sh > codigo.tgz
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../../.."
GOMODCACHE=${GOMODCACHE:-$(go env GOMODCACHE)}
KIND=$GOMODCACHE/cache/download/github.com/juan52878911/kindling
[ -d "$KIND/@v" ] || { echo "falta $KIND/@v (go mod download en server/)" >&2; exit 1; }
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
mkdir -p "$T/gomod-proxy/github.com/juan52878911"
cp -r "$KIND" "$T/gomod-proxy/github.com/juan52878911/"
find "$T/gomod-proxy" -name '*.lock' -delete
{
  find server runtime/l1 format/chispa3 -type f -not -path '*/__pycache__/*' -not -name '*.pyc' -not -name '*.so' \
    -not -path 'runtime/l1/aws/*' -size -1025k
  find "$T/gomod-proxy" -type f | sed "s|^$T/||"
} | LC_ALL=C sort -u > "$T/lista"
# lo de gomod-proxy está en $T: se añade con -C
grep -v '^gomod-proxy/' "$T/lista" > "$T/lista-repo"
tar -czf - -C . -T "$T/lista-repo" -C "$T" gomod-proxy
