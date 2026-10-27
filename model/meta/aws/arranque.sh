#!/bin/bash
CHISPA_S3=__CHISPA_S3__
# user-data de una Amazon Linux 2023 x86_64 recién creada (root, c6a.xlarge, ≥ 60 GB de disco): convierte los datos de
# metaentrenamiento (T1.8) y sube JSONL.gz en trozos de ~100 MB a $CHISPA_S3/meta/ con un resumen.json.
#   1. baja tasksource-jev (config `default`; `full` solo con CHISPA_TS_CONFIG=full), synthetic_zeroshot, PAWS-X es, SIB-200;
#   2. corre model.meta.convertir (los cuatro conversores);
#   3. sube $CHISPA_S3/meta/… (aws s3 cp --recursive) y, al salir, log.txt.
# El orquestador sustituye __CHISPA_S3__ por un prefijo s3://bucket/ruta y sube ahí codigo.tgz
# (bash model/meta/aws/empaquetar.sh); la instancia (rol con s3:GetObject y s3:PutObject, sin SSH) lo baja y se apaga.
# CHISPA_LOCAL=1: prueba en seco en kindling (sin dnf, pip, descargas ni shutdown; ~/venv, ~/hf, /tmp/chispa_meta);
# el "s3" es el directorio /tmp/chispa/s3/<prefijo sin s3://> y se copia con cp en vez de aws s3 cp.
[ "${CHISPA_LOCAL:-}" = 1 ] || shutdown -h +170   # apagado forzoso: la instancia se termina al apagarse
set -uo pipefail
export HOME="${HOME:-/root}"

if [ "${CHISPA_LOCAL:-}" = 1 ]; then
  BASE=/tmp/chispa_meta; VENV="$HOME/venv"; export HF_HOME="${HF_HOME:-$HOME/hf}"
else
  BASE=/opt/chispa; VENV=$BASE/venv; export HF_HOME=$BASE/hf
fi
mkdir -p "$BASE"
exec > >(tee -a "$BASE/log.txt") 2>&1
echo "== arranque $(date -u +%FT%TZ) local=${CHISPA_LOCAL:-0} base=$BASE"

REPO=$BASE/repo SALIDA=$BASE/meta
PY=$VENV/bin/python
FALLO=""
TS_CONFIG=${CHISPA_TS_CONFIG:-default}
case $TS_CONFIG in
  default) export CHISPA_TS_SUBDIR=data;;
  full) export CHISPA_TS_SUBDIR=full;;
  *) echo "CHISPA_TS_CONFIG debe ser default o full"; TS_CONFIG=default; export CHISPA_TS_SUBDIR=data;;
