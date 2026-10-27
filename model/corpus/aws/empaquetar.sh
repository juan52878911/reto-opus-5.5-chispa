#!/usr/bin/env bash
# Imprime en stdout el tar.gz con lo mínimo que necesita la instancia de AWS (ver arranque.sh): el código de
# model/corpus/ (sin tests, salidas ni caché), el catálogo y el test de herramientas y el test de whatsapp_comercio
# (para que el corpus no se parezca a ellos). Uso: bash model/corpus/aws/empaquetar.sh > codigo.tgz
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../../.."
{
  echo model/__init__.py
  find model/corpus -type f \( -name '*.py' -o -name '*.sh' \) -not -path '*/tests/*' -not -path '*/__pycache__/*' -not -path '*/salida/*'
  echo model/herramientas/catalogo.json
  echo model/herramientas/test.jsonl
  echo model/sondeo/whatsapp_comercio.jsonl
} | LC_ALL=C sort | tar -czf - -T -
