#!/usr/bin/env bash
# Imprime en stdout el tar.gz que necesita aws.sh: el de e2e (server/, runtime, sdk, model.l2…; server/deploy/arena/ ya va dentro)
# más arena/ (fuentes y los ficheros que embebe web.go: sin el binario, data/ ni models/). No cambia empaquetar_e2e.sh.
# Uso: bash server/deploy/arena/empaquetar.sh [--fixtures] > codigo.tgz
set -euo pipefail
cd "$(dirname "$0")/../../.."
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
bash server/deploy/aws/empaquetar_e2e.sh "$@" | tar -xzf - -C "$T"
find arena -type f -size -1025k -not -name arena -not -path 'arena/data/*' -not -path 'arena/models/*' -not -path '*/.git/*' \
  | LC_ALL=C sort > "$T.lista"
tar -cf - -T "$T.lista" | tar -xf - -C "$T"
rm -f "$T.lista"
[ -f "$T/server/deploy/arena/aws.sh" ] || { echo "falta server/deploy/arena/aws.sh en el paquete" >&2; exit 1; }
tar -czf - -C "$T" .
