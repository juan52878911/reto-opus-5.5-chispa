#!/usr/bin/env bash
# tar.gz (de una rama o sha de ESTE repo) con lo que necesita laya.sh: model/{datos,l2,evaluacion}, model/herramientas/test.jsonl, sdk/python (la batería)
# y las dos líneas base de Chispa (model/l2/resultados/linea-base-{oficial,v2}-20261102/*.json, de donde sale la tabla). Sin tests de Python ni resultados;
# con --fixtures (prueba en seco) también los fixtures. Stdout = el paquete.
# Uso: bash model/evaluacion/aws/empaquetar_laya.sh [rama-o-sha] [--fixtures] > codigo.tgz   (por defecto HEAD)
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../../.."
ref=HEAD; fix=0
for a in "$@"; do if [ "$a" = --fixtures ]; then fix=1; else ref=$a; fi; done
git rev-parse --verify --quiet "$ref^{commit}" >/dev/null || { echo "no existe la revisión '$ref'" >&2; exit 1; }
excl=(':(exclude,glob)model/l2/resultados/**' ':(exclude,glob)model/evaluacion/resultados/**' ':(exclude,glob)model/datos/**/resultados/**' ':(exclude,glob)sdk/**/resultados/**'
      ':(exclude,glob)**/__pycache__/**' ':(exclude,glob)model/*/tests/test_*' ':(exclude,glob)model/*/tests/gen_*' ':(exclude,glob)sdk/**/tests/**')
[ $fix = 1 ] || excl+=(':(exclude,glob)**/fixtures*/**')
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
git archive "$ref" -- model/__init__.py model/datos model/l2 model/evaluacion model/herramientas/test.jsonl sdk/python "${excl[@]}" | tar -xf - -C "$T"
for d in linea-base-oficial-20261102/linea-base.json linea-base-v2-20261102/linea-base-v2.json; do
  mkdir -p "$T/model/l2/resultados/$(dirname "$d")"
  git show "$ref:model/l2/resultados/$d" > "$T/model/l2/resultados/$d"
done
COPYFILE_DISABLE=1 tar -czf - -C "$T" .
