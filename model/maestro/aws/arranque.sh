#!/bin/bash
CHISPA_S3=__CHISPA_S3__
MAX_FILAS=__MAX_FILAS__   # tope total de filas a puntuar (0 = todas)
# user-data de una g5.xlarge on-demand (A10G, 24 GB) con la AMI «Deep Learning OSS Nvidia Driver AMI GPU PyTorch 2.10
# (Amazon Linux 2023)», root: puntúa con Qwen las etiquetas blandas (model/maestro/blandas.py) y deja
# /opt/chispa/blandas.tgz y /opt/chispa/LISTO. El orquestador sustituye __CHISPA_S3__ y __MAX_FILAS__ y sube
# $CHISPA_S3/codigo.tgz (bash model/maestro/aws/empaquetar.sh) y, si existe, $CHISPA_S3/corpus.tgz (la salida de T1.3).
# La instancia (rol con s3:GetObject y s3:PutObject, sin SSH, con internet) baja eso, y al terminar sube log.txt y
# blandas.tgz al mismo prefijo y se apaga.
# CHISPA_LOCAL=1: prueba en seco en kindling (sin pip, descargas ni shutdown; ~/venv; /tmp/chispa); CHISPA_MODELO es la
# ruta de un Qwen diminuto local; el "s3" es /tmp/chispa/s3/<prefijo sin s3://> y se copia con cp.
[ "${CHISPA_LOCAL:-}" = 1 ] || shutdown -h +200   # apagado forzoso: la instancia se termina al apagarse
set -uo pipefail
export HOME="${HOME:-/root}"

if [ "${CHISPA_LOCAL:-}" = 1 ]; then
  BASE=/tmp/chispa
  [ "${MAX_FILAS#__}" != "$MAX_FILAS" ] && MAX_FILAS=${CHISPA_MAX_FILAS:-50}
else
  BASE=/opt/chispa
fi
# model/datos lee los datasets de ~/hf/hub (ruta fija en comun.py): HF_HOME debe apuntar ahí también en la instancia.
export HF_HOME="$HOME/hf"
mkdir -p "$BASE"
exec > >(tee -a "$BASE/log.txt") 2>&1
echo "== arranque $(date -u +%FT%TZ) local=${CHISPA_LOCAL:-0} base=$BASE max_filas=$MAX_FILAS"

REPO=$BASE/repo RES=$BASE/blandas DATOS=$BASE/datos CORPUS=$BASE/corpus_in
FALLO=""

s3cp() {
  if [ "${CHISPA_LOCAL:-}" = 1 ]; then
    local o=$1 d=$2
    case $o in s3://*) o=/tmp/chispa/s3/${o#s3://};; esac
    case $d in s3://*) d=/tmp/chispa/s3/${d#s3://}; mkdir -p "$(dirname "$d")";; esac
    cp "$o" "$d"
  else
    aws s3 cp --only-show-errors "$1" "$2"
  fi
}

subir_y_apagar() {
  trap - EXIT
  sleep 1   # deja que tee vacíe el log
  s3cp "$BASE/log.txt" "$CHISPA_S3/log.txt" || echo "no se pudo subir log.txt"
  [ -f "$BASE/blandas.tgz" ] && { s3cp "$BASE/blandas.tgz" "$CHISPA_S3/blandas.tgz" || echo "no se pudo subir blandas.tgz"; }
  [ "${CHISPA_LOCAL:-}" = 1 ] || shutdown -h now
}
trap subir_y_apagar EXIT
trap 'exit 143' TERM INT HUP

fallo() { echo "FALLO: $*"; FALLO="${FALLO:+$FALLO; }$*"; }

cierre() {
  mkdir -p "$RES"
  [ -n "$FALLO" ] && echo "$FALLO" > "$BASE/FALLO" && cp "$BASE/FALLO" "$RES/"
  df -h "$BASE" | tail -1
  cp "$BASE/log.txt" "$RES/log.txt"
  tar -C "$BASE" -czf "$BASE/blandas.tgz" blandas
  touch "$BASE/LISTO"
  echo "== listo $(date -u +%FT%TZ) fallo=${FALLO:-no}"
  exit 0
}

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
  # Sin tocar torch: solo lo que falta o se actualiza.
  "$PY" -m pip install -q --no-cache-dir -U transformers accelerate huggingface_hub pyyaml pyarrow numpy datasets \
    || { fallo "pip install"; cierre; }
fi
"$PY" -m pip freeze 2>/dev/null | grep -iE '^(torch|transformers|accelerate|huggingface)' 

# --- código y corpus en S3 -----------------------------------------------------------------------------------------
echo "bajando $CHISPA_S3/codigo.tgz"
for _ in $(seq 1 90); do   # 90 × 30 s = 45 min
  s3cp "$CHISPA_S3/codigo.tgz" "$BASE/codigo.tgz" 2>/dev/null && tar -tzf "$BASE/codigo.tgz" >/dev/null 2>&1 && break
  rm -f "$BASE/codigo.tgz"
  sleep 30
done
rm -rf "$REPO"; mkdir -p "$REPO"
tar -xzf "$BASE/codigo.tgz" -C "$REPO" || { fallo "no llegó un codigo.tgz válido en 45 min"; cierre; }

# corpus.tgz es opcional: si no llega en 10 min se sigue sin él.
rm -rf "$CORPUS"; mkdir -p "$CORPUS"
HAY_CORPUS=0
for _ in $(seq 1 20); do   # 20 × 30 s = 10 min
  s3cp "$CHISPA_S3/corpus.tgz" "$BASE/corpus.tgz" 2>/dev/null && tar -tzf "$BASE/corpus.tgz" >/dev/null 2>&1 && { HAY_CORPUS=1; break; }
  rm -f "$BASE/corpus.tgz"
  [ "${CHISPA_LOCAL:-}" = 1 ] && break
  sleep 30
