#!/bin/bash
CHISPA_S3=__CHISPA_S3__
# user-data (≤ 16 KB) de una c6a.xlarge spot (Amazon Linux 2023, x86_64, 4 vCPU, sin GPU), root, con internet y rol con s3:GetObject
# y s3:PutObject (sin List), sin SSH: G.1, JevBench público (231 decisiones, MIT) con L2 y con la cascada de un cliente nuevo.
# El orquestador sustituye __CHISPA_S3__ y sube $CHISPA_S3/codigo.tgz (bash server/deploy/aws/empaquetar_e2e.sh > codigo.tgz: ya lleva
# model/evaluacion/*.py, model/l2, sdk/python/chispa y server). Opcionales: CHISPA_CKPT_S3 (por defecto el de l2-20261028b),
# CHISPA_JEV_REF (rama o sha de JevBench; por defecto el HEAD), CHISPA_CASCADA_MIN (minutos máx. de la cascada; por defecto lo que quede).
# En la instancia: 1. Go, Python 3.11 (venv con torch CPU, transformers, onnx…) y ORT; 2. código, checkpoint (fichero a fichero: el rol no
# lista el bucket), e5 y `git clone` de JevBench; 3. L2 zero-shot y con soporte k = 8 y 32 dejando fuera el caso (model.evaluacion.jevbench_l2);
# 4. tokenizador, `chispa train` sin --conjunta por pliegue y `chispa-server -tags ort` (jevbench_cascada); 5. informe (jevbench_informe).
# Al salir (trap: fin normal, error o SIGTERM) sube log.txt y resultados.tgz y apaga; apagado forzoso a los 60 min.
# CHISPA_LOCAL=1: prueba en seco sin dnf, pip, ORT ni shutdown: CHISPA_PY (por defecto ~/venv/bin/python), Go en el PATH, /tmp/chispa-jev;
# JevBench sale de CHISPA_JEV_LOCAL (por defecto el fixture del repo); checkpoint sin entrenar; servidor sin ORT (L2 en stub); el "s3" es
# /tmp/chispa/s3/<prefijo>. CHISPA_PLIEGUES=N limita los pliegues de la cascada.
CKPT_S3=${CHISPA_CKPT_S3:-s3://chispa-pruebas-879381269751/l2-20261028b/ckpt/mejor.pt}
LOCAL=${CHISPA_LOCAL:-0}
if [ "$LOCAL" = 1 ]; then [ "${CHISPA_S3#__}" != "$CHISPA_S3" ] && CHISPA_S3=s3://local/jevbench; else shutdown -h +60; fi
set -uo pipefail
export HOME="${HOME:-/root}"
T0=$(date +%s)
GO_VERSION=1.27.1; ORT_VERSION=1.22.0; ORT_GO_VERSION=v1.19.0; PUERTO=8090
if [ "$LOCAL" = 1 ]; then BASE=/tmp/chispa-jev; else BASE=/opt/chispa; fi
mkdir -p "$BASE"
exec > >(tee -a "$BASE/log.txt") 2>&1
echo "== arranque jevbench $(date -u +%FT%TZ) local=$LOCAL base=$BASE"
REPO=$BASE/repo RES=$BASE/resultados MODELOS=$BASE/modelos JEV=$BASE/jevbench
FALLO=""

s3cp() {   # un fichero (el rol no lista el bucket: nada de --recursive ni sync)
  if [ "$LOCAL" = 1 ]; then
    local o=$1 d=$2
    case $o in s3://*) o=/tmp/chispa/s3/${o#s3://};; esac
    case $d in s3://*) d=/tmp/chispa/s3/${d#s3://}; mkdir -p "$(dirname "$d")";; esac
    cp "$o" "$d"
  else aws s3 cp --only-show-errors "$1" "$2"
  fi
}
subir_y_apagar() {
  trap - EXIT
  sleep 1
  mkdir -p "$RES"
  [ -n "$FALLO" ] && echo "$FALLO" > "$RES/FALLO"
  cp "$BASE/log.txt" "$RES/log.txt" 2>/dev/null
  rm -f "$BASE/resultados.tgz"
  ( cd "$BASE" && find resultados -type f -not -name '*.chispa' -not -name '*.onnx' -not -name '*.chispa-tok' -size -50000k \
      | LC_ALL=C sort > "$BASE/resultados.lista" && tar -czf "$BASE/resultados.tgz" -T "$BASE/resultados.lista" ) || echo "no se pudo crear resultados.tgz"
  [ -f "$BASE/resultados.tgz" ] && { s3cp "$BASE/resultados.tgz" "$CHISPA_S3/resultados.tgz" || echo "no se pudo subir resultados.tgz"; }
  s3cp "$BASE/log.txt" "$CHISPA_S3/log.txt" || echo "no se pudo subir log.txt"
  [ "$LOCAL" = 1 ] || shutdown -h now
}
trap subir_y_apagar EXIT
trap 'exit 143' TERM INT HUP
fallo() { echo "FALLO: $*"; FALLO="${FALLO:+$FALLO; }$*"; }
cierre() { echo "== listo $(date -u +%FT%TZ) fallo=${FALLO:-no} ($(( $(date +%s) - T0 )) s)"; exit 0; }
quedan_min() { echo $(( 60 - ($(date +%s) - T0) / 60 )); }

# --- 1. entorno -------------------------------------------------------------------------------------------------------------
export HF_HOME="$HOME/hf"; mkdir -p "$HF_HOME" "$RES"
if [ "$LOCAL" = 1 ]; then
  PY=${CHISPA_PY:-$HOME/venv/bin/python}
else
  echo "== 1. entorno $(date -u +%T)"
  dnf install -y -q gcc tar gzip git python3.11 python3.11-pip || { fallo "dnf install"; cierre; }
  curl -fsSL "https://go.dev/dl/go${GO_VERSION}.linux-amd64.tar.gz" | tar -xzC /usr/local || { fallo "descarga de Go"; cierre; }
  export PATH=/usr/local/go/bin:$PATH
  mkdir -p /opt/ort && curl -fsSL "https://github.com/microsoft/onnxruntime/releases/download/v${ORT_VERSION}/onnxruntime-linux-x64-${ORT_VERSION}.tgz" \
    | tar -xzC /opt/ort --strip-components=1 || { fallo "descarga de ORT $ORT_VERSION"; cierre; }
  python3.11 -m venv "$BASE/venv" || { fallo "venv"; cierre; }
  PY=$BASE/venv/bin/python
  "$PY" -m pip install -q --no-cache-dir -U pip \
    && "$PY" -m pip install -q --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && "$PY" -m pip install -q --no-cache-dir numpy scikit-learn transformers tokenizers huggingface_hub pyyaml pyarrow datasets onnx onnxscript onnxruntime \
    || { fallo "pip install"; cierre; }
fi
go version
"$PY" -c "import sys, numpy, torch, transformers, onnxruntime; print(sys.version.split()[0], 'torch', torch.__version__, 'transformers', transformers.__version__)" \
  || { fallo "imports de Python"; cierre; }
export GOTOOLCHAIN=local GOFLAGS=-mod=mod GONOSUMDB='github.com/juan52878911/*'

# --- 2. código, checkpoint, e5 y JevBench ---------------------------------------------------------------------------------------
echo "== 2. código y datos $(date -u +%T)"
if [ "$LOCAL" = 1 ] && [ ! -f "/tmp/chispa/s3/${CHISPA_S3#s3://}/codigo.tgz" ]; then   # en seco lo empaqueta el propio script
  mkdir -p "/tmp/chispa/s3/${CHISPA_S3#s3://}"
  bash "$(dirname "${BASH_SOURCE[0]}")/../../../server/deploy/aws/empaquetar_e2e.sh" --fixtures > "/tmp/chispa/s3/${CHISPA_S3#s3://}/codigo.tgz" \
    || { fallo "empaquetar_e2e.sh"; cierre; }
fi
for _ in $(seq 1 90); do   # 90 × 30 s = 45 min
  s3cp "$CHISPA_S3/codigo.tgz" "$BASE/codigo.tgz" 2>/dev/null && tar -tzf "$BASE/codigo.tgz" >/dev/null 2>&1 && break
  rm -f "$BASE/codigo.tgz"
  [ "$LOCAL" = 1 ] && break
  sleep 30
done
rm -rf "$REPO" "$MODELOS" "$JEV"; mkdir -p "$REPO" "$MODELOS"
tar -xzf "$BASE/codigo.tgz" -C "$REPO" || { fallo "no llegó un codigo.tgz válido"; cierre; }
cd "$REPO" || { fallo "sin repo"; cierre; }
export PYTHONPATH=$REPO:$REPO/sdk/python
if [ "$LOCAL" = 1 ]; then export GOPROXY=off; else export GOPROXY=file://$REPO/gomod-proxy,https://proxy.golang.org; fi
{ lscpu; echo "nproc: $(nproc)"; } > "$RES/hardware.txt"

if [ "$LOCAL" = 1 ] && [ ! -f "/tmp/chispa/s3/${CKPT_S3#s3://}" ]; then
  echo "local: sin $CKPT_S3, checkpoint de L2 sin entrenar"
  mkdir -p "$(dirname "/tmp/chispa/s3/${CKPT_S3#s3://}")"
  "$PY" -c "
import sys, torch
from model.l2.modelo import ModeloL2
torch.manual_seed(0)
torch.save({'modelo': ModeloL2().state_dict(), 'cabezas': [], 'enc': None}, sys.argv[1])" "/tmp/chispa/s3/${CKPT_S3#s3://}" \
    || { fallo "no se pudo fabricar el checkpoint local"; cierre; }
fi
s3cp "$CKPT_S3" "$BASE/mejor.pt" || { fallo "no se pudo bajar el checkpoint $CKPT_S3"; cierre; }
ls -l "$BASE/mejor.pt"
if ! ls "$HF_HOME"/hub/models--intfloat--multilingual-e5-small/snapshots/*/tokenizer.json >/dev/null 2>&1; then
  "$PY" -I -c 'from huggingface_hub import snapshot_download as s; s("intfloat/multilingual-e5-small", allow_patterns=["*.json", "*.safetensors", "*.txt", "*.model", "tokenizer*"])' \
    || { fallo "descarga de e5"; cierre; }
fi
E5=$(ls -d "$HF_HOME"/hub/models--intfloat--multilingual-e5-small/snapshots/*/ 2>/dev/null | head -1)
[ -f "${E5}tokenizer.json" ] || { fallo "e5 (con tokenizer.json) no está en $HF_HOME"; cierre; }
export HF_HUB_OFFLINE=1
if [ "$LOCAL" = 1 ]; then
  cp -r "${CHISPA_JEV_LOCAL:-$REPO/model/evaluacion/tests/fixtures/jevbench}" "$JEV"
else
  git clone -q https://github.com/fstandhartinger/jevbench "$JEV" && { [ -z "${CHISPA_JEV_REF:-}" ] || git -C "$JEV" checkout -q "$CHISPA_JEV_REF"; } \
    || { fallo "git clone de JevBench"; cierre; }
fi
{ git -C "$JEV" rev-parse HEAD 2>/dev/null || echo "fixture"; } > "$RES/jevbench-sha.txt"
cat "$RES/jevbench-sha.txt"; wc -l "$JEV"/datasets/public/*.jsonl

# --- 3. L2 zero-shot y con soporte -------------------------------------------------------------------------------------------------
echo "== 3. L2 k=0,8,32 $(date -u +%T)"
"$PY" -u -m model.evaluacion.jevbench_l2 --ckpt "$BASE/mejor.pt" --jevbench "$JEV" --salida "$RES" --k 0 8 32 --device cpu \
  || { fallo "jevbench_l2"; cierre; }

# --- 4. cascada de chispa train (sin --conjunta) servida por chispa-server -tags ort ----------------------------------------
echo "== 4. tokenizador y servidor $(date -u +%T)"
TOK=$MODELOS/e5.chispa-tok
"$PY" -I "$REPO/runtime/tok/exportar.py" "$E5" "$TOK" || { fallo "exportar tokenizador"; cierre; }
cd "$REPO/server" || { fallo "sin server/"; cierre; }
if [ "$LOCAL" = 1 ]; then
  go build -o "$BASE/chispa-server" ./cmd/chispa-server || { fallo "go build chispa-server"; cierre; }
else
  export CGO_ENABLED=1 LD_LIBRARY_PATH=/opt/ort/lib
  go get github.com/yalue/onnxruntime_go@$ORT_GO_VERSION && go build -tags ort \
    -ldflags "-X github.com/juan52878911/chispa/server/decide.RutaORT=/opt/ort/lib/libonnxruntime.so.${ORT_VERSION}" \
    -o "$BASE/chispa-server" ./cmd/chispa-server || { fallo "go build -tags ort chispa-server"; cierre; }
fi
cd "$REPO" || cierre
CAS=(--jevbench "$JEV" --salida "$RES" --ckpt "$BASE/mejor.pt" --servidor "$BASE/chispa-server" --tok "$TOK" --repo "$REPO" --puerto $PUERTO --k 8 32)
if [ -n "${CHISPA_PLIEGUES:-}" ]; then CAS+=(--max-pliegues "$CHISPA_PLIEGUES"); fi
MIN=$(( $(quedan_min) - 8 )); MIN=${CHISPA_CASCADA_MIN:-$MIN}   # 8 min de reserva para el informe y la subida
[ "$MIN" -lt 3 ] && MIN=3
CAS+=(--minutos "$MIN")
echo "== 4. cascada $(date -u +%T): tope de $MIN min"
"$PY" -u -m model.evaluacion.jevbench_cascada "${CAS[@]}" || fallo "jevbench_cascada"

# --- 5. informe ------------------------------------------------------------------------------------------------------------------------
echo "== 5. informe $(date -u +%T)"
"$PY" -m model.evaluacion.jevbench_informe "$RES" || fallo "informe"
cierre
