#!/bin/bash
CHISPA_S3=__CHISPA_S3__
# user-data (≤ 16 KB) de una c6a.2xlarge bajo demanda (Amazon Linux 2023, x86_64, 8 vCPU, sin GPU; torch con 4 hilos), root, con internet y rol con
# s3:GetObject y s3:PutObject (sin ListBucket), sin SSH. W12: Laya (convaiinnovations/laya, `pip install laya`) zero-shot, sin ajustar, frente a Chispa:
# `multilingual` y `typed-decisions` sobre las mismas filas de la batería (sdk/python/ejemplos/bateria.json, split test) y en M4 (MASSIVE-es y MMMLU ES_LA).
# COSTE DECLARADO: ≈ 0,3 USD (c6a.2xlarge ≈ 0,31 USD/h × ≤ 1,5 h con apagado forzoso a los 90 min; sin GPU).
# El orquestador sustituye __CHISPA_S3__ y sube UN paquete (esperado hasta 45 min tras lanzar):
#   $CHISPA_S3/codigo.tgz    bash model/evaluacion/aws/empaquetar_laya.sh <sha> > codigo.tgz
# Pasos: 1 entorno · 2 código, datos de HF y JevBench · 3 datos (model.datos.convertir, como el M1 de estabilidad.sh) · 4 PRUEBA DE VELOCIDAD (50 preguntas de
# massive con multilingual; si la proyección del total pasa de 70 min se recorta con un tope de filas por conjunto, determinista y anotado; si ni con 50
# filas cabe, FALLO y no sigue) · 5 batería · 6 M4 · 7 licencia (tarjetas de HF) · 8 tabla laya-frente-chispa.md.
# Al salir (trap) sube resultados.tgz, estado.tsv, laya-frente-chispa.md y log.txt y apaga. Apagado forzoso a los 90 min (shutdown -h +90).
# Opcionales: CHISPA_MAX_FILAS_M4 (200 pares por conjunto), CHISPA_JEV_REF.
# CHISPA_LOCAL=1: prueba en seco sin dnf, pip, descargas ni shutdown, con un Laya falso (RouterFalso: misma interfaz Router.predict, devuelve la primera
# opción) y fixtures (model.datos.convertir --fixtures, JevBench y M4 de fixtures, tarjeta inventada).
LOCAL=${CHISPA_LOCAL:-0}
AQUI=$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)   # solo para la prueba en seco
if [ "$LOCAL" = 1 ]; then [ "${CHISPA_S3#__}" != "$CHISPA_S3" ] && CHISPA_S3=s3://local/laya; else shutdown -h +90; fi
set -uo pipefail
export HOME="${HOME:-/root}"
T0=$(date +%s); TOPE=90
if [ "$LOCAL" = 1 ]; then BASE=${CHISPA_BASE:-/tmp/chispa-laya}; else BASE=/opt/chispa; fi
mkdir -p "$BASE"
exec > >(tee -a "$BASE/log.txt") 2>&1
echo "== arranque laya $(date -u +%FT%TZ) local=$LOCAL base=$BASE"
REPO=$BASE/repo RES=$BASE/resultados JEV=$BASE/jevbench DATOS=$BASE/datos_bateria
FALLO=""
PY=${CHISPA_PY:-$HOME/venv/bin/python}
M4N=${CHISPA_MAX_FILAS_M4:-200}

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
  [ -f "$RES/laya-frente-chispa.md" ] && { s3cp "$RES/laya-frente-chispa.md" "$CHISPA_S3/laya-frente-chispa.md" || echo "no se pudo subir laya-frente-chispa.md"; }
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

# --- 1. entorno ---------------------------------------------------------------------------------------------------------------------
export HF_HOME="$HOME/hf"; mkdir -p "$HF_HOME"
if [ "$LOCAL" != 1 ]; then
  echo "== 1. entorno $(date -u +%T)"
  dnf install -y -q tar gzip git python3.11 python3.11-pip || { fallo "dnf install"; estado entorno "FALLO dnf"; cierre; }
  python3.11 -m venv "$BASE/venv" || { fallo "venv"; estado entorno "FALLO venv"; cierre; }
  PY=$BASE/venv/bin/python
  "$PY" -m pip install -q --no-cache-dir -U pip \
    && "$PY" -m pip install -q --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && "$PY" -m pip install -q --no-cache-dir numpy scipy scikit-learn transformers tokenizers huggingface_hub pyyaml pyarrow datasets laya \
    || { fallo "pip install"; estado entorno "FALLO pip"; cierre; }
  LAYA_V=$("$PY" -I -c "from importlib import metadata as m; print(m.version('laya'))" 2>/dev/null || echo "?")
