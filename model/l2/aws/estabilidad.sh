#!/bin/bash
CHISPA_S3=__CHISPA_S3__
# user-data (≤ 16 KB) de una c6a.2xlarge bajo demanda (Amazon Linux 2023, x86_64, 8 vCPU, sin GPU), root, con internet y rol con s3:GetObject y
# s3:PutObject (sin ListBucket: descargas fichero a fichero), sin SSH. W1: estabilidad de L2 en tres medidas, con el checkpoint de G.8
# (max_tok 256 dentro del checkpoint). El orquestador sustituye __CHISPA_S3__ y sube UN paquete (esperado hasta 45 min tras lanzar):
#   $CHISPA_S3/codigo.tgz    bash model/l2/aws/empaquetar_estabilidad.sh <sha> > codigo.tgz
# Pasos (6-8, W2, más abajo): 1 entorno (Go, Python, torch CPU) · 2 código, checkpoint, e5, potion, datasets de L1 y JevBench · 3 M2 `model.l2.largos` (5 estrategias de
# textos largos, IC95) · 4 M5 `model.l2.diag_score` (ranking, cabeza y datos de score; el meta de tsjev de S3) · 4b W4 `model.l2.orientacion_score` (ρ de s con el nivel de oro con la torre máxima, la mínima y −s, en JevBench y en el dev de score del meta; ≤ 10 min) · 5 M6 `model.l1.frente_l2`
# (macro-F1 L1/L2 por tarea; potion exportado con runtime/l1) · 6 empaqueta. Cada paso deja OK/FALLO en estado.tsv; al salir (trap) sube
# resultados.tgz, estado.tsv y log.txt y apaga. Apagado forzoso a los 90 min (shutdown -h +90).
# W2 añade al final (pasos 6-8): M1 línea base oficial de la batería de regresión (`chispa train --ckpt` perfil servidor, `chispa-server -tags ort`,
# `chispa evaluar --bateria` DOS veces, umbrales propuestos en umbrales-propuestos.json; salida 0 bien, 1 regresión, 2 configuración mal: el 2 se
# anota con su mensaje en estado.tsv y no se arregla, es de sdk/) · M3 `model.l2.robustez` (L1 y L2 frente a 9 tipos de variantes) · M4
# `model.l2.espanol` (es − en en massive, xnli, sib200 y paws-x, con plan de reentrenamiento si la brecha pasa de 3 puntos).
# Presupuesto (≤ 90 min en c6a.2xlarge, 8 vCPU; cada paso tiene su tope y tope() lo recorta a lo que quede menos 6 min):
#   entorno y descargas ~8 · M2 ≤ 25 · M5 ≤ 12 · M6 ≤ 18 · M1 ≤ 7 (ORT, Go, train) + 2 × ≤ 8 (batería, ~11 000 filas) · M3 ≤ 8 · M4 ≤ 5.
#   Típico ≈ 75 min, techo de los topes ≈ 99 → los últimos pasos se recortan antes que pasarse de los 90.
# Opcionales: CHISPA_ORT_VERSION (1.31.1), CHISPA_MAX_FILAS_M3 (150 filas por tarea), CHISPA_MAX_FILAS_M4 (400 pares por tarea), CHISPA_CKPT_S3, CHISPA_META_S3 (meta de G.8), CHISPA_JEV_REF, CHISPA_SIN_META=1 (M5 con el censo de conversion-20261027.json).
# Tiempo estimado: ~8 min de entorno y descargas, M2 ~15-25, M5 ~5-10 (más la descarga del meta), M6 ~10-15, M1 ~20-30, M3 ~6, M4 ~3: ≈ 75 min, ≈ 0,4 USD.
# CHISPA_LOCAL=1: prueba en seco sin dnf, pip, descargas ni shutdown, con checkpoint aleatorio y fixtures (max_tok 48, 30 filas por test en M6 y M3,
# fixtures de model.datos.convertir y de JevBench en la batería, fixtures_espanol en M4). M1 usa ORT de ~/ort (CHISPA_ORT_DIR) y gcc; sin ellos, OMITIDO.
CKPT_S3=${CHISPA_CKPT_S3:-s3://chispa-pruebas-879381269751/general-20261029b/ckpt/mejor.pt}
META_S3=${CHISPA_META_S3:-s3://chispa-pruebas-879381269751/meta-20261027/meta}
LOCAL=${CHISPA_LOCAL:-0}
AQUI=$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)   # solo para la prueba en seco
if [ "$LOCAL" = 1 ]; then [ "${CHISPA_S3#__}" != "$CHISPA_S3" ] && CHISPA_S3=s3://local/estabilidad; else shutdown -h +90; fi
set -uo pipefail
export HOME="${HOME:-/root}"
T0=$(date +%s); TOPE=90; ORT_VERSION=${CHISPA_ORT_VERSION:-1.31.1}
if [ "$LOCAL" = 1 ]; then BASE=${CHISPA_BASE:-/tmp/chispa-estab}; else BASE=/opt/chispa; fi
mkdir -p "$BASE"
exec > >(tee -a "$BASE/log.txt") 2>&1
echo "== arranque estabilidad $(date -u +%FT%TZ) local=$LOCAL base=$BASE"
REPO=$BASE/repo RES=$BASE/resultados JEV=$BASE/jevbench LB=$BASE/lb_datos META=$BASE/meta
FALLO=""
PY=${CHISPA_PY:-$HOME/venv/bin/python}

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
  cp "$BASE/log.txt" "$RES/log.txt" 2>/dev/null
  rm -f "$BASE/resultados.tgz"
  ( cd "$BASE" && find resultados -type f -size -20000k | LC_ALL=C sort > "$BASE/resultados.lista" && tar -czf "$BASE/resultados.tgz" -T "$BASE/resultados.lista" ) \
    || echo "no se pudo crear resultados.tgz"
  [ -f "$BASE/resultados.tgz" ] && { s3cp "$BASE/resultados.tgz" "$CHISPA_S3/resultados.tgz" || echo "no se pudo subir resultados.tgz"; }
  [ -f "$RES/estado.tsv" ] && { s3cp "$RES/estado.tsv" "$CHISPA_S3/estado.tsv" || echo "no se pudo subir estado.tsv"; }
  s3cp "$BASE/log.txt" "$CHISPA_S3/log.txt" || echo "no se pudo subir log.txt"
  [ "$LOCAL" = 1 ] || shutdown -h now
}
trap subir_y_apagar EXIT
trap 'exit 143' TERM INT HUP
mkdir -p "$RES"
estado() { printf '%s\t%s\n' "$1" "$2" >> "$RES/estado.tsv"; echo "[$1] $2"; }   # estado clave "OK detalle" | "FALLO detalle" | "OMITIDO motivo"
fallo() { echo "FALLO: $*"; FALLO="${FALLO:+$FALLO; }$*"; }
cierre() { echo "== listo $(date -u +%FT%TZ) fallo=${FALLO:-no} ($(( $(date +%s) - T0 )) s)"; echo "== estado.tsv"; cat "$RES/estado.tsv" 2>/dev/null; exit 0; }
quedan_min() { echo $(( TOPE - ($(date +%s) - T0) / 60 )); }
tope() { local m=$(( $(quedan_min) - 6 )); [ "$m" -gt "$1" ] && m=$1; [ "$m" -lt 2 ] && m=2; echo $m; }   # minutos para un paso: el tope propio o lo que quede menos 6
# microVM de kindling: torch CPU muere a veces con SIGILL (rc 132); solo en seco se limita a AVX2 y se repite hasta 3 veces
[ "$LOCAL" = 1 ] && export ONEDNN_MAX_CPU_ISA=${ONEDNN_MAX_CPU_ISA:-AVX2}
reint() { local n=0 rc; while :; do "$@"; rc=$?; n=$((n+1)); { [ "$rc" = 132 ] && [ "$LOCAL" = 1 ] && [ $n -lt 4 ]; } || return $rc; echo "SIGILL: se repite $*" >&2; done; }

