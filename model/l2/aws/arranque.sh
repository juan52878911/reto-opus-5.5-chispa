#!/bin/bash
CHISPA_S3=__CHISPA_S3__
HORAS=__HORAS__   # horas de vida de la instancia (entrenamiento + preparación + evaluación); apagado forzoso a HORAS×60+20 min
# user-data de una g5.xlarge on-demand (A10G, 24 GB) con la AMI «Deep Learning OSS Nvidia Driver AMI GPU PyTorch 2.10
# (Amazon Linux 2023)», root: entrena L2 (model/l2: ranuras, torres y cabezas sobre e5 congelado), lo evalúa en test frente
# a model/lineas_base/resultados.json y sube todo. El orquestador sustituye __CHISPA_S3__ y __HORAS__ y sube
# $CHISPA_S3/codigo.tgz (bash model/l2/aws/empaquetar.sh). Misma convención que model/maestro/aws/arranque.sh.
# En la instancia (rol con s3:GetObject y s3:PutObject, sin SSH, con internet):
#   1. baja de S3 el metaentrenamiento ($META_S3) y las blandas del maestro ($BLANDAS_S3);
#   2. baja e5 y los datasets públicos y corre model.datos.convertir (y model.liston.acuerdo_humano para el listón);
#   3. entrena (model.l2.entrenar) con checkpoint cada 10 min a $CHISPA_S3/ckpt/ y reanuda si ya hay uno;
#   4. evalúa en test (T1.7a, T1.4, listón) con model.l2.evaluar;
#   5. escribe delta.md (Δ de macro-F1 por tarea frente a kNN-32 y L0).
# Al salir (trap: fin normal, error o SIGTERM) sube log.txt, resultados.json, delta.md, entrenamiento.json, pred.tgz y
# los checkpoints a $CHISPA_S3 y apaga.
# CHISPA_LOCAL=1: prueba en seco en kindling (sin pip, descargas ni shutdown; ~/venv, ~/hf, /tmp/chispa; fixtures en vez de
# datos descargados; CHISPA_PASOS pasos, 50 por defecto); el "s3" es /tmp/chispa/s3/<prefijo sin s3://> y se copia con cp.
META_S3=${CHISPA_META_S3:-s3://chispa-pruebas-879381269751/meta-20261027/meta}
BLANDAS_S3=${CHISPA_BLANDAS_S3:-s3://chispa-pruebas-879381269751/maestro-20261027/ronda1}
if [ "${CHISPA_LOCAL:-}" = 1 ]; then
  [ "${HORAS#__}" != "$HORAS" ] && HORAS=1
else
  SEG_APAGADO=$(awk -v h="$HORAS" 'BEGIN{printf "%d", h*60+20}')
  shutdown -h +"$SEG_APAGADO"   # apagado forzoso: la instancia se termina al apagarse (HORAS×60 + 20 min)
fi
set -uo pipefail
export HOME="${HOME:-/root}"
T0=$(date +%s)

if [ "${CHISPA_LOCAL:-}" = 1 ]; then BASE=/tmp/chispa; else BASE=/opt/chispa; fi
export HF_HOME="$HOME/hf"   # model/datos lee los datasets de ~/hf/hub (ruta fija en comun.py)
mkdir -p "$BASE"
exec > >(tee -a "$BASE/log.txt") 2>&1
echo "== arranque $(date -u +%FT%TZ) local=${CHISPA_LOCAL:-0} base=$BASE horas=$HORAS"

REPO=$BASE/repo DATOS=$BASE/datos OUT=$BASE/salida META=$BASE/meta BLANDAS=$BASE/blandas LISTON=$BASE/liston CKPT=$OUT/ckpt
FALLO=""

s3cp() {   # s3cp [-r] ORIGEN DESTINO
  local r=""; [ "$1" = -r ] && { r=1; shift; }
  if [ "${CHISPA_LOCAL:-}" = 1 ]; then
    local o=$1 d=$2
    case $o in s3://*) o=/tmp/chispa/s3/${o#s3://};; esac
    case $d in s3://*) d=/tmp/chispa/s3/${d#s3://}; mkdir -p "$(dirname "$d")";; esac
    if [ -n "$r" ]; then mkdir -p "$d"; cp -r "$o"/. "$d"/; else cp "$o" "$d"; fi
  elif [ -n "$r" ]; then aws s3 cp --recursive --only-show-errors "$1" "$2"
  else aws s3 cp --only-show-errors "$1" "$2"
  fi
}

subir_y_apagar() {
  trap - EXIT
  sleep 1   # deja que tee vacíe el log
  mkdir -p "$OUT"
  [ -d "$OUT/pred" ] && tar -C "$OUT" -czf "$OUT/pred.tgz" pred
  [ -n "$FALLO" ] && echo "$FALLO" > "$OUT/FALLO"
  for f in resultados.json delta.md entrenamiento.json pred.tgz FALLO; do
    [ -f "$OUT/$f" ] && { s3cp "$OUT/$f" "$CHISPA_S3/$f" || echo "no se pudo subir $f"; }
  done
  for f in ultimo.pt mejor.pt; do
    [ -f "$CKPT/$f" ] && { s3cp "$CKPT/$f" "$CHISPA_S3/ckpt/$f" || echo "no se pudo subir $f"; }
  done
  s3cp "$BASE/log.txt" "$CHISPA_S3/log.txt" || echo "no se pudo subir log.txt"
  [ "${CHISPA_LOCAL:-}" = 1 ] || shutdown -h now
}
trap subir_y_apagar EXIT
trap 'exit 143' TERM INT HUP

fallo() { echo "FALLO: $*"; FALLO="${FALLO:+$FALLO; }$*"; }
cierre() { df -h "$BASE" | tail -1; echo "== listo $(date -u +%FT%TZ) fallo=${FALLO:-no}"; exit 0; }

# --- Python de la AMI --------------------------------------------------------------------------------------------
if [ "${CHISPA_LOCAL:-}" = 1 ]; then
  PY=$HOME/venv/bin/python
else
  echo "== /opt:"; ls /opt
  PY=""
  for c in /opt/pytorch/bin/python /opt/conda/envs/pytorch/bin/python /opt/conda/bin/python /usr/bin/python3; do
    [ -x "$c" ] && "$c" -c "import torch" 2>/dev/null && { PY=$c; break; }
  done
  [ -n "$PY" ] || { fallo "ningún Python de la AMI importa torch"; cierre; }
fi
echo "python: $PY"
"$PY" -c "import sys, torch; print(sys.version.split()[0], 'torch', torch.__version__, 'cuda', torch.version.cuda, 'disponible', torch.cuda.is_available())"
if [ "${CHISPA_LOCAL:-}" != 1 ]; then
  "$PY" -c "import torch; assert torch.cuda.is_available()" || { fallo "torch no ve la GPU"; cierre; }
  nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv
  "$PY" -m pip install -q --no-cache-dir -U transformers accelerate huggingface_hub pyyaml pyarrow numpy datasets \
    || { fallo "pip install"; cierre; }
fi
"$PY" -m pip freeze 2>/dev/null | grep -iE '^(torch|transformers|accelerate|huggingface)'

# --- código ----------------------------------------------------------------------------------------------------------
echo "bajando $CHISPA_S3/codigo.tgz"
for _ in $(seq 1 90); do   # 90 × 30 s = 45 min
  s3cp "$CHISPA_S3/codigo.tgz" "$BASE/codigo.tgz" 2>/dev/null && tar -tzf "$BASE/codigo.tgz" >/dev/null 2>&1 && break
  rm -f "$BASE/codigo.tgz"
  [ "${CHISPA_LOCAL:-}" = 1 ] && break
  sleep 30
done
rm -rf "$REPO"; mkdir -p "$REPO"
tar -xzf "$BASE/codigo.tgz" -C "$REPO" || { fallo "no llegó un codigo.tgz válido"; cierre; }
cd "$REPO" || { fallo "sin repo"; cierre; }
export PYTHONPATH=$REPO
mkdir -p "$OUT" "$DATOS" "$CKPT"

# --- modelo y datasets públicos ----------------------------------------------------------------------------------------
# Mismos repos que .delega/golden.sh (sin THX-01, mmBERT, etc.: aquí solo e5). Un fallo se cuenta y se sigue.
bajar() {
  "$PY" -I - <<'PYEOF' || return 1
import glob, os, shutil
from huggingface_hub import snapshot_download as s
fallos = []
def intenta(*a, **k):
    try:
        s(*a, **k)
    except Exception as e:
        fallos.append("%s: %s" % (a[0], type(e).__name__)); print("aviso: no se pudo bajar", a[0], e)
intenta("intfloat/multilingual-e5-small", allow_patterns=["*.json", "*.safetensors", "*.txt", "*.model", "tokenizer*"])
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
snaps = glob.glob(os.path.expanduser("~/hf/hub/datasets--PolyAI--banking77/snapshots/*"))
con_datos = [d for d in snaps if glob.glob(d + "/**/*.parquet", recursive=True)]
if con_datos:
    for d in snaps:
        if d not in con_datos:
            shutil.rmtree(d); print("banking77: borrado el snapshot sin parquet", d)
print("descargas con fallo:", fallos or "ninguna")
PYEOF
}
if [ "${CHISPA_LOCAL:-}" != 1 ]; then bajar || fallo "descarga de datasets"; fi
ls "$HF_HOME"/hub/models--intfloat--multilingual-e5-small/snapshots/*/config.json >/dev/null 2>&1 \
  || { fallo "e5 no está en $HF_HOME"; cierre; }
export HF_HUB_OFFLINE=1   # a partir de aquí todo sale de $HF_HOME

# --- conversión ------------------------------------------------------------------------------------------------------
echo "== convertir $(date -u +%T)"
CONV=(--salida "$DATOS"); [ "${CHISPA_LOCAL:-}" = 1 ] && CONV+=(--fixtures)
"$PY" -m model.datos.convertir "${CONV[@]}" || fallo "convertir"
[ -f "$DATOS/resumen.json" ] && grep -E '"estado"' "$DATOS/resumen.json" | sort | uniq -c
if [ "${CHISPA_LOCAL:-}" != 1 ]; then
  "$PY" -m model.liston.acuerdo_humano --salida "$LISTON" || { echo "aviso: sin listón"; rm -rf "$LISTON"; }
fi

# --- metaentrenamiento y blandas del maestro -----------------------------------------------------------------------
rm -rf "$META" "$BLANDAS"; mkdir -p "$META" "$BLANDAS"
HAY_META=0
echo "== meta $META_S3"
if s3cp -r "$META_S3" "$META"; then HAY_META=1; else echo "aviso: sin metaentrenamiento"; fi
if s3cp "$BLANDAS_S3/blandas.tgz" "$BASE/blandas.tgz" 2>/dev/null; then
  tar -xzf "$BASE/blandas.tgz" -C "$BLANDAS" || fallo "blandas.tgz no se pudo extraer"
else
  s3cp -r "$BLANDAS_S3" "$BLANDAS" || echo "aviso: sin blandas del maestro"
fi
find "$META" "$BLANDAS" -type f | head -40; du -sh "$META" "$BLANDAS" "$DATOS"

# --- entrenamiento ---------------------------------------------------------------------------------------------------
ARGS=(--salida "$CKPT" --datos "$DATOS" --herramientas --blandas "$BLANDAS" --s3 "$CHISPA_S3/ckpt" --max-filas 600000 --epocas 1)
[ $HAY_META = 1 ] && ARGS+=(--meta "$META")
if [ "${CHISPA_LOCAL:-}" = 1 ]; then
  ARGS+=(--pasos "${CHISPA_PASOS:-50}" --device cpu --max-filas "${CHISPA_MAX_FILAS:-2000}" --ckpt-cada 60 --eval-cada 25 --dev-max 200)
else
  # Reserva: 10 min de evaluación, 10 de subida y margen sobre el apagado (HORAS×60 + 20).
  MIN=$(awk -v h="$HORAS" -v t="$(( $(date +%s) - T0 ))" 'BEGIN{m=h*60-t/60-25; if (m<5) m=5; printf "%d", m}')
  echo "entrenamiento: tope de $MIN min"
  ARGS+=(--minutos "$MIN" --epocas "${CHISPA_EPOCAS:-1}")
fi
echo "== entrenar $(date -u +%T)"
OK=0
for intento in 1 2; do   # reanuda desde ultimo.pt
  "$PY" -u -m model.l2.entrenar "${ARGS[@]}" && { OK=1; break; }
  echo "entrenar intento $intento falló (rc=$?)"
done
[ $OK = 1 ] || fallo "entrenar falló dos veces"
cp "$CKPT/entrenamiento.json" "$OUT/" 2>/dev/null
[ -f "$CKPT/mejor.pt" ] || { fallo "sin mejor.pt"; cierre; }

# --- evaluación y Δ -------------------------------------------------------------------------------------------------
echo "== evaluar $(date -u +%T)"
EV=(--ckpt "$CKPT/mejor.pt" --salida "$OUT" --datos "$DATOS")
[ -d "$LISTON" ] && EV+=(--liston "$LISTON")
[ "${CHISPA_LOCAL:-}" = 1 ] && EV+=(--device cpu --max-filas 200)
"$PY" -u -m model.l2.evaluar "${EV[@]}" || fallo "evaluar"
[ -f "$OUT/delta.md" ] && { echo "== Δ por tarea"; cat "$OUT/delta.md"; }
cierre