else LAYA_V="falso"; fi
"$PY" -c "import sys, numpy, torch, transformers; print(sys.version.split()[0], 'torch', torch.__version__)" \
  && estado entorno "OK $(nproc) vCPU, laya $LAYA_V" || { fallo "imports de Python"; estado entorno "FALLO imports"; cierre; }

# --- 2. código, datos de HF y JevBench ----------------------------------------------------------------------------------------------
echo "== 2. código y datos $(date -u +%T)"
if [ "$LOCAL" = 1 ]; then   # en seco lo empaqueta el propio script (con fixtures)
  d=/tmp/chispa/s3/${CHISPA_S3#s3://}; mkdir -p "$d"
  bash "$AQUI/empaquetar_laya.sh" HEAD --fixtures > "$d/codigo.tgz" || { fallo "empaquetar"; estado paquete "FALLO empaquetar"; cierre; }
fi
rm -rf "$REPO" "$JEV" "$DATOS"; mkdir -p "$REPO"
for _ in $(seq 1 90); do   # un paquete a medias no se acepta: hasta 45 min de reintentos
  s3cp "$CHISPA_S3/codigo.tgz" "$BASE/codigo.tgz" 2>/dev/null && tar -tzf "$BASE/codigo.tgz" >/dev/null 2>&1 && break
  rm -f "$BASE/codigo.tgz"; [ "$LOCAL" = 1 ] && break; sleep 30
done
tar -xzf "$BASE/codigo.tgz" -C "$REPO" && estado paquete "OK" || { fallo "no llegó un codigo.tgz válido"; estado paquete "FALLO sin codigo.tgz"; cierre; }
cd "$REPO" || cierre
export PYTHONPATH=$REPO:$REPO/sdk/python
{ lscpu; echo "nproc: $(nproc)"; } > "$RES/hardware.txt" 2>&1
B1=$REPO/model/l2/resultados/linea-base-oficial-20261102/linea-base.json B2=$REPO/model/l2/resultados/linea-base-v2-20261102/linea-base-v2.json
[ -s "$B1" ] && [ -s "$B2" ] && estado lineas_base "OK ajuste 1 y v2" || { fallo "faltan los linea-base*.json de Chispa"; estado lineas_base "FALLO"; cierre; }
if [ "$LOCAL" != 1 ]; then
  "$PY" -I - <<'PYEOF' || fallo "descarga de datasets de HF"
import sys
from huggingface_hub import snapshot_download as s
fallos = []
def intenta(*a, **k):
    try:
        s(*a, **k)
    except Exception as e:
        fallos.append(a[0])
        print("aviso: no se pudo bajar", a[0], e)
intenta("mteb/amazon_massive_intent", repo_type="dataset", allow_patterns=["*es*", "*/en.json.gz", "*.json", "*.md", "*.csv"])   # massive (batería) y M4
intenta("tanaos/synthetic-spam-detection-dataset-spanish", repo_type="dataset")
intenta("Paul/hatecheck-spanish", repo_type="dataset", allow_patterns=["*es*", "*.json", "*.md", "*.csv"])
intenta("clinc/clinc_oos", repo_type="dataset")
intenta("deepset/prompt-injections", repo_type="dataset")
intenta("openai/MMMLU", repo_type="dataset", allow_patterns=["test/mmlu_ES-LA.csv", "README.md"])   # M4: español
intenta("cais/mmlu", repo_type="dataset", allow_patterns=["all/test-*", "README.md"])               # M4: su pareja en inglés
sys.exit(1 if fallos else 0)
PYEOF
  git clone -q https://github.com/fstandhartinger/jevbench "$JEV" && { [ -z "${CHISPA_JEV_REF:-}" ] || git -C "$JEV" checkout -q "$CHISPA_JEV_REF"; } \
    || { fallo "git clone de JevBench"; estado jevbench "FALLO clone"; cierre; }
else cp -r "$REPO/model/l2/tests/fixtures_largos/jevbench" "$JEV" || { fallo "sin JevBench local"; cierre; }; fi
{ git -C "$JEV" rev-parse HEAD 2>/dev/null || echo fixture; } > "$RES/jevbench-sha.txt"
estado jevbench "OK $(cat "$JEV"/datasets/public/*.jsonl | wc -l) casos ($(cut -c1-12 "$RES/jevbench-sha.txt"))"

# --- 3. datos: los mismos de M1 en estabilidad.sh -----------------------------------------------------------------------------------
echo "== 3. datos $(date -u +%T)"
CONV=(--salida "$DATOS" --fuentes massive,hatecheck,clinc150,inyecciones,spam_tanaos); [ "$LOCAL" = 1 ] && CONV+=(--fixtures)
if "$PY" -m model.datos.convertir "${CONV[@]}" > "$RES/datos.log" 2>&1; then estado datos "OK $(grep -c convertida "$RES/datos.log") fuentes convertidas"
else tail -8 "$RES/datos.log"; estado datos "FALLO ver datos.log"; fallo "datos"; cierre; fi
export JEVBENCH_DIR=$JEV CHISPA_DATOS=$DATOS CHISPA_REPO=$REPO
LAYA=("$PY" -u -m model.evaluacion.laya); [ "$LOCAL" = 1 ] && LAYA+=(--falso)
LAYA+=(--salida "$RES" --m4-filas "$([ "$LOCAL" = 1 ] && echo 20 || echo "$M4N")")
HF4=(); TARJ=(); [ "$LOCAL" = 1 ] && { HF4=(--hf "$REPO/model/l2/tests/fixtures_espanol"); TARJ=(--tarjetas "$REPO/model/evaluacion/tests/fixtures/laya_tarjeta"); }

# --- 4. prueba de velocidad -------------------------------------------------------------------------------------------------------
echo "== 4. velocidad $(date -u +%T)"
reint timeout "$(tope 15)m" "${LAYA[@]}" velocidad "${HF4[@]}" > "$RES/velocidad.log" 2>&1; rc=$?
if [ $rc = 0 ] && [ -f "$RES/velocidad.json" ]; then
  estado velocidad "OK $("$PY" -I -c "import json,sys; v=json.load(open(sys.argv[1])); print('%.2f s/pregunta; %s; proyección %.0f min' % (v['seg_por_pregunta'], v['nota'], v['proyeccion_min']))" "$RES/velocidad.json")"
else
  tail -8 "$RES/velocidad.log"
  if [ $rc = 3 ]; then estado velocidad "FALLO no cabe en 70 min ni con 50 filas por conjunto: no se sigue"; else estado velocidad "FALLO código $rc ver velocidad.log"; fi
  fallo "velocidad"; estado bateria "OMITIDO sin prueba de velocidad"; estado m4 "OMITIDO sin prueba de velocidad"; cierre
fi

# --- 5. batería ------------------------------------------------------------------------------------------------------------------
echo "== 5. batería $(date -u +%T)"
if reint timeout "$(tope 80)m" "${LAYA[@]}" bateria --max-minutos "$(( $(quedan_min) - 18 ))" > "$RES/bateria.log" 2>&1 && [ -f "$RES/bateria.json" ]; then
  estado bateria "OK $("$PY" -I -c "import json,sys; d=json.load(open(sys.argv[1])); print('tope=%s errores=%s' % (d['tope_filas'], d['errores']))" "$RES/bateria.json")"
else tail -8 "$RES/bateria.log"; estado bateria "FALLO ver bateria.log (3 = incompleta por tiempo)"; fallo "batería"; fi

# --- 6. M4 español ----------------------------------------------------------------------------------------------------------------
echo "== 6. M4 $(date -u +%T)"
if reint timeout "$(tope 14)m" "${LAYA[@]}" m4 "${HF4[@]}" > "$RES/m4.log" 2>&1 && [ -f "$RES/m4.json" ]; then estado m4 "OK $(tail -1 "$RES/m4.log" | cut -c1-200)"
else tail -8 "$RES/m4.log"; estado m4 "FALLO ver m4.log"; fallo "M4"; fi

# --- 7. licencia ------------------------------------------------------------------------------------------------------------------
echo "== 7. licencia $(date -u +%T)"
if timeout 5m "${LAYA[@]}" licencia "${TARJ[@]}" > "$RES/licencia.log" 2>&1 && [ -f "$RES/laya-licencia.json" ]; then
  estado licencia "OK $("$PY" -I -c "import json,sys; d=json.load(open(sys.argv[1])); print(', '.join('%s=%s' % (k, v['license']) for k, v in d['checkpoints'].items()))" "$RES/laya-licencia.json")"
else tail -5 "$RES/licencia.log"; estado licencia "FALLO ver licencia.log (la tarjeta no trae license o no se pudo bajar)"; fallo "licencia"; fi

# --- 8. tabla ---------------------------------------------------------------------------------------------------------------------
if [ -f "$RES/bateria.json" ] && "${LAYA[@]}" tabla --chispa "ajuste 1=$B1" --chispa "v2=$B2" > "$RES/tabla.log" 2>&1 && [ -f "$RES/laya-frente-chispa.md" ]; then estado tabla "OK laya-frente-chispa.md"
else tail -5 "$RES/tabla.log" 2>/dev/null; estado tabla "FALLO ver tabla.log"; fallo "tabla"; fi
cierre