# --- 1. entorno -------------------------------------------------------------------------------------------------------------------
export HF_HOME="$HOME/hf"; mkdir -p "$HF_HOME"
if [ "$LOCAL" != 1 ]; then
  echo "== 1. entorno $(date -u +%T)"
  dnf install -y -q gcc tar gzip git python3.11 python3.11-pip || { fallo "dnf install"; estado entorno "FALLO dnf"; cierre; }
  curl -fsSL "https://go.dev/dl/go1.27.1.linux-amd64.tar.gz" | tar -xzC /usr/local || { fallo "descarga de Go"; estado entorno "FALLO Go"; cierre; }
  python3.11 -m venv "$BASE/venv" || { fallo "venv"; estado entorno "FALLO venv"; cierre; }
  PY=$BASE/venv/bin/python
  "$PY" -m pip install -q --no-cache-dir -U pip \
    && "$PY" -m pip install -q --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && "$PY" -m pip install -q --no-cache-dir numpy scipy scikit-learn transformers tokenizers huggingface_hub pyyaml pyarrow datasets onnx onnxscript onnxruntime \
    || { fallo "pip install"; estado entorno "FALLO pip"; cierre; }
fi
ORT_DIR=/opt/ort
if [ "$LOCAL" != 1 ]; then   # M1: ORT para chispa-server (un fallo aquí solo cuesta M1)
  mkdir -p "$ORT_DIR" && curl -fsSL "https://github.com/microsoft/onnxruntime/releases/download/v${ORT_VERSION}/onnxruntime-linux-x64-${ORT_VERSION}.tgz" \
    | tar -xzC "$ORT_DIR" --strip-components=1 || fallo "descarga de ORT $ORT_VERSION"
