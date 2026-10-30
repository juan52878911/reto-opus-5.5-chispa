#!/usr/bin/env bash
# tar.gz (git archive, de una rama o sha de ESTE repo) con lo que necesita estabilidad.sh: model/{l1,l2,datos,evaluacion,lineas_base,meta},
# model/herramientas/{train,test}.jsonl y runtime/l1 (exportar.py y el Go de embeber). Sin tests, resultados ni fixtures; con --fixtures
# (prueba en seco) también los fixtures. Stdout = el paquete.
# Uso: bash model/l2/aws/empaquetar_estabilidad.sh [rama-o-sha] [--fixtures] > codigo.tgz   (por defecto HEAD)
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../../.."
ref=HEAD; fix=0
for a in "$@"; do if [ "$a" = --fixtures ]; then fix=1; else ref=$a; fi; done
git rev-parse --verify --quiet "$ref^{commit}" >/dev/null || { echo "no existe la revisión '$ref'" >&2; exit 1; }
excl=(':(exclude,glob)**/resultados/**' ':(exclude,glob)**/__pycache__/**' ':(exclude,glob)model/*/tests/test_*' ':(exclude,glob)model/*/tests/gen_*'
      ':(exclude,glob)model/*/tests/falso.py' ':(exclude,glob)**/*_test.go' ':(exclude,glob)model/lineas_base/pred/**')
[ $fix = 1 ] || excl+=(':(exclude,glob)**/fixtures*/**')
git archive --format=tar.gz "$ref" -- model/__init__.py model/l1 model/l2 model/datos model/evaluacion model/lineas_base model/meta \
  model/herramientas/train.jsonl model/herramientas/test.jsonl runtime/l1 "${excl[@]}"
