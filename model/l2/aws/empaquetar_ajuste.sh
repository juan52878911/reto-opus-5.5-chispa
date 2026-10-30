#!/usr/bin/env bash
# El mismo paquete que empaquetar_estabilidad.sh (código de model/{l1,l2,datos,evaluacion,lineas_base,meta}, runtime/l1, sdk/python con
# chispa.variantes, y model/meta/resultados/conversion-20261027.json para la lista de ficheros del meta), que es todo lo que necesita ajuste.sh.
# Uso: bash model/l2/aws/empaquetar_ajuste.sh [rama-o-sha] [--fixtures] > codigo.tgz   (por defecto HEAD)
exec bash "$(dirname "${BASH_SOURCE[0]}")/empaquetar_estabilidad.sh" "$@"
