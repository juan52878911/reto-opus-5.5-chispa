#!/usr/bin/env bash
# Imprime en stdout un tar.gz con lo mínimo que necesita la instancia de AWS (ver arranque.sh): el código de
# model/meta/ (sin tests ni salidas) y lo que importa de model/datos/ (comun.py y validar.py, sin tests ni fixtures).
# Uso: bash model/meta/aws/empaquetar.sh > codigo.tgz
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../../.."
{
  echo model/__init__.py
  echo model/datos/__init__.py
  echo model/datos/comun.py
  echo model/datos/validar.py
  find model/meta -type f \( -name '*.py' -o -name '*.sh' \) -not -path '*/tests/*' -not -path '*/__pycache__/*'
} | LC_ALL=C sort | tar -czf - -T -
