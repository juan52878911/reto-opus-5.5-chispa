#!/bin/bash
CHISPA_S3=__CHISPA_S3__
# Parámetros que sustituye el orquestador junto con __CHISPA_S3__ (en modo local no hacen falta):
POR_CLASE=${POR_CLASE:-__POR_CLASE__}   # textos pedidos por clase y tarea (para ≥ 2 k útiles por tarea, ver el informe de T1.3b)
TOPE_MIN=${TOPE_MIN:-__TOPE_MIN__}      # minutos de reloj para la generación (máx. 140: el apagado forzoso es a los 170)
CHISPA_MODELO=${CHISPA_MODELO:-}        # opcional; por defecto el mayor Qwen Apache-2.0 que quepa en la GPU (4B con < 30 GB; ver backends.py)
CHISPA_MOTOR=${CHISPA_MOTOR:-auto}      # transformers | vllm | auto (vLLM si se instala y arranca; si no, transformers)
# user-data de una g5.xlarge on-demand (A10G, 24 GB) con la AMI «Deep Learning OSS Nvidia Driver AMI GPU PyTorch 2.10
# (Amazon Linux 2023)», root: corre model/corpus/generar.py con el backend local (Qwen abierto, vLLM si se puede instalar,
# si no transformers) y deja /opt/chispa/corpus.tgz y /opt/chispa/LISTO. Sin Bedrock ni gasto de tokens: el coste son horas de GPU.
# El orquestador sube $CHISPA_S3/codigo.tgz (bash model/corpus/aws/empaquetar.sh); la instancia (rol con s3:GetObject y
# s3:PutObject, sin SSH, con internet) lo baja, y al terminar sube log.txt y corpus.tgz al mismo prefijo y se apaga.
# CHISPA_LOCAL=1: prueba en seco en kindling (sin pip, descargas ni shutdown; ~/venv, ~/hf, /tmp/chispa; backend simulado);
# el "s3" es /tmp/chispa/s3/<prefijo sin s3://> y se copia con cp en vez de aws s3 cp.
[ "${CHISPA_LOCAL:-}" = 1 ] || shutdown -h +170   # apagado forzoso: la instancia se termina al apagarse
set -uo pipefail
export HOME="${HOME:-/root}"

if [ "${CHISPA_LOCAL:-}" = 1 ]; then
  BASE=/tmp/chispa; export HF_HOME="$HOME/hf"
  BACKEND=simulado; POR_CLASE=${CHISPA_POR_CLASE:-30}; TOPE_MIN=${CHISPA_TOPE_MIN:-0}
else
  BASE=/opt/chispa; export HF_HOME=$BASE/hf
  BACKEND=local
fi
mkdir -p "$BASE"
exec > >(tee -a "$BASE/log.txt") 2>&1
echo "== arranque $(date -u +%FT%TZ) local=${CHISPA_LOCAL:-0} base=$BASE backend=$BACKEND"

REPO=$BASE/repo RES=$BASE/corpus
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
# Python de la AMI (el que importa torch con CUDA), sin tocar torch.
if [ "${CHISPA_LOCAL:-}" = 1 ]; then
  PY=$HOME/venv/bin/python
else
  case "$POR_CLASE$TOPE_MIN" in *__*) fallo "faltan POR_CLASE o TOPE_MIN sin sustituir"; cierre;; esac
  echo "== /opt:"; ls /opt
  PY=""
  for c in /opt/pytorch/bin/python /opt/conda/envs/pytorch/bin/python /opt/conda/bin/python /usr/bin/python3; do
    [ -x "$c" ] && "$c" -c "import torch" 2>/dev/null && { PY=$c; break; }
  done
  [ -n "$PY" ] || { fallo "ningún Python de la AMI importa torch"; cierre; }
fi
echo "python: $PY"
"$PY" -c "import sys, torch; print(sys.version.split()[0], 'torch', torch.__version__, 'cuda', torch.version.cuda, 'disponible', torch.cuda.is_available())"
case "$CHISPA_MOTOR" in transformers|vllm|auto) ;; *) fallo "CHISPA_MOTOR=$CHISPA_MOTOR no vale (transformers|vllm|auto)"; cierre;; esac
MOTOR=transformers
if [ "${CHISPA_LOCAL:-}" != 1 ]; then
  "$PY" -c "import torch; assert torch.cuda.is_available()" || { fallo "torch no ve la GPU"; cierre; }
  nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv
  "$PY" -m pip install -q --no-cache-dir -U transformers accelerate huggingface_hub numpy \
    || { fallo "pip install de transformers"; cierre; }
  # vLLM trae su propio torch: va en un venv aparte y solo se usa si se instala; si no, transformers con el Python de la AMI.
  # Con «auto», si vLLM se instala pero luego falla al crear el motor (memoria, flashinfer sin nvcc), Local sigue con transformers.
  PYV=$BASE/venv-vllm/bin/python
  if [ "$CHISPA_MOTOR" = transformers ]; then
    echo "CHISPA_MOTOR=transformers: no se instala vLLM"
  elif "$PY" -m venv "$BASE/venv-vllm" && "$BASE/venv-vllm/bin/pip" install -q --no-cache-dir vllm huggingface_hub numpy \
       && "$PYV" -c "import vllm, torch; assert torch.cuda.is_available(); print('vllm', vllm.__version__)"; then
    PY=$PYV; MOTOR=$CHISPA_MOTOR
  elif [ "$CHISPA_MOTOR" = vllm ]; then
    fallo "CHISPA_MOTOR=vllm pero vLLM no se pudo instalar"; cierre
  else
    echo "vLLM no se pudo instalar o no arranca; sigo con transformers"
  fi
  rm -rf "$HOME/.cache/pip"
fi
"$PY" -m pip freeze 2>/dev/null | grep -iE '^(torch|transformers|vllm|huggingface)'
echo "motor: $MOTOR"

bajar() {
  "$PY" -I - <<'PYEOF' || return 1
import glob, os
from huggingface_hub import snapshot_download as s
d = s("intfloat/multilingual-e5-small", allow_patterns=["*.json", "*.safetensors", "*.txt", "*.model", "tokenizer*"])
assert glob.glob(d + "/*.safetensors"), "sin pesos de e5-small"
print("modelo e5-small", os.listdir(d))
PYEOF
}
[ "${CHISPA_LOCAL:-}" = 1 ] || bajar || { fallo "descarga de e5-small de Hugging Face"; cierre; }

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
export PYTHONPATH=$REPO
ARGS=(--por-clase "$POR_CLASE" --salida "$RES" --backend "$BACKEND")
if [ "$BACKEND" = local ]; then
  ARGS+=(--tope-min "$TOPE_MIN" --motor "$MOTOR")
  [ -n "$CHISPA_MODELO" ] && ARGS+=(--modelo "$CHISPA_MODELO")
fi
echo "== generar $(date -u +%T) ${ARGS[*]}"
# 150 min como máximo: deja 20 min para ensamblar y subir antes del apagado forzoso (170). generar.py reanuda desde crudo/.
timeout 9000 "$PY" model/corpus/generar.py "${ARGS[@]}" || {
  fallo "generar.py terminó con error o tiempo agotado (rc=$?)"
  # Lo ya generado está en crudo/: ensambla las salidas sin llamar al modelo.
  "$PY" model/corpus/generar.py "${ARGS[@]}" --sin-llamadas || fallo "ensamblado sin llamadas"
}
ls -l "$RES" | head -20
[ -f "$RES/resumen.json" ] || fallo "sin resumen.json"
cierre
