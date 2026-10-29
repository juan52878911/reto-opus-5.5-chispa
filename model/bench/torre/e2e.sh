#!/bin/bash
CHISPA_S3=__CHISPA_S3__
# user-data (≤ 16 KB) de una c6a.xlarge spot (Amazon Linux 2023, x86_64, 4 vCPU, sin GPU), root, con internet y rol con s3:GetObject y
# s3:PutObject (sin List), sin SSH. G.6/G.7: la torre de L2 (variantes fp32, int8 dinámico y int8 estático) de punta a punta con el checkpoint real.
# El orquestador sustituye __CHISPA_S3__ y sube UN paquete de la rama unificada (modelo, servidor, runtime, formato y SDK, con el proxy de módulos de kindling):
#   $CHISPA_S3/codigo.tgz    CHISPA_GOMOD_PROXY=1 bash model/bench/torre/empaquetar.sh <sha> model server runtime format sdk
# (sin rutas, empaquetar.sh usa justo esas). Modo antiguo de dos ramas (codigo-modelo.tgz + codigo-sdk.tgz): CHISPA_DOS_PAQUETES=1.
# Opcionales: CHISPA_CKPT_S3 (por defecto el de G.8 corrida 2, max_tok 256 dentro del checkpoint), CHISPA_JEV_REF, CHISPA_TODOS_MIN (minutos máx. de los 231 casos),
# CHISPA_EXPORT_ARGS (por defecto «--sin-poda»: el exportador de esta base no tiene `--perfil servidor`; si lo tiene, «--perfil servidor» y CHISPA_VARIANTES=ninguna),
# CHISPA_VARIANTES (por defecto «ninguna»: --cuant-torre ninguna), CHISPA_TODOS_VAR (variante con los 231 casos, por defecto la primera), CHISPA_TAU_NUEVO (por defecto «no»:
# una pasada extra con tau_l2_esquema_nuevo=X, p. ej. 0.276), CHISPA_ORT_VERSION (por defecto 1.31.1).
# D1 (una sola corrida): tras la pasada base del servidor, 5b diagnostica la paridad servidor ↔ Python (paridad_servidor.py: texto de consulta y de torre, tokens, s, CALIB,
# probabilidad; causa de cada discrepancia) y repite los 231 casos con (a) la CALIB global del checkpoint en vez de la de `chispa train --torre` y (b) además la consulta ONNX
# fp32 sin poda (`exportar --perfil servidor`) en lugar de la int8 con poda que mete `chispa train --ckpt`; 5c mide el perfil móvil con la poda corregida (fp16 y fp32:
# top-1, MB y latencia; movil.py). CHISPA_MOVIL=no la omite; CHISPA_N_PARIDAD (90 casos del diagnóstico).
# Pasos: 1 Go, gcc, ORT, Python+torch CPU · 2 paquetes (se funden en un árbol), checkpoint, e5, massive-es, JevBench · 3 exporta consulta y torre
# (paridad: coseno de h y top-1 de choice en 300 filas, con poda y sin <unk>) y comprueba las metadata_props · 4 SDK: go test -tags ort
# ./torre/..., TestIgualdadTransformersPasaje · 5 chispa train --torre, chispa-server -tags ort, los 5 esquemas de JevBench y los 231 casos por /v1/decide junto a Python k=0,
# con /metrics leído tras las peticiones (chispa_torres_calculadas_total > 0 y L2 en las capas, o FALLO) y una pasada con tau_l2_esquema_nuevo · 6 informe.md (OK/FALLO por punto).
# Al salir (trap) sube log.txt y resultados.tgz y apaga; apagado forzoso a los 75 min.
# CHISPA_LOCAL=1: prueba en seco sin dnf, pip, descargas ni shutdown, con checkpoint aleatorio y fixtures. Con ORT (~/ort o CHISPA_ORT_DIR) y gcc en el nodo
# recorre TODOS los pasos (Go con ORT, servidor, pasadas, diagnósticos y móvil); sin ellos se omiten (OMITIDO) los pasos de Go con ORT, `train --torre` y el servidor. Con CHISPA_DOS_PAQUETES=1, CHISPA_TRY_REF elige la rama del SDK.
CKPT_S3=${CHISPA_CKPT_S3:-s3://chispa-pruebas-879381269751/general-20261029b/ckpt/mejor.pt}
LOCAL=${CHISPA_LOCAL:-0}
AQUI=$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)   # solo para la prueba en seco
if [ "$LOCAL" = 1 ]; then [ "${CHISPA_S3#__}" != "$CHISPA_S3" ] && CHISPA_S3=s3://local/torre; else shutdown -h +75; fi
set -uo pipefail
export HOME="${HOME:-/root}"
T0=$(date +%s)
GO_VERSION=1.27.1; ORT_VERSION=${CHISPA_ORT_VERSION:-1.31.1}; PUERTO=8091
if [ "$LOCAL" = 1 ]; then BASE=/tmp/chispa-torre; else BASE=/opt/chispa; fi
mkdir -p "$BASE"
exec > >(tee -a "$BASE/log.txt") 2>&1
echo "== arranque torre $(date -u +%FT%TZ) local=$LOCAL base=$BASE"
REPO=$BASE/repo RES=$BASE/resultados JEV=$BASE/jevbench MODELOS=$BASE/modelos
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
  "$PY" -I -c "import sys; sys.path.insert(0, sys.argv[1]); from model.bench.torre.informe import main; main(sys.argv[2])" "$REPO" "$RES" >/dev/null 2>&1 \
    || echo "no se pudo escribir informe.md"
  cp "$BASE/log.txt" "$RES/log.txt" 2>/dev/null
  rm -f "$BASE/resultados.tgz"
  ( cd "$BASE" && find resultados -type f -not -name '*.chispa' -not -name '*.chispa-tok' -not -name '*.onnx' -size -50000k \
      | LC_ALL=C sort > "$BASE/resultados.lista" && tar -czf "$BASE/resultados.tgz" -T "$BASE/resultados.lista" ) || echo "no se pudo crear resultados.tgz"
  [ -f "$BASE/resultados.tgz" ] && { s3cp "$BASE/resultados.tgz" "$CHISPA_S3/resultados.tgz" || echo "no se pudo subir resultados.tgz"; }
  s3cp "$BASE/log.txt" "$CHISPA_S3/log.txt" || echo "no se pudo subir log.txt"
  for f in exportar-score.log calib-score.log; do   # además de ir en el tgz, sueltos: así se ve el fallo de G.7b aunque el tgz no suba
    [ -f "$RES/$f" ] && { s3cp "$RES/$f" "$CHISPA_S3/score/$f" || echo "no se pudo subir $f"; }
  done
  [ "$LOCAL" = 1 ] || shutdown -h now
}
PY=${CHISPA_PY:-$HOME/venv/bin/python}
trap subir_y_apagar EXIT
trap 'exit 143' TERM INT HUP
mkdir -p "$RES"
estado() { printf '%s\t%s\n' "$1" "$2" >> "$RES/estado.tsv"; echo "[$1] $2"; }   # estado clave "OK detalle" | "FALLO detalle" | "OMITIDO motivo"
fallo() { echo "FALLO: $*"; FALLO="${FALLO:+$FALLO; }$*"; }
cierre() { echo "== listo $(date -u +%FT%TZ) fallo=${FALLO:-no} ($(( $(date +%s) - T0 )) s)"; exit 0; }
quedan_min() { echo $(( 75 - ($(date +%s) - T0) / 60 )); }