done
if [ $HAY_CORPUS = 1 ]; then tar -xzf "$BASE/corpus.tgz" -C "$CORPUS" || { HAY_CORPUS=0; echo "corpus.tgz no se pudo extraer; sigo sin él"; }
else echo "sin corpus.tgz; sigo sin él"; fi

# --- modelo y datasets públicos ------------------------------------------------------------------------------------
# Mismos repos y filtros que .delega/golden.sh.
bajar() {
  "$PY" -I - <<'PYEOF' || return 1
import os
from huggingface_hub import snapshot_download as s
fallos = []
def intenta(*a, **k):
    try:
        s(*a, **k)
    except Exception as e:
        fallos.append("%s: %s" % (a[0], type(e).__name__)); print("aviso: no se pudo bajar", a[0], e)
intenta("mteb/amazon_massive_intent", repo_type="dataset", allow_patterns=["*es*", "*.json", "*.md", "*.csv"])
intenta("Paul/hatecheck-spanish", repo_type="dataset", allow_patterns=["*es*", "*.json", "*.md", "*.csv"])
for d in ("PolyAI/banking77", "clinc/clinc_oos", "deepset/prompt-injections"):
    intenta(d, repo_type="dataset")
intenta("PolyAI/banking77", repo_type="dataset", revision="refs/convert/parquet")
intenta("facebook/xnli", repo_type="dataset", allow_patterns=["es/*", "*.md"])
# model/datos/comun.py toma el último snapshot por nombre: si banking77 tiene el de main (un script, sin datos) y el de
# refs/convert/parquet, se borra el que no trae ficheros de datos para que no gane por azar del hash.
import glob, shutil
snaps = glob.glob(os.path.expanduser("~/hf/hub/datasets--PolyAI--banking77/snapshots/*"))
con_datos = [d for d in snaps if glob.glob(d + "/**/*.parquet", recursive=True)]
if con_datos:
    for d in snaps:
        if d not in con_datos:
            shutil.rmtree(d); print("banking77: borrado el snapshot sin parquet", d)
print("descargas con fallo:", fallos or "ninguna")
PYEOF
}
if [ "${CHISPA_LOCAL:-}" != 1 ]; then
  bajar || fallo "descarga de datasets"   # convertir marca cada fuente ausente; no se aborta
fi

# --- conversión ----------------------------------------------------------------------------------------------------
cd "$REPO" || { fallo "sin repo"; cierre; }
export PYTHONPATH=$REPO
mkdir -p "$RES" "$DATOS"
echo "== convertir $(date -u +%T)"
"$PY" -m model.datos.convertir --salida "$DATOS" || fallo "convertir"
[ -f "$DATOS/resumen.json" ] && grep -E '"estado"' "$DATOS/resumen.json" | sort | uniq -c
cp "$DATOS/resumen.json" "$RES/conversion.json" 2>/dev/null

ENTRADAS=()
for f in "$DATOS"/*.jsonl; do [ -f "$f" ] && ENTRADAS+=("$f"); done
for f in model/herramientas/train.jsonl model/herramientas/test.jsonl; do [ -f "$f" ] && ENTRADAS+=("$f"); done
if [ $HAY_CORPUS = 1 ]; then
  for f in "$CORPUS"/corpus/*.jsonl; do
    case $(basename "$f") in gasto*) continue;; esac
    [ -f "$f" ] && ENTRADAS+=("$f")
  done
fi
echo "entradas: ${#ENTRADAS[@]}"
[ ${#ENTRADAS[@]} -gt 0 ] || { fallo "sin filas que puntuar"; cierre; }
# Nombres de salida únicos: <origen>_<nombre>.jsonl (herramientas/train y herramientas/test, datos y corpus).
mkdir -p "$BASE/entradas"; rm -f "$BASE"/entradas/*
for f in "${ENTRADAS[@]}"; do
  case $f in
    "$DATOS"/*) n=datos_$(basename "$f");;
    "$CORPUS"/*) n=corpus_$(basename "$f");;
    *) n=$(basename "$(dirname "$f")")_$(basename "$f");;
  esac
  cp "$f" "$BASE/entradas/$n"
done
ENTRADAS=("$BASE"/entradas/*.jsonl)

# --- puntuación ----------------------------------------------------------------------------------------------------
MODELO=${CHISPA_MODELO:-Qwen/Qwen3.5-4B-Instruct}
LOTE=${CHISPA_LOTE:-16}
[ "${CHISPA_LOCAL:-}" = 1 ] && LOTE=4
ARGS=(--entrada "${ENTRADAS[@]}" --salida "$RES" --modelo "$MODELO" --lote "$LOTE")
[ "${MAX_FILAS:-0}" != 0 ] && ARGS+=(--max-filas "$MAX_FILAS")
echo "== blandas $(date -u +%T) modelo=$MODELO lote=$LOTE"
# 170 min como máximo: deja 30 min para subir antes del apagado forzoso (200). Reanuda, así que un segundo intento
# aprovecha lo escrito.
OK=0
for intento in 1 2; do
  timeout 10200 "$PY" -m model.maestro.blandas "${ARGS[@]}" && { OK=1; break; }
  echo "blandas.py intento $intento falló (rc=$?)"
done
[ $OK = 1 ] || fallo "blandas.py falló dos veces"
[ -f "$RES/resumen.json" ] || fallo "sin resumen.json"
ls -l "$RES" | head -30
cierre
