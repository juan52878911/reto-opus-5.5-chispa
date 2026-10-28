#!/bin/bash
CHISPA_S3=__CHISPA_S3__
CKPT_S3='__CKPT__'   # s3://… del checkpoint de L2 (un .pt); sin sustituir: el de T2.1b
# user-data de una g5.xlarge on-demand con la AMI «Deep Learning OSS Nvidia Driver AMI GPU PyTorch 2.10 (Amazon Linux 2023)»,
# root: T2.2c, cabeza conjunta L0 + L2 (model/l2/conjunta.py; diseño en model/l2/conjunta.md). Mismo patrón que arranque.sh.
# El orquestador sustituye __CHISPA_S3__ (y __CKPT__ si quiere otro checkpoint) y sube $CHISPA_S3/codigo.tgz
# (bash model/l2/aws/empaquetar_conjunta.sh). En la instancia (rol con s3:GetObject y s3:PutObject, sin SSH, con internet):
#   1. baja de S3, FICHERO A FICHERO (el rol no lista el bucket), el código, el checkpoint y las características que ya haya
#      en $CHISPA_S3/caracteristicas/<tarea>.npz (si valen para estos datos y este checkpoint, no se recalculan);
#   2. baja e5 y los cuatro datasets públicos de T1.7a y corre model.datos.convertir;
#   3. características de train (L0 fuera de pliegue, L2 sin la propia fila) y de test → las sube a $CHISPA_S3/caracteristicas/;
#   4. entrena las cabezas por tarea (CV en train), evalúa en test y hace la evaluación con las opciones renombradas (--renombrar);
#   5. al salir (trap: fin normal, error o SIGTERM) sube log.txt y resultados.tgz (pred*, resultados*, cabezas.json, delta.md,
#      caida.md) y apaga. Apagado forzoso a los 120 min.
# CHISPA_LOCAL=1: prueba en seco en kindling (sin pip, descargas ni shutdown; ~/venv, ~/hf, /tmp/chispa/conjunta); solo la tarea
# herramientas (model/herramientas, en el repo) recortada a CHISPA_MAX_FILAS (500) filas, e5 de ~/hf y, si el .pt no existe,
# un checkpoint sin entrenar; el "s3" es /tmp/chispa/s3/<prefijo sin s3://> y se copia con cp.
DEFECTO_CKPT=s3://chispa-pruebas-879381269751/l2-20261028b/ckpt/mejor.pt
if [ "${CKPT_S3#__}" != "$CKPT_S3" ]; then CKPT_S3=$DEFECTO_CKPT; fi
TAREAS=massive,hatecheck,clinc150,inyecciones,herramientas
if [ "${CHISPA_LOCAL:-}" = 1 ]; then
  TAREAS=herramientas
else
  shutdown -h +120   # apagado forzoso: la instancia se termina al apagarse
fi
set -uo pipefail
export HOME="${HOME:-/root}"
T0=$(date +%s)

if [ "${CHISPA_LOCAL:-}" = 1 ]; then BASE=/tmp/chispa/conjunta; else BASE=/opt/chispa; fi
export HF_HOME="$HOME/hf"   # model/datos lee los datasets de ~/hf/hub (ruta fija en comun.py)
mkdir -p "$BASE"
exec > >(tee -a "$BASE/log.txt") 2>&1
echo "== arranque conjunta $(date -u +%FT%TZ) local=${CHISPA_LOCAL:-0} base=$BASE ckpt=$CKPT_S3"

REPO=$BASE/repo DATOS=$BASE/datos OUT=$BASE/salida CACHE=$BASE/salida/caracteristicas
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
  tar -C "$OUT" --exclude=caracteristicas -czf "$BASE/resultados.tgz" . 2>/dev/null || echo "no se pudo crear resultados.tgz"
  [ -f "$BASE/resultados.tgz" ] && { s3cp "$BASE/resultados.tgz" "$CHISPA_S3/resultados.tgz" || echo "no se pudo subir resultados.tgz"; }
  s3cp "$BASE/log.txt" "$CHISPA_S3/log.txt" || echo "no se pudo subir log.txt"
  [ "${CHISPA_LOCAL:-}" = 1 ] || shutdown -h now
}
trap subir_y_apagar EXIT
trap 'exit 143' TERM INT HUP

fallo() { echo "FALLO: $*"; FALLO="${FALLO:+$FALLO; }$*"; }
cierre() { df -h "$BASE" | tail -1; echo "== listo $(date -u +%FT%TZ) fallo=${FALLO:-no} ($(( $(date +%s) - T0 )) s)"; exit 0; }

# --- Python de la AMI --------------------------------------------------------------------------------------------
if [ "${CHISPA_LOCAL:-}" = 1 ]; then
  PY=$HOME/venv/bin/python
else
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
  "$PY" -m pip install -q --no-cache-dir -U transformers accelerate huggingface_hub pyyaml pyarrow numpy datasets scikit-learn \
    || { fallo "pip install"; cierre; }