# --- 1. entorno ---------------------------------------------------------------------------------------------------------------
export HF_HOME="$HOME/hf"; mkdir -p "$HF_HOME"
if [ "$LOCAL" != 1 ]; then
  echo "== 1. entorno $(date -u +%T)"
  dnf install -y -q gcc tar gzip git python3.11 python3.11-pip || { fallo "dnf install"; cierre; }
  curl -fsSL "https://go.dev/dl/go${GO_VERSION}.linux-amd64.tar.gz" | tar -xzC /usr/local || { fallo "descarga de Go"; cierre; }
  mkdir -p /opt/ort && curl -fsSL "https://github.com/microsoft/onnxruntime/releases/download/v${ORT_VERSION}/onnxruntime-linux-x64-${ORT_VERSION}.tgz" \
    | tar -xzC /opt/ort --strip-components=1 || { fallo "descarga de ORT $ORT_VERSION"; cierre; }
  python3.11 -m venv "$BASE/venv" || { fallo "venv"; cierre; }
  PY=$BASE/venv/bin/python
  "$PY" -m pip install -q --no-cache-dir -U pip \
    && "$PY" -m pip install -q --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && "$PY" -m pip install -q --no-cache-dir numpy scikit-learn transformers tokenizers huggingface_hub pyyaml pyarrow datasets onnx onnxscript onnxruntime \
    || { fallo "pip install"; cierre; }
