#!/usr/bin/env bash
# Imprime en stdout un tar.gz con lo que necesita la instancia de AWS (ver arranque.sh): sdk/android/ (sin aws/), sdk/ios/,
# sdk/movil/, runtime/l1/ y format/chispa3/ (los `replace` de sdk/movil/chispamovil/go.mod los exigen),
# server/testdata/*.chispa y demo/wasm/ejemplo_pregunta.json (los tests los usan) y gomod-proxy/ con la caché de
# módulos de kindling (está en la caché de Go de esta máquina, no se puede bajar de un proxy público).
# Sin ficheros de más de 1 MB ni binarios. Uso: bash sdk/android/aws/empaquetar.sh > codigo.tgz
# Portable (GNU tar y bsdtar): solo find, cp, sort y tar -T sin -C.
set -euo pipefail
RAIZ=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
GOMODCACHE=${GOMODCACHE:-$(go env GOMODCACHE)}
KIND=$GOMODCACHE/cache/download/github.com/juan52878911/kindling
[ -d "$KIND/@v" ] || { echo "falta $KIND/@v (go mod download en sdk/movil/chispamovil/)" >&2; exit 1; }
T=$(mktemp -d); L=$(mktemp -d); trap 'rm -rf "$T" "$L"' EXIT
mkdir -p "$T/gomod-proxy/github.com/juan52878911"
cp -R "$KIND" "$T/gomod-proxy/github.com/juan52878911/"
find "$T/gomod-proxy" -name '*.lock' -type f -exec rm -f {} +
cd "$RAIZ"
find sdk/android sdk/ios sdk/movil runtime/l1 format/chispa3 server/testdata demo/wasm/ejemplo_pregunta.json -type f \
  -not -path 'sdk/android/aws/*' -not -path '*/.gradle/*' -not -path '*/.build/*' -not -path '*/build/*' -not -path '*/__pycache__/*' \
  -not -path 'runtime/l1/aws/*' -not -name '*.pyc' -not -name '*.so' -not -name '*.aar' -not -name '*.jar' \
  -not -name '*.apk' -not -name '*.chispa-l1' -not -name '*.wasm' -size -1025k | LC_ALL=C sort > "$L/lista-repo"
# se pasa por un directorio intermedio: así no hace falta -C junto a -T
tar -cf - -T "$L/lista-repo" | (cd "$T" && tar -xf -)
cd "$T"
find . -type f | sed 's|^\./||' | LC_ALL=C sort > "$L/lista"
tar -czf - -T "$L/lista"
