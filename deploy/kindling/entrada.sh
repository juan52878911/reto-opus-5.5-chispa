#!/bin/sh
# Arranca chispa-server con el .chispa y el tokenizador montados por volumen.
#   CHISPA_PUERTO  puerto (8090)        CHISPA_MODELO  /modelos/modelo.chispa
#   CHISPA_TOK     /modelos/e5.chispa-tok (opcional; sin fichero, L2 sin torres al vuelo)
#   CHISPA_CONFIG  JSON de config con api_keys (OBLIGATORIO)
#   CHISPA_ABIERTO=1  o primer argumento -abierto: arranca sin config ni claves (/v1/decide sin autenticación; solo pruebas)
#   GOMEMLIMIT     tope blando del recolector de Go (p. ej. 400MiB; ver README)
#   CHISPA_ORT_LIB libonnxruntime.so (imagen-ort la trae fijada; chispa-server la lee, o se pasa -ort-lib como argumento)
# El resto de argumentos pasa tal cual a chispa-server.
set -eu
set -f # sin expansión de comodines en rutas
abierto=${CHISPA_ABIERTO:-0}
if [ "${1:-}" = "-abierto" ]; then abierto=1; shift; fi
modelo=${CHISPA_MODELO:-/modelos/modelo.chispa}
tok=${CHISPA_TOK:-/modelos/e5.chispa-tok}
config=${CHISPA_CONFIG:-}
if [ -z "$config" ] && [ "$abierto" != 1 ]; then
  echo "entrada.sh: falta CHISPA_CONFIG (JSON con api_keys). Para arrancar abierto a propósito: CHISPA_ABIERTO=1 o -abierto" >&2
  exit 64
fi
if [ -n "$config" ]; then
  [ -f "$config" ] || { echo "entrada.sh: CHISPA_CONFIG no es un fichero: $config" >&2; exit 64; }
  if [ "$abierto" != 1 ] && ! grep -q '"api_keys"' "$config"; then
    echo "entrada.sh: $config no trae api_keys; con CHISPA_ABIERTO=1 o -abierto se permite" >&2
    exit 64
  fi
fi
set -- "$@"
[ -n "$config" ] && set -- -config "$config" "$@"
[ -f "$tok" ] && set -- -tok "$tok" "$@"
exec /usr/local/bin/chispa-server -addr "0.0.0.0:${CHISPA_PUERTO:-8090}" -modelo "$modelo" "$@"
