#!/bin/bash
CHISPA_S3=__CHISPA_S3__
# user-data de una c6a.xlarge spot (Amazon Linux 2023, x86_64, 4 vCPU, sin GPU), root, con internet y rol con s3:GetObject y
# s3:PutObject (sin List) y sin SSH: T4.5, prueba de punta a punta de L2c en el servidor. El orquestador sustituye
# __CHISPA_S3__ (salida de esta ejecución) y sube $CHISPA_S3/codigo.tgz (bash server/deploy/aws/empaquetar_e2e.sh > codigo.tgz).
# Variables opcionales: CHISPA_CKPT_S3 (por defecto s3://chispa-pruebas-879381269751/l2-20261028b/ckpt/mejor.pt),
# CHISPA_E2E_MAX (filas de test por tarea; 0 = todas), CHISPA_TAREAS (massive,clinc150).
# En la instancia:
#   1. instala Go, Python 3.11 (venv con torch CPU, transformers, onnx, onnxruntime, scikit-learn…) y la .so de ONNX Runtime;
#   2. baja de S3, FICHERO A FICHERO (el rol no lista el bucket), el código y el checkpoint; baja e5 y los datasets públicos
#      (HF) y corre model.datos.convertir;
#   3. exporta el tokenizador de e5 (runtime/tok/exportar.py) y corre sus tests contra transformers, con fuzz;
#   4. calibra y exporta L2 a ONNX int8 con model.l2.exportar (paridad con PyTorch incluida);
#   5. corre `chispa train --conjunta` con el train de cada tarea (L0 de Chispa + CONJ + el L2 del paso 4);
#   6. compila `chispa-server -tags ort` y, por tarea y por modo, lo arranca y le manda el test completo por /v1/decide:
#        · «forzado»: τ(L0) = 1, τ(L1) = 1, τ(L2) = 0: casi todo lo contesta L2c (la comparable con conjunta.py);
#        · «cascada»: los τ de CALIB (lo que serviría de verdad);
#   7. chispa_eval (macro-F1), fracción por capa y p50/p99 por capa y total (server/deploy/aws/e2e_util.py informe);
#   8. compara con model/l2/resultados/t22c-conjunta/resultados.json (conjunta.py, T2.2c): H2 = Δ de macro-F1 ≥ −0,01.
# Al salir (trap: fin normal, error o SIGTERM) sube log.txt y resultados.tgz y apaga; apagado forzoso a los 90 min.
# CHISPA_LOCAL=1: prueba en seco en kindling: sin dnf, pip, descargas, ORT ni shutdown; ~/venv, ~/go-sdk, ~/hf y /tmp/chispa-e2e;
# fixtures de convertir, checkpoint de L2 sin entrenar; el servidor se compila SIN la etiqueta ort (L2 queda en stub, solo
# contesta L0) y las pruebas de L2c con similitudes falsas se corren con `go test`. El "s3" es /tmp/chispa/s3/<prefijo sin s3://>.
CKPT_S3=${CHISPA_CKPT_S3:-s3://chispa-pruebas-879381269751/l2-20261028b/ckpt/mejor.pt}
TAREAS=${CHISPA_TAREAS:-massive,clinc150}
MAX_FILAS=${CHISPA_E2E_MAX:-0}
if [ "${CHISPA_LOCAL:-}" = 1 ]; then
  [ "${CHISPA_S3#__}" != "$CHISPA_S3" ] && CHISPA_S3=s3://local/e2e
else
  shutdown -h +90   # apagado forzoso: la instancia se termina al apagarse
fi
set -uo pipefail
export HOME="${HOME:-/root}"
T0=$(date +%s)

GO_VERSION=1.27.1        # tar de go.dev
ORT_VERSION=1.22.0       # release de microsoft/onnxruntime
ORT_GO_VERSION=v1.19.0   # github.com/yalue/onnxruntime_go (el de la imagen de T4.4, que compiló)
PUERTO=8090

if [ "${CHISPA_LOCAL:-}" = 1 ]; then BASE=/tmp/chispa-e2e; else BASE=/opt/chispa; fi
mkdir -p "$BASE"
exec > >(tee -a "$BASE/log.txt") 2>&1
echo "== arranque e2e $(date -u +%FT%TZ) local=${CHISPA_LOCAL:-0} base=$BASE tareas=$TAREAS max=$MAX_FILAS"

REPO=$BASE/repo DATOS=$BASE/datos PREP=$BASE/prep MODELOS=$BASE/modelos RES=$BASE/resultados
FALLO=""
SRVPID=""

s3cp() {   # s3cp ORIGEN DESTINO: un fichero (el rol no lista el bucket: nada de --recursive ni sync)
  if [ "${CHISPA_LOCAL:-}" = 1 ]; then
    local o=$1 d=$2
    case $o in s3://*) o=/tmp/chispa/s3/${o#s3://};; esac
    case $d in s3://*) d=/tmp/chispa/s3/${d#s3://}; mkdir -p "$(dirname "$d")";; esac
    cp "$o" "$d"
  else aws s3 cp --only-show-errors "$1" "$2"
  fi
}

parar_servidor() {
  [ -n "$SRVPID" ] && kill "$SRVPID" 2>/dev/null
  [ -n "$SRVPID" ] && wait "$SRVPID" 2>/dev/null
  SRVPID=""
  return 0
}

subir_y_apagar() {
  trap - EXIT
  parar_servidor
  sleep 1   # deja que tee vacíe el log
  mkdir -p "$RES"
  [ -n "$FALLO" ] && echo "$FALLO" > "$RES/FALLO"
  cp "$BASE/log.txt" "$RES/log.txt" 2>/dev/null
  empaquetar
  [ -f "$BASE/resultados.tgz" ] && { s3cp "$BASE/resultados.tgz" "$CHISPA_S3/resultados.tgz" || echo "no se pudo subir resultados.tgz"; }
  s3cp "$BASE/log.txt" "$CHISPA_S3/log.txt" || echo "no se pudo subir log.txt"
  [ "${CHISPA_LOCAL:-}" = 1 ] || shutdown -h now
}

# resultados.tgz: find y tar portables (bsdtar): una lista de rutas relativas a $BASE, sin -C junto a -T. Nada de modelos.
empaquetar() {
  rm -f "$BASE/resultados.tgz"
  ( cd "$BASE" && find resultados -type f -not -name '*.chispa' -not -name '*.onnx' -not -name '*.chispa-tok' -size -50000k \
      | LC_ALL=C sort > "$BASE/resultados.lista" && tar -czf "$BASE/resultados.tgz" -T "$BASE/resultados.lista" ) \
    || echo "no se pudo crear resultados.tgz"
}
trap subir_y_apagar EXIT
trap 'exit 143' TERM INT HUP

fallo() { echo "FALLO: $*"; FALLO="${FALLO:+$FALLO; }$*"; }
cierre() { df -h "$BASE" | tail -1; echo "== listo $(date -u +%FT%TZ) fallo=${FALLO:-no} ($(( $(date +%s) - T0 )) s)"; exit 0; }
quedan_min() { echo $(( 90 - ($(date +%s) - T0) / 60 )); }

# --- 1. entorno ------------------------------------------------------------------------------------------------------------
export HF_HOME="$HOME/hf"
mkdir -p "$HF_HOME"
if [ "${CHISPA_LOCAL:-}" = 1 ]; then
  PY=$HOME/venv/bin/python
  export PATH="$HOME/go-sdk/bin:$PATH"
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
"$PY" -c "import sys, numpy, sklearn, torch, transformers, onnxruntime; print(sys.version.split()[0], 'torch', torch.__version__, 'transformers', transformers.__version__, 'onnxruntime', onnxruntime.__version__)" \
  || { fallo "imports de Python"; cierre; }
export GOTOOLCHAIN=local GOFLAGS=-mod=mod GONOSUMDB='github.com/juan52878911/*'

# --- 2. código, checkpoint y datos --------------------------------------------------------------------------------------------
echo "== 2. código y datos $(date -u +%T)"
if [ "${CHISPA_LOCAL:-}" = 1 ] && [ ! -f "/tmp/chispa/s3/${CHISPA_S3#s3://}/codigo.tgz" ]; then   # prueba en seco: lo empaqueta el propio script
  mkdir -p "/tmp/chispa/s3/${CHISPA_S3#s3://}"
  bash "$(dirname "${BASH_SOURCE[0]}")/empaquetar_e2e.sh" --fixtures > "/tmp/chispa/s3/${CHISPA_S3#s3://}/codigo.tgz" \
    || { fallo "empaquetar_e2e.sh"; cierre; }
fi
for _ in $(seq 1 90); do   # 90 × 30 s = 45 min
  s3cp "$CHISPA_S3/codigo.tgz" "$BASE/codigo.tgz" 2>/dev/null && tar -tzf "$BASE/codigo.tgz" >/dev/null 2>&1 && break
  rm -f "$BASE/codigo.tgz"
  [ "${CHISPA_LOCAL:-}" = 1 ] && break
  sleep 30
done
rm -rf "$REPO" "$DATOS" "$PREP" "$MODELOS" "$RES"; mkdir -p "$REPO" "$DATOS" "$PREP" "$MODELOS" "$RES"
tar -xzf "$BASE/codigo.tgz" -C "$REPO" || { fallo "no llegó un codigo.tgz válido"; cierre; }
cd "$REPO" || { fallo "sin repo"; cierre; }
export PYTHONPATH=$REPO:$REPO/sdk/python
{ lscpu; echo; echo "nproc: $(nproc)"; } > "$RES/hardware.txt"
grep -E 'Model name|^CPU\(s\)' "$RES/hardware.txt"
# Go: kindling sale de gomod-proxy/ del tgz; el resto, de proxy.golang.org (en local, sin red: la caché).
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
ls -l "$BASE/mejor.pt"

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

CONV=(--salida "$DATOS" --fuentes "$TAREAS"); [ "${CHISPA_LOCAL:-}" = 1 ] && CONV+=(--fixtures)
"$PY" -m model.datos.convertir "${CONV[@]}" || { fallo "convertir"; cierre; }
PREPARAR=(--datos "$DATOS" --salida "$PREP" --tareas "$TAREAS"); [ "${CHISPA_LOCAL:-}" = 1 ] && PREPARAR+=(--recortar)
"$PY" -I "$REPO/server/deploy/aws/e2e_util.py" preparar "${PREPARAR[@]}" || { fallo "preparar datos"; cierre; }

# --- 3. tokenizador de e5 en Go --------------------------------------------------------------------------------------------------
echo "== 3. tokenizador $(date -u +%T)"
TOK=$MODELOS/e5.chispa-tok
"$PY" -I "$REPO/runtime/tok/exportar.py" "$E5" "$TOK" || { fallo "exportar tokenizador"; cierre; }
NFUZZ=8000; [ "${CHISPA_LOCAL:-}" = 1 ] && NFUZZ=500
"$PY" -I "$REPO/runtime/tok/referencia.py" "$E5" "$BASE/ref_fuzz.jsonl" --fuzz $NFUZZ 2>&1 | tail -1
( cd "$REPO/runtime/tok" && CHISPA_TOK="$TOK" CHISPA_TOK_FUZZ="$BASE/ref_fuzz.jsonl" go test -count=1 -v ./... 2>&1 | tail -15 ) \
  | tee "$RES/tok-test.txt"
[ "${PIPESTATUS[0]}" = 0 ] && ! grep -q '^FAIL' "$RES/tok-test.txt" || fallo "tests del tokenizador"

# --- 4. L2 a ONNX int8 ---------------------------------------------------------------------------------------------------------------
echo "== 4. calibrar y exportar L2 $(date -u +%T)"
L2CH=$MODELOS/l2.chispa
mkdir -p "$MODELOS/onnx"
"$PY" -u -m model.l2.calibrar --ckpt "$BASE/mejor.pt" --dev "$PREP/dev.jsonl" --salida "$MODELOS/calib.json" --device cpu \
  || { fallo "calibrar"; cierre; }
"$PY" -u -m model.l2.exportar --ckpt "$BASE/mejor.pt" --calib "$MODELOS/calib.json" --esquemas "$PREP/dev.jsonl" \
  --paridad "$PREP/dev.jsonl" --n-paridad 300 --salida "$L2CH" --trabajo "$MODELOS/onnx" ${CHISPA_EXPORT_ARGS:-} || { fallo "exportar L2"; cierre; }
cp "$L2CH.informe.json" "$RES/exportar.informe.json" 2>/dev/null
ls -l "$L2CH"

# --- 5. chispa train --conjunta --------------------------------------------------------------------------------------------------------
for t in ${TAREAS//,/ }; do
  echo "== 5. chispa train --conjunta $t $(date -u +%T) (quedan $(quedan_min) min)"
  "$PY" -u -m chispa train --ejemplos "$PREP/$t/ejemplos.jsonl" --esquema "$PREP/$t/esquema.json" --salida "$MODELOS/$t.chispa" \
    --ckpt "$BASE/mejor.pt" --l2 "$L2CH" --conjunta --repo "$REPO" 2>&1 | tail -15 | tee "$RES/train-$t.txt"
  [ "${PIPESTATUS[0]}" = 0 ] && [ -f "$MODELOS/$t.chispa" ] || fallo "chispa train $t"
done

# --- 6. servidor y /v1/decide --------------------------------------------------------------------------------------------------------------
echo "== 6. compilar chispa-server $(date -u +%T)"
cd "$REPO/server" || { fallo "sin server/"; cierre; }
ORTFLAGS=()
if [ "${CHISPA_LOCAL:-}" = 1 ]; then
  go build -o "$BASE/chispa-server" ./cmd/chispa-server || { fallo "go build chispa-server"; cierre; }
else
  export CGO_ENABLED=1 LD_LIBRARY_PATH=/opt/ort/lib
  go get github.com/yalue/onnxruntime_go@$ORT_GO_VERSION && go vet -tags ort ./decide \
    && go build -tags ort -ldflags "-X github.com/juan52878911/chispa/server/decide.RutaORT=/opt/ort/lib/libonnxruntime.so.${ORT_VERSION}" \
         -o "$BASE/chispa-server" ./cmd/chispa-server || { fallo "go build -tags ort chispa-server"; cierre; }
fi
go vet ./... && go test -count=1 ./... 2>&1 | tail -5 | tee "$RES/test-server.txt"
[ "${CHISPA_LOCAL:-}" = 1 ] && go test -count=1 -v -run 'L2c|Simproto|Dot3' ./decide 2>&1 | grep -E '^(---|ok|FAIL)' | tee "$RES/test-l2c-simulada.txt"
cat > "$BASE/forzado.json" <<'JSON'
{"capas": [{"nombre": "L0", "tau": 1.0}, {"nombre": "L1", "tau": 1.0}, {"nombre": "L2", "tau": 0.0}, {"nombre": "L3", "tau": 0.0}],
 "cache_esquemas": 1024, "cache_respuestas": 4096}
JSON

servir() {   # servir TAREA MODO: arranca, manda el test, evalúa y para
  local t=$1 modo=$2 d=$RES/$1/$2 cfg=()
  mkdir -p "$d"
  [ "$modo" = forzado ] && cfg=(-config "$BASE/forzado.json")
  "$BASE/chispa-server" -addr 127.0.0.1:$PUERTO -modelo "$MODELOS/$t.chispa" -tok "$TOK" ${cfg[@]+"${cfg[@]}"} > "$d/servidor.log" 2>&1 &
  SRVPID=$!
  local listo=0
  for _ in $(seq 1 120); do curl -sf -m 2 http://127.0.0.1:$PUERTO/healthz >/dev/null && { listo=1; break; }; sleep 1; done
  [ $listo = 1 ] || { fallo "el servidor ($t/$modo) no responde en /healthz"; parar_servidor; return; }
  cat "$d/servidor.log"
  if grep -q 'L2 queda como stub' "$d/servidor.log"; then
    if [ "${CHISPA_LOCAL:-}" = 1 ]; then echo "(prueba en seco: L2 en stub, como se esperaba sin ORT)"; else fallo "$t/$modo: L2 quedó en stub con ORT"; fi
  fi
  "$PY" -I "$REPO/server/deploy/aws/e2e_util.py" cliente --url http://127.0.0.1:$PUERTO --test "$PREP/$t/test.jsonl" \
    --salida "$d/pred.jsonl" --max "$MAX_FILAS" || fallo "$t/$modo: errores del cliente"
  curl -sf http://127.0.0.1:$PUERTO/metrics > "$d/metrics.txt"
  parar_servidor
  local datos=$PREP/$t/test.jsonl
  if [ "$MAX_FILAS" != 0 ]; then head -n "$MAX_FILAS" "$PREP/$t/test.jsonl" > "$d/test.jsonl"; datos=$d/test.jsonl; fi
  "$PY" -m model.evaluacion.chispa_eval --datos "$datos" --pred "$d/pred.jsonl" --salida "$d/eval.json" > "$d/eval.txt" 2>&1 \
    || fallo "$t/$modo: chispa_eval"
  tail -4 "$d/eval.txt"
}
for t in ${TAREAS//,/ }; do
  for modo in forzado cascada; do
    [ -f "$MODELOS/$t.chispa" ] || continue
    if [ "$(quedan_min)" -lt 8 ]; then fallo "$t/$modo: sin tiempo (quedan $(quedan_min) min)"; continue; fi
    echo "== 6. /v1/decide $t/$modo $(date -u +%T) (quedan $(quedan_min) min)"
    servir "$t" "$modo"
  done
done

# --- 7-8. informe y comparación con conjunta.py ---------------------------------------------------------------------------------------------
echo "== 7. informe $(date -u +%T)"
"$PY" -I "$REPO/server/deploy/aws/e2e_util.py" informe --dir "$RES" --ref "$REPO/model/l2/resultados/t22c-conjunta/resultados.json" \
  --tareas "$TAREAS" || fallo "informe (errores en las predicciones)"
cierre
