#!/bin/bash
CHISPA_S3=__CHISPA_S3__
# user-data (≤ 16 KB) de una c6a.2xlarge spot (Amazon Linux 2023, x86_64, 8 vCPU, 16 GB, sin GPU), root, con internet y rol con s3:GetObject y
# s3:PutObject (sin List), sin SSH. P2b: variantes del perfil móvil (consulta y torre) frente a PyTorch con el checkpoint real de G.8 corrida 2.
# El orquestador sustituye __CHISPA_S3__ y sube UN paquete de la rama: bash model/bench/torre/empaquetar.sh <sha> model > codigo.tgz
# (con las rutas por defecto de empaquetar.sh no vale: aquí solo hace falta «model»).
# Variantes (CHISPA_VARIANTES, por defecto «dinamico ffn-estatico fp16 fp32»), cada una con vocabulario completo y con la poda ampliada con el corpus:
#   dinamico      int8 dinámico por canal en MatMul y embeddings (consulta con las ranuras en fp32; torre con la Torre en fp32): lo de P5
#   ffn-estatico  QDQ estático por canal solo en los MatMul de las FFN y la tabla de embeddings; atención y LayerNorm en fp32
#   fp16          todo en fp16, salidas en fp32 (onnxruntime.transformers.float16)
#   fp32          referencia
# Por variante: MB de consulta y torre, coseno de h y de S, top-1 de choice (300 filas), latencia p50/p99 con 1 hilo y % de <unk> sobre el conjunto de
# comprobación (massive-es test y JevBench, quitados de lo que amplía la poda). Resultado: informe.md (marca las que cumplen top-1 ≥ 0,93 y ≤ 60 MB).
# Opcionales: CHISPA_CKPT_S3 (por defecto el de G.8 corrida 2, max_tok 256 dentro del checkpoint), CHISPA_JEV_REF, CHISPA_N_CALIB (500), CHISPA_FILAS (300).
# Pasos: 1 Python+torch CPU · 2 paquete, checkpoint, e5, JevBench y los datos de la poda (cada fichero por separado) · 3 corpus_poda · 4 movil medir · 5 sube
# resultados.tgz y log.txt y apaga. Apagado forzoso a los 60 min (shutdown -h +60). Coste: c6a.2xlarge spot ≈ 0,06 USD/h → < 0,10 USD.
# CHISPA_LOCAL=1: prueba en seco sin dnf, pip ni shutdown, con pesos aleatorios, fixtures de datos y de JevBench; sin red.
CKPT_S3=${CHISPA_CKPT_S3:-s3://chispa-pruebas-879381269751/general-20261029b/ckpt/mejor.pt}
LOCAL=${CHISPA_LOCAL:-0}
AQUI=$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)   # solo para la prueba en seco
if [ "$LOCAL" = 1 ]; then [ "${CHISPA_S3#__}" != "$CHISPA_S3" ] && CHISPA_S3=s3://local/movil; else shutdown -h +60; fi
set -uo pipefail
export HOME="${HOME:-/root}"
T0=$(date +%s)
if [ "$LOCAL" = 1 ]; then BASE=${CHISPA_BASE:-/tmp/chispa-movil}; else BASE=/opt/chispa; fi
mkdir -p "$BASE"
exec > >(tee -a "$BASE/log.txt") 2>&1
echo "== arranque movil $(date -u +%FT%TZ) local=$LOCAL base=$BASE"
REPO=$BASE/repo RES=$BASE/resultados JEV=$BASE/jevbench CORPUS=$BASE/corpus
FALLO=""

