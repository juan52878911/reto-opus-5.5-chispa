#!/bin/bash
CHISPA_S3=__CHISPA_S3__
# user-data de una Amazon Linux 2023 x86_64 recién creada (root, c6a.2xlarge, ≥ 30 GB de disco, sin GPU): W10, traduce al español las
# filas commercial de tsjev (meta ya convertido) con Opus-MT en→es (Helsinki-NLP/opus-mt-en-es, CC-BY-4.0: comprueba la licencia de la
# tarjeta y exige atribución; NLLB no, es no comercial; MADLAD-400 en g5.xlarge solo si Opus-MT no valiera).
#   1. baja los trozos tsjev/ del meta ($CHISPA_META_S3, fichero a fichero: el rol no tiene ListBucket; la lista sale de
#      model/meta/resultados/conversion-20261027.json) y el modelo;
#   2. python -m model.meta.traducir (tope --max-por-tarea 300, --max-filas $CHISPA_MAX_FILAS, y de tiempo: traduce lo que quepa);
#   3. sube a $CHISPA_S3/tsjev-es/ los .jsonl.gz, muestra-revision.md, resumen.json y estado.tsv, y al salir log.txt.
# El orquestador sustituye __CHISPA_S3__ por s3://bucket/ruta y sube ahí codigo.tgz (bash model/meta/aws/empaquetar.sh); la instancia
# (rol con s3:GetObject y s3:PutObject, sin SSH) lo baja y se apaga. Opcionales: CHISPA_META_S3, CHISPA_MAX_FILAS (por defecto 40000).
# Coste: c6a.2xlarge on-demand ≈ 0,31 USD/h × 100 min de apagado forzoso (shutdown -h +100) ≈ 0,52 USD + ≈ 0,02 de disco y tráfico.
# Tope declarado: 2 USD (no se mide el rendimiento de Opus-MT en CPU; el tope de tiempo de la traducción hace que no pase de ahí
# y que termine en ≤ 90 min; si fuera lento salen menos filas, no más coste).
# CHISPA_LOCAL=1: prueba en seco en kindling (sin dnf, pip, descargas ni shutdown; ~/venv, ~/hf, /tmp/chispa_traducir; meta inventado;
# Opus-MT desde ~/hf si está y, si no, un traductor FALSO marcado; el "s3" es /tmp/chispa/s3/<prefijo sin s3://>).
LOCAL=${CHISPA_LOCAL:-0}
TOPE_MIN=100
[ "$LOCAL" = 1 ] || shutdown -h +$TOPE_MIN   # apagado forzoso: la instancia se termina al apagarse
set -uo pipefail
export HOME="${HOME:-/root}"
T0=$(date +%s)
META_S3=${CHISPA_META_S3:-s3://chispa-pruebas-879381269751/meta-20261027/meta}
MAX_FILAS=${CHISPA_MAX_FILAS:-40000}
if [ "$LOCAL" = 1 ]; then
  BASE=/tmp/chispa_traducir; VENV="$HOME/venv"; export HF_HOME="${HF_HOME:-$HOME/hf}"
  AQUI=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
else
  BASE=/opt/chispa; VENV=$BASE/venv; export HF_HOME=$BASE/hf
fi
rm -rf "$BASE/meta" "$BASE/salida"; mkdir -p "$BASE"
exec > >(tee -a "$BASE/log.txt") 2>&1
echo "== arranque traducir $(date -u +%FT%TZ) local=$LOCAL base=$BASE max_filas=$MAX_FILAS"
REPO=$BASE/repo META=$BASE/meta SALIDA=$BASE/salida PY=$VENV/bin/python FALLO=""
ESTADO=$SALIDA/estado.tsv
mkdir -p "$SALIDA"; printf 'paso\testado\tsegundos\tdetalle\n' > "$ESTADO"

s3cp() {   # un fichero (nada de --recursive ni sync)
  if [ "$LOCAL" = 1 ]; then
    local o=$1 d=$2
    case $o in s3://*) o=/tmp/chispa/s3/${o#s3://};; esac
    case $d in s3://*) d=/tmp/chispa/s3/${d#s3://}; mkdir -p "$(dirname "$d")";; esac
    cp "$o" "$d"
  else aws s3 cp --only-show-errors "$1" "$2"
  fi
}
paso() {   # paso NOMBRE ESTADO T_INICIO [detalle]
  printf '%s\t%s\t%s\t%s\n' "$1" "$2" "$(( $(date +%s) - $3 ))" "${4:-}" >> "$ESTADO"
}
fallo() { echo "FALLO: $*"; FALLO="${FALLO:+$FALLO; }$*"; }
quedan() { echo $(( TOPE_MIN - ($(date +%s) - T0) / 60 )); }
subir_y_apagar() {
  trap - EXIT
  sleep 1   # deja que tee vacíe el log
  [ -n "$FALLO" ] && { echo "$FALLO" > "$SALIDA/FALLO"; paso subir fallo "$T0" "$FALLO"; }
  if [ -d "$SALIDA/tsjev-es" ]; then
    find "$SALIDA/tsjev-es" -type f | LC_ALL=C sort | while IFS= read -r f; do
      s3cp "$f" "$CHISPA_S3/tsjev-es/${f#$SALIDA/tsjev-es/}" || echo "no se pudo subir $f"
    done
  fi
  for f in muestra-revision.md resumen.json estado.tsv FALLO; do
    [ -f "$SALIDA/$f" ] && { s3cp "$SALIDA/$f" "$CHISPA_S3/tsjev-es/$f" || echo "no se pudo subir $f"; }
  done
  s3cp "$BASE/log.txt" "$CHISPA_S3/tsjev-es/log.txt" || echo "no se pudo subir log.txt"
  [ "$LOCAL" = 1 ] || shutdown -h now
}
trap subir_y_apagar EXIT
trap 'exit 143' TERM INT HUP
cierre() { df -h "$BASE" | tail -1; echo "== listo $(date -u +%FT%TZ) fallo=${FALLO:-no} ($(( $(date +%s) - T0 )) s)"; exit 0; }

# --- entorno -----------------------------------------------------------------------------------------------
t=$(date +%s)
if [ "$LOCAL" != 1 ]; then
  dnf install -y python3.11 python3.11-pip tar gzip || { fallo "dnf"; paso entorno fallo "$t" dnf; cierre; }
  python3.11 -m venv "$VENV" || { fallo "venv"; paso entorno fallo "$t" venv; cierre; }
  # torch de CPU (la rueda por defecto arrastra CUDA y pesa varios GB)
  "$VENV/bin/pip" install -q --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    || "$VENV/bin/pip" install -q --no-cache-dir torch || { fallo "pip torch"; paso entorno fallo "$t" torch; cierre; }
  "$VENV/bin/pip" install -q --no-cache-dir transformers sentencepiece sacremoses pyarrow pyyaml huggingface_hub numpy \
    || { fallo "pip"; paso entorno fallo "$t" pip; cierre; }
fi
"$PY" -c "import torch, transformers; print('torch', torch.__version__, 'transformers', transformers.__version__)" \
  || { fallo "falta torch o transformers"; paso entorno fallo "$t"; cierre; }
paso entorno ok "$t"

# --- código (subido por el orquestador; reintenta cada 30 s hasta 25 min) -----------------------------------
t=$(date +%s)
for _ in $(seq 1 50); do
  s3cp "$CHISPA_S3/codigo.tgz" "$BASE/codigo.tgz" 2>/dev/null && tar -tzf "$BASE/codigo.tgz" >/dev/null 2>&1 && break
  rm -f "$BASE/codigo.tgz"
  if [ "$LOCAL" = 1 ]; then bash "$AQUI/empaquetar.sh" > "$BASE/codigo.tgz" && break; fi
  sleep 30
done
rm -rf "$REPO"; mkdir -p "$REPO" "$META"
tar -xzf "$BASE/codigo.tgz" -C "$REPO" || { fallo "no llegó un codigo.tgz válido"; paso codigo fallo "$t"; cierre; }
cd "$REPO" || { fallo "sin repo"; cierre; }
export PYTHONPATH=$REPO
paso codigo ok "$t"

# --- modelo y meta -------------------------------------------------------------------------------------------
t=$(date +%s)
if [ "$LOCAL" != 1 ]; then
  "$PY" -I - <<'PYEOF' || { fallo "descarga de Opus-MT"; paso modelo fallo "$t"; cierre; }
from huggingface_hub import snapshot_download
d = snapshot_download("Helsinki-NLP/opus-mt-en-es", allow_patterns=["*.json", "*.spm", "*.md", "*.txt", "*.safetensors"])
print("modelo:", d)
PYEOF
  export HF_HUB_OFFLINE=1   # a partir de aquí todo sale de $HF_HOME
fi
paso modelo ok "$t"

t=$(date +%s)
if [ "$LOCAL" = 1 ]; then   # meta inventado en el "s3" simulado
  META_S3=s3://chispa-traducir-local/meta
  rm -rf "/tmp/chispa/s3/${META_S3#s3://}"
  "$PY" -m model.meta.traducir --crear-fixture "/tmp/chispa/s3/${META_S3#s3://}" || { fallo "fixture"; cierre; }
  (cd "/tmp/chispa/s3/${META_S3#s3://}" && find tsjev -name '*.jsonl.gz' | LC_ALL=C sort) > "$BASE/meta.lista"
else
  "$PY" -I -c 'import json,sys; print("\n".join(f for f in json.load(open(sys.argv[1]))["ficheros"] if f.startswith("tsjev/")))' \
    model/meta/resultados/conversion-20261027.json > "$BASE/meta.lista" || { fallo "lista de meta"; paso meta fallo "$t"; cierre; }
fi
NM=0; NF=0
while IFS= read -r f; do
  [ -n "$f" ] || continue
  mkdir -p "$META/$(dirname "$f")"
  if s3cp "$META_S3/$f" "$META/$f" 2>/dev/null; then NM=$((NM+1)); else NF=$((NF+1)); echo "aviso: no se pudo bajar $f"; fi
done < "$BASE/meta.lista"
echo "meta: $NM ficheros, $NF con fallo"
[ "$NF" -gt 0 ] && fallo "meta: $NF ficheros sin bajar"
if [ "$NM" -eq 0 ]; then paso meta fallo "$t" "0 ficheros"; cierre; fi
paso meta "$([ "$NF" -gt 0 ] && echo fallo || echo ok)" "$t" "$NM ficheros, $NF con fallo"

# --- traducción ----------------------------------------------------------------------------------------------------
t=$(date +%s)
if [ "$LOCAL" = 1 ]; then MIN=5; TRAD=auto; else MIN=$(( $(quedan) - 15 )); [ "$MIN" -lt 5 ] && MIN=5; TRAD=opus; fi
echo "== traducir $(date -u +%T): tope de $MIN min, traductor $TRAD"
"$PY" -u -m model.meta.traducir "$META" "$SALIDA" --traductor "$TRAD" --max-por-tarea 300 --max-filas "$MAX_FILAS" --minutos "$MIN" \
  || { fallo "traducir"; paso traducir fallo "$t"; cierre; }
DET=$("$PY" -I -c 'import json,sys; r=json.load(open(sys.argv[1])); print("%d filas, %d descartadas, %s %s" % (r["filas_escritas"], r["descartadas_total"], r["traductor"]["modelo"], r["traductor"]["revision"]))' "$SALIDA/resumen.json" 2>/dev/null)
paso traducir ok "$t" "$DET"
paso total ok "$T0" "$DET"
cierre