fi
"$PY" -c "import sklearn; print('scikit-learn', sklearn.__version__)" || { fallo "sin scikit-learn (L0)"; cierre; }

# --- código y checkpoint ---------------------------------------------------------------------------------------------
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
mkdir -p "$OUT" "$DATOS" "$CACHE"
[ -f "$REPO/model/lineas_base/correr.py" ] || { fallo "el código no trae model/lineas_base/correr.py (empaquetar_conjunta.sh)"; cierre; }

if [ "${CHISPA_LOCAL:-}" = 1 ] && [ ! -f "/tmp/chispa/s3/${CKPT_S3#s3://}" ]; then
  echo "local: sin $CKPT_S3, checkpoint sin entrenar"
  mkdir -p "$(dirname "/tmp/chispa/s3/${CKPT_S3#s3://}")"
  "$PY" -c "
import sys, torch
from model.l2.modelo import ModeloL2
torch.manual_seed(0)
torch.save({'modelo': ModeloL2().state_dict(), 'cabezas': [], 'enc': None}, sys.argv[1])" "/tmp/chispa/s3/${CKPT_S3#s3://}" \
    || { fallo "no se pudo fabricar el checkpoint local"; cierre; }
fi
s3cp "$CKPT_S3" "$BASE/mejor.pt" || { fallo "no se pudo bajar el checkpoint $CKPT_S3"; cierre; }
ls -l "$BASE/mejor.pt"

# --- modelo y datasets públicos ----------------------------------------------------------------------------------------
# Los mismos repos que arranque.sh, solo los de T1.7a (herramientas viene en el código).
bajar() {
  "$PY" -I - <<'PYEOF' || return 1
fallos = []
from huggingface_hub import snapshot_download as s
def intenta(*a, **k):
    try:
        s(*a, **k)
    except Exception as e:
        fallos.append("%s: %s" % (a[0], type(e).__name__)); print("aviso: no se pudo bajar", a[0], e)
intenta("intfloat/multilingual-e5-small", allow_patterns=["*.json", "*.safetensors", "*.txt", "*.model", "tokenizer*"])
intenta("mteb/amazon_massive_intent", repo_type="dataset", allow_patterns=["*es*", "*.json", "*.md", "*.csv"])
intenta("Paul/hatecheck-spanish", repo_type="dataset", allow_patterns=["*es*", "*.json", "*.md", "*.csv"])
for d in ("clinc/clinc_oos", "deepset/prompt-injections"):
    intenta(d, repo_type="dataset")
print("descargas con fallo:", fallos or "ninguna")
PYEOF
}
if [ "${CHISPA_LOCAL:-}" != 1 ]; then bajar || fallo "descarga de datasets"; fi
ls "$HF_HOME"/hub/models--intfloat--multilingual-e5-small/snapshots/*/config.json >/dev/null 2>&1 \
  || { fallo "e5 no está en $HF_HOME"; cierre; }
export HF_HUB_OFFLINE=1   # a partir de aquí todo sale de $HF_HOME

echo "== convertir $(date -u +%T)"
if [ "${CHISPA_LOCAL:-}" = 1 ]; then
  "$PY" -m model.datos.convertir --salida "$DATOS" --fuentes massive,hatecheck,clinc150,inyecciones --fixtures || fallo "convertir"
else
  "$PY" -m model.datos.convertir --salida "$DATOS" --fuentes massive,hatecheck,clinc150,inyecciones || fallo "convertir"
fi

# --- características: reutiliza las de S3 si valen ---------------------------------------------------------------------
for t in ${TAREAS//,/ }; do
  s3cp "$CHISPA_S3/caracteristicas/$t.npz" "$CACHE/$t.npz" 2>/dev/null && echo "caché de S3: $t" || rm -f "$CACHE/$t.npz"
done
CJ=(--ckpt "$BASE/mejor.pt" --salida "$OUT" --datos "$DATOS" --cache "$CACHE" --tareas "$TAREAS")
[ "${CHISPA_LOCAL:-}" = 1 ] && CJ+=(--device cpu --max-filas "${CHISPA_MAX_FILAS:-500}")
echo "== características $(date -u +%T)"
"$PY" -u -m model.l2.conjunta --fase caracteristicas "${CJ[@]}" || { fallo "características"; cierre; }
for t in ${TAREAS//,/ }; do   # se suben ya: un fallo posterior no las pierde
  [ -f "$CACHE/$t.npz" ] && { s3cp "$CACHE/$t.npz" "$CHISPA_S3/caracteristicas/$t.npz" || echo "no se pudo subir $t.npz"; }
done

# --- cabezas, evaluación y renombrado -----------------------------------------------------------------------------------
echo "== cabezas y evaluación $(date -u +%T)"
"$PY" -u -m model.l2.conjunta --fase cabezas --renombrar "${CJ[@]}" || fallo "cabezas"
[ -f "$OUT/delta.md" ] && { echo "== delta"; cat "$OUT/delta.md"; }
cierre
