#!/usr/bin/env bash
# tar.gz (git archive, de una rama o sha de ESTE repo) con lo que necesita estabilidad.sh: model/{l1,l2,datos,evaluacion,lineas_base,meta},
# model/herramientas/{train,test}.jsonl, runtime (exportar.py de L1, el Go de embeber y el tokenizador), y, para M1 (batería de regresión),
# server, format y sdk (chispa-server con ORT, `chispa train` y `chispa evaluar --bateria`). Sin tests de Python, resultados ni fixtures;
# con --fixtures (prueba en seco) también los fixtures. Stdout = el paquete.
# CHISPA_GOMOD_PROXY=1 añade gomod-proxy/ (la caché de módulos de kindling del GOMODCACHE local, que no está en un proxy público; la
# necesita `go build` de server/ en la c6a), igual que model/bench/torre/empaquetar.sh. En la prueba en seco no hace falta (GOPROXY=off).
# Uso: [CHISPA_GOMOD_PROXY=1] bash model/l2/aws/empaquetar_estabilidad.sh [rama-o-sha] [--fixtures] > codigo.tgz   (por defecto HEAD)
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../../.."
ref=HEAD; fix=0
for a in "$@"; do if [ "$a" = --fixtures ]; then fix=1; else ref=$a; fi; done
git rev-parse --verify --quiet "$ref^{commit}" >/dev/null || { echo "no existe la revisión '$ref'" >&2; exit 1; }
excl=(':(exclude,glob)**/resultados/**' ':(exclude,glob)**/__pycache__/**' ':(exclude,glob)model/*/tests/test_*' ':(exclude,glob)model/*/tests/gen_*'
      ':(exclude,glob)model/*/tests/falso.py' ':(exclude,glob)**/*_test.go' ':(exclude,glob)model/lineas_base/pred/**')
[ $fix = 1 ] || excl+=(':(exclude,glob)**/fixtures*/**')
rutas=(model/__init__.py model/l1 model/l2 model/datos model/evaluacion model/lineas_base model/meta model/herramientas/train.jsonl model/herramientas/test.jsonl
       runtime server format sdk)
if [ "${CHISPA_GOMOD_PROXY:-0}" != 1 ]; then git archive --format=tar.gz "$ref" -- "${rutas[@]}" "${excl[@]}"; exit; fi
KIND=${GOMODCACHE:-$(go env GOMODCACHE)}/cache/download/github.com/juan52878911/kindling
[ -d "$KIND/@v" ] || { echo "falta $KIND/@v (go mod download en server/)" >&2; exit 1; }
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
git archive "$ref" -- "${rutas[@]}" "${excl[@]}" | tar -xf - -C "$T"
mkdir -p "$T/gomod-proxy/github.com/juan52878911"
cp -R "$KIND" "$T/gomod-proxy/github.com/juan52878911/"
find "$T/gomod-proxy" -name '*.lock' -exec rm -f {} +
COPYFILE_DISABLE=1 tar -czf - -C "$T" .