else ORT_DIR=${CHISPA_ORT_DIR:-$HOME/ort}; fi
export PATH=/usr/local/go/bin:$HOME/go-sdk/bin:$PATH GOTOOLCHAIN=local GOFLAGS=-mod=mod GONOSUMDB='github.com/juan52878911/*'
[ "$LOCAL" = 1 ] && export GOPROXY=off
"$PY" -c "import sys, numpy, scipy, torch, transformers; print(sys.version.split()[0], 'torch', torch.__version__)" && go version \
  && estado entorno "OK $(nproc) vCPU" || { fallo "imports de Python o Go"; estado entorno "FALLO imports"; cierre; }

# --- 2. código, checkpoint, modelos, datos y JevBench -------------------------------------------------------------------------------
echo "== 2. código y datos $(date -u +%T)"
if [ "$LOCAL" = 1 ]; then   # en seco lo empaqueta el propio script (con fixtures)
  d=/tmp/chispa/s3/${CHISPA_S3#s3://}; mkdir -p "$d"
  bash "$AQUI/empaquetar_estabilidad.sh" HEAD --fixtures > "$d/codigo.tgz" || { fallo "empaquetar"; estado paquete "FALLO empaquetar"; cierre; }
fi
rm -rf "$REPO" "$JEV" "$LB" "$META"; mkdir -p "$REPO"
for _ in $(seq 1 90); do   # un paquete a medias no se acepta: hasta 45 min de reintentos
  s3cp "$CHISPA_S3/codigo.tgz" "$BASE/codigo.tgz" 2>/dev/null && tar -tzf "$BASE/codigo.tgz" >/dev/null 2>&1 && break
  rm -f "$BASE/codigo.tgz"; [ "$LOCAL" = 1 ] && break; sleep 30
done
tar -xzf "$BASE/codigo.tgz" -C "$REPO" && estado paquete "OK" || { fallo "no llegó un codigo.tgz válido"; estado paquete "FALLO sin codigo.tgz"; cierre; }
cd "$REPO" || cierre
export PYTHONPATH=$REPO:$REPO/sdk/python
if [ "$LOCAL" != 1 ]; then export GOPROXY=file://$REPO/gomod-proxy,https://proxy.golang.org; fi
{ lscpu; echo "nproc: $(nproc)"; } > "$RES/hardware.txt" 2>&1
CKPT=$BASE/mejor.pt
if [ "$LOCAL" = 1 ]; then   # checkpoint aleatorio, como e2e.sh
  "$PY" -I -c "import sys; sys.path.insert(0, sys.argv[1]); import torch; from model.l2.exportar import modelo_aleatorio
torch.save({'modelo': modelo_aleatorio().state_dict(), 'cabezas': [], 'max_tok': 128}, sys.argv[2])" "$REPO" "$CKPT" \
    && estado checkpoint "OK aleatorio" || { fallo "checkpoint aleatorio"; estado checkpoint "FALLO"; cierre; }
else s3cp "$CKPT_S3" "$CKPT" && estado checkpoint "OK $(stat -c %s "$CKPT") bytes" || { fallo "checkpoint $CKPT_S3"; estado checkpoint "FALLO"; cierre; }
fi
if [ "$LOCAL" != 1 ]; then
  "$PY" -I - <<'PYEOF' || fallo "descarga de modelos y datasets de HF"
import sys
from huggingface_hub import snapshot_download as s
fallos = []
def intenta(*a, opcional=False, **k):
    try:
        s(*a, **k)
    except Exception as e:
        if not opcional:
            fallos.append(a[0])
        print("aviso: no se pudo bajar", a[0], e)
intenta("intfloat/multilingual-e5-small", allow_patterns=["*.json", "*.safetensors", "*.txt", "*.model", "tokenizer*"])
intenta("minishlab/potion-multilingual-128M")
intenta("mteb/amazon_massive_intent", repo_type="dataset", allow_patterns=["*es*", "*/en.json.gz", "*.json", "*.md", "*.csv"])
intenta("tanaos/synthetic-spam-detection-dataset-spanish", repo_type="dataset")   # M1: el conjunto «spam» de la batería
# M4: pares es/en (solo test) y las tarjetas con la licencia de las fuentes del plan de reentrenamiento; si faltan, M4 mide menos pares
intenta("facebook/xnli", repo_type="dataset", allow_patterns=["es/test-*", "en/test-*", "README.md"], opcional=True)
intenta("google-research-datasets/paws-x", repo_type="dataset", allow_patterns=["es/test-*", "en/test-*", "README.md"], opcional=True)
intenta("Davlan/sib200", repo_type="dataset", allow_patterns=["data/spa_Latn/*", "data/eng_Latn/*", "README.md"], opcional=True)
for r in ("SINAI/ALIA-es-discriminative-hate-speech", "Multilingual-Perspectivist-NLU/MultiPICo", "bgonzalezbustamante/toxicity-Constitution-ES",
          "bgonzalezbustamante/toxicity-protests-ES"):
    intenta(r, repo_type="dataset", allow_patterns=["README.md"], opcional=True)
intenta("Paul/hatecheck-spanish", repo_type="dataset", allow_patterns=["*es*", "*.json", "*.md", "*.csv"])
intenta("clinc/clinc_oos", repo_type="dataset")
intenta("deepset/prompt-injections", repo_type="dataset")
sys.exit(1 if fallos else 0)
PYEOF
fi
ls "$HF_HOME"/hub/models--intfloat--multilingual-e5-small/snapshots/*/config.json >/dev/null 2>&1 || { fallo "e5 no está en $HF_HOME"; estado modelos "FALLO sin e5"; cierre; }
export HF_HUB_OFFLINE=1
if [ "$LOCAL" = 1 ]; then cp -r "$REPO/model/l2/tests/fixtures_largos/jevbench" "$JEV" || { fallo "sin JevBench local"; cierre; }
else
  git clone -q https://github.com/fstandhartinger/jevbench "$JEV" && { [ -z "${CHISPA_JEV_REF:-}" ] || git -C "$JEV" checkout -q "$CHISPA_JEV_REF"; } \
    || { fallo "git clone de JevBench"; estado jevbench "FALLO clone"; cierre; }
fi
{ git -C "$JEV" rev-parse HEAD 2>/dev/null || echo fixture; } > "$RES/jevbench-sha.txt"
NCASOS=$(cat "$JEV"/datasets/public/*.jsonl | wc -l)
estado jevbench "OK $NCASOS casos ($(cat "$RES/jevbench-sha.txt" | cut -c1-12))"
MAXTOK=(); [ "$LOCAL" = 1 ] && MAXTOK=(--max-tok 48)   # en seco, con textos cortos, para que haya casos largos

# --- 3. M2 textos largos ---------------------------------------------------------------------------------------------------------------
echo "== 3. M2 largos $(date -u +%T)"
if reint timeout "$(tope 25)m" "$PY" -u -m model.l2.largos --ckpt "$CKPT" --jevbench "$JEV" --salida "$RES/m2" "${MAXTOK[@]}" > "$RES/m2.log" 2>&1 \
   && [ -f "$RES/m2/largos.json" ]; then
  estado m2_largos "OK $("$PY" -I -c "import json,sys; d=json.load(open(sys.argv[1])); r=d['recomendacion']; print('%d casos, %d largos, recomienda %s' % (d['n'], d['n_largos'], r['estrategia']))" "$RES/m2/largos.json")"
else tail -15 "$RES/m2.log"; estado m2_largos "FALLO ver m2.log"; fallo "M2 largos"; fi

# --- 4. M5 diagnóstico de score ----------------------------------------------------------------------------------------------------------
echo "== 4. M5 score $(date -u +%T)"
META_ARG=()
if [ "$LOCAL" = 1 ]; then   # meta inventado: dos tareas score (K = 5 y 3) y una choice de tsjev
  "$PY" -I - "$META" <<'PYEOF' && META_ARG=(--meta "$META") && estado m5_meta "OK inventado"
import gzip, json, os, sys
os.makedirs(sys.argv[1] + "/tsjev")
with gzip.open(sys.argv[1] + "/tsjev/train-00000.jsonl.gz", "wt", encoding="utf-8") as f:
    for tarea, tipo, n, k in (("demo/s5", "score", 30, 5), ("demo/s3", "score", 12, 3), ("demo/c", "choice", 50, 3)):
        for i in range(n):
            f.write(json.dumps({"id": "tsjev:train:%s-%d" % (tarea[-2:], i), "split": "train", "tarea": tarea, "tipo": tipo, "opciones": [str(j + 1) for j in range(k)]}) + "\n")
with gzip.open(sys.argv[1] + "/tsjev/validation-00000.jsonl.gz", "wt", encoding="utf-8") as f:   # dev de score con texto, para orientacion_score
    for tarea, k, n in (("demo/s5", 5, 30), ("demo/s3", 3, 12)):
        for i in range(n):
            ops = [str(j + 1) for j in range(k)]
            f.write(json.dumps({"id": "tsjev:dev:%s-%d" % (tarea[-2:], i), "split": "dev", "tarea": tarea, "tipo": "score", "pregunta": "¿Qué gravedad tiene?",
                                "texto": "mensaje inventado %d" % i, "opciones": ops, "descripciones": {o: "nivel " + o for o in ops}, "etiqueta": ops[i % k]}) + "\n")
PYEOF
elif [ "${CHISPA_SIN_META:-0}" = 1 ]; then estado m5_meta "OMITIDO CHISPA_SIN_META=1 (censo de conversion-20261027.json)"
else   # solo los ficheros de tsjev del meta de G.8 (los de synzs pesan y no tienen score)
  "$PY" -I -c 'import json,sys; print("\n".join(f for f in json.load(open(sys.argv[1]))["ficheros"] if f.startswith("tsjev/")))' \
    "$REPO/model/meta/resultados/conversion-20261027.json" > "$BASE/meta.lista"
  NM=0; NF=0
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    mkdir -p "$META/$(dirname "$f")"
    if s3cp "$META_S3/$f" "$META/$f" 2>/dev/null; then NM=$((NM+1)); else NF=$((NF+1)); echo "aviso: no se pudo bajar $f"; fi
  done < "$BASE/meta.lista"
  if [ "$NF" = 0 ] && [ "$NM" -gt 0 ]; then META_ARG=(--meta "$META"); estado m5_meta "OK $NM ficheros de tsjev"
  else estado m5_meta "FALLO $NF de $((NM+NF)) ficheros sin bajar (se usa el censo de conversion-20261027.json)"; fallo "meta de tsjev"; fi
fi
if reint timeout "$(tope 12)m" "$PY" -u -m model.l2.diag_score --ckpt "$CKPT" --jevbench "$JEV" --salida "$RES/m5" "${META_ARG[@]}" "${MAXTOK[@]}" > "$RES/m5.log" 2>&1 \
   && [ -f "$RES/m5/diag_score.json" ]; then
  estado m5_score "OK $("$PY" -I -c "import json,sys; d=json.load(open(sys.argv[1])); g=d['casos']['global']; print('n=%d ckpt=%.3f reajuste=%.3f oraculo=%.3f; arreglo: %s' % (g['n'], g['ckpt'], g['loso'], g['oraculo'], d['arreglo']['donde']))" "$RES/m5/diag_score.json")"
else tail -15 "$RES/m5.log"; estado m5_score "FALLO ver m5.log"; fallo "M5 score"; fi

# --- 4b. orientación de score (W4 a): ρ de s con el nivel de oro, torre máxima/mínima y s invertida, en JevBench y en el dev del meta --------
echo "== 4b. orientacion_score $(date -u +%T)"
if reint timeout "$(tope 10)m" "$PY" -u -m model.l2.orientacion_score --ckpt "$CKPT" --jevbench "$JEV" --salida "$RES/orientacion" "${META_ARG[@]}" "${MAXTOK[@]}" > "$RES/orientacion.log" 2>&1 \
   && [ -f "$RES/orientacion/orientacion_score.json" ]; then
  estado orientacion_score "OK $("$PY" -I -c "import json,sys; d=json.load(open(sys.argv[1])); j=d['jevbench']['global']; m=(d['meta'] or {}).get('global') or {}; print('jev rho max/min/inv=%.2f/%.2f/%.2f; meta rho max=%s; %s' % (j['rho_max'], j['rho_min'], j['rho_invertida'], ('%.2f' % m['rho_max']) if m else 'sin meta', d['veredicto']))" "$RES/orientacion/orientacion_score.json")"
else tail -15 "$RES/orientacion.log"; estado orientacion_score "FALLO ver orientacion.log"; fallo "orientacion_score"; fi

# --- 5. M6 L1 frente a L2 ----------------------------------------------------------------------------------------------------------------
echo "== 5. M6 L1 frente a L2 $(date -u +%T)"
CONV=(--salida "$LB" --fuentes massive,hatecheck,clinc150,inyecciones); [ "$LOCAL" = 1 ] && CONV+=(--fixtures)
POTION=$BASE/potion.chispa-l1
if "$PY" -m model.datos.convertir "${CONV[@]}" > "$RES/m6-datos.log" 2>&1 \
   && "$PY" runtime/l1/exportar.py "$(ls -d "$HF_HOME"/hub/models--minishlab--potion-multilingual-128M/snapshots/* | head -1)" "$POTION" >> "$RES/m6-datos.log" 2>&1; then
  estado m6_datos "OK $(grep -c convertida "$RES/m6-datos.log") tareas convertidas, potion $(stat -c %s "$POTION") bytes"
  FILAS=(); [ "$LOCAL" = 1 ] && FILAS=(--max-filas 30)
  if reint timeout "$(tope 18)m" "$PY" -u -m model.l1.frente_l2 --potion "$POTION" --ckpt "$CKPT" --datos "$LB" --salida "$RES/m6" "${FILAS[@]}" > "$RES/m6.log" 2>&1 \
     && [ -f "$RES/m6/frente_l2.json" ]; then
    estado m6_frente_l2 "OK $("$PY" -I -c "import json,sys; d=json.load(open(sys.argv[1])); r=d['resumen_k']; print('media L1/L2 k=%d: %s (%d tareas), cumple>=0,90: %s' % (d['k'], 'sin dato' if r['media'] is None else '%.3f' % r['media'], r['n_tareas'], 'si' if r['cumple'] else 'no'))" "$RES/m6/frente_l2.json")"
  else tail -15 "$RES/m6.log"; estado m6_frente_l2 "FALLO ver m6.log"; fallo "M6 frente a L2"; fi
else tail -10 "$RES/m6-datos.log"; estado m6_datos "FALLO ver m6-datos.log"; estado m6_frente_l2 "FALLO sin datos"; fallo "M6 datos de L1"; fi

# --- 6. M1 línea base oficial de la batería de regresión ------------------------------------------------------------------------------
echo "== 6. M1 batería $(date -u +%T)"
DATOS=$BASE/datos_bateria TOK=$BASE/e5.chispa-tok SERV=$BASE/chispa-server M=$BASE/g8.chispa
ORT_LIB=$ORT_DIR/lib/libonnxruntime.so.$ORT_VERSION
M1_LISTO=0
if [ ! -f "$ORT_LIB" ] || ! command -v gcc >/dev/null; then   # en seco, sin ORT ni gcc en el nodo
  estado m1_modelo "OMITIDO sin ORT ($ORT_LIB) o sin gcc"; estado m1_bateria_1 "OMITIDO sin ORT"; estado m1_bateria_2 "OMITIDO sin ORT"
  [ "$LOCAL" = 1 ] || fallo "M1 sin ORT"
else
  export CGO_ENABLED=1 LD_LIBRARY_PATH=$ORT_DIR/lib CHISPA_ORT_LIB=$ORT_LIB
  E5=$(ls -d "$HF_HOME"/hub/models--intfloat--multilingual-e5-small/snapshots/*/ | head -1)
  # esquema mínimo de e2e.sh (model/bench/torre/servidor.py): L2 y las ESQUEMAS salen del checkpoint, el esquema solo da el contenedor
  cat > "$BASE/esquema-minimo.json" <<'JSON'
{"id": "minimo-saludo", "pregunta": "¿El mensaje es un saludo o una despedida?", "tipo": "choice",
 "opciones": {"saludo": "La persona saluda al empezar.", "despedida": "La persona se despide al terminar."}}
