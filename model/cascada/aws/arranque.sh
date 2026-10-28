#!/bin/bash
CHISPA_S3=__CHISPA_S3__
# user-data de una instancia CPU (Amazon Linux 2023, x86_64; la de menos coste que aguante potion y scikit-learn, p. ej. una m6i.xlarge
# con ≥ 8 GB), root, con internet y rol con s3:GetObject y s3:PutObject (sin List) y sin SSH. Mide la cascada L0 → L1 → L2 (T2.7):
#   1. instala Python 3.11 y las dependencias (numpy, scikit-learn, model2vec, huggingface_hub, pyyaml, pyarrow);
#   2. baja $CHISPA_S3/codigo.tgz (bash model/cascada/aws/empaquetar.sh) y, FICHERO A FICHERO (el rol no lista: nada de --recursive ni
#      sync), las predicciones de L2 de T2.1b y T2.2 ($L2B_S3/pred.tgz y $L2C_S3/pred.tgz), cada una con pred/ y pred_soporte/;
#   3. baja de Hugging Face potion-multilingual-128M y los 4 datasets públicos y corre model.datos.convertir (las claves de
#      model/meta/resultados/conversion-20261027.json son del metaentrenamiento —pawsx, sib200, synzs, tsjev—: no traen estas tareas,
#      así que los datos salen del conversor, como en model/l2/aws/arranque.sh; herramientas viene en codigo.tgz);
#   4. calcula L0, L1-zs y L1-proto (model.cascada.capas), corre la cascada y escribe el informe (model.cascada.informe).
# Al salir (trap: fin normal, error o SIGTERM) sube log.txt y resultados.tgz (informe.md, resultados.json y FALLO si lo hubo) a $CHISPA_S3 y apaga.
# El orquestador sustituye __CHISPA_S3__ (p. ej. s3://chispa-pruebas-879381269751/cascada-20261028). Opcionales, por entorno:
# CHISPA_L2B_S3 / CHISPA_L2C_S3 (por defecto s3://chispa-pruebas-879381269751/l2-20261028b y …/l2-20261028c), CHISPA_FECHA (nombre de la
# carpeta de resultados; por defecto la fecha UTC).
# CHISPA_LOCAL=1: prueba en seco en kindling (sin pip, dnf, descargas ni shutdown; ~/venv, ~/hf, /tmp/chispa; fixtures inventados de
# model.cascada.fixtures en vez de datos descargados y L2 falso); el "s3" es /tmp/chispa/s3/<prefijo sin s3://> y se copia con cp.
if [ "${CHISPA_LOCAL:-}" = 1 ]; then
  [ "${CHISPA_S3#__}" != "$CHISPA_S3" ] && CHISPA_S3=s3://local/cascada
else
  shutdown -h +60   # apagado forzoso: la instancia se termina a los 60 min
