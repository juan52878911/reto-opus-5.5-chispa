#!/bin/bash
CHISPA_S3=__CHISPA_S3__
# user-data de una c6a.xlarge spot (Amazon Linux 2023, x86_64, 4 vCPU, sin GPU), root, con internet y rol con s3:GetObject y
# s3:PutObject (sin List) y sin SSH: T4.5b, ablación de H2 (qué componente de L2c explica los 4–5 puntos de punta a punta).
# Mismo patrón que server/deploy/aws/e2e.sh (que no se toca). El orquestador sustituye __CHISPA_S3__ (salida de esta ejecución)
# y sube $CHISPA_S3/codigo.tgz (bash server/deploy/aws/empaquetar_e2e.sh > codigo.tgz: ya trae server/deploy/ablacion).
# Variables opcionales: CHISPA_CKPT_S3 (por defecto s3://chispa-pruebas-879381269751/l2-20261028b/ckpt/mejor.pt),
# CHISPA_TAREAS (massive,clinc150), CHISPA_EXPORT_ARGS (argumentos extra de model.l2.exportar), CHISPA_ABL_MAX (filas de test; 0 = todas),
# CHISPA_ABL_EXTRAS (1 = también E+ y «conjunta.py pura», lentos; por defecto 1).
# En la instancia:
#   1. instala Go, Python 3.11 (venv con torch CPU, transformers, onnxruntime, scikit-learn…) y la .so de ONNX Runtime;
#   2. baja de S3, FICHERO A FICHERO (el rol no lista el bucket), el código y el checkpoint; baja e5 y los datasets públicos (HF)
#      y corre model.datos.convertir;
#   3. exporta el tokenizador de e5, calibra y exporta L2 a ONNX int8 con los valores por defecto actuales de model.l2.exportar;
#   4. `chispa train --conjunta` en cada tarea (L0 de Chispa + CONJ + el L2 del paso 3);
#   5. compila chispa-server -tags ort, lo arranca en modo «forzado» (τ(L0)=1, τ(L1)=1, τ(L2)=0) y guarda pred.jsonl con las
#      probabilidades de la cabeza (la comparación F del arnés);
#   6. corre server/deploy/ablacion/ablacion.py por tarea: corridas 1 (todo servidor), 2 (todo referencia) y una sustitución cada
#      vez en A–E, con el L0 de Chispa sacado del propio binario del servidor.
# Al salir (trap: fin normal, error o SIGTERM) sube log.txt y resultados.tgz y apaga; apagado forzoso a los 75 min.
CKPT_S3=${CHISPA_CKPT_S3:-s3://chispa-pruebas-879381269751/l2-20261028b/ckpt/mejor.pt}
TAREAS=${CHISPA_TAREAS:-massive,clinc150}
MAX_FILAS=${CHISPA_ABL_MAX:-0}
EXTRAS=${CHISPA_ABL_EXTRAS:-1}
LIMITE_MIN=75
shutdown -h +$LIMITE_MIN   # apagado forzoso: la instancia se termina al apagarse
set -uo pipefail
export HOME="${HOME:-/root}"
T0=$(date +%s)

GO_VERSION=1.27.1        # tar de go.dev
ORT_VERSION=1.22.0       # release de microsoft/onnxruntime
ORT_GO_VERSION=v1.19.0   # github.com/yalue/onnxruntime_go (el de la imagen de T4.4, que compiló)
PUERTO=8090

BASE=/opt/chispa
mkdir -p "$BASE"
exec > >(tee -a "$BASE/log.txt") 2>&1
echo "== arranque ablación $(date -u +%FT%TZ) base=$BASE tareas=$TAREAS max=$MAX_FILAS extras=$EXTRAS"

REPO=$BASE/repo DATOS=$BASE/datos PREP=$BASE/prep MODELOS=$BASE/modelos RES=$BASE/resultados
FALLO=""
SRVPID=""

s3cp() {   # s3cp ORIGEN DESTINO: un fichero (el rol no lista el bucket: nada de --recursive ni sync)
  aws s3 cp --only-show-errors "$1" "$2"
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
  shutdown -h now
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
quedan_min() { echo $(( LIMITE_MIN - ($(date +%s) - T0) / 60 )); }

# --- 1. entorno ------------------------------------------------------------------------------------------------------------
export HF_HOME="$HOME/hf"
mkdir -p "$HF_HOME"
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
go version
"$PY" -c "import sys, numpy, sklearn, torch, transformers, onnxruntime; print(sys.version.split()[0], 'torch', torch.__version__, 'transformers', transformers.__version__, 'onnxruntime', onnxruntime.__version__)" \
  || { fallo "imports de Python"; cierre; }
export GOTOOLCHAIN=local GOFLAGS=-mod=mod GONOSUMDB='github.com/juan52878911/*'

# --- 2. código, checkpoint y datos --------------------------------------------------------------------------------------------
echo "== 2. código y datos $(date -u +%T)"
for _ in $(seq 1 90); do   # 90 × 30 s = 45 min
  s3cp "$CHISPA_S3/codigo.tgz" "$BASE/codigo.tgz" 2>/dev/null && tar -tzf "$BASE/codigo.tgz" >/dev/null 2>&1 && break
  rm -f "$BASE/codigo.tgz"
  sleep 30
done
rm -rf "$REPO" "$DATOS" "$PREP" "$MODELOS" "$RES"; mkdir -p "$REPO" "$DATOS" "$PREP" "$MODELOS" "$RES"
tar -xzf "$BASE/codigo.tgz" -C "$REPO" || { fallo "no llegó un codigo.tgz válido"; cierre; }
cd "$REPO" || { fallo "sin repo"; cierre; }
[ -f "$REPO/server/deploy/ablacion/ablacion.py" ] || { fallo "codigo.tgz sin server/deploy/ablacion/ablacion.py"; cierre; }
export PYTHONPATH=$REPO:$REPO/sdk/python
{ lscpu; echo; echo "nproc: $(nproc)"; } > "$RES/hardware.txt"
grep -E 'Model name|^CPU\(s\)' "$RES/hardware.txt"
export GOPROXY=file://$REPO/gomod-proxy,https://proxy.golang.org   # kindling sale de gomod-proxy/ del tgz; el resto, de proxy.golang.org

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
bajar || fallo "descarga de modelo o datasets"
E5=$(ls -d "$HF_HOME"/hub/models--intfloat--multilingual-e5-small/snapshots/*/ 2>/dev/null | head -1)
[ -f "${E5}tokenizer.json" ] || { fallo "e5 (con tokenizer.json) no está en $HF_HOME"; cierre; }
export HF_HUB_OFFLINE=1   # a partir de aquí todo sale de $HF_HOME

"$PY" -m model.datos.convertir --salida "$DATOS" --fuentes "$TAREAS" || { fallo "convertir"; cierre; }
"$PY" -I "$REPO/server/deploy/aws/e2e_util.py" preparar --datos "$DATOS" --salida "$PREP" --tareas "$TAREAS" || { fallo "preparar datos"; cierre; }

# --- 3. tokenizador y L2 a ONNX int8 ----------------------------------------------------------------------------------------------
echo "== 3. tokenizador, calibrar y exportar L2 $(date -u +%T)"
TOK=$MODELOS/e5.chispa-tok
"$PY" -I "$REPO/runtime/tok/exportar.py" "$E5" "$TOK" || { fallo "exportar tokenizador"; cierre; }
L2CH=$MODELOS/l2.chispa
mkdir -p "$MODELOS/onnx"
"$PY" -u -m model.l2.calibrar --ckpt "$BASE/mejor.pt" --dev "$PREP/dev.jsonl" --salida "$MODELOS/calib.json" --device cpu \
  || { fallo "calibrar"; cierre; }
"$PY" -u -m model.l2.exportar --ckpt "$BASE/mejor.pt" --calib "$MODELOS/calib.json" --esquemas "$PREP/dev.jsonl" \
  --paridad "$PREP/dev.jsonl" --n-paridad 300 --salida "$L2CH" --trabajo "$MODELOS/onnx" ${CHISPA_EXPORT_ARGS:-} || { fallo "exportar L2"; cierre; }
cp "$L2CH.informe.json" "$RES/exportar.informe.json" 2>/dev/null
ls -l "$L2CH"

# --- 4. chispa train --conjunta ----------------------------------------------------------------------------------------------------
for t in ${TAREAS//,/ }; do
  echo "== 4. chispa train --conjunta $t $(date -u +%T) (quedan $(quedan_min) min)"
  "$PY" -u -m chispa train --ejemplos "$PREP/$t/ejemplos.jsonl" --esquema "$PREP/$t/esquema.json" --salida "$MODELOS/$t.chispa" \
    --ckpt "$BASE/mejor.pt" --l2 "$L2CH" --conjunta --repo "$REPO" 2>&1 | tail -15 | tee "$RES/train-$t.txt"
  [ "${PIPESTATUS[0]}" = 0 ] && [ -f "$MODELOS/$t.chispa" ] || fallo "chispa train $t"
done

# --- 5. servidor en modo forzado ---------------------------------------------------------------------------------------------------------
echo "== 5. compilar chispa-server $(date -u +%T)"
cd "$REPO/server" || { fallo "sin server/"; cierre; }
export CGO_ENABLED=1 LD_LIBRARY_PATH=/opt/ort/lib
go get github.com/yalue/onnxruntime_go@$ORT_GO_VERSION && go vet -tags ort ./decide \
  && go build -tags ort -ldflags "-X github.com/juan52878911/chispa/server/decide.RutaORT=/opt/ort/lib/libonnxruntime.so.${ORT_VERSION}" \
       -o "$BASE/chispa-server" ./cmd/chispa-server || { fallo "go build -tags ort chispa-server"; cierre; }
cat > "$BASE/forzado.json" <<'JSON'
{"capas": [{"nombre": "L0", "tau": 1.0}, {"nombre": "L1", "tau": 1.0}, {"nombre": "L2", "tau": 0.0}, {"nombre": "L3", "tau": 0.0}],
 "cache_esquemas": 1024, "cache_respuestas": 4096}
JSON

servir_forzado() {   # servir_forzado TAREA: arranca el servidor forzado, manda el test (pred.jsonl) y evalúa
  local t=$1 d=$RES/$1/servidor
  mkdir -p "$d"
  "$BASE/chispa-server" -addr 127.0.0.1:$PUERTO -modelo "$MODELOS/$t.chispa" -tok "$TOK" -config "$BASE/forzado.json" > "$d/servidor.log" 2>&1 &
  SRVPID=$!
  local listo=0
  for _ in $(seq 1 120); do curl -sf -m 2 http://127.0.0.1:$PUERTO/healthz >/dev/null && { listo=1; break; }; sleep 1; done
  [ $listo = 1 ] || { fallo "el servidor ($t) no responde en /healthz"; parar_servidor; return; }
  cat "$d/servidor.log"
  grep -q 'L2 queda como stub' "$d/servidor.log" && fallo "$t: L2 quedó en stub con ORT"
  "$PY" -I "$REPO/server/deploy/aws/e2e_util.py" cliente --url http://127.0.0.1:$PUERTO --test "$PREP/$t/test.jsonl" \
    --salida "$d/pred.jsonl" --max "$MAX_FILAS" || fallo "$t: errores del cliente"
  parar_servidor
  local datos=$PREP/$t/test.jsonl
  if [ "$MAX_FILAS" != 0 ]; then head -n "$MAX_FILAS" "$PREP/$t/test.jsonl" > "$d/test.jsonl"; datos=$d/test.jsonl; fi
  "$PY" -m model.evaluacion.chispa_eval --datos "$datos" --pred "$d/pred.jsonl" --salida "$d/eval.json" > "$d/eval.txt" 2>&1 \
    || fallo "$t: chispa_eval"
  tail -4 "$d/eval.txt"
}
for t in ${TAREAS//,/ }; do
  [ -f "$MODELOS/$t.chispa" ] || continue
  echo "== 5. /v1/decide forzado $t $(date -u +%T) (quedan $(quedan_min) min)"
  servir_forzado "$t"
done

# --- 6. ablación ------------------------------------------------------------------------------------------------------------------------
# Las corridas principales de cada tarea primero; los extras (E+, conjunta.py pura) solo si queda tiempo, y nunca más allá del límite.
cd "$REPO" || { fallo "sin repo"; cierre; }
unset LD_LIBRARY_PATH   # el ONNX Runtime de pip trae el suyo
for t in ${TAREAS//,/ }; do
  [ -f "$MODELOS/$t.chispa" ] || continue
  if [ "$(quedan_min)" -lt 12 ]; then fallo "$t: sin tiempo para la ablación (quedan $(quedan_min) min)"; continue; fi
  echo "== 6. ablación $t $(date -u +%T) (quedan $(quedan_min) min)"
  ARGS=(correr --tarea "$t" --chispa "$MODELOS/$t.chispa" --prep "$PREP/$t" --ckpt "$BASE/mejor.pt" --salida "$RES/$t/ablacion"
        --servidor "$BASE/chispa-server" --datos-orig "$DATOS/$t.jsonl" --max "$MAX_FILAS")
  [ -f "$RES/$t/servidor/pred.jsonl" ] && [ "$MAX_FILAS" = 0 ] && ARGS+=(--pred-servidor "$RES/$t/servidor/pred.jsonl")
  # extras: solo si tras las corridas principales (≈ 10 min) quedan ≥ 25 min; con la tarea siguiente por delante, la mitad
  if [ "$EXTRAS" = 1 ] && [ "$(quedan_min)" -ge 35 ]; then ARGS+=(--extras --presupuesto-s 900); fi
  timeout $(( ($(quedan_min) - 6) * 60 )) "$PY" -u server/deploy/ablacion/ablacion.py "${ARGS[@]}" 2>&1 | tee "$RES/ablacion-$t.txt"
  rc=${PIPESTATUS[0]}
  [ "$rc" = 0 ] || fallo "ablación $t: código $rc (3 = el arnés no reproduce 1 o 2; 124 = tiempo)"
done
cierre
