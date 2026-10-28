#!/bin/bash
CHISPA_S3=__CHISPA_S3__
# user-data de una c6a.xlarge spot (Amazon Linux 2023, x86_64, 4 vCPU, sin GPU), root, con internet y rol con s3:GetObject y
# s3:PutObject (sin List) y sin SSH: T2.6d, ASR de la Arena con la cascada nueva (chispa-cascada) y curvas de cobertura de T2.4.
# El orquestador sustituye __CHISPA_S3__ y sube $CHISPA_S3/codigo.tgz (bash server/deploy/arena/empaquetar.sh > codigo.tgz).
# Variables opcionales: CHISPA_CKPT_S3 (por defecto el de e2e.sh), CHISPA_T22D_S3 (por defecto
# s3://chispa-pruebas-879381269751/t22d-20261028/resultados.tgz), CHISPA_ATAQUES (por run; por defecto 37000 ≈ 10 s a 3.700
# ataques/s, la ejecución del README de la Arena), CHISPA_RUN_MIN (tope de cada run, 15), CHISPA_EXPORT_ARGS (como en e2e.sh).
# En la instancia:
#   1. instala Go, Python 3.11 (venv con torch CPU, transformers, onnx…) y la .so de ONNX Runtime (igual que e2e.sh);
#   2. baja de S3, FICHERO A FICHERO, el código, el checkpoint de L2 y resultados.tgz de T2.2d; baja e5, massive y hatecheck (HF);
#   3. genera el dataset de la Arena (`arena dataset`), entrena los 4 detectores de siempre (`arena train`) y saca train y test
#      de spam e injection (arena_util.py preparar);
#   4. exporta el tokenizador de e5 y L2 a ONNX int8 (dev = valid de la Arena) y corre `chispa train --conjunta` por dimensión;
#   5. arranca un `chispa-server -tags ort` por dimensión (8091 spam, 8092 injection);
#   6. corre la Arena (`arena run -smoke -max-attacks N … -cascada …`, aprendizaje apagado) tres veces: «solo» (chispa-cascada
#      es el único detector), «enjambre» (los 4 + chispa-cascada) y «base» (los 4, control sin -cascada);
#   7. ASR por dimensión del ledger de cada run (arena_util.py asr);
#   8. curvas de cobertura de massive, herramientas y hatecheck con cvtest/pred/ de T2.2d (curvas.py): tabla cada 5 % y SVG.
# Al salir (trap: fin normal, error o SIGTERM) sube log.txt y resultados.tgz y apaga; apagado forzoso a los 75 min.
# CHISPA_LOCAL=1: prueba en seco en kindling: sin dnf, pip, descargas, ORT ni shutdown; ~/venv, ~/go-sdk, ~/hf y /tmp/chispa-arena;
# fixtures de convertir, checkpoint de L2 sin entrenar y predicciones inventadas para las curvas; los servidores se compilan SIN la
# etiqueta ort (L2 en stub, solo contesta L0). El "s3" es /tmp/chispa/s3/<prefijo sin s3://>.
CKPT_S3=${CHISPA_CKPT_S3:-s3://chispa-pruebas-879381269751/l2-20261028b/ckpt/mejor.pt}
T22D_S3=${CHISPA_T22D_S3:-s3://chispa-pruebas-879381269751/t22d-20261028/resultados.tgz}
ATAQUES=${CHISPA_ATAQUES:-37000}
RUN_MIN=${CHISPA_RUN_MIN:-15}
DIMS=spam,injection
TAREAS_CURVAS=massive,herramientas,hatecheck
if [ "${CHISPA_LOCAL:-}" = 1 ]; then
  [ "${CHISPA_S3#__}" != "$CHISPA_S3" ] && CHISPA_S3=s3://local/arena
  ATAQUES=${CHISPA_ATAQUES:-200}
else
  shutdown -h +75   # apagado forzoso: la instancia se termina al apagarse
fi
set -uo pipefail
export HOME="${HOME:-/root}"
T0=$(date +%s)

GO_VERSION=1.27.1        # tar de go.dev
ORT_VERSION=1.22.0       # release de microsoft/onnxruntime
ORT_GO_VERSION=v1.19.0   # github.com/yalue/onnxruntime_go
PUERTO_SPAM=8091
PUERTO_INJ=8092

if [ "${CHISPA_LOCAL:-}" = 1 ]; then BASE=/tmp/chispa-arena; else BASE=/opt/chispa; fi
mkdir -p "$BASE"
exec > >(tee -a "$BASE/log.txt") 2>&1
echo "== arranque arena $(date -u +%FT%TZ) local=${CHISPA_LOCAL:-0} base=$BASE ataques=$ATAQUES por run, tope $RUN_MIN min"

REPO=$BASE/repo PREP=$BASE/prep MODELOS=$BASE/modelos RES=$BASE/resultados
DATA=$BASE/arena-data AMODELS=$BASE/arena-models
FALLO=""
SRVPIDS=()

s3cp() {   # s3cp ORIGEN DESTINO: un fichero (el rol no lista el bucket: nada de --recursive ni sync)
  if [ "${CHISPA_LOCAL:-}" = 1 ]; then
    local o=$1 d=$2
    case $o in s3://*) o=/tmp/chispa/s3/${o#s3://};; esac
    case $d in s3://*) d=/tmp/chispa/s3/${d#s3://}; mkdir -p "$(dirname "$d")";; esac
    cp "$o" "$d"
  else aws s3 cp --only-show-errors "$1" "$2"
  fi
}

parar_servidores() {
  local p
  for p in ${SRVPIDS[@]+"${SRVPIDS[@]}"}; do kill "$p" 2>/dev/null; wait "$p" 2>/dev/null; done
  SRVPIDS=()
  return 0
}

subir_y_apagar() {
  trap - EXIT
  parar_servidores
  pkill -f "$BASE/arena " 2>/dev/null
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
quedan_min() { echo $(( 75 - ($(date +%s) - T0) / 60 )); }

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
  bash "$(dirname "${BASH_SOURCE[0]}")/empaquetar.sh" --fixtures > "/tmp/chispa/s3/${CHISPA_S3#s3://}/codigo.tgz" \
    || { fallo "empaquetar.sh"; cierre; }
fi
for _ in $(seq 1 90); do   # 90 × 30 s = 45 min
  s3cp "$CHISPA_S3/codigo.tgz" "$BASE/codigo.tgz" 2>/dev/null && tar -tzf "$BASE/codigo.tgz" >/dev/null 2>&1 && break
  rm -f "$BASE/codigo.tgz"
  [ "${CHISPA_LOCAL:-}" = 1 ] && break
  sleep 30
done
rm -rf "$REPO" "$PREP" "$MODELOS" "$RES" "$DATA" "$AMODELS" "$BASE/datos" "$BASE/t22d"
mkdir -p "$REPO" "$PREP" "$MODELOS" "$RES" "$DATA" "$AMODELS" "$BASE/datos" "$BASE/t22d"
tar -xzf "$BASE/codigo.tgz" -C "$REPO" || { fallo "no llegó un codigo.tgz válido"; cierre; }
cd "$REPO" || { fallo "sin repo"; cierre; }
export PYTHONPATH=$REPO:$REPO/sdk/python
AU=$REPO/server/deploy/arena
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
intenta("Paul/hatecheck-spanish", repo_type="dataset")
print("descargas con fallo:", fallos or "ninguna")
raise SystemExit(1 if fallos else 0)
PYEOF
}
if [ "${CHISPA_LOCAL:-}" != 1 ]; then bajar || fallo "descarga de modelo o datasets"; fi
E5=$(ls -d "$HF_HOME"/hub/models--intfloat--multilingual-e5-small/snapshots/*/ 2>/dev/null | head -1)
[ -f "${E5}tokenizer.json" ] || { fallo "e5 (con tokenizer.json) no está en $HF_HOME"; cierre; }
export HF_HUB_OFFLINE=1   # a partir de aquí todo sale de $HF_HOME

# verdad de las curvas: massive y hatecheck salen de convertir; herramientas es model/herramientas/test.jsonl (va en el código)
CONV=(--salida "$BASE/datos" --fuentes massive,hatecheck); [ "${CHISPA_LOCAL:-}" = 1 ] && CONV+=(--fixtures)
"$PY" -m model.datos.convertir "${CONV[@]}" || { fallo "convertir"; cierre; }

# resultados.tgz de T2.2d: cvtest/pred/<tarea>.jsonl
if [ "${CHISPA_LOCAL:-}" = 1 ] && [ ! -f "/tmp/chispa/s3/${T22D_S3#s3://}" ]; then
  echo "local: sin $T22D_S3, predicciones inventadas"
  "$PY" -I "$AU/curvas_fixture.py" --datos "$BASE/datos" --herramientas "$REPO/model/herramientas/test.jsonl" --salida "$BASE/t22d_fake" \
    && mkdir -p "$(dirname "/tmp/chispa/s3/${T22D_S3#s3://}")" \
    && tar -C "$BASE/t22d_fake" -czf "/tmp/chispa/s3/${T22D_S3#s3://}" . || { fallo "no se pudieron fabricar las predicciones locales"; cierre; }
fi
s3cp "$T22D_S3" "$BASE/t22d.tgz" || fallo "no se pudo bajar $T22D_S3 (las curvas no se harán)"

# --- 3. dataset de la Arena, detectores de siempre, train y test de spam e injection ----------------------------------------------
echo "== 3. arena dataset y train $(date -u +%T)"
cd "$REPO/arena" || { fallo "sin arena/"; cierre; }
go build -o "$BASE/arena" ./cmd/arena || { fallo "go build arena"; cierre; }
go vet ./... && go test -count=1 ./... 2>&1 | tail -12 | tee "$RES/test-arena.txt"
[ "${PIPESTATUS[0]}" = 0 ] && ! grep -q 'FAIL' "$RES/test-arena.txt" || fallo "tests de la arena"
"$BASE/arena" dataset -out "$DATA" | tail -5 || { fallo "arena dataset"; cierre; }
"$BASE/arena" train -data "$DATA" -models "$AMODELS" | tee "$RES/arena-train.txt" || { fallo "arena train"; cierre; }
"$PY" -I "$AU/arena_util.py" preparar --datos "$DATA" --salida "$PREP" --dims "$DIMS" || { fallo "preparar datos de la arena"; cierre; }

# --- 4. tokenizador de e5, L2 a ONNX int8 y chispa train --conjunta ---------------------------------------------------------------
echo "== 4. tokenizador y L2 $(date -u +%T)"
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
for t in ${DIMS//,/ }; do
  echo "== 4. chispa train --conjunta $t $(date -u +%T) (quedan $(quedan_min) min)"
  "$PY" -u -m chispa train --ejemplos "$PREP/$t/ejemplos.jsonl" --esquema "$PREP/$t/esquema.json" --salida "$MODELOS/$t.chispa" \
    --ckpt "$BASE/mejor.pt" --l2 "$L2CH" --conjunta --repo "$REPO" 2>&1 | tail -15 | tee "$RES/train-$t.txt"
  [ "${PIPESTATUS[0]}" = 0 ] && [ -f "$MODELOS/$t.chispa" ] || fallo "chispa train $t"
done

# --- 5. servidores ---------------------------------------------------------------------------------------------------------------------
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
mkdir -p "$RES/servidores"
arrancar() {   # arrancar DIM PUERTO
  "$BASE/chispa-server" -addr 127.0.0.1:$2 -modelo "$MODELOS/$1.chispa" -tok "$TOK" > "$RES/servidores/$1.log" 2>&1 &
  SRVPIDS+=($!)
  local listo=0
  for _ in $(seq 1 120); do curl -sf -m 2 http://127.0.0.1:$2/healthz >/dev/null && { listo=1; break; }; sleep 1; done
  [ $listo = 1 ] || { fallo "el servidor de $1 no responde en /healthz"; return 1; }
  if grep -q 'L2 queda como stub' "$RES/servidores/$1.log"; then
    if [ "${CHISPA_LOCAL:-}" = 1 ]; then echo "(prueba en seco: L2 en stub, como se esperaba sin ORT)"; else fallo "$1: L2 quedó en stub con ORT"; fi
  fi
}
SERVIDORES=1
[ -f "$MODELOS/spam.chispa" ] && [ -f "$MODELOS/injection.chispa" ] && arrancar spam $PUERTO_SPAM && arrancar injection $PUERTO_INJ || SERVIDORES=0
CASCADA="spam=http://127.0.0.1:$PUERTO_SPAM,injection=http://127.0.0.1:$PUERTO_INJ"

# --- 6. la Arena: solo, enjambre y base ---------------------------------------------------------------------------------------------
correr() {   # correr NOMBRE [flags de arena run]: ATAQUES ataques, aprendizaje apagado (-batch enorme), tope de RUN_MIN minutos
  local n=$1; shift
  local tope=$RUN_MIN
  [ "$(quedan_min)" -lt $(( tope + 12 )) ] && tope=$(( $(quedan_min) - 12 ))
  if [ "$tope" -lt 1 ]; then fallo "$n: sin tiempo (quedan $(quedan_min) min)"; return; fi
  echo "== 6. arena $n $(date -u +%T) (tope $tope min, quedan $(quedan_min) min)"
  rm -f "$DATA/ledger.jsonl"
  ( cd "$BASE" && timeout -s TERM ${tope}m "$BASE/arena" run -smoke -max-attacks "$ATAQUES" -data "$DATA" -models "$AMODELS" \
      -addr 127.0.0.1:8089 -base-port 9300 -batch 1000000000 "$@" ) > "$RES/arena-$n.txt" 2>&1
  local rc=$?
  tail -3 "$RES/arena-$n.txt"
  [ $rc = 0 ] || fallo "arena $n: salió con $rc"
  [ -f "$DATA/ledger.jsonl" ] && gzip -c "$DATA/ledger.jsonl" > "$RES/ledger-$n.jsonl.gz"
  if grep -q '^chispa-cascada:' "$RES/arena-$n.txt"; then fallo "arena $n: errores contra /v1/decide (el ASR no vale)"; fi
}
if [ $SERVIDORES = 1 ]; then
  correr solo -cascada "$CASCADA" -solo-cascada
  correr enjambre -cascada "$CASCADA"
else
  fallo "sin servidores: no se corre la arena con chispa-cascada"
fi
parar_servidores
correr base

# --- 7. ASR -------------------------------------------------------------------------------------------------------------------------------
echo "== 7. ASR $(date -u +%T)"
for n in solo enjambre base; do
  [ -f "$RES/ledger-$n.jsonl.gz" ] || continue
  gzip -dc "$RES/ledger-$n.jsonl.gz" > "$BASE/ledger-$n.jsonl"
  echo "-- $n"
  "$PY" -I "$AU/arena_util.py" asr --ledger "$BASE/ledger-$n.jsonl" --salida "$RES/asr-$n" --max-ataques "$ATAQUES" || fallo "asr $n (menos ataques de los pedidos)"
  rm -f "$BASE/ledger-$n.jsonl"
done

# --- 8. curvas de cobertura ---------------------------------------------------------------------------------------------------------------
echo "== 8. curvas $(date -u +%T)"
if [ -f "$BASE/t22d.tgz" ] && tar -tzf "$BASE/t22d.tgz" >/dev/null 2>&1; then
  tar -xzf "$BASE/t22d.tgz" -C "$BASE/t22d" 2>/dev/null
  PRED=$(find "$BASE/t22d" -type d -path '*cvtest/pred' | head -1)
  if [ -n "$PRED" ]; then
    "$PY" -I "$AU/curvas.py" --pred "$PRED" --salida "$RES/curvas" \
      --verdad massive="$BASE/datos/massive.jsonl" --verdad hatecheck="$BASE/datos/hatecheck.jsonl" \
      --verdad herramientas="$REPO/model/herramientas/test.jsonl" || fallo "curvas"
  else
    fallo "t22d.tgz sin cvtest/pred"
  fi
else
  fallo "sin resultados.tgz de T2.2d válido"
fi
cierre
