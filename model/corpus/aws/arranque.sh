#!/bin/bash
CHISPA_S3=__CHISPA_S3__
# Parámetros que sustituye el orquestador junto con __CHISPA_S3__ (en modo local no hacen falta):
PRECIO_IN=__PRECIO_IN__     # USD por millón de tokens de entrada de us.anthropic.claude-haiku-5-5
PRECIO_OUT=__PRECIO_OUT__   # USD por millón de tokens de salida
POR_CLASE=${POR_CLASE:-__POR_CLASE__}   # textos pedidos por clase y tarea (para ≥ 2 k útiles por tarea, ver el informe de T1.3)
TOPE_USD=${TOPE_USD:-8}
# user-data de una Amazon Linux 2023 x86_64 (c6a.large) recién creada (root): corre model/corpus/generar.py contra Haiku en
# Bedrock (us-east-1; el rol de la instancia lo permite) y deja /opt/chispa/corpus.tgz y /opt/chispa/LISTO.
# El orquestador sube $CHISPA_S3/codigo.tgz (bash model/corpus/aws/empaquetar.sh); la instancia (rol con s3:GetObject y
# s3:PutObject y bedrock:InvokeModel, sin SSH) lo baja, y al terminar sube log.txt y corpus.tgz al mismo prefijo y se apaga.
# CHISPA_LOCAL=1: prueba en seco en kindling (sin dnf, pip, descargas, Bedrock ni shutdown; ~/venv, ~/hf, /tmp/chispa;
# backend simulado); el "s3" es /tmp/chispa/s3/<prefijo sin s3://> y se copia con cp en vez de aws s3 cp.
[ "${CHISPA_LOCAL:-}" = 1 ] || shutdown -h +170   # apagado forzoso: la instancia se termina al apagarse
set -uo pipefail
export HOME="${HOME:-/root}"

if [ "${CHISPA_LOCAL:-}" = 1 ]; then
  BASE=/tmp/chispa; VENV="$HOME/venv"; export HF_HOME="$HOME/hf"
  BACKEND=simulado; PRECIO_IN=1; PRECIO_OUT=5; POR_CLASE=${CHISPA_POR_CLASE:-30}
  [ -n "${CHISPA_TOPE_USD:-}" ] && TOPE_USD=$CHISPA_TOPE_USD
else
  BASE=/opt/chispa; VENV=$BASE/venv; export HF_HOME=$BASE/hf
  BACKEND=bedrock
fi
mkdir -p "$BASE"
exec > >(tee -a "$BASE/log.txt") 2>&1
echo "== arranque $(date -u +%FT%TZ) local=${CHISPA_LOCAL:-0} base=$BASE backend=$BACKEND"