fi
export PATH=/usr/local/go/bin:$HOME/go-sdk/bin:$PATH
go version
"$PY" -c "import sys, numpy, torch, transformers, onnx, onnxruntime; print(sys.version.split()[0], 'torch', torch.__version__)" || { fallo "imports de Python"; cierre; }
export GOTOOLCHAIN=local GOFLAGS=-mod=mod GONOSUMDB='github.com/juan52878911/*'

# --- 2. paquetes, checkpoint, e5, massive-es y JevBench --------------------------------------------------------------------------------
echo "== 2. código y datos $(date -u +%T)"
if [ "$LOCAL" = 1 ]; then   # en seco los empaqueta el propio script (SDK: por defecto el HEAD, que ya trae server/ y runtime/)
  d=/tmp/chispa/s3/${CHISPA_S3#s3://}; mkdir -p "$d"
  if [ "${CHISPA_DOS_PAQUETES:-0}" = 1 ]; then
    bash "$AQUI/empaquetar.sh" HEAD model > "$d/codigo-modelo.tgz" || { fallo "empaquetar modelo"; cierre; }
    CHISPA_GOMOD_PROXY=1 bash "$AQUI/empaquetar.sh" "${CHISPA_TRY_REF:-HEAD}" server runtime format sdk > "$d/codigo-sdk.tgz" || { fallo "empaquetar sdk"; cierre; }
  else CHISPA_GOMOD_PROXY=1 bash "$AQUI/empaquetar.sh" HEAD > "$d/codigo.tgz" || { fallo "empaquetar"; cierre; }
  fi
fi
if [ "${CHISPA_DOS_PAQUETES:-0}" = 1 ]; then PAQUETES="codigo-modelo codigo-sdk"; else PAQUETES=codigo; fi
rm -rf "$REPO" "$JEV" "$MODELOS"; mkdir -p "$REPO" "$MODELOS"
for p in $PAQUETES; do   # un paquete a medias no se acepta: hasta 45 min de reintentos (el orquestador los sube tras lanzar)
  for _ in $(seq 1 90); do
    s3cp "$CHISPA_S3/$p.tgz" "$BASE/$p.tgz" 2>/dev/null && tar -tzf "$BASE/$p.tgz" >/dev/null 2>&1 && break
    rm -f "$BASE/$p.tgz"; [ "$LOCAL" = 1 ] && break; sleep 30
  done
  tar -xzf "$BASE/$p.tgz" -C "$REPO" || { fallo "no llegó un $p.tgz válido"; cierre; }
done
cd "$REPO" || { fallo "sin repo"; cierre; }
export PYTHONPATH=$REPO:$REPO/sdk/python
if [ "$LOCAL" = 1 ]; then export GOPROXY=off; else export GOPROXY=file://$REPO/gomod-proxy,https://proxy.golang.org; fi
{ lscpu; echo "nproc: $(nproc)"; free -m 2>/dev/null; } > "$RES/hardware.txt"

CKPT=$BASE/mejor.pt
if [ "$LOCAL" = 1 ]; then CKPT_ARG=(--ckpt-aleatorio)   # y un mejor.pt aleatorio para calibrar.py y el .chispa score
  "$PY" -I -c "import sys; sys.path.insert(0, sys.argv[1]); import torch; from model.l2.exportar import modelo_aleatorio
torch.save({'modelo': modelo_aleatorio().state_dict(), 'cabezas': [], 'max_tok': 128}, sys.argv[2])" "$REPO" "$CKPT" || { fallo "checkpoint aleatorio"; cierre; }
else
  s3cp "$CKPT_S3" "$CKPT" || { fallo "no se pudo bajar el checkpoint $CKPT_S3"; cierre; }
  ls -l "$CKPT"; CKPT_ARG=(--ckpt "$CKPT")
fi
ls "$HF_HOME"/hub/models--intfloat--multilingual-e5-small/snapshots/*/tokenizer.json >/dev/null 2>&1 \
  || "$PY" -I -c 'from huggingface_hub import snapshot_download as s; s("intfloat/multilingual-e5-small", allow_patterns=["*.json", "*.safetensors", "*.txt", "*.model", "tokenizer*"])' \
  || { fallo "descarga de e5"; cierre; }
ls "$HF_HOME"/hub/datasets--mteb--amazon_massive_intent/snapshots/*/validation/es.json.gz >/dev/null 2>&1 \
  || "$PY" -I -c 'from huggingface_hub import snapshot_download as s; s("mteb/amazon_massive_intent", repo_type="dataset", allow_patterns=["validation/es.json.gz"])' \
  || { fallo "descarga de massive-es"; cierre; }
E5=$(ls -d "$HF_HOME"/hub/models--intfloat--multilingual-e5-small/snapshots/*/ | head -1)
export HF_HUB_OFFLINE=1
if [ "$LOCAL" = 1 ]; then cp -r "${CHISPA_JEV_LOCAL:-$REPO/model/evaluacion/tests/fixtures/jevbench}" "$JEV" || { fallo "sin JevBench local"; cierre; }
else
  git clone -q https://github.com/fstandhartinger/jevbench "$JEV" && { [ -z "${CHISPA_JEV_REF:-}" ] || git -C "$JEV" checkout -q "$CHISPA_JEV_REF"; } \
    || { fallo "git clone de JevBench"; cierre; }
fi
{ git -C "$JEV" rev-parse HEAD 2>/dev/null || echo fixture; } > "$RES/jevbench-sha.txt"

# --- 3. torre (una exportación por variante): paridad, tamaño, latencia y metadata_props --------------------------------------------------
echo "== 3. exportar torre y paridad $(date -u +%T)"
VARIANTES=${CHISPA_VARIANTES:-ninguna}
EXPORT_ARGS=${CHISPA_EXPORT_ARGS---sin-poda}   # este exportador no tiene --perfil servidor: torre fp32 («--cuant-torre ninguna») y sin vocabulario podado
echo "export: --cuant-torre <variante> $EXPORT_ARGS"
"$PY" -m model.bench.torre.datos_g7 calib "$RES/calib-torre.jsonl" 2>&1 | tail -1
for v in $VARIANTES; do
  TORRE=$RES/torre-$v.onnx
  if "$PY" -u -m model.l2.exportar --torre-onnx "$TORRE" "${CKPT_ARG[@]}" $EXPORT_ARGS --cuant-torre "$v" --calib-torre "$RES/calib-torre.jsonl" --n-calib 500 \
       --medir-torre "$RES/paridad-$v" > "$RES/exportar-torre-$v.log" 2>&1 \
     || { echo "exportar con --medir-torre falló (sin poda cabe justo en memoria); se repite sin medir la paridad"; fallo "paridad-$v no medida"
          "$PY" -u -m model.l2.exportar --torre-onnx "$TORRE" "${CKPT_ARG[@]}" $EXPORT_ARGS --cuant-torre "$v" --calib-torre "$RES/calib-torre.jsonl" --n-calib 500 \
            >> "$RES/exportar-torre-$v.log" 2>&1; }; then tail -3 "$RES/exportar-torre-$v.log"   # su LEEME.md habla de pesos aleatorios: solo vale paridad.json
  else tail -20 "$RES/exportar-torre-$v.log"; fallo "exportar --torre-onnx $v"; estado "metadata_$v" "FALLO no se exportó"; continue; fi
  "$PY" -I -c "
import json, onnx, os, sys
p = {x.key: x.value for x in onnx.load(sys.argv[1], load_external_data=False).metadata_props}
esp = {'chispa.torre.dim': '256', 'chispa.torre.max_len': str(json.load(open(sys.argv[2]))['max_len'] if os.path.exists(sys.argv[2]) else p.get('chispa.torre.max_len')), 'chispa.torre.prefijo': 'passage: '}
mal = {k: p.get(k) for k in esp if p.get(k) != esp[k]}
print(p); sys.exit('metadata_props mal: %r' % mal if mal else 0)" "$TORRE" "$RES/paridad-$v/paridad.json" \
    && estado "metadata_$v" "OK dim=256 max_len prefijo='passage: '" || estado "metadata_$v" "FALLO ver log"
done

# --- 3b. .chispa con score K≥3 para la sesión del SDK: calibrar.py + exportar.py sobre un dev con tareas score de JevBench -----------------
echo "== 3b. .chispa score $(date -u +%T)"
: > "$RES/exportar-score.log"   # existe siempre, falle el paso que falle
if "$PY" -m model.bench.torre.datos_g7 dev "$RES/dev-score.jsonl" --jevbench "$JEV" \
   && "$PY" -u -m model.l2.calibrar --ckpt "$CKPT" --dev "$RES/dev-score.jsonl" --salida "$RES/calib-score.json" --device cpu > "$RES/calib-score.log" 2>&1 \
   && "$PY" -u -m model.l2.exportar --ckpt "$CKPT" --calib "$RES/calib-score.json" --esquemas "$RES/dev-score.jsonl" --salida "$RES/l2-score.chispa" \
        > "$RES/exportar-score.log" 2>&1 \
   && "$PY" -I -c "
import json, sys
k = sorted(x for x in json.load(open(sys.argv[1]))['chispa']['tipos'] if x.startswith('score'))
open(sys.argv[2], 'w').write(json.dumps(k)); sys.exit(0 if k else 'sin claves score')" "$RES/calib-score.json" "$RES/calib-score-claves.json" \
   && s3cp "$RES/l2-score.chispa" "$CHISPA_S3/score/l2-score.chispa"; then estado chispa_score "OK $(cat "$RES/calib-score-claves.json")"
else tail -5 "$RES/exportar-score.log" 2>/dev/null; estado chispa_score "FALLO ver exportar-score.log"; fallo "chispa score K>=3"; fi

# --- 4. SDK: tokenizador y pruebas de Go con ORT ------------------------------------------------------------------------------------
echo "== 4. Go y ORT $(date -u +%T)"
TOK=$MODELOS/e5.chispa-tok
"$PY" -I "$REPO/runtime/tok/exportar.py" "$E5" "$TOK" || { fallo "exportar tokenizador"; cierre; }
SERV=$BASE/chispa-server
ORT_DIR=/opt/ort
# en seco, con ORT (~/ort) y gcc en el nodo se recorren también los pasos de Go reales; sin ellos se omiten
LOCAL_ORT=0; if [ "$LOCAL" = 1 ] && [ -f "${CHISPA_ORT_DIR:-$HOME/ort}/lib/libonnxruntime.so.${ORT_VERSION}" ] && command -v gcc >/dev/null; then LOCAL_ORT=1; ORT_DIR=${CHISPA_ORT_DIR:-$HOME/ort}; fi
if [ "$LOCAL" = 1 ] && [ "$LOCAL_ORT" != 1 ]; then
  estado go_test_ort "OMITIDO local (sin ORT)"; estado go_test_tok "OMITIDO local (sin ORT ni CHISPA_TOK del SDK)"
  ( cd "$REPO/server" && go build -o "$SERV" ./cmd/chispa-server ) && estado build_server "OK sin ORT (local)" || estado build_server "FALLO go build"
else
  export CGO_ENABLED=1 LD_LIBRARY_PATH=$ORT_DIR/lib CHISPA_ORT_LIB=$ORT_DIR/lib/libonnxruntime.so.${ORT_VERSION}
  if [ -f go.work ]; then GODIR=$REPO TORRE_PKG=./server/torre/...; else GODIR=$REPO/server TORRE_PKG=./torre/...; fi
  prueba() {   # prueba clave "go test…": OK solo con algún PASS y ningún SKIP ni FAIL (un test saltado no demuestra nada)
    local k=$1; shift; ( cd "$GODIR" && "$@" ) > "$RES/$k.log" 2>&1; local rc=$?
    local p s; p=$(grep -c -- '^--- PASS\|^    --- PASS' "$RES/$k.log"); s=$(grep -c -- '--- SKIP' "$RES/$k.log")
    if [ $rc = 0 ] && [ "$p" -gt 0 ] && [ "$s" = 0 ]; then estado "$k" "OK $p PASS"; else estado "$k" "FALLO rc=$rc pass=$p skip=$s (ver $k.log)"; tail -5 "$RES/$k.log"; fi
  }
  CHISPA_TOK=$TOK prueba go_test_ort go test -v -count=1 -tags ort "$TORRE_PKG"
  if [ -f go.work ]; then GODIR=$REPO TOK_PKG=./runtime/tok/...; else GODIR=$REPO/runtime/tok TOK_PKG=./...; fi   # runtime/tok es otro módulo
  CHISPA_TOK=$TOK prueba go_test_tok go test -v -count=1 -tags ort -run TestIgualdadTransformersPasaje "$TOK_PKG"
  ( cd "$REPO/server" && go build -tags ort -ldflags "-X github.com/juan52878911/chispa/server/decide.RutaORT=$CHISPA_ORT_LIB" -o "$SERV" ./cmd/chispa-server ) \
    && estado build_server "OK -tags ort" || estado build_server "FALLO go build -tags ort"
fi
cd "$REPO" || cierre

# --- 5. por variante: chispa train --torre, chispa-server y esquemas de JevBench por /v1/decide (los 231 casos, solo en CHISPA_TODOS_VAR) ----
echo "== 5. servidor $(date -u +%T)"
if [ "$LOCAL" = 1 ] && [ "$LOCAL_ORT" != 1 ]; then for v in $VARIANTES; do estado "train_torre_$v" "OMITIDO local (sin ORT)"; done
elif [ -x "$SERV" ]; then
  "$PY" -u -m model.evaluacion.jevbench_l2 --ckpt "$CKPT" --jevbench "$JEV" --salida "$RES" --k 0 --device cpu || fallo "jevbench_l2 k=0"
  TODOS_VAR=${CHISPA_TODOS_VAR:-${VARIANTES%% *}}
  TAU=${CHISPA_TAU_NUEVO:-no}
  for v in $VARIANTES; do
    [ -f "$RES/torre-$v.onnx" ] || { estado "train_torre_$v" "FALLO sin torre exportada"; continue; }
    MIN=$(( ($(quedan_min) - 30) / 3 )); MIN=${CHISPA_TODOS_MIN:-$MIN}; [ "$MIN" -lt 2 ] && MIN=2   # tres pasadas de 231 casos y el móvil (~20 min)
    TODOS=(); [ "$v" = "$TODOS_VAR" ] && TODOS=(--todos --minutos "$MIN")
    if "$PY" -u -m model.bench.torre.servidor --jevbench "$JEV" --salida "$RES/servidor-$v" --ckpt "$CKPT" --torre "$RES/torre-$v.onnx" --servidor "$SERV" \
         --tok "$TOK" --repo "$REPO" --puerto $PUERTO --pred "$RES/pred/l2_k0.jsonl" --ort-lib "$CHISPA_ORT_LIB" --exigir-torres "${TODOS[@]}" > "$RES/servidor-$v.log" 2>&1; then estado "train_torre_$v" "OK chispa train --torre y servidor"
    else tail -20 "$RES/servidor-$v.log"; estado "train_torre_$v" "FALLO ver servidor-$v.log"; fallo "servidor $v sin torres calculadas o error"; fi
    if [ "$TAU" != no ] && [ ${#TODOS[@]} -gt 0 ]; then   # misma torre, tau_l2_esquema_nuevo del barrido (abstención 20 %): cuánto contesta L2
      MIN=$(( $(quedan_min) - 8 )); MIN=${CHISPA_TODOS_MIN:-$MIN}; [ "$MIN" -lt 2 ] && MIN=2
      "$PY" -u -m model.bench.torre.servidor --jevbench "$JEV" --salida "$RES/servidor-$v-tau" --ckpt "$CKPT" --torre "$RES/torre-$v.onnx" --servidor "$SERV" \
         --tok "$TOK" --repo "$REPO" --puerto $PUERTO --pred "$RES/pred/l2_k0.jsonl" --ort-lib "$CHISPA_ORT_LIB" --exigir-torres --tau-nuevo "$TAU" --todos --minutos "$MIN" \
         > "$RES/servidor-$v-tau.log" 2>&1 && estado "tau_$v" "OK tau_l2_esquema_nuevo=$TAU" || { tail -20 "$RES/servidor-$v-tau.log"; estado "tau_$v" "FALLO ver servidor-$v-tau.log"; fallo "servidor $v tau $TAU"; }
    fi
  done

  # --- 5b. D1: diagnóstico de paridad y pasadas con la CALIB global del checkpoint ------------------------------------------------------
  echo "== 5b. paridad y CALIB global $(date -u +%T)"
  BASE_CH=$RES/servidor-$TODOS_VAR/servidor/minimo.chispa; BASE_CAPAS=$RES/servidor-$TODOS_VAR/capas_por_caso.jsonl
  diagnosticar() {   # nombre .chispa capas
    "$PY" -u -m model.bench.torre.paridad_servidor diagnosticar --jevbench "$JEV" --ckpt "$CKPT" --chispa "$2" --capas "$3" --pred "$RES/pred/l2_k0.jsonl" \
      --salida "$RES/diag-$1" --n "${CHISPA_N_PARIDAD:-90}" > "$RES/diag-$1.log" 2>&1 && estado "diag_$1" "OK $(tail -c 300 "$RES/diag-$1.log" | tr '\n' ' ' | cut -c1-120)" \
      || { tail -5 "$RES/diag-$1.log"; estado "diag_$1" "FALLO ver diag-$1.log"; fallo "diagnóstico de paridad $1"; }
  }
  pasada() {   # nombre .chispa restantes: los 231 casos por el servidor con este .chispa (sin entrenar otro)
    local m=$(( ($(quedan_min) - 22) / $3 )); [ "$m" -lt 2 ] && m=2; m=${CHISPA_TODOS_MIN:-$m}
    "$PY" -u -m model.bench.torre.servidor --jevbench "$JEV" --salida "$RES/servidor-$1" --ckpt "$CKPT" --torre "$RES/torre-$TODOS_VAR.onnx" --servidor "$SERV" \
      --tok "$TOK" --repo "$REPO" --puerto $PUERTO --pred "$RES/pred/l2_k0.jsonl" --ort-lib "$CHISPA_ORT_LIB" --exigir-torres --todos --minutos "$m" --chispa "$2" \
      > "$RES/servidor-$1.log" 2>&1 && estado "pasada_$1" "OK" || { tail -10 "$RES/servidor-$1.log"; estado "pasada_$1" "FALLO ver servidor-$1.log"; fallo "pasada $1"; }
  }
  if [ -f "$BASE_CH" ]; then   # ¿copia chispa train la CALIB global de L2 (tipos_l2) del l2.chispa?
    "$PY" -u -m model.bench.torre.paridad_servidor tipos-l2 --chispa "$BASE_CH" --ckpt "$CKPT" --jevbench "$JEV" > "$RES/tipos-l2.log" 2>&1 \
      && estado "tipos_l2" "OK $(tail -1 "$RES/tipos-l2.log")" || estado "tipos_l2" "FALLO $(tail -1 "$RES/tipos-l2.log" | cut -c1-120)"
  fi
  if [ -f "$BASE_CH" ] && [ -f "$BASE_CAPAS" ]; then
    diagnosticar base "$BASE_CH" "$BASE_CAPAS"
    if "$PY" -u -m model.bench.torre.paridad_servidor reescribir --ckpt "$CKPT" --jevbench "$JEV" --entrada "$BASE_CH" --salida "$RES/calib-global.chispa" --calib-ckpt \
         > "$RES/reescribir-calib.log" 2>&1; then
      pasada calib "$RES/calib-global.chispa" 2
      [ -f "$RES/servidor-calib/capas_por_caso.jsonl" ] && diagnosticar calib "$RES/calib-global.chispa" "$RES/servidor-calib/capas_por_caso.jsonl"
    else tail -5 "$RES/reescribir-calib.log"; estado "pasada_calib" "FALLO reescribir CALIB"; fallo "reescribir CALIB"; fi
    # la consulta de L2 que mete `chispa train --ckpt` es int8 con la poda base: se cambia por la fp32 sin poda del perfil servidor
    if "$PY" -u -m model.l2.exportar --ckpt "$CKPT" --calib "$RES/calib-score.json" --esquemas "$RES/dev-score.jsonl" --salida "$RES/l2-servidor.chispa" --perfil servidor \
         > "$RES/exportar-l2-servidor.log" 2>&1 \
       && "$PY" -u -m model.bench.torre.paridad_servidor reescribir --ckpt "$CKPT" --jevbench "$JEV" --entrada "$BASE_CH" --salida "$RES/calib-global-l2fp32.chispa" \
            --calib-ckpt --l2-de "$RES/l2-servidor.chispa" >> "$RES/reescribir-calib.log" 2>&1; then
      rm -f "$RES/l2-servidor.chispa"
      pasada calib-l2fp32 "$RES/calib-global-l2fp32.chispa" 1
      [ -f "$RES/servidor-calib-l2fp32/capas_por_caso.jsonl" ] && diagnosticar calib-l2fp32 "$RES/calib-global-l2fp32.chispa" "$RES/servidor-calib-l2fp32/capas_por_caso.jsonl"
    else tail -5 "$RES/exportar-l2-servidor.log"; estado "pasada_calib-l2fp32" "FALLO exportar consulta fp32"; fallo "consulta fp32 sin poda"; fi
  else estado "diag_base" "FALLO sin la pasada base (servidor-$TODOS_VAR)"; fi
else for v in $VARIANTES; do estado "train_torre_$v" "FALLO sin binario del servidor"; done; fi

# --- 5c. D1: perfil móvil con la poda corregida (fp16 y fp32): top-1, MB y latencia ---------------------------------------------------
if [ "${CHISPA_MOVIL:-si}" != no ]; then
  echo "== 5c. móvil $(date -u +%T)"
  mkdir -p "$RES/ampliar" "$RES/comprobacion" && cp "$RES/calib-torre.jsonl" "$RES/ampliar/"
  "$PY" -I -c "
import json, sys
sys.path.insert(0, sys.argv[1])
from model.evaluacion.jevbench import cargar_jevbench
with open(sys.argv[3], 'w', encoding='utf-8') as f:
    for r in cargar_jevbench(sys.argv[2]):
        f.write(json.dumps({k: r[k] for k in ('texto', 'pregunta', 'opciones', 'descripciones')}, ensure_ascii=False) + '\n')" "$REPO" "$JEV" "$RES/comprobacion/jevbench.jsonl"
  # «ampliado»: base + textos de calibración (sin los medidos); «ampliado+eval»: además los textos que mide el banco (la poda corregida: 0 % de <unk>)
  if "$PY" -u -m model.bench.torre.movil medir "$RES/movil" "${CKPT_ARG[@]}" --ampliar "$RES/ampliar" --comprobacion "$RES/comprobacion" --calib "$RES/calib-torre.jsonl" \
       --variantes fp16 fp32 --vocabularios ampliado ampliado+eval --n-calib 100 --filas "${CHISPA_FILAS:-300}" > "$RES/movil.log" 2>&1; then estado movil "OK $RES/movil/informe.md"
  else tail -15 "$RES/movil.log"; estado movil "FALLO ver movil.log"; fallo "movil"; fi
else estado movil "OMITIDO CHISPA_MOVIL=no"; fi

# --- 6. informe ---------------------------------------------------------------------------------------------------------------------------
echo "== 6. informe $(date -u +%T)"
cierre