s3cp() {   # un fichero (el rol no lista el bucket)
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
  [ -f "$RES/movil.json" ] && "$PY" -I -c "import sys; sys.path.insert(0, sys.argv[1]); from model.bench.torre.movil import informe; informe(sys.argv[2])" "$REPO" "$RES" >/dev/null 2>&1
  cp "$BASE/log.txt" "$RES/log.txt" 2>/dev/null
  rm -f "$BASE/resultados.tgz"
  ( cd "$BASE" && find resultados -type f -not -name '*.onnx' -size -50000k | LC_ALL=C sort > "$BASE/resultados.lista" \
      && tar -czf "$BASE/resultados.tgz" -T "$BASE/resultados.lista" ) || echo "no se pudo crear resultados.tgz"
  [ -f "$BASE/resultados.tgz" ] && { s3cp "$BASE/resultados.tgz" "$CHISPA_S3/resultados.tgz" || echo "no se pudo subir resultados.tgz"; }
  s3cp "$BASE/log.txt" "$CHISPA_S3/log.txt" || echo "no se pudo subir log.txt"
  [ "$LOCAL" = 1 ] || shutdown -h now
}
PY=${CHISPA_PY:-$HOME/venv/bin/python}
trap subir_y_apagar EXIT
trap 'exit 143' TERM INT HUP
mkdir -p "$RES"
fallo() { echo "FALLO: $*"; FALLO="${FALLO:+$FALLO; }$*"; }
cierre() { echo "== listo $(date -u +%FT%TZ) fallo=${FALLO:-no} ($(( $(date +%s) - T0 )) s)"; exit 0; }

# --- 1. entorno ---------------------------------------------------------------------------------------------------------------
export HF_HOME="${HF_HOME:-$HOME/hf}"; mkdir -p "$HF_HOME"
if [ "$LOCAL" != 1 ]; then
  echo "== 1. entorno $(date -u +%T)"
  dnf install -y -q tar gzip git python3.11 python3.11-pip || { fallo "dnf install"; cierre; }
  python3.11 -m venv "$BASE/venv" || { fallo "venv"; cierre; }
  PY=$BASE/venv/bin/python
  "$PY" -m pip install -q --no-cache-dir -U pip \
    && "$PY" -m pip install -q --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && "$PY" -m pip install -q --no-cache-dir numpy scikit-learn transformers tokenizers huggingface_hub pyyaml pyarrow datasets onnx onnxscript onnxruntime \
    || { fallo "pip install"; cierre; }
fi
"$PY" -c "import sys, numpy, torch, transformers, onnx, onnxruntime; from onnxruntime.transformers.float16 import convert_float_to_float16; print(sys.version.split()[0], 'torch', torch.__version__, 'ort', onnxruntime.__version__)" \
  || { fallo "imports de Python"; cierre; }