REPO=$BASE/repo RES=$BASE/corpus
PY=$VENV/bin/python
FALLO=""
S3LOCAL=/tmp/chispa/s3/${CHISPA_S3#s3://}

# s3cp ORIGEN DESTINO: aws s3 cp, o cp contra el directorio simulado en modo local.
s3cp() {
  if [ "${CHISPA_LOCAL:-}" = 1 ]; then
    local o=$1 d=$2
    case $o in s3://*) o=/tmp/chispa/s3/${o#s3://};; esac
    case $d in s3://*) d=/tmp/chispa/s3/${d#s3://}; mkdir -p "$(dirname "$d")";; esac
    cp "$o" "$d"
  else
    aws s3 cp --only-show-errors "$1" "$2"
  fi
}

# Al salir, bien o mal: sube el log y, si existe, corpus.tgz; después apaga (salvo en local).
subir_y_apagar() {
  trap - EXIT
  sleep 1   # deja que tee vacíe el log
  s3cp "$BASE/log.txt" "$CHISPA_S3/log.txt" || echo "no se pudo subir log.txt"
  [ -f "$BASE/corpus.tgz" ] && { s3cp "$BASE/corpus.tgz" "$CHISPA_S3/corpus.tgz" || echo "no se pudo subir corpus.tgz"; }
  [ "${CHISPA_LOCAL:-}" = 1 ] || shutdown -h now
}
trap subir_y_apagar EXIT
trap 'exit 143' TERM INT HUP

fallo() { echo "FALLO: $*"; FALLO="${FALLO:+$FALLO; }$*"; }

cierre() {
  mkdir -p "$RES"
  [ -n "$FALLO" ] && echo "$FALLO" > "$BASE/FALLO" && cp "$BASE/FALLO" "$RES/"
  df -h "$BASE" | tail -1
  cp "$BASE/log.txt" "$RES/log.txt"
  tar -C "$BASE" -czf "$BASE/corpus.tgz" corpus
  touch "$BASE/LISTO"
  echo "== listo $(date -u +%FT%TZ) fallo=${FALLO:-no}"
  exit 0
}

# --- entorno -----------------------------------------------------------------------------------------------
instalar() {
  dnf install -y python3.11 python3.11-pip tar gzip || return 1
  python3.11 -m venv "$VENV" || return 1
  # Un solo pip install: si torch se instala aparte, las dependencias lo reemplazan por el de CUDA (6 GB).
  "$VENV/bin/pip" install -q --no-cache-dir --index-url https://download.pytorch.org/whl/cpu \
    --extra-index-url https://pypi.org/simple torch transformers huggingface_hub numpy boto3 || return 1
}
bajar() {
  "$PY" -I - <<'PYEOF' || return 1
import glob, os
from huggingface_hub import snapshot_download as s
d = s("intfloat/multilingual-e5-small", allow_patterns=["*.json", "*.safetensors", "*.txt", "*.model", "tokenizer*"])
assert glob.glob(d + "/*.safetensors"), "sin pesos de e5-small"
print("modelo e5-small", os.listdir(d))
PYEOF
}

if [ "${CHISPA_LOCAL:-}" != 1 ]; then
  case "$PRECIO_IN$PRECIO_OUT$POR_CLASE" in *__*) fallo "faltan PRECIO_IN, PRECIO_OUT o POR_CLASE sin sustituir"; cierre;; esac
  instalar || { fallo "dnf/venv/pip"; cierre; }
  bajar || { fallo "descarga de e5-small de Hugging Face"; cierre; }
fi
"$PY" -c "import torch, numpy; assert not torch.version.cuda, 'torch con CUDA: ' + str(torch.version.cuda); print('torch', torch.__version__, 'sin CUDA')" \
  || { fallo "torch trae CUDA o no importa"; cierre; }

# --- código en S3, subido por el orquestador (reintenta cada 30 s hasta 45 min) -------------------------------
echo "bajando $CHISPA_S3/codigo.tgz"
for _ in $(seq 1 90); do   # 90 × 30 s = 45 min
  s3cp "$CHISPA_S3/codigo.tgz" "$BASE/codigo.tgz" 2>/dev/null && tar -tzf "$BASE/codigo.tgz" >/dev/null 2>&1 && break
  rm -f "$BASE/codigo.tgz"
  sleep 30
done
rm -rf "$REPO"; mkdir -p "$REPO"
tar -xzf "$BASE/codigo.tgz" -C "$REPO" || { fallo "no llegó un codigo.tgz válido en 45 min"; cierre; }

# --- generación -----------------------------------------------------------------------------------------------
mkdir -p "$RES"
cd "$REPO" || { fallo "sin repo"; cierre; }
ARGS=(--por-clase "$POR_CLASE" --salida "$RES" --backend "$BACKEND" --tope-usd "$TOPE_USD" --precio-in "$PRECIO_IN" --precio-out "$PRECIO_OUT")
echo "== generar $(date -u +%T) ${ARGS[*]}"
# 150 min como máximo: deja 20 min para ensamblar y subir antes del apagado forzoso (170).
timeout 9000 "$PY" model/corpus/generar.py "${ARGS[@]}" || {
  fallo "generar.py terminó con error o tiempo agotado (rc=$?)"
  # Lo ya generado está en crudo/: ensambla las salidas sin llamar al modelo.
  "$PY" model/corpus/generar.py "${ARGS[@]}" --sin-llamadas || fallo "ensamblado sin llamadas"
}
ls -l "$RES" | head -20
[ -f "$RES/resumen.json" ] || fallo "sin resumen.json"
cierre