JSON
  "$PY" -I - "$BASE/ejemplos-minimo.jsonl" <<'PYEOF'
import json, sys
S = ["hola, buenos días a todos", "buenas tardes, ¿cómo estáis?", "qué tal, encantado de verte", "hola de nuevo", "muy buenas", "saludos desde aquí",
     "hey, ¿hay alguien?", "bienvenidos al grupo"]
D = ["adiós, hasta mañana", "nos vemos pronto", "me voy, que paséis buena noche", "hasta luego", "chao, cuídate", "un abrazo y hasta la próxima",
     "me despido por hoy", "buen viaje y hasta pronto"]
with open(sys.argv[1], "w", encoding="utf-8") as f:
    for t, e in [(t, "saludo") for t in S] + [(t, "despedida") for t in D]:
        f.write(json.dumps({"texto": t, "etiqueta": e}, ensure_ascii=False) + "\n")
PYEOF
  if "$PY" -I "$REPO/runtime/tok/exportar.py" "$E5" "$TOK" > "$RES/m1-build.log" 2>&1 \
     && ( cd "$REPO/server" && timeout "$(tope 7)m" go build -tags ort -ldflags "-X github.com/juan52878911/chispa/server/decide.RutaORT=$ORT_LIB" -o "$SERV" ./cmd/chispa-server ) >> "$RES/m1-build.log" 2>&1 \
     && ( cd "$REPO" && reint timeout "$(tope 7)m" "$PY" -u -m model.l2.exportar --torre-onnx "$BASE/torre-m1.onnx" --ckpt "$CKPT" --cuant-torre ninguna \
            $([ "$LOCAL" = 1 ] || echo --sin-poda) ) >> "$RES/m1-build.log" 2>&1 \
     && ( cd "$REPO" && reint timeout "$(tope 7)m" "$PY" -u -m chispa train --ejemplos "$BASE/ejemplos-minimo.jsonl" --esquema "$BASE/esquema-minimo.json" \
            --salida "$M" --ckpt "$CKPT" --perfil servidor --torre "$BASE/torre-m1.onnx" --repo "$REPO" ) >> "$RES/m1-build.log" 2>&1 \
     && [ -s "$M" ] && [ -x "$SERV" ]; then
    estado m1_modelo "OK .chispa $(stat -c %s "$M") bytes (chispa train --ckpt, perfil servidor), chispa-server -tags ort, tokenizador e5"
    # /healthz debe anunciar las capas efectivas y torre_al_vuelo (sin torre, ningún esquema nuevo tiene opinión: M1 «sin probs», 2026-11-02)
    "$SERV" -addr 127.0.0.1:8097 -modelo "$M" -tok "$TOK" > "$RES/m1-healthz-servidor.log" 2>&1 & HP=$!
    for _ in $(seq 1 60); do curl -fsS http://127.0.0.1:8097/healthz > "$RES/m1-healthz.json" 2>/dev/null && break; sleep 1; done
    kill $HP 2>/dev/null; wait $HP 2>/dev/null
    if grep -q '"torre_al_vuelo": *true' "$RES/m1-healthz.json" 2>/dev/null; then estado m1_healthz "OK $(tr -d '\n ' < "$RES/m1-healthz.json" | cut -c1-150)"
    else estado m1_healthz "FALLO sin torre_al_vuelo: $(tr -d '\n ' < "$RES/m1-healthz.json" 2>/dev/null | cut -c1-150)"; fi
    # datos: las fuentes que usa el manifiesto (massive, clinc150, hatecheck, spam, inyecciones; herramientas va en el repo y JevBench en $JEV)
    CONV=(--salida "$DATOS" --fuentes massive,hatecheck,clinc150,inyecciones,spam_tanaos); [ "$LOCAL" = 1 ] && CONV+=(--fixtures)
    if "$PY" -m model.datos.convertir "${CONV[@]}" > "$RES/m1-datos.log" 2>&1; then
      estado m1_datos "OK $(grep -c convertida "$RES/m1-datos.log") fuentes convertidas"; M1_LISTO=1
    else tail -8 "$RES/m1-datos.log"; estado m1_datos "FALLO ver m1-datos.log"; fallo "M1 datos"; fi
  else tail -12 "$RES/m1-build.log"; estado m1_modelo "FALLO ver m1-build.log"; estado m1_bateria_1 "FALLO sin modelo"; estado m1_bateria_2 "FALLO sin modelo"; fallo "M1 modelo, servidor o tokenizador"; fi
