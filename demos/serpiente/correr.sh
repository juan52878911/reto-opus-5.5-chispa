#!/usr/bin/env bash
# «Chispa: Serpiente»: jugar (traza) + medir (latencia) + evaluar (20 partidas por agente) y, si hay Pillow y ffmpeg, renderizar.
# Uso: demos/serpiente/correr.sh --url http://host:8090 --salida dir/ [--semilla N] [--partidas N] [--n-medir N] [--decidir argmax|tau]
set -euo pipefail
AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
URL=""; SALIDA=""; SEMILLA=1; PARTIDAS=20; NMEDIR=100; DECIDIR=tau
while [ $# -gt 0 ]; do
  case "$1" in
    --url) URL="$2"; shift 2;;
    --salida) SALIDA="$2"; shift 2;;
    --semilla) SEMILLA="$2"; shift 2;;
    --partidas) PARTIDAS="$2"; shift 2;;
    --n-medir) NMEDIR="$2"; shift 2;;
    --decidir) DECIDIR="$2"; shift 2;;
    *) echo "argumento desconocido: $1" >&2; exit 64;;
  esac
done
case "$DECIDIR" in argmax|tau) ;; *) echo "--decidir: argmax o tau, no «$DECIDIR»" >&2; exit 64;; esac
[ -n "$URL" ] && [ -n "$SALIDA" ] || { echo "uso: correr.sh --url http://… --salida dir/" >&2; exit 64; }
PY="${PYTHON:-python3}"
mkdir -p "$SALIDA"
cd "$AQUI"
export PYTHONPATH="$AQUI${PYTHONPATH:+:$PYTHONPATH}"

echo "== 1/4 jugar: partida grabada (semilla $SEMILLA, decidir $DECIDIR) =="
"$PY" -m serpiente.jugar --url "$URL" --salida "$SALIDA/traza.jsonl" --semilla "$SEMILLA" --decidir "$DECIDIR"
echo "== 2/4 medir: latencia por decisión =="
"$PY" -m serpiente.medir --url "$URL" --salida "$SALIDA" --n "$NMEDIR" --decidir "$DECIDIR"
echo "== 3/4 evaluar: $PARTIDAS partidas por agente =="
"$PY" -m serpiente.evaluar --url "$URL" --salida "$SALIDA" --partidas "$PARTIDAS" --decidir "$DECIDIR"
echo "== 4/4 renderizar: vídeo =="
set +e
"$PY" -m serpiente.renderizar --traza "$SALIDA/traza.jsonl" --salida "$SALIDA/partida.mp4"
rc=$?
set -e
if [ "$rc" -eq 3 ]; then
  echo "AVISO: sin Pillow o sin ffmpeg: SE SALTA EL VÍDEO (el resto está hecho). Para generarlo: pip install -r $AQUI/requirements-render.txt y repite: $PY -m serpiente.renderizar --traza $SALIDA/traza.jsonl --salida $SALIDA/partida.mp4"
elif [ "$rc" -ne 0 ]; then
  echo "renderizar falló con código $rc" >&2
  exit "$rc"
fi
echo "Listo en $SALIDA: traza.jsonl, latencia.json/.md, evaluacion.json/.md$([ "$rc" -eq 0 ] && echo ', partida.mp4')"