fi
L2B_S3=${CHISPA_L2B_S3:-s3://chispa-pruebas-879381269751/l2-20261028b}
L2C_S3=${CHISPA_L2C_S3:-s3://chispa-pruebas-879381269751/l2-20261028c}
set -uo pipefail
export HOME="${HOME:-/root}"
T0=$(date +%s)

if [ "${CHISPA_LOCAL:-}" = 1 ]; then BASE=/tmp/chispa; else BASE=/opt/chispa; fi
mkdir -p "$BASE"
exec > >(tee -a "$BASE/log.txt") 2>&1
echo "== arranque $(date -u +%FT%TZ) local=${CHISPA_LOCAL:-0} base=$BASE"

REPO=$BASE/repo DATOS=$BASE/datos OUT=$BASE/salida PRED=$BASE/capas L2B=$BASE/l2b L2C=$BASE/l2c
FECHA=${CHISPA_FECHA:-$(date -u +%F)}
TAREAS=massive,clinc150,herramientas,hatecheck,inyecciones
[ "${CHISPA_LOCAL:-}" = 1 ] && TAREAS=tarea_a,tarea_b,tarea_c
FALLO=""

s3cp() {   # s3cp ORIGEN DESTINO: un fichero (el rol no lista el bucket: nada de --recursive ni sync)
  if [ "${CHISPA_LOCAL:-}" = 1 ]; then
    local o=$1 d=$2
    case $o in s3://*) o=/tmp/chispa/s3/${o#s3://};; esac
    case $d in s3://*) d=/tmp/chispa/s3/${d#s3://}; mkdir -p "$(dirname "$d")";; esac
    cp "$o" "$d"
  else aws s3 cp --only-show-errors "$1" "$2"
  fi
}

subir_y_apagar() {
  trap - EXIT
  sleep 1   # deja que tee vacíe el log
  mkdir -p "$OUT"
  [ -n "$FALLO" ] && echo "$FALLO" > "$OUT/FALLO"
  tar -C "$OUT" -czf "$BASE/resultados.tgz" . && { s3cp "$BASE/resultados.tgz" "$CHISPA_S3/resultados.tgz" || echo "no se pudo subir resultados.tgz"; }
  s3cp "$BASE/log.txt" "$CHISPA_S3/log.txt" || echo "no se pudo subir log.txt"
  [ "${CHISPA_LOCAL:-}" = 1 ] || shutdown -h now
}
trap subir_y_apagar EXIT
trap 'exit 143' TERM INT HUP

fallo() { echo "FALLO: $*"; FALLO="${FALLO:+$FALLO; }$*"; }
cierre() { df -h "$BASE" | tail -1; echo "== listo $(date -u +%FT%TZ) fallo=${FALLO:-no}"; exit 0; }

# --- Python y dependencias ---------------------------------------------------------------------------------------------
if [ "${CHISPA_LOCAL:-}" = 1 ]; then
  PY=$HOME/venv/bin/python
  export HF_HOME="$HOME/hf"
else
  export HF_HOME="$HOME/hf"   # model/datos lee de ~/hf/hub (ruta fija en comun.py)
  dnf install -y -q python3.11 python3.11-pip || { fallo "dnf install python3.11"; cierre; }
  python3.11 -m venv "$BASE/venv" || { fallo "venv"; cierre; }
  PY=$BASE/venv/bin/python
  "$PY" -m pip install -q --no-cache-dir -U pip numpy scikit-learn model2vec huggingface_hub pyyaml pyarrow \
    || { fallo "pip install"; cierre; }
fi
mkdir -p "$HF_HOME"
echo "python: $PY"; "$PY" -c "import sys, numpy, sklearn, model2vec; print(sys.version.split()[0], 'numpy', numpy.__version__, 'sklearn', sklearn.__version__, 'model2vec', model2vec.__version__)" \
  || { fallo "imports"; cierre; }

# --- código ----------------------------------------------------------------------------------------------------------
echo "bajando $CHISPA_S3/codigo.tgz"
if [ "${CHISPA_LOCAL:-}" = 1 ] && [ ! -f "/tmp/chispa/s3/${CHISPA_S3#s3://}/codigo.tgz" ]; then   # prueba en seco: lo empaqueta el propio script
  mkdir -p "/tmp/chispa/s3/${CHISPA_S3#s3://}"
  bash "$(dirname "${BASH_SOURCE[0]}")/empaquetar.sh" --fixtures > "/tmp/chispa/s3/${CHISPA_S3#s3://}/codigo.tgz" || { fallo "empaquetar.sh"; cierre; }
fi
for _ in $(seq 1 90); do   # 90 × 30 s = 45 min
  s3cp "$CHISPA_S3/codigo.tgz" "$BASE/codigo.tgz" 2>/dev/null && tar -tzf "$BASE/codigo.tgz" >/dev/null 2>&1 && break
  rm -f "$BASE/codigo.tgz"
  [ "${CHISPA_LOCAL:-}" = 1 ] && break
  sleep 30
done
rm -rf "$REPO" "$DATOS" "$PRED" "$L2B" "$L2C" "$OUT"; mkdir -p "$REPO" "$DATOS" "$PRED" "$L2B" "$L2C" "$OUT"
tar -xzf "$BASE/codigo.tgz" -C "$REPO" || { fallo "no llegó un codigo.tgz válido"; cierre; }
cd "$REPO" || { fallo "sin repo"; cierre; }
export PYTHONPATH=$REPO

# --- predicciones de L2 (un fichero por ronda) -----------------------------------------------------------------------------
if [ "${CHISPA_LOCAL:-}" = 1 ]; then   # L2 falso en el "s3" local
  "$PY" -m model.cascada.fixtures "$DATOS" "$BASE/l2b_fix" "$BASE/l2c_fix" || { fallo "fixtures"; cierre; }
  for r in b c; do
    eval "u=\$L2${r^^}_S3"; mkdir -p "/tmp/chispa/s3/${u#s3://}"
    tar -C "$BASE/l2${r}_fix" -czf "/tmp/chispa/s3/${u#s3://}/pred.tgz" pred pred_soporte
  done
fi
for r in b c; do
  eval "u=\$L2${r^^}_S3; d=\$L2${r^^}"
  if s3cp "$u/pred.tgz" "$BASE/pred_$r.tgz" && tar -xzf "$BASE/pred_$r.tgz" -C "$d"; then
    echo "L2 $r: $(ls "$d/pred" | wc -l) tareas sin soporte, $(ls "$d/pred_soporte" 2>/dev/null | wc -l) con soporte"
  else
    fallo "sin $u/pred.tgz"
  fi
done

# --- modelo y datos ------------------------------------------------------------------------------------------------------
if [ "${CHISPA_LOCAL:-}" != 1 ]; then
  echo "== descargas $(date -u +%T)"
  "$PY" -I - <<'PYEOF' || fallo "descarga"
from huggingface_hub import snapshot_download as s
fallos = []
def intenta(*a, **k):
    try:
        s(*a, **k)
    except Exception as e:
        fallos.append("%s: %s" % (a[0], type(e).__name__)); print("aviso: no se pudo bajar", a[0], e)
intenta("minishlab/potion-multilingual-128M")
intenta("mteb/amazon_massive_intent", repo_type="dataset", allow_patterns=["*es*", "*.json", "*.md", "*.csv"])
intenta("Paul/hatecheck-spanish", repo_type="dataset", allow_patterns=["*es*", "*.json", "*.md", "*.csv"])
intenta("clinc/clinc_oos", repo_type="dataset")
intenta("deepset/prompt-injections", repo_type="dataset")
print("descargas con fallo:", fallos or "ninguna")
if fallos:
    raise SystemExit(1)
PYEOF
  export HF_HUB_OFFLINE=1   # a partir de aquí todo sale de $HF_HOME
  echo "== convertir $(date -u +%T)"
  "$PY" -m model.datos.convertir --salida "$DATOS" --fuentes massive,hatecheck,clinc150,inyecciones || fallo "convertir"
  [ -f "$DATOS/resumen.json" ] && grep -E '"estado"' "$DATOS/resumen.json" | sort | uniq -c
fi
ls "$DATOS"

# --- capas, cascada e informe -------------------------------------------------------------------------------------------
echo "== capas $(date -u +%T)"
"$PY" -u -m model.cascada.capas --datos "$DATOS" --salida "$PRED" --tareas "$TAREAS" --l0-pred "$BASE/sin_pred_l0" \
  || { fallo "capas"; cierre; }
echo "== informe $(date -u +%T)"
ARGS=(--datos "$DATOS" --pred "$PRED" --tareas "$TAREAS" --fecha "$FECHA" --salida "$OUT")
[ -d "$L2B/pred" ] && ARGS+=(--l2b "$L2B")
[ -d "$L2C/pred" ] && ARGS+=(--l2c "$L2C")
[ "${CHISPA_LOCAL:-}" = 1 ] && ARGS+=(--base "$REPO/model/lineas_base/resultados.json")
"$PY" -u -m model.cascada.informe "${ARGS[@]}" || fallo "informe"
[ -f "$OUT/$FECHA/informe.md" ] && grep -A12 "^## Resumen" "$OUT/$FECHA/informe.md"
cierre
