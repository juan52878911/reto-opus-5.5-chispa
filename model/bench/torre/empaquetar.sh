#!/usr/bin/env bash
# Imprime en stdout un tar.gz (git archive, sin bsdtar) con las rutas pedidas de una rama o sha de ESTE repo.
# Uso: bash model/bench/torre/empaquetar.sh <rama-o-sha> <ruta>… > paquete.tgz
#   rama unificada: CHISPA_GOMOD_PROXY=1 bash model/bench/torre/empaquetar.sh <sha> > codigo.tgz   (model server runtime format sdk)
#   rutas sueltas:  bash model/bench/torre/empaquetar.sh HEAD model > codigo-modelo.tgz
# CHISPA_GOMOD_PROXY=1 añade gomod-proxy/ (la caché de módulos de kindling del GOMODCACHE local, que no está en un proxy público): el
# paquete del SDK lo necesita para compilar `server/`.
# Las rutas que no existen en esa revisión se omiten con un aviso en stderr (go.work puede no existir); si no queda ninguna, falla.
set -euo pipefail
[ $# -ge 1 ] || { echo "uso: $0 <rama-o-sha> [<ruta>…]  (sin rutas: model server runtime format sdk, la rama unificada)" >&2; exit 2; }
cd "$(dirname "${BASH_SOURCE[0]}")/../../.."
ref=$1; shift
[ $# -gt 0 ] || set -- model server runtime format sdk
git rev-parse --verify --quiet "$ref^{commit}" >/dev/null || { echo "no existe la revisión '$ref' en este repo" >&2; exit 1; }
rutas=()
for r in "$@"; do
  if [ -n "$(git ls-tree --name-only "$ref" -- "$r")" ]; then rutas+=("$r"); else echo "aviso: '$r' no existe en $ref, se omite" >&2; fi
done
[ ${#rutas[@]} -gt 0 ] || { echo "ninguna de las rutas existe en $ref" >&2; exit 1; }
if [ "${CHISPA_GOMOD_PROXY:-0}" != 1 ]; then git archive --format=tar.gz "$ref" -- "${rutas[@]}"; exit; fi
KIND=${GOMODCACHE:-$(go env GOMODCACHE)}/cache/download/github.com/juan52878911/kindling
[ -d "$KIND/@v" ] || { echo "falta $KIND/@v (go mod download en server/)" >&2; exit 1; }
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
git archive "$ref" -- "${rutas[@]}" | tar -xf - -C "$T"
mkdir -p "$T/gomod-proxy/github.com/juan52878911"
cp -R "$KIND" "$T/gomod-proxy/github.com/juan52878911/"
find "$T/gomod-proxy" -name '*.lock' -exec rm -f {} +
COPYFILE_DISABLE=1 tar -czf - -C "$T" .   # sin ficheros ._* de macOS (AppleDouble)
