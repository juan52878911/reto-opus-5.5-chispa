#!/bin/bash
CHISPA_S3=__CHISPA_S3__
# user-data de una c6a.xlarge spot (Amazon Linux 2023, x86_64, 4 vCPU, sin GPU), root, con internet y rol con s3:GetObject y
# s3:PutObject (sin List) y sin SSH: T4.6, abstención de la cascada con tráfico no adversarial (test limpio completo).
# El orquestador sustituye __CHISPA_S3__ y sube $CHISPA_S3/codigo.tgz (bash server/deploy/arena/empaquetar.sh > codigo.tgz: ya lleva
# server/, así que este script y medir.py van dentro). Opcionales: CHISPA_CKPT_S3 (el de e2e.sh), CHISPA_MAX (filas de test por
# tarea; 0 = todas), CHISPA_EXPORT_ARGS (como en e2e.sh), CHISPA_TAREAS (massive,clinc150,spam,injection).
# En la instancia (pasos de e2e.sh y arena/aws.sh, recortados): 1. Go, Python y ORT; 2. código, checkpoint (FICHERO A FICHERO), e5,
# massive y clinc150; 3. `arena dataset` (su split test no lleva ataques: estos salen luego, en `arena run`); 4. tokenizador, L2 a ONNX
# int8 (dev = dev de las 4 tareas) y `chispa train --conjunta` por tarea; 5. chispa-server -tags ort en modo cascada (sin -config:
# τ de CALIB) y el test limpio entero por /v1/decide; 6. medir.py. Al salir (trap) sube log.txt y resultados.tgz y apaga (a los 75 min).
# CHISPA_LOCAL=1: prueba en seco en kindling: sin dnf, pip, descargas, ORT ni shutdown; ~/venv, ~/go-sdk, ~/hf y /tmp/chispa-abst;
# fixtures, checkpoint sin entrenar y servidor sin la etiqueta ort (L2 en stub). El "s3" es /tmp/chispa/s3/<prefijo sin s3://>.
CKPT_S3=${CHISPA_CKPT_S3:-s3://chispa-pruebas-879381269751/l2-20261028b/ckpt/mejor.pt}
TAREAS=${CHISPA_TAREAS:-massive,clinc150,spam,injection}
MAX_FILAS=${CHISPA_MAX:-0}
if [ "${CHISPA_LOCAL:-}" = 1 ]; then
  [ "${CHISPA_S3#__}" != "$CHISPA_S3" ] && CHISPA_S3=s3://local/abst
  MAX_FILAS=${CHISPA_MAX:-40}
  TAREAS=${CHISPA_TAREAS:-clinc150,spam,injection}   # el fixture de massive (5 ejemplos) no da para `chispa train --conjunta`
else
  shutdown -h +75   # apagado forzoso: la instancia se termina al apagarse
fi
set -uo pipefail
export HOME="${HOME:-/root}"
T0=$(date +%s)
GO_VERSION=1.27.1; ORT_VERSION=1.22.0; ORT_GO_VERSION=v1.19.0
PUERTO=8093
if [ "${CHISPA_LOCAL:-}" = 1 ]; then BASE=/tmp/chispa-abst; else BASE=/opt/chispa; fi
mkdir -p "$BASE"
exec > >(tee -a "$BASE/log.txt") 2>&1
echo "== arranque abstención $(date -u +%FT%TZ) local=${CHISPA_LOCAL:-0} base=$BASE tareas=$TAREAS max=$MAX_FILAS"
REPO=$BASE/repo MODELOS=$BASE/modelos RES=$BASE/resultados DATOS=$BASE/datos ADATA=$BASE/arena-data
FALLO="" SRVPID=""

s3cp() {   # un fichero (el rol no lista el bucket: nada de --recursive ni sync)
  if [ "${CHISPA_LOCAL:-}" = 1 ]; then
    local o=$1 d=$2
    case $o in s3://*) o=/tmp/chispa/s3/${o#s3://};; esac
    case $d in s3://*) d=/tmp/chispa/s3/${d#s3://}; mkdir -p "$(dirname "$d")";; esac
    cp "$o" "$d"
  else aws s3 cp --only-show-errors "$1" "$2"
  fi
}
parar_servidor() { [ -n "$SRVPID" ] && { kill "$SRVPID" 2>/dev/null; wait "$SRVPID" 2>/dev/null; }; SRVPID=""; return 0; }
subir_y_apagar() {
  trap - EXIT
  parar_servidor
  sleep 1   # deja que tee vacíe el log
  mkdir -p "$RES"
  [ -n "$FALLO" ] && echo "$FALLO" > "$RES/FALLO"
  cp "$BASE/log.txt" "$RES/log.txt" 2>/dev/null
  rm -f "$BASE/resultados.tgz"   # find y tar portables: lista de rutas relativas a $BASE, sin -C junto a -T. Nada de modelos.
  ( cd "$BASE" && find resultados -type f -not -name '*.chispa' -not -name '*.onnx' -not -name '*.chispa-tok' -size -50000k \
      | LC_ALL=C sort > "$BASE/resultados.lista" && tar -czf "$BASE/resultados.tgz" -T "$BASE/resultados.lista" ) || echo "no se pudo crear resultados.tgz"
  [ -f "$BASE/resultados.tgz" ] && { s3cp "$BASE/resultados.tgz" "$CHISPA_S3/resultados.tgz" || echo "no se pudo subir resultados.tgz"; }
  s3cp "$BASE/log.txt" "$CHISPA_S3/log.txt" || echo "no se pudo subir log.txt"
  [ "${CHISPA_LOCAL:-}" = 1 ] || shutdown -h now
}
trap subir_y_apagar EXIT
trap 'exit 143' TERM INT HUP
fallo() { echo "FALLO: $*"; FALLO="${FALLO:+$FALLO; }$*"; }
cierre() { df -h "$BASE" | tail -1; echo "== listo $(date -u +%FT%TZ) fallo=${FALLO:-no} ($(( $(date +%s) - T0 )) s)"; exit 0; }
quedan_min() { echo $(( 75 - ($(date +%s) - T0) / 60 )); }

# --- 1. entorno -----------------------------------------------------------------------------------------------------------------
export HF_HOME="$HOME/hf"
mkdir -p "$HF_HOME"
if [ "${CHISPA_LOCAL:-}" = 1 ]; then
  PY=$HOME/venv/bin/python
  export PATH="$HOME/go-sdk/bin:$PATH" ATEN_CPU_CAPABILITY=default   # la microVM de kindling a veces da «Illegal instruction» con los kernels AVX de torch
else
  echo "== 1. entorno $(date -u +%T)"
  dnf install -y -q gcc tar gzip python3.11 python3.11-pip || { fallo "dnf install"; cierre; }
  curl -fsSL "https://go.dev/dl/go${GO_VERSION}.linux-amd64.tar.gz" | tar -xzC /usr/local || { fallo "descarga de Go"; cierre; }
  export PATH=/usr/local/go/bin:$PATH
  mkdir -p /opt/ort && curl -fsSL "https://github.com/microsoft/onnxruntime/releases/download/v${ORT_VERSION}/onnxruntime-linux-x64-${ORT_VERSION}.tgz" \
    | tar -xzC /opt/ort --strip-components=1 || { fallo "descarga de ORT $ORT_VERSION"; cierre; }
  python3.11 -m venv "$BASE/venv" || { fallo "venv"; cierre; }
  PY=$BASE/venv/bin/python
  "$PY" -m pip install -q --no-cache-dir -U pip \
    && "$PY" -m pip install -q --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && "$PY" -m pip install -q --no-cache-dir numpy scikit-learn transformers tokenizers huggingface_hub pyyaml pyarrow datasets \
         onnx onnxscript onnxruntime \
    || { fallo "pip install"; cierre; }
fi
go version
"$PY" -c "import sys, numpy, sklearn, torch, transformers, onnxruntime; print(sys.version.split()[0], 'torch', torch.__version__, 'onnxruntime', onnxruntime.__version__)" \
  || { fallo "imports de Python"; cierre; }
export GOTOOLCHAIN=local GOFLAGS=-mod=mod GONOSUMDB='github.com/juan52878911/*'

# --- 2. código, checkpoint y datos ----------------------------------------------------------------------------------------------
echo "== 2. código y datos $(date -u +%T)"
if [ "${CHISPA_LOCAL:-}" = 1 ] && [ ! -f "/tmp/chispa/s3/${CHISPA_S3#s3://}/codigo.tgz" ]; then   # prueba en seco: lo empaqueta el propio script
  mkdir -p "/tmp/chispa/s3/${CHISPA_S3#s3://}"
  bash "$(dirname "${BASH_SOURCE[0]}")/../arena/empaquetar.sh" --fixtures > "/tmp/chispa/s3/${CHISPA_S3#s3://}/codigo.tgz" \
    || { fallo "empaquetar.sh"; cierre; }
fi
for _ in $(seq 1 90); do   # 90 × 30 s = 45 min
  s3cp "$CHISPA_S3/codigo.tgz" "$BASE/codigo.tgz" 2>/dev/null && tar -tzf "$BASE/codigo.tgz" >/dev/null 2>&1 && break
  rm -f "$BASE/codigo.tgz"
  [ "${CHISPA_LOCAL:-}" = 1 ] && break
  sleep 30
done
rm -rf "$REPO" "$MODELOS" "$RES" "$DATOS" "$ADATA" "$BASE/prep"
mkdir -p "$REPO" "$MODELOS" "$RES" "$DATOS" "$ADATA" "$BASE/prep"
tar -xzf "$BASE/codigo.tgz" -C "$REPO" || { fallo "no llegó un codigo.tgz válido"; cierre; }
cd "$REPO" || { fallo "sin repo"; cierre; }
export PYTHONPATH=$REPO:$REPO/sdk/python
AU=$REPO/server/deploy/arena EU=$REPO/server/deploy/aws/e2e_util.py
[ -f "$REPO/server/deploy/abstencion/medir.py" ] || { fallo "codigo.tgz sin server/deploy/abstencion/medir.py"; cierre; }
if [ "${CHISPA_LOCAL:-}" = 1 ]; then export GOPROXY=off; else export GOPROXY=file://$REPO/gomod-proxy,https://proxy.golang.org; fi

if [ "${CHISPA_LOCAL:-}" = 1 ] && [ ! -f "/tmp/chispa/s3/${CKPT_S3#s3://}" ]; then
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

bajar() {
  "$PY" -I - <<'PYEOF' || return 1
from huggingface_hub import snapshot_download as s
fallos = []
def intenta(*a, **k):
    try:
        s(*a, **k)
    except Exception as e:
        fallos.append("%s: %s" % (a[0], type(e).__name__)); print("aviso: no se pudo bajar", a[0], e)
intenta("intfloat/multilingual-e5-small", allow_patterns=["*.json", "*.safetensors", "*.txt", "*.model", "tokenizer*"])
intenta("mteb/amazon_massive_intent", repo_type="dataset", allow_patterns=["*es*", "*.json", "*.md", "*.csv"])
intenta("clinc/clinc_oos", repo_type="dataset")
print("descargas con fallo:", fallos or "ninguna")
raise SystemExit(1 if fallos else 0)
PYEOF
}
if [ "${CHISPA_LOCAL:-}" != 1 ]; then bajar || fallo "descarga de modelo o datasets"; fi
E5=$(ls -d "$HF_HOME"/hub/models--intfloat--multilingual-e5-small/snapshots/*/ 2>/dev/null | head -1)
[ -f "${E5}tokenizer.json" ] || { fallo "e5 (con tokenizer.json) no está en $HF_HOME"; cierre; }
export HF_HUB_OFFLINE=1   # a partir de aquí todo sale de $HF_HOME

# --- 3. datos: massive y clinc150 (e2e) y spam e injection (Arena, split test sin ataques) ----------------------------------------
echo "== 3. datos $(date -u +%T)"
CONV=(--salida "$DATOS" --fuentes massive,clinc150); [ "${CHISPA_LOCAL:-}" = 1 ] && CONV+=(--fixtures)
"$PY" -m model.datos.convertir "${CONV[@]}" || { fallo "convertir"; cierre; }
PREPARAR=(--datos "$DATOS" --salida "$BASE/prep/e2e" --tareas massive,clinc150); [ "${CHISPA_LOCAL:-}" = 1 ] && PREPARAR+=(--recortar)
"$PY" -I "$EU" preparar "${PREPARAR[@]}" || { fallo "preparar massive y clinc150"; cierre; }
( cd "$REPO/arena" && go build -o "$BASE/arena" ./cmd/arena && "$BASE/arena" dataset -out "$ADATA" | tail -3 ) || { fallo "arena dataset"; cierre; }
"$PY" -I "$AU/arena_util.py" preparar --datos "$ADATA" --salida "$BASE/prep/arena" --dims spam,injection || { fallo "preparar spam e injection"; cierre; }
cat "$BASE/prep/e2e/dev.jsonl" "$BASE/prep/arena/dev.jsonl" > "$BASE/prep/dev.jsonl"
dir_de() { case $1 in spam|injection) echo "$BASE/prep/arena/$1";; *) echo "$BASE/prep/e2e/$1";; esac; }

# --- 4. tokenizador de e5, L2 a ONNX int8 y chispa train --conjunta -------------------------------------------------------------------
echo "== 4. tokenizador y L2 $(date -u +%T)"
TOK=$MODELOS/e5.chispa-tok L2CH=$MODELOS/l2.chispa
mkdir -p "$MODELOS/onnx"
"$PY" -I "$REPO/runtime/tok/exportar.py" "$E5" "$TOK" || { fallo "exportar tokenizador"; cierre; }
"$PY" -u -m model.l2.calibrar --ckpt "$BASE/mejor.pt" --dev "$BASE/prep/dev.jsonl" --salida "$MODELOS/calib.json" --device cpu \
  || { fallo "calibrar"; cierre; }
"$PY" -u -m model.l2.exportar --ckpt "$BASE/mejor.pt" --calib "$MODELOS/calib.json" --esquemas "$BASE/prep/dev.jsonl" \
  --paridad "$BASE/prep/dev.jsonl" --n-paridad 300 --salida "$L2CH" --trabajo "$MODELOS/onnx" ${CHISPA_EXPORT_ARGS:-} || { fallo "exportar L2"; cierre; }
cp "$L2CH.informe.json" "$RES/exportar.informe.json" 2>/dev/null
for t in ${TAREAS//,/ }; do
  d=$(dir_de "$t")
  echo "== 4. chispa train --conjunta $t $(date -u +%T) (quedan $(quedan_min) min)"
  # T4.6c: el τ de L2c sale de validación. e2e: el dev de la tarea (convertir); Arena: un 20 % reservado del train.
  case $t in spam|injection) DEVARG=();; *) DEVARG=(--dev "$BASE/prep/dev.jsonl");; esac
  "$PY" -I "$REPO/server/deploy/abstencion/validacion.py" --dir "$d" --esquema "$d/esquema.json" "${DEVARG[@]}" | tee "$RES/validacion-$t.txt" \
    || fallo "validacion.py $t"
  EJ=$d/ejemplos.jsonl; [ -f "$d/ejemplos-entrenar.jsonl" ] && EJ=$d/ejemplos-entrenar.jsonl
  VAL=(); [ -s "$d/validacion.jsonl" ] && VAL=(--validacion "$d/validacion.jsonl")
  "$PY" -u -m chispa train --ejemplos "$EJ" --esquema "$d/esquema.json" --salida "$MODELOS/$t.chispa" \
    --ckpt "$BASE/mejor.pt" --l2 "$L2CH" --conjunta --repo "$REPO" "${VAL[@]}" 2>&1 | tail -15 | tee "$RES/train-$t.txt"
  [ "${PIPESTATUS[0]}" = 0 ] && [ -f "$MODELOS/$t.chispa" ] || fallo "chispa train $t"
done

# --- 5. servidor en cascada (τ de CALIB) y el test limpio por /v1/decide ----------------------------------------------------------
echo "== 5. compilar chispa-server $(date -u +%T)"
cd "$REPO/server" || { fallo "sin server/"; cierre; }
if [ "${CHISPA_LOCAL:-}" = 1 ]; then
  go build -o "$BASE/chispa-server" ./cmd/chispa-server || { fallo "go build chispa-server"; cierre; }
else
  export CGO_ENABLED=1 LD_LIBRARY_PATH=/opt/ort/lib
  go get github.com/yalue/onnxruntime_go@$ORT_GO_VERSION && go vet -tags ort ./decide \
    && go build -tags ort -ldflags "-X github.com/juan52878911/chispa/server/decide.RutaORT=/opt/ort/lib/libonnxruntime.so.${ORT_VERSION}" \
         -o "$BASE/chispa-server" ./cmd/chispa-server || { fallo "go build -tags ort chispa-server"; cierre; }
fi
MEDIR=()
servir() {   # servir TAREA: sin -config, así los τ salen de CALIB (tauDeCalib); manda el test entero y para
  local t=$1 o=$RES/$1 test
  test=$(dir_de "$t")/test.jsonl
  mkdir -p "$o"
  "$BASE/chispa-server" -addr 127.0.0.1:$PUERTO -modelo "$MODELOS/$t.chispa" -tok "$TOK" > "$o/servidor.log" 2>&1 &
  SRVPID=$!
  local listo=0
  for _ in $(seq 1 120); do curl -sf -m 2 http://127.0.0.1:$PUERTO/healthz >/dev/null && { listo=1; break; }; sleep 1; done
  [ $listo = 1 ] || { fallo "el servidor ($t) no responde en /healthz"; parar_servidor; return; }
  if grep -q 'L2 queda como stub' "$o/servidor.log"; then
    if [ "${CHISPA_LOCAL:-}" = 1 ]; then echo "(prueba en seco: L2 en stub, como se esperaba sin ORT)"; else fallo "$t: L2 quedó en stub con ORT"; fi
  fi
  "$PY" -I "$EU" cliente --url http://127.0.0.1:$PUERTO --test "$test" --salida "$o/pred.jsonl" --max "$MAX_FILAS" || fallo "$t: errores del cliente"
  curl -sf http://127.0.0.1:$PUERTO/metrics > "$o/metrics.txt"
  parar_servidor
  [ -s "$o/pred.jsonl" ] && MEDIR+=(--pred "$t=$o/pred.jsonl" --verdad "$t=$test")
}
for t in ${TAREAS//,/ }; do
  [ -f "$MODELOS/$t.chispa" ] || continue
  if [ "$(quedan_min)" -lt 6 ]; then fallo "$t: sin tiempo (quedan $(quedan_min) min)"; continue; fi
  echo "== 5. /v1/decide $t $(date -u +%T) (quedan $(quedan_min) min)"
  servir "$t"
done

# --- 6. medir -----------------------------------------------------------------------------------------------------------------
echo "== 6. medir $(date -u +%T)"
if [ ${#MEDIR[@]} -gt 0 ]; then
  for t in ${TAREAS//,/ }; do   # precisión estimada que anotó `chispa train` (línea «precisión esperada X»)
    est=$(sed -n 's/.*precisión esperada \([0-9.]*\),.*/\1/p' "$RES/train-$t.txt" 2>/dev/null | tail -1)
    [ -n "$est" ] && MEDIR+=(--estimada "$t=$est")
  done
  "$PY" -I "$REPO/server/deploy/abstencion/medir.py" "${MEDIR[@]}" --salida "$RES/abstencion" || fallo "medir.py"
else
  fallo "sin pred.jsonl que medir"
fi
cierre