fi
LB_ARG=(--guardar-linea-base "$RES/linea-base-g8.json"); [ "$LOCAL" = 1 ] && LB_ARG=()   # en seco la corrida es parcial (fixtures) y chispa no guarda su línea base (código 2)
bateria() {   # n: una corrida de la batería; el código de salida manda (0 bien, 1 regresión, 2 configuración mal)
  ( cd "$REPO" && JEVBENCH_DIR=$JEV/datasets/public CHISPA_DATOS=$DATOS CHISPA_REPO=$REPO PYTHONPATH=$REPO/sdk/python \
      timeout "$(tope 8)m" "$PY" -u -m chispa evaluar --bateria sdk/python/ejemplos/bateria.json --modelo "$M" --tok "$TOK" --servidor "$SERV" \
        --salida "$RES/bateria-g8-$1" "${LB_ARG[@]}" ) > "$RES/bateria-$1.log" 2>&1
  local rc=$?
  case $rc in
    0) estado "m1_bateria_$1" "OK $("$PY" -I -c "import json,sys; g=json.load(open(sys.argv[1]))['global']; print('n=%d exactitud=%.4f f1_macro=%.4f p50=%.1f ms' % (g['n'], g['exactitud'], g['f1_macro'], g['p50_ms']))" "$RES/bateria-g8-$1.json")";;
    1) estado "m1_bateria_$1" "OK con regresión (código 1) frente a la línea base"; echo "batería $1: código 1";;
    2) estado "m1_bateria_$1" "FALLO configuración (código 2), fallo de la batería (sdk/, no se arregla aquí): $(grep -v '^chispa: aviso' "$RES/bateria-$1.log" | tail -1 | cut -c1-300)"
       fallo "M1 batería $1: código 2"; return 2;;
    *) tail -8 "$RES/bateria-$1.log"; estado "m1_bateria_$1" "FALLO código $rc (124 = tiempo agotado) ver bateria-$1.log"; fallo "M1 batería $1: código $rc"; return $rc;;
  esac
}
if [ "$M1_LISTO" = 1 ]; then
  bateria 1 && bateria 2   # no se repite si la primera falla: el mismo error saldría otra vez
  if [ -f "$RES/bateria-g8-1.json" ] && [ -f "$RES/bateria-g8-2.json" ]; then
    if "$PY" -m model.l2.umbrales_bateria --corridas "$RES/bateria-g8-1.json" "$RES/bateria-g8-2.json" --manifiesto "$REPO/sdk/python/ejemplos/bateria.json" \
         --salida "$RES/umbrales-propuestos.json" > "$RES/m1-umbrales.log" 2>&1; then
      estado m1_umbrales "OK $("$PY" -I -c "import json,sys; d=json.load(open(sys.argv[1])); print('%d métricas, %d conjuntos con umbral propio, %d avisos' % (len(d['umbrales']) - ('por_conjunto' in d['umbrales']), len(d['umbrales'].get('por_conjunto', {})), len(d['avisos'])))" "$RES/umbrales-propuestos.json")"
    else tail -8 "$RES/m1-umbrales.log"; estado m1_umbrales "FALLO ver m1-umbrales.log"; fallo "M1 umbrales"; fi
  else estado m1_umbrales "FALLO sin las dos corridas"; fi
