#!/bin/sh
# Arranca chispa-server con el .chispa y el tokenizador montados por volumen.
#   CHISPA_PUERTO  puerto (8090)        CHISPA_MODELO  /modelos/modelo.chispa
#   CHISPA_TOK     /modelos/e5.chispa-tok (opcional; sin fichero, L2 sin torres al vuelo)
#   CHISPA_CONFIG  JSON de config (opcional)
#   GOMEMLIMIT     tope blando del recolector de Go (p. ej. 400MiB; ver README)
#   CHISPA_ORT_LIB libonnxruntime.so (imagen-ort la trae fijada; chispa-server la lee, o se pasa -ort-lib como argumento)
set -eu
args="-addr 0.0.0.0:${CHISPA_PUERTO:-8090} -modelo ${CHISPA_MODELO:-/modelos/modelo.chispa}"
[ -f "${CHISPA_TOK:-/modelos/e5.chispa-tok}" ] && args="$args -tok ${CHISPA_TOK:-/modelos/e5.chispa-tok}"
[ -n "${CHISPA_CONFIG:-}" ] && args="$args -config $CHISPA_CONFIG"
# shellcheck disable=SC2086
exec /usr/local/bin/chispa-server $args "$@"