esac
S3LOCAL=/tmp/chispa/s3/${CHISPA_S3#s3://}

# s3cp ORIGEN DESTINO: aws s3 cp, o cp contra el directorio simulado en modo local. Con -r, copia un directorio
# entero (aws s3 cp --recursive).
s3cp() {
  local r=""; [ "$1" = -r ] && { r=1; shift; }
  if [ "${CHISPA_LOCAL:-}" = 1 ]; then
    local o=$1 d=$2
    case $o in s3://*) o=/tmp/chispa/s3/${o#s3://};; esac
    case $d in s3://*) d=/tmp/chispa/s3/${d#s3://}; mkdir -p "$([ -n "$r" ] && echo "$d" || dirname "$d")";; esac
    if [ -n "$r" ]; then cp -r "$o"/. "$d"/; else cp "$o" "$d"; fi
  elif [ -n "$r" ]; then
    aws s3 cp --only-show-errors --recursive "$1" "$2"
  else
    aws s3 cp --only-show-errors "$1" "$2"
  fi
}

# Al salir, bien o mal: sube el log y, si ya hay conversión, lo que haya en meta/; después apaga (salvo en local).
subir_y_apagar() {
  trap - EXIT
  sleep 1   # deja que tee vacíe el log
  [ -f "$SALIDA/resumen.json" ] && [ -z "$FALLO" ] || echo "salida incompleta o con fallo: $FALLO"
  s3cp "$BASE/log.txt" "$CHISPA_S3/log.txt" || echo "no se pudo subir log.txt"
  [ "${CHISPA_LOCAL:-}" = 1 ] || shutdown -h now
}
trap subir_y_apagar EXIT
trap 'exit 143' TERM INT HUP

fallo() { echo "FALLO: $*"; FALLO="${FALLO:+$FALLO; }$*"; }

cierre() {
  df -h "$BASE" | tail -1
  [ -n "$FALLO" ] && { mkdir -p "$SALIDA"; echo "$FALLO" > "$SALIDA/FALLO"; s3cp -r "$SALIDA" "$CHISPA_S3/meta" || echo "no se pudo subir meta/"; }
  echo "== listo $(date -u +%FT%TZ) fallo=${FALLO:-no}"
  touch "$BASE/LISTO"
  exit 0
}

# --- entorno -----------------------------------------------------------------------------------------------
instalar() {
  dnf install -y python3.11 python3.11-pip tar gzip || return 1
  python3.11 -m venv "$VENV" || return 1
  "$VENV/bin/pip" install -q --no-cache-dir pyarrow pyyaml huggingface_hub || return 1
}
bajar() {
  "$PY" -I - <<'PYEOF' || return 1
import glob, os
from huggingface_hub import snapshot_download as s
sub = os.environ["CHISPA_TS_SUBDIR"]
casos = [
  ("tasksource/tasksource-jev-typed-decisions", [sub + "/*", "sources.yaml", "README.md"]),
  ("MoritzLaurer/synthetic_zeroshot_mixtral_v0.1", ["*/*.parquet", "README.md"]),
  ("google-research-datasets/paws-x", ["es/*", "README.md"]),
  ("Davlan/sib200", ["data/spa_Latn/*", "README.md"]),
]
for repo, pat in casos:
    d = s(repo, repo_type="dataset", allow_patterns=pat)
    print("dataset", repo, sorted(os.listdir(d)))
d = s("tasksource/tasksource-jev-typed-decisions", repo_type="dataset", allow_patterns=[sub + "/*"])
assert glob.glob(d + "/" + sub + "/*.parquet"), "tasksource sin parquet en " + sub
PYEOF
}

if [ "${CHISPA_LOCAL:-}" != 1 ]; then
  instalar || { fallo "dnf/venv/pip"; cierre; }
  df -h "$BASE" | tail -1
  t0=$(date +%s)
  bajar || { fallo "descarga de datos de Hugging Face"; cierre; }
  echo "descarga: $(( $(date +%s) - t0 )) s, config tasksource=$TS_CONFIG"
  df -h "$BASE" | tail -1
fi
"$PY" -c "import pyarrow, yaml; print('pyarrow', pyarrow.__version__)" || { fallo "falta pyarrow o pyyaml"; cierre; }

# --- código en S3, subido por el orquestador (reintenta cada 30 s hasta 45 min) -------------------------------
echo "bajando $CHISPA_S3/codigo.tgz"
for _ in $(seq 1 90); do   # 90 × 30 s = 45 min
  s3cp "$CHISPA_S3/codigo.tgz" "$BASE/codigo.tgz" 2>/dev/null && tar -tzf "$BASE/codigo.tgz" >/dev/null 2>&1 && break
  rm -f "$BASE/codigo.tgz"
  sleep 30
done
rm -rf "$REPO" "$SALIDA"; mkdir -p "$REPO"
tar -xzf "$BASE/codigo.tgz" -C "$REPO" || { fallo "no llegó un codigo.tgz válido en 45 min"; cierre; }

# --- conversión ------------------------------------------------------------------------------------------------
cd "$REPO" || { fallo "sin repo"; cierre; }
echo "== convertir $(date -u +%T)"
PYTHONPATH="$REPO" "$PY" -m model.meta.convertir "$SALIDA" ${CHISPA_LOCAL:+--permitir-vacias} \
  || fallo "model.meta.convertir (código de salida $?)"
[ -f "$SALIDA/resumen.json" ] || { fallo "sin resumen.json"; cierre; }
du -sh "$SALIDA"; ls "$SALIDA"

# --- subida ----------------------------------------------------------------------------------------------------
echo "== subiendo $CHISPA_S3/meta/ $(date -u +%T)"
s3cp -r "$SALIDA" "$CHISPA_S3/meta" || fallo "no se pudo subir meta/"
cierre
