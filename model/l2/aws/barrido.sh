#!/bin/bash
CHISPA_S3=__CHISPA_S3__
CHISPA_G8_S3=__CHISPA_G8_S3__
# user-data (≤ 16 KB) de una c6a.xlarge spot (Amazon Linux 2023, x86_64, sin GPU), root, con internet y rol con s3:GetObject/PutObject (sin List).
# G.8b, barrido de λ (κ = λ de formula-shrinkage.md) en test y τ para esquemas nuevos. Mismo patrón que conjunta_cpu.sh. El orquestador
# sustituye __CHISPA_S3__ (salida de esta ejecución) y __CHISPA_G8_S3__ (la de general.sh: de ahí salen ckpt/mejor.pt y entrenamiento.json),
# y sube $CHISPA_S3/codigo.tgz (bash model/l2/aws/empaquetar_barrido.sh). La g5 de G.8 no se toca. Pasos:
#   1. python3.11 + venv + torch CPU, transformers, model2vec (L1) y lo demás; baja e5 y potion, massive, hatecheck, deepset/prompt-injections
#      y JevBench; model.datos.convertir de las tres tareas excluidas;
#   2. baja el checkpoint de G.8 y su entrenamiento.json (κ = kappa_pos, 4 si falta);
#   3. model.l2.barrido --l1: λ ∈ {0, 1, 2, 4, 8, ∞} y el κ de dev, en las tareas no vistas y JevBench con k = 8, e5 una vez por texto;
#      tabla λ × tarea y «τ para esquemas nuevos» en comparacion.md. Si --l1 falla, repite sin L1. tasksource_fuera no entra (no hay meta
#      aquí; es zero-shot y sale en la comparación de general.sh);
#   4. al salir (trap) sube comparacion.md, barrido.json, FALLO y log.txt, y apaga. Apagado forzoso a los 90 min.
# CHISPA_LOCAL=1: prueba en seco en kindling (fixtures, checkpoint sin entrenar, ~/venv, sin dnf, pip, descargas ni shutdown; el "s3" es
# /tmp/chispa/s3/<prefijo>). CHISPA_MAX_FILAS (por conjunto, 600; 60 en seco).
LOCAL=${CHISPA_LOCAL:-0}
EXCLUIR=${CHISPA_EXCLUIR:-massive,hatecheck,inyecciones}
MAX_FILAS=${CHISPA_MAX_FILAS:-600}
if [ "$LOCAL" = 1 ]; then
  MAX_FILAS=${CHISPA_MAX_FILAS:-60}
  [ "${CHISPA_S3#__}" != "$CHISPA_S3" ] && CHISPA_S3=s3://local/barrido
  [ "${CHISPA_G8_S3#__}" != "$CHISPA_G8_S3" ] && CHISPA_G8_S3=s3://local/general
else shutdown -h +90; fi   # apagado forzoso: la instancia se termina al apagarse
set -uo pipefail
export HOME="${HOME:-/root}"
T0=$(date +%s)
if [ "$LOCAL" = 1 ]; then BASE=/tmp/chispa/barrido; AQUI=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd); else BASE=/opt/chispa; fi
mkdir -p "$BASE"
exec > >(tee -a "$BASE/log.txt") 2>&1
echo "== arranque barrido $(date -u +%FT%TZ) local=$LOCAL base=$BASE excluir=$EXCLUIR max_filas=$MAX_FILAS"
REPO=$BASE/repo DATOS=$BASE/datos OUT=$BASE/salida CK=$BASE/ckpt JEV=$BASE/jevbench
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
  for f in comparacion.md barrido.json FALLO; do
    [ -f "$OUT/$f" ] && { s3cp "$OUT/$f" "$CHISPA_S3/$f" || echo "no se pudo subir $f"; }
  done
  s3cp "$BASE/log.txt" "$CHISPA_S3/log.txt" || echo "no se pudo subir log.txt"
  [ "$LOCAL" = 1 ] || shutdown -h now
}
trap subir_y_apagar EXIT
trap 'exit 143' TERM INT HUP
fallo() { echo "FALLO: $*"; FALLO="${FALLO:+$FALLO; }$*"; }
cierre() { df -h "$BASE" | tail -1; echo "== listo $(date -u +%FT%TZ) fallo=${FALLO:-no} ($(( $(date +%s) - T0 )) s)"; exit 0; }

# --- Python y dependencias ---------------------------------------------------------------------------------------------
export HF_HOME="$HOME/hf"
if [ "$LOCAL" = 1 ]; then PY=$HOME/venv/bin/python
else
  dnf install -y -q python3.11 python3.11-pip git || { fallo "dnf install"; cierre; }
  python3.11 -m venv "$BASE/venv" || { fallo "venv"; cierre; }
  PY=$BASE/venv/bin/python
  "$PY" -m pip install -q --no-cache-dir -U pip \
    && "$PY" -m pip install -q --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && "$PY" -m pip install -q --no-cache-dir transformers numpy huggingface_hub pyyaml pyarrow datasets model2vec scikit-learn \
    || { fallo "pip install"; cierre; }
fi
mkdir -p "$HF_HOME"
"$PY" -c "import sys, torch, numpy; print(sys.version.split()[0], 'torch', torch.__version__, 'hilos', torch.get_num_threads())" || { fallo "imports"; cierre; }

