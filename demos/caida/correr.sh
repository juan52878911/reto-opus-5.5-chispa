#!/usr/bin/env bash
# «Chispa: Caída»: jugar (traza) + medir (latencia) + evaluar (20 partidas por agente) y, si hay Pillow y ffmpeg, renderizar.
# Uso: demos/caida/correr.sh --url http://host:8090 --salida dir/ [--url-fewshot URL] [--semilla N] [--max-piezas N] [--partidas N] [--n-medir N]
set -euo pipefail
AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
URL=""; URL_FS=""; SALIDA=""; SEMILLA=1; MAXP=150; PARTIDAS=20; NMEDIR=100
while [ $# -gt 0 ]; do
  case "$1" in
    --url) URL="$2"; shift 2;;
    --url-fewshot) URL_FS="$2"; shift 2;;
    --salida) SALIDA="$2"; shift 2;;
    --semilla) SEMILLA="$2"; shift 2;;
    --max-piezas) MAXP="$2"; shift 2;;
    --partidas) PARTIDAS="$2"; shift 2;;
    --n-medir) NMEDIR="$2"; shift 2;;
    *) echo "argumento desconocido: $1" >&2; exit 64;;
  esac
done
[ -n "$URL" ] && [ -n "$SALIDA" ] || { echo "uso: correr.sh --url http://… --salida dir/" >&2; exit 64; }
PY="${PYTHON:-python3}"
mkdir -p "$SALIDA"
cd "$AQUI"
export PYTHONPATH="$AQUI${PYTHONPATH:+:$PYTHONPATH}"

echo "== 1/4 jugar: partida grabada (semilla $SEMILLA) =="
"$PY" -m caida.jugar --url "$URL" --salida "$SALIDA/traza.jsonl" --semilla "$SEMILLA" --max-piezas "$MAXP"
echo "== 2/4 medir: latencia por petición de 3 preguntas =="
"$PY" -m caida.medir --url "$URL" --salida "$SALIDA" --n "$NMEDIR"
echo "== 3/4 evaluar: $PARTIDAS partidas por agente =="
"$PY" -m caida.evaluar --url "$URL" ${URL_FS:+--url-fewshot "$URL_FS"} --salida "$SALIDA" --partidas "$PARTIDAS" --max-piezas "$MAXP"
echo "== 4/4 renderizar: vídeo =="
set +e
"$PY" -m caida.renderizar --traza "$SALIDA/traza.jsonl" --salida "$SALIDA/partida.mp4"
rc=$?
set -e
if [ "$rc" -eq 3 ]; then
  echo "AVISO: sin Pillow o sin ffmpeg: SE SALTA EL VÍDEO (el resto está hecho). Para generarlo: pip install -r $AQUI/requirements-render.txt y repite: $PY -m caida.renderizar --traza $SALIDA/traza.jsonl --salida $SALIDA/partida.mp4"
elif [ "$rc" -ne 0 ]; then
  echo "renderizar falló con código $rc" >&2
  exit "$rc"
fi
echo "Listo en $SALIDA: traza.jsonl, latencia.json/.md, evaluacion.json/.md$([ "$rc" -eq 0 ] && echo ', partida.mp4')"
