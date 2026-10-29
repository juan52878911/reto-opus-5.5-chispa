#!/bin/bash
CHISPA_S3=__CHISPA_S3__
# user-data (≤ 16 KB) de una c6a.xlarge spot (Amazon Linux 2023, x86_64, sin GPU), root, con internet y rol con s3:GetObject/PutObject (sin List).
# R9b, recuento de filas noul con «true» no última (model.l2.contar_orden_noul). Mismo patrón que barrido.sh: el orquestador sustituye
# __CHISPA_S3__ y sube $CHISPA_S3/codigo.tgz (bash model/l2/aws/empaquetar_contar.sh). Pasos:
#   1. python3.11 + venv + dependencias (sin torch: solo hace falta numpy/pyarrow/pandas para los conversores);
#   2. meta: un fichero a la vez de $META_S3 (las claves de conversion-20261027.json, como general.sh); tsinst, de $TSINST_S3/tsinst.tgz
#      si está (general-20261029b/), si no se convierte desde tasksource-instruct-v0 (HF);
#   3. datasets de model.datos (HF, como general.sh) y JevBench (git clone);
#   4. recuento → orden-noul.json y orden-noul.md; sube eso, FALLO y log.txt. Apagado forzoso a los 45 min.
# CHISPA_LOCAL=1: prueba en seco en kindling (fixtures, ~/venv, sin dnf, pip, descargas ni shutdown; el "s3" es /tmp/chispa/s3/<prefijo>).
META_S3=${CHISPA_META_S3:-s3://chispa-pruebas-879381269751/meta-20261027/meta}
TSINST_S3=${CHISPA_TSINST_S3:-s3://chispa-pruebas-879381269751/general-20261029b}
LOCAL=${CHISPA_LOCAL:-0}
if [ "$LOCAL" = 1 ]; then [ "${CHISPA_S3#__}" != "$CHISPA_S3" ] && CHISPA_S3=s3://local/contar
else shutdown -h +45; fi   # apagado forzoso: la instancia se termina al apagarse
set -uo pipefail
export HOME="${HOME:-/root}"
T0=$(date +%s)
if [ "$LOCAL" = 1 ]; then BASE=/tmp/chispa/contar; AQUI=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd); else BASE=/opt/chispa; fi
mkdir -p "$BASE"
exec > >(tee -a "$BASE/log.txt") 2>&1
echo "== arranque contar_noul $(date -u +%FT%TZ) local=$LOCAL base=$BASE"
REPO=$BASE/repo OUT=$BASE/salida META=$BASE/meta JEV=$BASE/jevbench
FALLO=""
s3cp() {   # un fichero (el rol no lista el bucket: nada de --recursive ni sync)
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
  mkdir -p "$OUT"
  [ -n "$FALLO" ] && echo "$FALLO" > "$OUT/FALLO"
  for f in orden-noul.json orden-noul.md FALLO; do
    [ -f "$OUT/$f" ] && { s3cp "$OUT/$f" "$CHISPA_S3/$f" || echo "no se pudo subir $f"; }
  done
  s3cp "$BASE/log.txt" "$CHISPA_S3/log.txt" || echo "no se pudo subir log.txt"
  [ "$LOCAL" = 1 ] || shutdown -h now
}
trap subir_y_apagar EXIT
trap 'exit 143' TERM INT HUP
fallo() { echo "FALLO: $*"; FALLO="${FALLO:+$FALLO; }$*"; }
cierre() { echo "== listo $(date -u +%FT%TZ) fallo=${FALLO:-no} ($(( $(date +%s) - T0 )) s)"; exit 0; }

# --- Python ------------------------------------------------------------------------------------------------------------
export HF_HOME="$HOME/hf"
if [ "$LOCAL" = 1 ]; then PY=$HOME/venv/bin/python
else
  dnf install -y -q python3.11 python3.11-pip git || { fallo "dnf install"; cierre; }
  python3.11 -m venv "$BASE/venv" || { fallo "venv"; cierre; }
  PY=$BASE/venv/bin/python
  "$PY" -m pip install -q --no-cache-dir -U pip \
    && "$PY" -m pip install -q --no-cache-dir numpy pandas huggingface_hub pyyaml pyarrow datasets \
    || { fallo "pip install"; cierre; }
fi
mkdir -p "$HF_HOME"

# --- código ------------------------------------------------------------------------------------------------------------
for _ in $(seq 1 90); do   # 90 × 30 s = 45 min
  if [ "$LOCAL" = 1 ]; then bash "$AQUI/empaquetar_contar.sh" --fixtures > "$BASE/codigo.tgz" && break; fi
  s3cp "$CHISPA_S3/codigo.tgz" "$BASE/codigo.tgz" 2>/dev/null && tar -tzf "$BASE/codigo.tgz" >/dev/null 2>&1 && break
  rm -f "$BASE/codigo.tgz"; sleep 30
done
rm -rf "$REPO" "$OUT" "$META"; mkdir -p "$REPO" "$OUT" "$META"
tar -xzf "$BASE/codigo.tgz" -C "$REPO" || { fallo "no llegó un codigo.tgz válido"; cierre; }
cd "$REPO" || { fallo "sin repo"; cierre; }
export PYTHONPATH=$REPO
[ -f model/l2/contar_orden_noul.py ] || { fallo "el código no trae contar_orden_noul.py"; cierre; }

# --- datasets, meta y JevBench -----------------------------------------------------------------------------------------
ARGS=(--salida "$OUT")
if [ "$LOCAL" != 1 ]; then
  echo "== descargas $(date -u +%T)"
  "$PY" -I - <<'PYEOF' || fallo "descarga de datasets (ver aviso)"
from huggingface_hub import snapshot_download as s
fallos = []
def intenta(*a, **k):
    try:
        s(*a, **k)
    except Exception as e:
        fallos.append("%s: %s" % (a[0], type(e).__name__)); print("aviso: no se pudo bajar", a[0], e)
intenta("mteb/amazon_massive_intent", repo_type="dataset", allow_patterns=["*es*", "*.json", "*.md", "*.csv"])
intenta("Paul/hatecheck-spanish", repo_type="dataset", allow_patterns=["*es*", "*.json", "*.md", "*.csv"])
for d in ("PolyAI/banking77", "clinc/clinc_oos", "deepset/prompt-injections", "SINAI/ALIA-es-discriminative-hate-speech",
          "Multilingual-Perspectivist-NLU/MultiPICo", "bgonzalezbustamante/toxicity-protests-ES",
          "bgonzalezbustamante/toxicity-Constitution-ES", "mrm8488/go_emotions-es-mt",
          "tanaos/synthetic-spam-detection-dataset-spanish", "tasksource/it-support-tickets",
          "FelipeGuerra/Colombian_Spanish_Cyberbullying_Dataset_1", "FelipeGuerra/Colombian_Spanish_Cyberbullying_Dataset_2",
          "somosnlp/suicide-comments-es", "somosnlp/spa_climate_detection"):
    intenta(d, repo_type="dataset")
intenta("PolyAI/banking77", repo_type="dataset", revision="refs/convert/parquet")
intenta("facebook/xnli", repo_type="dataset", allow_patterns=["es/*", "*.md"])
intenta("google-research-datasets/go_emotions", repo_type="dataset", allow_patterns=["raw/*", "*.md", "*.yaml", "*.json"])
intenta("tasksource/tasksource-jev-typed-decisions", repo_type="dataset", allow_patterns=["sources.yaml", "README.md"])
intenta("tasksource/tasksource-instruct-v0", repo_type="dataset", allow_patterns=["*.parquet", "*.json", "README.md"])
print("descargas con fallo:", fallos or "ninguna")
PYEOF
  git clone -q https://github.com/fstandhartinger/jevbench "$JEV" || fallo "git clone de JevBench"
  LISTA=$REPO/model/meta/resultados/conversion-20261027.json
  "$PY" -I -c 'import json,sys; print("\n".join(json.load(open(sys.argv[1]))["ficheros"]))' "$LISTA" > "$BASE/meta.lista" || fallo "lista de meta"
  NM=0; NF=0
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    mkdir -p "$META/$(dirname "$f")"
    if s3cp "$META_S3/$f" "$META/$f" 2>/dev/null; then NM=$((NM+1)); else NF=$((NF+1)); echo "aviso: no se pudo bajar $f"; fi
  done < "$BASE/meta.lista"
  echo "meta: $NM ficheros, $NF con fallo"
  [ "$NF" -gt 0 ] && fallo "meta: $NF ficheros sin bajar"
  if s3cp "$TSINST_S3/tsinst.tgz" "$BASE/tsinst.tgz" 2>/dev/null && tar -xzf "$BASE/tsinst.tgz" -C "$META"; then echo "tsinst de S3"
  else
    echo "== tsinst desde HF $(date -u +%T)"
    export HF_HUB_OFFLINE=1
    timeout 1500 "$PY" -u -m model.meta.convertir "$META" --solo tsinst --permitir-vacias || fallo "tasksource-instruct (se sigue sin él)"
    rm -f "$META/resumen.json"
  fi
  export HF_HUB_OFFLINE=1   # a partir de aquí todo sale de $HF_HOME
else
  cp -r "$REPO/model/evaluacion/tests/fixtures/jevbench" "$JEV"
  "$PY" -I - "$META" <<'PYEOF'
import gzip, json, os, sys
for fuente in ("tsjev", "tsinst"):
    os.makedirs("%s/%s" % (sys.argv[1], fuente), exist_ok=True)
    with gzip.open("%s/%s/train-00000.jsonl.gz" % (sys.argv[1], fuente), "wt", encoding="utf-8") as f:
        for i, ops in enumerate((["true", "false"], ["false", "true"], ["true", "x", "false"])):
            f.write(json.dumps({"split": "train", "tarea": "demo/" + fuente, "tipo": "noul", "opciones": ops, "id": str(i)}) + "\n")
PYEOF
  ARGS+=(--fixtures)
fi
ARGS+=(--meta "$META" --convertir --jevbench "$JEV")

# --- recuento ----------------------------------------------------------------------------------------------------------
echo "== recuento $(date -u +%T)"
"$PY" -m model.l2.contar_orden_noul "${ARGS[@]}" || fallo "contar_orden_noul"
[ -f "$OUT/orden-noul.json" ] || fallo "sin orden-noul.json"
cierre
