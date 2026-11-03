#!/usr/bin/env bash
# Paquete de código de la alternativa (b): model/alt y lo que importa (model/{datos,meta,evaluacion}, model/l2/datos.py).
# Uso: bash model/alt/aws/empaquetar.sh [rama-o-sha] > codigo.tgz   (por defecto HEAD). No sube nada.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
git archive --format=tar.gz "${1:-HEAD}" model/__init__.py model/alt model/datos model/meta model/evaluacion model/l2/__init__.py model/l2/datos.py
