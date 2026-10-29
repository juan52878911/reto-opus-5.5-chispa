#!/bin/bash
CHISPA_S3=__CHISPA_S3__
# user-data (≤ 16 KB) de una g5.xlarge on-demand (AMI «Deep Learning OSS Nvidia Driver AMI GPU PyTorch 2.10 (Amazon Linux 2023)», root).
# G.8, L2 de propósito general. Mismo patrón que no_vistas.sh (el orquestador sustituye __CHISPA_S3__ y sube $CHISPA_S3/codigo.tgz con
# `bash model/l2/aws/empaquetar_general.sh`; descargas fichero a fichero). Pasos:
#   1. baja y convierte: datos locales (model.datos), meta de S3 (T1.8) y tasksource-instruct-v0 (model.meta, solo tareas comerciales);
#   2. entrena desde cero con T2.1b (--episodios …) + reparto por tarea (tope 2000, p ∝ n^0,3), max_tok 256, sin massive, hatecheck,
#      inyecciones ni el ~10 % de las tareas de tasksource (lista fija con semilla; fuera.json), y elige κ en el dev (k = 2);
#   3. evalúa: JevBench (k = 0, 8, 32; con y sin shrinkage) y las tareas no vistas (k = 8, 32, con y sin κ), y T2.1b ($REF_S3) igual;
#   4. escribe comparacion.md (H1 y H2).
# Coste: apagado forzoso a los 240 min = 4,0 USD de g5 a ~1 USD/h (+ ~0,1 USD de disco y tráfico); el entrenamiento ocupa lo que quede
# tras la descarga (≈ 140 min) menos 55 min de reserva para evaluar y subir. CHISPA_LOCAL=1: prueba en seco (fixtures, CHISPA_PASOS
# pasos, 30 por defecto; el meta es inventado, sin tasksource-instruct; JevBench sale del fixture; el "s3" es /tmp/chispa/s3/<prefijo>).
EXCLUIR=${CHISPA_EXCLUIR:-massive,hatecheck,inyecciones}
EPIS="--episodios --k-min 4 --k-max 32 --frac-meta 0.5 --frac-zeroshot 0.25"   # = T2.1b
G8="--tope-tarea 2000 --alfa 0.3 --max-tok 256 --excluir-fuera --elegir-kappa 1 2 4 8 16"
REF_S3=${CHISPA_REF_S3:-s3://chispa-pruebas-879381269751/l2-20261028b/ckpt/mejor.pt}
META_S3=${CHISPA_META_S3:-s3://chispa-pruebas-879381269751/meta-20261027/meta}
BLANDAS_S3=${CHISPA_BLANDAS_S3:-s3://chispa-pruebas-879381269751/maestro-20261027/ronda1}
TOPE_MIN=240
LOCAL=${CHISPA_LOCAL:-0}
if [ "$LOCAL" != 1 ]; then shutdown -h +$TOPE_MIN; fi   # apagado forzoso: la instancia se termina al apagarse
set -uo pipefail
export HOME="${HOME:-/root}"
T0=$(date +%s)
if [ "$LOCAL" = 1 ]; then BASE=/tmp/chispa/general; AQUI=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd); else BASE=/opt/chispa; fi
export HF_HOME="$HOME/hf"
mkdir -p "$BASE"
exec > >(tee -a "$BASE/log.txt") 2>&1
echo "== arranque general $(date -u +%FT%TZ) local=$LOCAL base=$BASE excluir=$EXCLUIR"
REPO=$BASE/repo DATOS=$BASE/datos OUT=$BASE/salida META=$BASE/meta BLANDAS=$BASE/blandas CKPT=$OUT/ckpt REF=$BASE/ref JEV=$BASE/jevbench
FALLO=""

s3cp() {   # un fichero (nada de --recursive ni sync)
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
  for f in comparacion.md entrenamiento.json fuera.json conversion-instruct.json FALLO; do
    [ -f "$OUT/$f" ] && { s3cp "$OUT/$f" "$CHISPA_S3/$f" || echo "no se pudo subir $f"; }
  done
  ( cd "$BASE" && find salida ref -name '*.json' -o -name '*.md' -o -name 'l2_k*.jsonl' | grep -v ckpt | LC_ALL=C sort > resultados.lista \
      && tar -czf resultados.tgz -T resultados.lista ) && s3cp "$BASE/resultados.tgz" "$CHISPA_S3/resultados.tgz" || echo "no se pudo subir resultados.tgz"
  [ -f "$CKPT/mejor.pt" ] && { s3cp "$CKPT/mejor.pt" "$CHISPA_S3/ckpt/mejor.pt" || echo "no se pudo subir mejor.pt"; }
  s3cp "$BASE/log.txt" "$CHISPA_S3/log.txt" || echo "no se pudo subir log.txt"
  [ "$LOCAL" = 1 ] || shutdown -h now
}
trap subir_y_apagar EXIT
trap 'exit 143' TERM INT HUP
fallo() { echo "FALLO: $*"; FALLO="${FALLO:+$FALLO; }$*"; }
cierre() { df -h "$BASE" | tail -1; echo "== listo $(date -u +%FT%TZ) fallo=${FALLO:-no} ($(( $(date +%s) - T0 )) s)"; exit 0; }
quedan() { echo $(( TOPE_MIN - ($(date +%s) - T0) / 60 )); }

# --- Python de la AMI --------------------------------------------------------------------------------------------
if [ "$LOCAL" = 1 ]; then PY=$HOME/venv/bin/python
else
  PY=""
  for c in /opt/pytorch/bin/python /opt/conda/envs/pytorch/bin/python /opt/conda/bin/python /usr/bin/python3; do
    [ -x "$c" ] && "$c" -c "import torch" 2>/dev/null && { PY=$c; break; }
  done
  [ -n "$PY" ] || { fallo "ningún Python de la AMI importa torch"; cierre; }
  "$PY" -c "import torch; assert torch.cuda.is_available()" || { fallo "torch no ve la GPU"; cierre; }
  nvidia-smi --query-gpu=name,memory.total --format=csv
  "$PY" -m pip install -q --no-cache-dir -U transformers accelerate huggingface_hub pyyaml pyarrow numpy datasets || { fallo "pip install"; cierre; }
fi
echo "python: $PY"; "$PY" -c "import torch; print('torch', torch.__version__, 'cuda', torch.cuda.is_available())"

# --- código ----------------------------------------------------------------------------------------------------------
for _ in $(seq 1 90); do   # 90 × 30 s = 45 min
  s3cp "$CHISPA_S3/codigo.tgz" "$BASE/codigo.tgz" 2>/dev/null && tar -tzf "$BASE/codigo.tgz" >/dev/null 2>&1 && break
  rm -f "$BASE/codigo.tgz"
  if [ "$LOCAL" = 1 ]; then bash "$AQUI/empaquetar_general.sh" --fixtures > "$BASE/codigo.tgz" && break; fi
  sleep 30
done
rm -rf "$REPO"; mkdir -p "$REPO" "$OUT" "$DATOS" "$CKPT" "$META"
tar -xzf "$BASE/codigo.tgz" -C "$REPO" || { fallo "no llegó un codigo.tgz válido"; cierre; }
cd "$REPO" || { fallo "sin repo"; cierre; }
export PYTHONPATH=$REPO

# --- modelo y datasets públicos (los de no_vistas.sh + sources.yaml de tsjev, tasksource-instruct-v0 y JevBench) -------------------
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
intenta("tasksource/tasksource-jev-typed-decisions", repo_type="dataset", allow_patterns=["sources.yaml", "README.md"])
intenta("tasksource/tasksource-instruct-v0", repo_type="dataset", allow_patterns=["*.parquet", "*.json", "README.md"])
snaps = glob.glob(os.path.expanduser("~/hf/hub/datasets--PolyAI--banking77/snapshots/*"))
con_datos = [d for d in snaps if glob.glob(d + "/**/*.parquet", recursive=True)]
if con_datos:
    for d in snaps:
        if d not in con_datos:
            shutil.rmtree(d)
print("descargas con fallo:", fallos or "ninguna")
PYEOF
}
if [ "$LOCAL" != 1 ]; then
  bajar || fallo "descarga de datasets"
  git clone -q https://github.com/fstandhartinger/jevbench "$JEV" || fallo "git clone de JevBench"
else cp -r "$AQUI/../../evaluacion/tests/fixtures/jevbench" "$JEV"; fi
ls "$HF_HOME"/hub/models--intfloat--multilingual-e5-small/snapshots/*/config.json >/dev/null 2>&1 || { fallo "e5 no está en $HF_HOME"; cierre; }
export HF_HUB_OFFLINE=1   # a partir de aquí todo sale de $HF_HOME

# --- conversión y meta -------------------------------------------------------------------------------------------------
echo "== convertir $(date -u +%T)"
CONV=(--salida "$DATOS"); [ "$LOCAL" = 1 ] && CONV+=(--fixtures)
"$PY" -m model.datos.convertir "${CONV[@]}" || fallo "convertir"
rm -rf "$BLANDAS"; mkdir -p "$BLANDAS"
if s3cp "$BLANDAS_S3/blandas.tgz" "$BASE/blandas.tgz" 2>/dev/null; then tar -xzf "$BASE/blandas.tgz" -C "$BLANDAS" || fallo "blandas.tgz"; fi
HAY_META=0
if [ "$LOCAL" = 1 ]; then   # meta inventado: 3 tareas de tasksource, una de instruct y una sintética
  "$PY" -I - "$META" <<'PYEOF' && HAY_META=1
import gzip, json, sys
for fuente, tarea, n in (("tsjev", "demo/a", 60), ("tsjev", "demo/b", 40), ("tsinst", "instruct/demo/c", 50), ("synzs", "sint", 40)):
    import os; os.makedirs("%s/%s" % (sys.argv[1], fuente), exist_ok=True)
    with gzip.open("%s/%s/train-00000.jsonl.gz" % (sys.argv[1], fuente), "at", encoding="utf-8") as f:
        for i in range(n):
            ops = ["x", "y", "z"]
            f.write(json.dumps({"id": "%s:train:%s-%d" % (fuente, tarea.replace("/", "_"), i), "split": "train", "uso_comercial": True, "tarea": tarea,
              "tipo": "choice", "pregunta": "¿Cuál?", "texto": "texto inventado %d de %s" % (i, tarea), "opciones": ops,
              "descripciones": {o: "desc " + o for o in ops}, "etiqueta": ops[i % 3], "idioma": "en", "fuente": "x", "licencia": "mit"}) + "\n")
PYEOF
else
  LISTA=$REPO/model/meta/resultados/conversion-20261027.json
  "$PY" -I -c 'import json,sys; print("\n".join(json.load(open(sys.argv[1]))["ficheros"]))' "$LISTA" > "$BASE/meta.lista" || fallo "lista de meta"
  NM=0; NF=0
  while IFS= read -r f; do   # sin synzs entero si pesa: aquí entra todo; el reparto por tarea lo recorta al leer
    [ -n "$f" ] || continue
    mkdir -p "$META/$(dirname "$f")"
    if s3cp "$META_S3/$f" "$META/$f" 2>/dev/null; then NM=$((NM+1)); else NF=$((NF+1)); echo "aviso: no se pudo bajar $f"; fi
  done < "$BASE/meta.lista"
  echo "meta: $NM ficheros, $NF con fallo"
  [ "$NF" -gt 0 ] && fallo "meta: $NF ficheros sin bajar"
  [ "$NM" -gt 0 ] && HAY_META=1
  echo "== tasksource-instruct $(date -u +%T)"   # solo tareas comerciales; si falla o tarda más de 25 min se sigue sin él
  timeout 1500 "$PY" -u -m model.meta.convertir "$META" --solo tsinst --permitir-vacias || fallo "tasksource-instruct (se sigue sin él)"
  cp "$META/resumen.json" "$OUT/conversion-instruct.json" 2>/dev/null
  rm -f "$META/resumen.json"
fi
du -sh "$META" "$DATOS"
[ $HAY_META = 1 ] && "$PY" -m model.meta.muestreo "$META" > "$OUT/fuera.json" && head -c 600 "$OUT/fuera.json"

# --- entrenamiento -------------------------------------------------------------------------------------------------------
ARGS=(--salida "$CKPT" --datos "$DATOS" --herramientas --blandas "$BLANDAS" --s3 "$CHISPA_S3/ckpt" --max-filas 600000 --excluir-tareas "$EXCLUIR")
[ $HAY_META = 1 ] && ARGS+=(--meta "$META")
read -ra L2A <<< "$EPIS $G8"
ARGS+=("${L2A[@]}")
if [ "$LOCAL" = 1 ]; then
  ARGS+=(--pasos "${CHISPA_PASOS:-30}" --device cpu --max-filas 2000 --ckpt-cada 60 --eval-cada 15 --dev-max 200)
else
  MIN=$(( $(quedan) - 55 )); [ "$MIN" -lt 5 ] && MIN=5   # reserva: evaluar el modelo y T2.1b, subir y margen
  echo "entrenamiento: tope de $MIN min"
  ARGS+=(--minutos "$MIN" --epocas 1)
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
KAPPA=$("$PY" -I -c 'import json,sys; d=json.load(open(sys.argv[1])).get("kappa_dev"); print(d["kappa_pos"] if d and d.get("kappa_pos") else 4)' "$OUT/entrenamiento.json" 2>/dev/null || echo 4)
echo "κ > 0 elegido en dev: $KAPPA (por defecto 4)"

# --- evaluación: el modelo y T2.1b ----------------------------------------------------------------------------------------
EV_EXTRA=(); [ $HAY_META = 1 ] && EV_EXTRA=(--meta-fuera "$META")
[ "$LOCAL" = 1 ] && EV_EXTRA+=(--device cpu --max-filas 100)
evaluar() {   # evaluar CKPT DIR [con κ]: k = 8 y 32; sin κ salen también los zero-shot
  for k in 8 32; do
    mkdir -p "$2/k$k"
    "$PY" -u -m model.l2.evaluar --ckpt "$1" --salida "$2/k$k" --datos "$DATOS" --soporte "$k" "${EV_EXTRA[@]}" || fallo "evaluar $2 k=$k"
  done
}
echo "== evaluar $(date -u +%T)"
evaluar "$CKPT/mejor.pt" "$OUT"
for k in 8 32; do
  mkdir -p "$OUT/kappa-k$k"
  "$PY" -u -m model.l2.evaluar --ckpt "$CKPT/mejor.pt" --salida "$OUT/kappa-k$k" --datos "$DATOS" --soporte "$k" --kappa "$KAPPA" "${EV_EXTRA[@]}" \
    || fallo "evaluar κ k=$k"
done
mkdir -p "$REF"
if [ "$LOCAL" = 1 ]; then cp "$CKPT/mejor.pt" "$REF/mejor.pt"
elif ! s3cp "$REF_S3" "$REF/mejor.pt"; then fallo "sin referencia $REF_S3"; rm -f "$REF/mejor.pt"; fi
[ -f "$REF/mejor.pt" ] && evaluar "$REF/mejor.pt" "$REF"

echo "== JevBench $(date -u +%T)"
JD=(); [ "$LOCAL" = 1 ] && JD=(--device cpu --max-casos 40) || JD=(--device cuda)
"$PY" -u -m model.evaluacion.jevbench_l2 --ckpt "$CKPT/mejor.pt" --jevbench "$JEV" --salida "$OUT/jev" --k 0 8 32 "${JD[@]}" || fallo "jevbench κ=0"
"$PY" -u -m model.evaluacion.jevbench_l2 --ckpt "$CKPT/mejor.pt" --jevbench "$JEV" --salida "$OUT/jev-kappa" --k 8 32 --kappa "$KAPPA" "${JD[@]}" \
  || fallo "jevbench κ=$KAPPA"

# --- comparación (H1, H2) ------------------------------------------------------------------------------------------------------
"$PY" "$REPO/model/evaluacion/aws/comparar_g8.py" --out "$OUT" --ref "$REF" --kappa "$KAPPA" --excluir "$EXCLUIR" || fallo "comparación"
cierre
