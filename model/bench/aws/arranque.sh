#!/bin/bash
CHISPA_S3=__CHISPA_S3__
# user-data de una Amazon Linux 2023 x86_64 recién creada (root): mide la latencia de los codificadores de la
# fase 0 (model/bench/codificadores.py) y deja /opt/chispa/resultados.tgz y /opt/chispa/LISTO.
# El orquestador sustituye __CHISPA_S3__ por un prefijo s3://bucket/ruta y sube ahí codigo.tgz
# (bash model/bench/aws/empaquetar.sh); la instancia (rol con s3:GetObject y s3:PutObject, sin SSH) lo baja, y al
# terminar sube log.txt y resultados.tgz al mismo prefijo y se apaga.
# CHISPA_LOCAL=1: prueba en seco en kindling (sin dnf, pip, descargas ni shutdown; ~/venv, ~/hf, /tmp/chispa);
# el "s3" es el directorio /tmp/chispa/s3/<prefijo sin s3://> y se copia con cp en vez de aws s3 cp.
[ "${CHISPA_LOCAL:-}" = 1 ] || shutdown -h +170   # apagado forzoso: la instancia se termina al apagarse
set -uo pipefail
export HOME="${HOME:-/root}"

if [ "${CHISPA_LOCAL:-}" = 1 ]; then
  BASE=/tmp/chispa; VENV="$HOME/venv"; export HF_HOME="$HOME/hf"; export CHISPA_REPS=20
else
  BASE=/opt/chispa; VENV=$BASE/venv; export HF_HOME=$BASE/hf; export CHISPA_REPS=200
fi
mkdir -p "$BASE"
exec > >(tee -a "$BASE/log.txt") 2>&1
echo "== arranque $(date -u +%FT%TZ) local=${CHISPA_LOCAL:-0} base=$BASE"

REPO=$BASE/repo RES=$BASE/resultados
export CHISPA_WORK=$BASE/work CHISPA_SALIDA=$RES/resultados-x86.md
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

# Al salir, bien o mal: sube el log y, si existe, resultados.tgz; después apaga (salvo en local).
subir_y_apagar() {
  trap - EXIT
  sleep 1   # deja que tee vacíe el log
  s3cp "$BASE/log.txt" "$CHISPA_S3/log.txt" || echo "no se pudo subir log.txt"
  [ -f "$BASE/resultados.tgz" ] && { s3cp "$BASE/resultados.tgz" "$CHISPA_S3/resultados.tgz" || echo "no se pudo subir resultados.tgz"; }
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
  tar -C "$BASE" -czf "$BASE/resultados.tgz" resultados
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
    --extra-index-url https://pypi.org/simple torch transformers onnx onnxruntime huggingface_hub model2vec numpy || return 1
}
bajar() {
  "$PY" -I - <<'PYEOF' || return 1
import glob, os
from huggingface_hub import snapshot_download as s
sin_red = ["*.json", "*.safetensors", "*.txt", "*.model", "tokenizer*"]
for m in ("intfloat/multilingual-e5-small", "jhu-clsp/mmBERT-small", "minishlab/potion-multilingual-128M"):
    d = s(m, allow_patterns=sin_red)
    if not glob.glob(d + "/*.safetensors"):  # mmBERT-small solo publica pytorch_model.bin
        s(m, allow_patterns=["pytorch_model.bin"])
    assert glob.glob(d + "/*.safetensors") or os.path.exists(d + "/pytorch_model.bin"), "sin pesos: " + m
    print("modelo", m, os.listdir(d))
# datos de la poda y de la comprobación de coseno (codificadores.py preparar)
s("mteb/amazon_massive_intent", repo_type="dataset", allow_patterns=[
  "test/es.json.gz", "test/en.json.gz", "test/pt.json.gz", "train/es.json.gz", "validation/es.json.gz", "*.md"])
s("Paul/hatecheck-spanish", repo_type="dataset", allow_patterns=["*.csv", "*.md"])
PYEOF
}

if [ "${CHISPA_LOCAL:-}" != 1 ]; then
  instalar || { fallo "dnf/venv/pip"; cierre; }
  bajar || { fallo "descarga de modelos o datos de Hugging Face"; cierre; }
fi
"$PY" -c "import torch; assert not torch.version.cuda, 'torch con CUDA: ' + str(torch.version.cuda); print('torch', torch.__version__, 'sin CUDA')" \
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

# --- hardware -------------------------------------------------------------------------------------------------
mkdir -p "$RES"
{ lscpu; echo; echo "nproc: $(nproc)"; } > "$RES/hardware.txt"
lscpu > "$RES/lscpu.txt"; nproc > "$RES/nproc.txt"
grep -m1 '^flags' /proc/cpuinfo | tr ' ' '\n' | grep -E '^(avx|fma|amx)' | sort -u | tr '\n' ' ' > "$RES/banderas_avx.txt"
echo "banderas AVX: $(cat "$RES/banderas_avx.txt")"
"$VENV/bin/pip" freeze 2>/dev/null | grep -iE '^(torch|transformers|onnx|onnxruntime|model2vec|numpy|huggingface)' > "$RES/versiones.txt"
if [ "${CHISPA_LOCAL:-}" != 1 ]; then   # tipo de instancia (IMDSv2); si falla, no pasa nada
  t=$(curl -sf -m 3 -X PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 60') &&
    curl -sf -m 3 -H "X-aws-ec2-metadata-token: $t" http://169.254.169.254/latest/meta-data/instance-type > "$RES/instance-type.txt"
fi
cat "$RES/hardware.txt" | grep -E 'Model name|^CPU\(s\)|nproc'
df -h "$BASE" | tail -1

# --- medición -------------------------------------------------------------------------------------------------
# preparar es idempotente (salta lo ya exportado); medir reintenta cada variante 2 veces y apunta los errores.
cd "$REPO/model/bench" || { fallo "no existe model/bench en codigo.tgz"; cierre; }
for paso in preparar medir informe; do
  echo "== $paso $(date -u +%T)"
  "$PY" -I codificadores.py "$paso" || { fallo "codificadores.py $paso"; [ "$paso" = informe ] || break; }
done
cp "$CHISPA_WORK/medidas.jsonl" "$RES/" 2>/dev/null || fallo "sin medidas.jsonl"
cp "$REPO"/model/bench/coseno-poda.json "$REPO"/model/bench/vocab-podado-*.json "$RES/" 2>/dev/null
grep -c '"error"' "$RES/medidas.jsonl" 2>/dev/null | sed 's/^/variantes con error: /'
cierre
