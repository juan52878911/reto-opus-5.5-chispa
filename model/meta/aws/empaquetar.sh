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
  echo model/meta/resultados/conversion-20261027.json   # traducir.sh lista las claves del meta con él (el rol no tiene ListBucket)
} | LC_ALL=C sort | COPYFILE_DISABLE=1 tar --no-xattrs -czf - -T -
