#!/bin/bash
CHISPA_S3=__CHISPA_S3__
# user-data de una m6a.xlarge spot (Amazon Linux 2023, x86_64, sin GPU), root, con internet y rol con s3:GetObject y s3:PutObject
# (sin List) y sin SSH: T2.2d, cabeza conjunta con la cabeza entrenada en test por pliegues, calibración y comparación con la cascada.
# Mismo patrón que conjunta.sh y cascada/aws/arranque.sh. El orquestador sustituye __CHISPA_S3__ (salida de esta ejecución) y sube
# $CHISPA_S3/codigo.tgz (bash model/l2/aws/empaquetar_conjunta.sh). CHISPA_FUENTE_S3 (por defecto
# s3://chispa-pruebas-879381269751/conjunta-20261028) es de donde salen las características y los resultados de T2.2c. En la instancia:
#   1. python3.11 + venv + torch CPU, numpy, scikit-learn, huggingface_hub, pyyaml, pyarrow (sin e5 ni transformers: no hay codificador);
#   2. baja de S3, FICHERO A FICHERO (el rol no lista el bucket), el código, $FUENTE/caracteristicas/<tarea>.npz y $FUENTE/resultados.tgz
#      (pred_l0/ = L0 con todo train; pred_l2/ = L2 con soporte, que es L2b-sop); baja los 4 datasets públicos y corre model.datos.convertir;
#   3. model.l2.conjunta --desde-cache en las dos modalidades (--modo-cabeza train y cvtest), las dos con --calibrar; cvtest escribe h1.md;
#   4. model.cascada.informe --completo para cada modalidad: L0c → L2b-sop, L0c → conjunta y conjunta sola, con el mismo L0 completo;
#   5. al salir (trap: fin normal, error o SIGTERM) sube log.txt y resultados.tgz (train/, cvtest/, cascada_train/, cascada_cvtest/) y apaga.
#      Apagado forzoso a los 45 min.
# CHISPA_LOCAL=1: prueba en seco en kindling (sin dnf, pip, descargas ni shutdown; ~/venv, /tmp/chispa/conjunta_cpu): solo la tarea
# herramientas (model/herramientas) recortada a CHISPA_MAX_FILAS (500) filas; si en el "s3" local no están las características y el
# resultados.tgz de la fuente, los fabrica con model.l2.conjunta y un checkpoint sin entrenar (e5 de ~/hf, como conjunta.sh).
# El "s3" local es /tmp/chispa/s3/<prefijo sin s3://> y se copia con cp.
FUENTE_S3=${CHISPA_FUENTE_S3:-s3://chispa-pruebas-879381269751/conjunta-20261028}
TAREAS=massive,hatecheck,clinc150,inyecciones,herramientas
if [ "${CHISPA_LOCAL:-}" = 1 ]; then
  TAREAS=herramientas
  [ "${CHISPA_S3#__}" != "$CHISPA_S3" ] && CHISPA_S3=s3://local/conjunta_cpu
  FUENTE_S3=${CHISPA_FUENTE_S3:-s3://local/conjunta_fuente}
else
  shutdown -h +45   # apagado forzoso: la instancia se termina al apagarse
fi
set -uo pipefail
export HOME="${HOME:-/root}"
T0=$(date +%s)

if [ "${CHISPA_LOCAL:-}" = 1 ]; then BASE=/tmp/chispa/conjunta_cpu; else BASE=/opt/chispa; fi
mkdir -p "$BASE"
exec > >(tee -a "$BASE/log.txt") 2>&1
echo "== arranque conjunta_cpu $(date -u +%FT%TZ) local=${CHISPA_LOCAL:-0} base=$BASE fuente=$FUENTE_S3"

REPO=$BASE/repo DATOS=$BASE/datos OUT=$BASE/salida CACHE=$BASE/cache FUENTE=$BASE/fuente L2B=$BASE/l2b
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
  tar -C "$OUT" -czf "$BASE/resultados.tgz" . 2>/dev/null || echo "no se pudo crear resultados.tgz"
  [ -f "$BASE/resultados.tgz" ] && { s3cp "$BASE/resultados.tgz" "$CHISPA_S3/resultados.tgz" || echo "no se pudo subir resultados.tgz"; }
  s3cp "$BASE/log.txt" "$CHISPA_S3/log.txt" || echo "no se pudo subir log.txt"
  [ "${CHISPA_LOCAL:-}" = 1 ] || shutdown -h now
}
trap subir_y_apagar EXIT
trap 'exit 143' TERM INT HUP

fallo() { echo "FALLO: $*"; FALLO="${FALLO:+$FALLO; }$*"; }
cierre() { df -h "$BASE" | tail -1; echo "== listo $(date -u +%FT%TZ) fallo=${FALLO:-no} ($(( $(date +%s) - T0 )) s)"; exit 0; }

# --- Python y dependencias ---------------------------------------------------------------------------------------------
export HF_HOME="$HOME/hf"   # model/datos lee los datasets de ~/hf/hub (ruta fija en comun.py)
if [ "${CHISPA_LOCAL:-}" = 1 ]; then
  PY=$HOME/venv/bin/python
else
  dnf install -y -q python3.11 python3.11-pip || { fallo "dnf install python3.11"; cierre; }
  python3.11 -m venv "$BASE/venv" || { fallo "venv"; cierre; }
  PY=$BASE/venv/bin/python
  "$PY" -m pip install -q --no-cache-dir -U pip \
    && "$PY" -m pip install -q --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && "$PY" -m pip install -q --no-cache-dir numpy scikit-learn huggingface_hub pyyaml pyarrow datasets \
    || { fallo "pip install"; cierre; }
fi
mkdir -p "$HF_HOME"
echo "python: $PY"
"$PY" -c "import sys, numpy, sklearn, torch; print(sys.version.split()[0], 'numpy', numpy.__version__, 'sklearn', sklearn.__version__, 'torch', torch.__version__)" \
  || { fallo "imports"; cierre; }

# --- código --------------------------------------------------------------------------------------------------------------
echo "bajando $CHISPA_S3/codigo.tgz"
if [ "${CHISPA_LOCAL:-}" = 1 ] && [ ! -f "/tmp/chispa/s3/${CHISPA_S3#s3://}/codigo.tgz" ]; then   # prueba en seco: lo empaqueta el propio script
  mkdir -p "/tmp/chispa/s3/${CHISPA_S3#s3://}"
  bash "$(dirname "${BASH_SOURCE[0]}")/empaquetar_conjunta.sh" --fixtures > "/tmp/chispa/s3/${CHISPA_S3#s3://}/codigo.tgz" \
    || { fallo "empaquetar_conjunta.sh"; cierre; }
fi
for _ in $(seq 1 90); do   # 90 × 30 s = 45 min
  s3cp "$CHISPA_S3/codigo.tgz" "$BASE/codigo.tgz" 2>/dev/null && tar -tzf "$BASE/codigo.tgz" >/dev/null 2>&1 && break
  rm -f "$BASE/codigo.tgz"
  [ "${CHISPA_LOCAL:-}" = 1 ] && break
  sleep 30
done
rm -rf "$REPO" "$DATOS" "$OUT" "$CACHE" "$FUENTE" "$L2B"; mkdir -p "$REPO" "$DATOS" "$OUT" "$CACHE" "$FUENTE" "$L2B"
tar -xzf "$BASE/codigo.tgz" -C "$REPO" || { fallo "no llegó un codigo.tgz válido"; cierre; }
cd "$REPO" || { fallo "sin repo"; cierre; }
export PYTHONPATH=$REPO
for f in model/lineas_base/correr.py model/cascada/informe.py model/cascada/cascada.py; do
  [ -f "$REPO/$f" ] || { fallo "el código no trae $f (empaquetar_conjunta.sh)"; cierre; }
done

# --- datos públicos --------------------------------------------------------------------------------------------------------
if [ "${CHISPA_LOCAL:-}" != 1 ]; then
  echo "== descargas $(date -u +%T)"
  "$PY" -I - <<'PYEOF' || fallo "descarga de datasets"
from huggingface_hub import snapshot_download as s
fallos = []
def intenta(*a, **k):
    try:
        s(*a, **k)
    except Exception as e:
        fallos.append("%s: %s" % (a[0], type(e).__name__)); print("aviso: no se pudo bajar", a[0], e)
intenta("mteb/amazon_massive_intent", repo_type="dataset", allow_patterns=["*es*", "*.json", "*.md", "*.csv"])
intenta("Paul/hatecheck-spanish", repo_type="dataset", allow_patterns=["*es*", "*.json", "*.md", "*.csv"])
for d in ("clinc/clinc_oos", "deepset/prompt-injections"):
    intenta(d, repo_type="dataset")
print("descargas con fallo:", fallos or "ninguna")
if fallos:
    raise SystemExit(1)
PYEOF
  export HF_HUB_OFFLINE=1   # a partir de aquí todo sale de $HF_HOME
fi
echo "== convertir $(date -u +%T)"
if [ "${CHISPA_LOCAL:-}" = 1 ]; then
  "$PY" -m model.datos.convertir --salida "$DATOS" --fuentes massive,hatecheck,clinc150,inyecciones --fixtures || fallo "convertir"
else
  "$PY" -m model.datos.convertir --salida "$DATOS" --fuentes massive,hatecheck,clinc150,inyecciones || fallo "convertir"
fi
[ -f "$DATOS/herramientas.jsonl" ] || ls "$DATOS"

# --- fuente: características y resultados de T2.2c --------------------------------------------------------------------------
if [ "${CHISPA_LOCAL:-}" = 1 ] && [ ! -f "/tmp/chispa/s3/${FUENTE_S3#s3://}/resultados.tgz" ]; then
  echo "== local: fabrica la fuente (características con un checkpoint sin entrenar) $(date -u +%T)"
  export HF_HUB_OFFLINE=1
  "$PY" -c "
import sys, torch
from model.l2.modelo import ModeloL2
torch.manual_seed(0)
torch.save({'modelo': ModeloL2().state_dict(), 'cabezas': [], 'enc': None}, sys.argv[1])" "$BASE/mejor.pt" || { fallo "checkpoint local"; cierre; }
  "$PY" -u -m model.l2.conjunta --ckpt "$BASE/mejor.pt" --salida "$BASE/fuente_gen" --datos "$DATOS" --tareas "$TAREAS" \
    --device cpu --max-filas "${CHISPA_MAX_FILAS:-500}" || { fallo "fuente local"; cierre; }
  mkdir -p "/tmp/chispa/s3/${FUENTE_S3#s3://}/caracteristicas"
  cp "$BASE"/fuente_gen/caracteristicas/*.npz "/tmp/chispa/s3/${FUENTE_S3#s3://}/caracteristicas/"
  tar -C "$BASE/fuente_gen" --exclude=caracteristicas -czf "/tmp/chispa/s3/${FUENTE_S3#s3://}/resultados.tgz" .
fi
for t in ${TAREAS//,/ }; do
  s3cp "$FUENTE_S3/caracteristicas/$t.npz" "$CACHE/$t.npz" || fallo "sin $FUENTE_S3/caracteristicas/$t.npz"
done
s3cp "$FUENTE_S3/resultados.tgz" "$BASE/fuente.tgz" && tar -xzf "$BASE/fuente.tgz" -C "$FUENTE" || fallo "sin $FUENTE_S3/resultados.tgz"
ls "$CACHE" "$FUENTE" | head -30
[ -d "$FUENTE/pred_l0" ] && [ -d "$FUENTE/pred_l2" ] || { fallo "resultados.tgz sin pred_l0/ ni pred_l2/"; cierre; }
mkdir -p "$L2B/pred_soporte" && cp "$FUENTE"/pred_l2/*.jsonl "$L2B/pred_soporte/"   # L2 con soporte = «L2b-sop» del informe

# --- cabezas: las dos modalidades, con calibración -------------------------------------------------------------------------------
CJ=(--desde-cache "$CACHE" --datos "$DATOS" --tareas "$TAREAS" --calibrar)
[ "${CHISPA_LOCAL:-}" = 1 ] && CJ+=(--max-filas "${CHISPA_MAX_FILAS:-500}")
echo "== cabeza train $(date -u +%T)"
timeout 1200 "$PY" -u -m model.l2.conjunta "${CJ[@]}" --modo-cabeza train --salida "$OUT/train" || fallo "conjunta train"
echo "== cabeza cvtest $(date -u +%T)"
timeout 1200 "$PY" -u -m model.l2.conjunta "${CJ[@]}" --modo-cabeza cvtest --comparar-con "$OUT/train" --salida "$OUT/cvtest" || fallo "conjunta cvtest"
for m in train cvtest; do
  for f in calibracion.md delta.md h1.md; do [ -f "$OUT/$m/$f" ] && { echo "== $m/$f"; cat "$OUT/$m/$f"; }; done
done

# --- cascada con L0 completo ---------------------------------------------------------------------------------------------------------
for m in train cvtest; do
  [ -d "$OUT/$m/pred" ] || { fallo "sin $OUT/$m/pred"; continue; }
  COMP=$BASE/completo_$m; rm -rf "$COMP"; mkdir -p "$COMP"
  cp -r "$FUENTE/pred_l0" "$COMP/pred_l0"; cp -r "$OUT/$m/pred" "$COMP/pred"
  echo "== cascada $m $(date -u +%T)"
  "$PY" -u -m model.cascada.informe --datos "$DATOS" --l2b "$L2B" --completo "$COMP" --tareas "$TAREAS" --fecha "$m" \
    --salida "$OUT/cascada_$m" || fallo "cascada $m"
  [ -f "$OUT/cascada_$m/$m/informe.md" ] && grep -E "^H3|^\| .*(conjunta|L0c).* — " "$OUT/cascada_$m/$m/informe.md" | head -20
done
cierre