# --- 2. paquete, checkpoint, e5, JevBench y datos de la poda ---------------------------------------------------------------------
echo "== 2. código y datos $(date -u +%T)"
if [ "$LOCAL" = 1 ]; then   # en seco lo empaqueta el propio script
  d=/tmp/chispa/s3/${CHISPA_S3#s3://}; mkdir -p "$d"
  bash "$AQUI/empaquetar.sh" HEAD model > "$d/codigo.tgz" || { fallo "empaquetar"; cierre; }
fi
rm -rf "$REPO" "$JEV" "$CORPUS"; mkdir -p "$REPO"
for _ in $(seq 1 90); do   # un paquete a medias no se acepta: hasta 45 min de reintentos (el orquestador lo sube tras lanzar)
  s3cp "$CHISPA_S3/codigo.tgz" "$BASE/codigo.tgz" 2>/dev/null && tar -tzf "$BASE/codigo.tgz" >/dev/null 2>&1 && break
  rm -f "$BASE/codigo.tgz"; [ "$LOCAL" = 1 ] && break; sleep 30
done
tar -xzf "$BASE/codigo.tgz" -C "$REPO" || { fallo "no llegó un codigo.tgz válido"; cierre; }
cd "$REPO" || { fallo "sin repo"; cierre; }
export PYTHONPATH=$REPO
{ lscpu; echo "nproc: $(nproc)"; free -m 2>/dev/null; } > "$RES/hardware.txt" 2>&1

CKPT=$BASE/mejor.pt
if [ "$LOCAL" = 1 ]; then CKPT_ARG=(--ckpt-aleatorio); else
  s3cp "$CKPT_S3" "$CKPT" || { fallo "no se pudo bajar el checkpoint $CKPT_S3"; cierre; }
  ls -l "$CKPT"; CKPT_ARG=(--ckpt "$CKPT")
fi
descarga() {   # descarga(repo, tipo, fichero…): un fichero cada vez, para que un fallo diga cuál
  local repo=$1 tipo=$2; shift 2
  for f in "$@"; do
    "$PY" -I -c 'import sys; from huggingface_hub import hf_hub_download as d; d(sys.argv[1], sys.argv[3], repo_type=sys.argv[2])' "$repo" "$tipo" "$f" \
      || { fallo "descarga de $repo/$f"; return 1; }
  done
}
# repos de los conversores de model.datos (lista de model/datos/*.py); uno a uno, y el que falte lo salta corpus_poda (queda en corpus-resumen.json)
DATASETS="mteb/amazon_massive_intent Paul/hatecheck-spanish facebook/xnli SINAI/ALIA-es-discriminative-hate-speech mrm8488/go_emotions-es-mt
  tanaos/synthetic-spam-detection-dataset-spanish tasksource/it-support-tickets somosnlp/spa_climate_detection bgonzalezbustamante/toxicity-protests-ES
  bgonzalezbustamante/toxicity-Constitution-ES FelipeGuerra/Colombian_Spanish_Cyberbullying_Dataset_1 FelipeGuerra/Colombian_Spanish_Cyberbullying_Dataset_2
  somosnlp/suicide-comments-es deepset/prompt-injections"
if [ "$LOCAL" != 1 ]; then
  descarga intfloat/multilingual-e5-small model config.json tokenizer.json tokenizer_config.json special_tokens_map.json sentencepiece.bpe.model model.safetensors || cierre
  for d in $DATASETS; do
    "$PY" -I -c 'import sys; from huggingface_hub import snapshot_download as s; s(sys.argv[1], repo_type="dataset")' "$d" || echo "AVISO: sin $d (se omite esa fuente)"
  done
fi
export HF_HUB_OFFLINE=1
if [ "$LOCAL" = 1 ]; then cp -r "${CHISPA_JEV_LOCAL:-$REPO/model/evaluacion/tests/fixtures/jevbench}" "$JEV" || { fallo "sin JevBench local"; cierre; }
else
  git clone -q https://github.com/fstandhartinger/jevbench "$JEV" && { [ -z "${CHISPA_JEV_REF:-}" ] || git -C "$JEV" checkout -q "$CHISPA_JEV_REF"; } \
    || { fallo "git clone de JevBench"; cierre; }
fi
{ git -C "$JEV" rev-parse HEAD 2>/dev/null || echo fixture; } > "$RES/jevbench-sha.txt"

# --- 3. corpus de la poda y conjunto de comprobación -------------------------------------------------------------------------------
echo "== 3. corpus_poda $(date -u +%T)"
FIX=(); [ "$LOCAL" = 1 ] && FIX=(--fixtures)
"$PY" -u -m model.bench.torre.corpus_poda "$CORPUS" "${FIX[@]}" --jevbench "$JEV" > "$RES/corpus_poda.log" 2>&1 || { tail -20 "$RES/corpus_poda.log"; fallo "corpus_poda"; cierre; }
cp "$CORPUS/resumen.json" "$RES/corpus-resumen.json"; tail -3 "$RES/corpus_poda.log"
"$PY" -m model.bench.torre.datos_g7 calib "$RES/calib-torre.jsonl" | tail -1

# --- 4. variantes ---------------------------------------------------------------------------------------------------------------------
echo "== 4. medir $(date -u +%T)"
VARIANTES=${CHISPA_VARIANTES:-dinamico ffn-estatico fp16 fp32}
VOCABS="completo ampliado"; [ "$LOCAL" = 1 ] && VOCABS=ampliado   # el vocabulario completo en fp32 no cabe en los 4 GB de la prueba en seco
"$PY" -u -m model.bench.torre.movil medir "$RES" "${CKPT_ARG[@]}" --ampliar "$CORPUS/ampliar" --comprobacion "$CORPUS/comprobacion" \
  --calib "$RES/calib-torre.jsonl" --variantes $VARIANTES --vocabularios $VOCABS --n-calib "${CHISPA_N_CALIB:-500}" --filas "${CHISPA_FILAS:-300}" > "$RES/movil.log" 2>&1 \
  || { tail -30 "$RES/movil.log"; fallo "movil medir (ver movil.log; movil.json lleva lo medido hasta el fallo)"; }
[ -f "$RES/informe.md" ] && cat "$RES/informe.md"
cierre