# --- código ----------------------------------------------------------------------------------------------------------------
for _ in $(seq 1 90); do   # 90 × 30 s = 45 min
  if [ "$LOCAL" = 1 ]; then bash "$AQUI/empaquetar_barrido.sh" --fixtures > "$BASE/codigo.tgz" && break; fi
  s3cp "$CHISPA_S3/codigo.tgz" "$BASE/codigo.tgz" 2>/dev/null && tar -tzf "$BASE/codigo.tgz" >/dev/null 2>&1 && break
  rm -f "$BASE/codigo.tgz"; sleep 30
done
rm -rf "$REPO" "$DATOS" "$OUT" "$CK"; mkdir -p "$REPO" "$DATOS" "$OUT" "$CK"
tar -xzf "$BASE/codigo.tgz" -C "$REPO" || { fallo "no llegó un codigo.tgz válido"; cierre; }
cd "$REPO" || { fallo "sin repo"; cierre; }
export PYTHONPATH=$REPO
[ -f model/l2/barrido.py ] && [ -f model/cascada/capas.py ] || { fallo "el código no trae barrido.py o capas.py"; cierre; }

# --- datos, modelos y checkpoint -----------------------------------------------------------------------------------------
if [ "$LOCAL" != 1 ]; then
  echo "== descargas $(date -u +%T)"
  "$PY" -I - <<'PYEOF' || fallo "descarga (ver aviso)"
from huggingface_hub import snapshot_download as s
fallos = []
def intenta(*a, **k):
    try:
        s(*a, **k)
    except Exception as e:
        fallos.append("%s: %s" % (a[0], type(e).__name__)); print("aviso: no se pudo bajar", a[0], e)
intenta("intfloat/multilingual-e5-small", allow_patterns=["*.json", "*.safetensors", "*.txt", "*.model", "tokenizer*"])
intenta("minishlab/potion-multilingual-128M")
intenta("mteb/amazon_massive_intent", repo_type="dataset", allow_patterns=["*es*", "*.json", "*.md", "*.csv"])
intenta("Paul/hatecheck-spanish", repo_type="dataset", allow_patterns=["*es*", "*.json", "*.md", "*.csv"])
intenta("deepset/prompt-injections", repo_type="dataset")
print("descargas con fallo:", fallos or "ninguna")
raise SystemExit(1 if fallos else 0)
PYEOF
  git clone -q https://github.com/fstandhartinger/jevbench "$JEV" || { fallo "git clone de JevBench"; cierre; }
  export HF_HUB_OFFLINE=1   # a partir de aquí todo sale de $HF_HOME
else cp -r "$REPO/model/evaluacion/tests/fixtures/jevbench" "$JEV"; fi
ls "$HF_HOME"/hub/models--intfloat--multilingual-e5-small/snapshots/*/config.json >/dev/null 2>&1 || { fallo "e5 no está en $HF_HOME"; cierre; }
echo "== convertir $(date -u +%T)"
CONV=(--salida "$DATOS" --fuentes "$EXCLUIR"); [ "$LOCAL" = 1 ] && CONV+=(--fixtures)
"$PY" -m model.datos.convertir "${CONV[@]}" || fallo "convertir"
if [ "$LOCAL" = 1 ]; then   # checkpoint sin entrenar y entrenamiento.json de mentira
  "$PY" -c "
import sys, torch
from model.l2.modelo import ModeloL2
torch.manual_seed(0)
torch.save({'modelo': ModeloL2().state_dict(), 'cabezas': [], 'enc': None}, sys.argv[1])" "$CK/mejor.pt" || { fallo "checkpoint local"; cierre; }
  echo '{"kappa_dev": {"kappa": 4, "kappa_pos": 4}}' > "$CK/entrenamiento.json"
else
  s3cp "$CHISPA_G8_S3/ckpt/mejor.pt" "$CK/mejor.pt" || { fallo "sin $CHISPA_G8_S3/ckpt/mejor.pt"; cierre; }
  s3cp "$CHISPA_G8_S3/entrenamiento.json" "$CK/entrenamiento.json" || fallo "sin entrenamiento.json (κ = 4)"
fi
KAPPA=$("$PY" -I -c 'import json,sys; d=json.load(open(sys.argv[1])).get("kappa_dev"); print(d["kappa_pos"] if d and d.get("kappa_pos") else 4)' "$CK/entrenamiento.json" 2>/dev/null || echo 4)
echo "κ elegido en dev: $KAPPA"

# --- barrido ---------------------------------------------------------------------------------------------------------------
echo "== barrido $(date -u +%T)"
BA=(--ckpt "$CK/mejor.pt" --salida "$OUT" --datos "$DATOS" --jevbench "$JEV" --kappa "$KAPPA" --excluir "$EXCLUIR" --k 8 --max-filas "$MAX_FILAS" --device cpu)
[ "$LOCAL" = 1 ] && BA+=(--max-jev 40)
"$PY" -u -m model.l2.barrido "${BA[@]}" --l1 || {
  echo "barrido con L1 falló (rc=$?): se repite sin L1"
  "$PY" -u -m model.l2.barrido "${BA[@]}" || fallo "barrido falló dos veces"
}
[ -f "$OUT/comparacion.md" ] || fallo "sin comparacion.md"
cierre