else estado m1_umbrales "OMITIDO sin corridas de la batería (ver m1_modelo)"; fi

# --- 7. M3 robustez de L1 y L2 frente a variantes ---------------------------------------------------------------------------------------
echo "== 7. M3 robustez $(date -u +%T)"
FILAS3=(--max-filas "${CHISPA_MAX_FILAS_M3:-150}"); [ "$LOCAL" = 1 ] && FILAS3=(--max-filas 30)
if [ -f "$POTION" ] && [ -d "$LB" ]; then
  if reint timeout "$(tope 8)m" "$PY" -u -m model.l2.robustez --ckpt "$CKPT" --potion "$POTION" --datos "$LB" --salida "$RES/m3" "${FILAS3[@]}" "${MAXTOK[@]}" \
       > "$RES/m3.log" 2>&1 && [ -f "$RES/m3/robustez.json" ]; then
    estado m3_robustez "OK $("$PY" -I -c "
import json, sys
d = json.load(open(sys.argv[1])); g = d['global']
def peor(m):
    t, r = max(g[m].items(), key=lambda kv: kv[1]['pct_cambia']); return '%s %s %.1f %%' % (m, t, 100 * r['pct_cambia'])
print('%d tareas, peor tipo: %s, %s; %d (modelo, tipo) por encima del 5 %%, %d arreglos propuestos' % (len(d['tareas']), peor('L1'), peor('L2'),
      sum(1 for m in g for r in g[m].values() if r['pct_cambia'] > d['umbral_cambio']), len(d['arreglos'])))" "$RES/m3/robustez.json")"
  else tail -15 "$RES/m3.log"; estado m3_robustez "FALLO ver m3.log"; fallo "M3 robustez"; fi
