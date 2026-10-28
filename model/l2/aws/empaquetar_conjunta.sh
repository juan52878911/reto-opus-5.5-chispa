#!/usr/bin/env bash
# El tar.gz de empaquetar.sh más lo que necesita model/l2/conjunta.py y empaquetar.sh no lleva: model/lineas_base/correr.py
# (L0 con el mismo código que las líneas base) y model/cascada/*.py sin tests (conjunta.py importa la partición de cascada.py y
# conjunta_cpu.sh corre el informe de la cascada). empaquetar.sh ya incluye conjunta.py y conjunta.sh (model/l2/*.py y *.sh).
# Uso: bash model/l2/aws/empaquetar_conjunta.sh [--fixtures] > codigo.tgz
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../../.."
tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT
bash model/l2/aws/empaquetar.sh "$@" | gunzip > "$tmp"
tar -rf "$tmp" model/lineas_base/__init__.py model/lineas_base/correr.py model/cascada/__init__.py model/cascada/cascada.py \
  model/cascada/capas.py model/cascada/informe.py
gzip -c "$tmp"
