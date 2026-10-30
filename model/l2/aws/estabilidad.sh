#!/bin/bash
CHISPA_S3=__CHISPA_S3__
# user-data (≤ 16 KB) de una c6a.2xlarge bajo demanda (Amazon Linux 2023, x86_64, 8 vCPU, sin GPU), root, con internet y rol con s3:GetObject y
# s3:PutObject (sin ListBucket: descargas fichero a fichero), sin SSH. W1: estabilidad de L2 en tres medidas, con el checkpoint de G.8
# (max_tok 256 dentro del checkpoint). El orquestador sustituye __CHISPA_S3__ y sube UN paquete (esperado hasta 45 min tras lanzar):
#   $CHISPA_S3/codigo.tgz    bash model/l2/aws/empaquetar_estabilidad.sh <sha> > codigo.tgz
# Pasos: 1 entorno (Go, Python, torch CPU) · 2 código, checkpoint, e5, potion, datasets de L1 y JevBench · 3 M2 `model.l2.largos` (5 estrategias de
# textos largos, IC95) · 4 M5 `model.l2.diag_score` (ranking, cabeza y datos de score; el meta de tsjev de S3) · 5 M6 `model.l1.frente_l2`
# (macro-F1 L1/L2 por tarea; potion exportado con runtime/l1) · 6 empaqueta. Cada paso deja OK/FALLO en estado.tsv; al salir (trap) sube
# resultados.tgz, estado.tsv y log.txt y apaga. Apagado forzoso a los 90 min (shutdown -h +90).
# Opcionales: CHISPA_CKPT_S3, CHISPA_META_S3 (meta de G.8), CHISPA_JEV_REF, CHISPA_SIN_META=1 (M5 con el censo de conversion-20261027.json).
# Tiempo estimado: ~8 min de entorno y descargas, M2 ~15-25, M5 ~5-10 (más la descarga del meta), M6 ~10-15: ≈ 45-60 min, ≈ 0,3 USD.
# CHISPA_LOCAL=1: prueba en seco sin dnf, pip, descargas ni shutdown, con checkpoint aleatorio y fixtures (max_tok 48, 30 filas por test en M6).
CKPT_S3=${CHISPA_CKPT_S3:-s3://chispa-pruebas-879381269751/general-20261029b/ckpt/mejor.pt}
META_S3=${CHISPA_META_S3:-s3://chispa-pruebas-879381269751/meta-20261027/meta}
LOCAL=${CHISPA_LOCAL:-0}
AQUI=$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)   # solo para la prueba en seco
if [ "$LOCAL" = 1 ]; then [ "${CHISPA_S3#__}" != "$CHISPA_S3" ] && CHISPA_S3=s3://local/estabilidad; else shutdown -h +90; fi
set -uo pipefail
export HOME="${HOME:-/root}"
T0=$(date +%s); TOPE=90
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
# microVM de kindling: torch CPU muere a veces con SIGILL (rc 132); solo en seco se limita a AVX2 y se repite una vez
[ "$LOCAL" = 1 ] && export ONEDNN_MAX_CPU_ISA=${ONEDNN_MAX_CPU_ISA:-AVX2}
reint() { "$@"; local rc=$?; if [ "$rc" = 132 ] && [ "$LOCAL" = 1 ]; then echo "SIGILL: se repite $*" >&2; "$@"; rc=$?; fi; return $rc; }

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
    && "$PY" -m pip install -q --no-cache-dir numpy scipy scikit-learn transformers tokenizers huggingface_hub pyyaml pyarrow datasets \
    || { fallo "pip install"; estado entorno "FALLO pip"; cierre; }
fi
export PATH=/usr/local/go/bin:$HOME/go-sdk/bin:$PATH GOTOOLCHAIN=local GOFLAGS=-mod=mod
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
export PYTHONPATH=$REPO
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
def intenta(*a, **k):
    try:
        s(*a, **k)
    except Exception as e:
        fallos.append(a[0]); print("aviso: no se pudo bajar", a[0], e)
intenta("intfloat/multilingual-e5-small", allow_patterns=["*.json", "*.safetensors", "*.txt", "*.model", "tokenizer*"])
intenta("minishlab/potion-multilingual-128M")
intenta("mteb/amazon_massive_intent", repo_type="dataset", allow_patterns=["*es*", "*.json", "*.md", "*.csv"])
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
if reint timeout "$(tope 35)m" "$PY" -u -m model.l2.largos --ckpt "$CKPT" --jevbench "$JEV" --salida "$RES/m2" "${MAXTOK[@]}" > "$RES/m2.log" 2>&1 \
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
if reint timeout "$(tope 20)m" "$PY" -u -m model.l2.diag_score --ckpt "$CKPT" --jevbench "$JEV" --salida "$RES/m5" "${META_ARG[@]}" "${MAXTOK[@]}" > "$RES/m5.log" 2>&1 \
   && [ -f "$RES/m5/diag_score.json" ]; then
  estado m5_score "OK $("$PY" -I -c "import json,sys; d=json.load(open(sys.argv[1])); g=d['casos']['global']; print('n=%d ckpt=%.3f reajuste=%.3f oraculo=%.3f; arreglo: %s' % (g['n'], g['ckpt'], g['loso'], g['oraculo'], d['arreglo']['donde']))" "$RES/m5/diag_score.json")"
else tail -15 "$RES/m5.log"; estado m5_score "FALLO ver m5.log"; fallo "M5 score"; fi

# --- 5. M6 L1 frente a L2 ----------------------------------------------------------------------------------------------------------------
echo "== 5. M6 L1 frente a L2 $(date -u +%T)"
CONV=(--salida "$LB" --fuentes massive,hatecheck,clinc150,inyecciones); [ "$LOCAL" = 1 ] && CONV+=(--fixtures)
POTION=$BASE/potion.chispa-l1
if "$PY" -m model.datos.convertir "${CONV[@]}" > "$RES/m6-datos.log" 2>&1 \
   && "$PY" runtime/l1/exportar.py "$(ls -d "$HF_HOME"/hub/models--minishlab--potion-multilingual-128M/snapshots/* | head -1)" "$POTION" >> "$RES/m6-datos.log" 2>&1; then
  estado m6_datos "OK $(tail -4 "$RES/m6-datos.log" | grep -c convertida) tareas convertidas, potion $(stat -c %s "$POTION") bytes"
  FILAS=(); [ "$LOCAL" = 1 ] && FILAS=(--max-filas 30)
  if reint timeout "$(tope 40)m" "$PY" -u -m model.l1.frente_l2 --potion "$POTION" --ckpt "$CKPT" --datos "$LB" --salida "$RES/m6" "${FILAS[@]}" > "$RES/m6.log" 2>&1 \
     && [ -f "$RES/m6/frente_l2.json" ]; then
    estado m6_frente_l2 "OK $("$PY" -I -c "import json,sys; d=json.load(open(sys.argv[1])); r=d['resumen_k']; print('media L1/L2 k=%d: %s (%d tareas), cumple>=0,90: %s' % (d['k'], 'sin dato' if r['media'] is None else '%.3f' % r['media'], r['n_tareas'], 'si' if r['cumple'] else 'no'))" "$RES/m6/frente_l2.json")"
  else tail -15 "$RES/m6.log"; estado m6_frente_l2 "FALLO ver m6.log"; fallo "M6 frente a L2"; fi
else tail -10 "$RES/m6-datos.log"; estado m6_datos "FALLO ver m6-datos.log"; estado m6_frente_l2 "FALLO sin datos"; fallo "M6 datos de L1"; fi

# --- 6. cierre ---------------------------------------------------------------------------------------------------------------------------
echo "== 6. cierre $(date -u +%T)"
cat "$RES"/m2/largos.md "$RES"/m5/diag_score.md "$RES"/m6/frente_l2.md > "$RES/informe.md" 2>/dev/null
cierre