else estado m3_robustez "FALLO sin el potion o los datos de M6 (falló m6_datos)"; fallo "M3 sin datos de M6"; fi

# --- 8. M4 español frente a inglés ---------------------------------------------------------------------------------------------------------
echo "== 8. M4 español $(date -u +%T)"
HF4=(); [ "$LOCAL" = 1 ] && HF4=(--hf "$REPO/model/l2/tests/fixtures_espanol")
if reint timeout "$(tope 5)m" "$PY" -u -m model.l2.espanol --ckpt "$CKPT" --salida "$RES/m4" --max-filas "$([ "$LOCAL" = 1 ] && echo 30 || echo "${CHISPA_MAX_FILAS_M4:-400}")" \
     "${HF4[@]}" "${MAXTOK[@]}" > "$RES/m4.log" 2>&1 && [ -f "$RES/m4/espanol.json" ]; then
  estado m4_espanol "OK $("$PY" -I -c "
import json, sys
d = json.load(open(sys.argv[1])); m = d['tareas']['__media__']
print('%d pares, Δ(es−en) exactitud %+.1f pts [%+.1f, %+.1f], F1 %+.1f pts; brecha > 3 pts: %s; no medidos: %s' % (len(d['tareas']) - 1, 100 * m['d_acc'],
      100 * m['d_acc_ic95'][0], 100 * m['d_acc_ic95'][1], 100 * m['d_f1'], 'si (plan.md)' if d['brecha'] else 'no', ', '.join(d['no_medido']) or 'ninguno'))" "$RES/m4/espanol.json")"
else tail -15 "$RES/m4.log"; estado m4_espanol "FALLO ver m4.log"; fallo "M4 español"; fi

# --- 9. cierre ---------------------------------------------------------------------------------------------------------------------------
echo "== 9. cierre $(date -u +%T)"
cat "$RES"/m2/largos.md "$RES"/m5/diag_score.md "$RES"/orientacion/orientacion_score.md "$RES"/m6/frente_l2.md "$RES"/bateria-g8-1.md "$RES"/m3/robustez.md "$RES"/m4/espanol.md "$RES"/m4/plan.md > "$RES/informe.md" 2>/dev/null
cierre
