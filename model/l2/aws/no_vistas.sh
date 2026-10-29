#!/bin/bash
CHISPA_S3=__CHISPA_S3__
# user-data de una g5.xlarge on-demand (AMI «Deep Learning OSS Nvidia Driver AMI GPU PyTorch 2.10 (Amazon Linux 2023)», root).
# G.2, generalización a tareas no vistas. Mismo patrón que arranque.sh (el orquestador sustituye __CHISPA_S3__ y sube
# $CHISPA_S3/codigo.tgz con empaquetar.sh; el rol no lista el bucket: descargas fichero a fichero). Pasos:
#   1. entrena L2 desde cero con los hiperparámetros de T2.1b (--episodios …) y --excluir-tareas $EXCLUIR;
#   2. evalúa con model.l2.evaluar sin soporte y con k = 8 y k = 32 (en salida/k8 y salida/k32; los zero-shot salen en las dos);
#   3. evalúa el checkpoint de T2.1b ($REF_S3) igual, en ref/, y escribe comparacion.md: H1 sobre las tareas excluidas
#      (zero-shot ≥ 0,9 × T2.1b; k = 32 a ≤ 0,03). Si no se baja la referencia, usa las cifras de resultados/ronda2 (solo k = 32).
#   La cascada de `chispa train` sin --conjunta (paso 4 del brief) NO está aquí: necesita chispa-server (Go + ort) y no cabe en este user-data.
# Apagado forzoso a los 150 min. CHISPA_LOCAL=1: prueba en seco en kindling (fixtures, CHISPA_PASOS pasos, 50 por defecto,
# sin ref de S3; el "s3" es /tmp/chispa/s3/<prefijo>).
EXCLUIR=${CHISPA_EXCLUIR:-massive,hatecheck,inyecciones}   # un caso de cada tipo: muchas clases, noul y seguridad
EPIS="--episodios --k-min 4 --k-max 32 --frac-meta 0.5 --frac-zeroshot 0.25"   # = T2.1b
REF_S3=${CHISPA_REF_S3:-s3://chispa-pruebas-879381269751/l2-20261028b/ckpt/mejor.pt}
META_S3=${CHISPA_META_S3:-s3://chispa-pruebas-879381269751/meta-20261027/meta}
BLANDAS_S3=${CHISPA_BLANDAS_S3:-s3://chispa-pruebas-879381269751/maestro-20261027/ronda1}
HORAS=2.5
if [ "${CHISPA_LOCAL:-}" != 1 ]; then shutdown -h +150; fi   # apagado forzoso: la instancia se termina al apagarse
set -uo pipefail
export HOME="${HOME:-/root}"
T0=$(date +%s)

if [ "${CHISPA_LOCAL:-}" = 1 ]; then BASE=/tmp/chispa/no_vistas; else BASE=/opt/chispa; fi
export HF_HOME="$HOME/hf"
mkdir -p "$BASE"
exec > >(tee -a "$BASE/log.txt") 2>&1
echo "== arranque no_vistas $(date -u +%FT%TZ) local=${CHISPA_LOCAL:-0} base=$BASE excluir=$EXCLUIR"

REPO=$BASE/repo DATOS=$BASE/datos OUT=$BASE/salida META=$BASE/meta BLANDAS=$BASE/blandas CKPT=$OUT/ckpt REF=$BASE/ref
FALLO=""

s3cp() {   # un fichero (nada de --recursive ni sync)
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
  sleep 1
  mkdir -p "$OUT"
  for f in comparacion.md entrenamiento.json FALLO; do
    [ -f "$OUT/$f" ] && { s3cp "$OUT/$f" "$CHISPA_S3/$f" || echo "no se pudo subir $f"; }
  done
  [ -n "$FALLO" ] && echo "$FALLO" > "$OUT/FALLO" && s3cp "$OUT/FALLO" "$CHISPA_S3/FALLO"
  for d in k8 k32; do   # resultados y deltas de cada k, y de la referencia
    for f in resultados.json resultados_soporte.json delta.md; do
      for r in "$OUT/$d" "$REF/$d"; do
        [ -f "$r/$f" ] && { s3cp "$r/$f" "$CHISPA_S3/$(basename "$r")-$d/$f" || echo "no se pudo subir $r/$f"; }
      done
    done
  done
  [ -f "$CKPT/mejor.pt" ] && { s3cp "$CKPT/mejor.pt" "$CHISPA_S3/ckpt/mejor.pt" || echo "no se pudo subir mejor.pt"; }
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

# --- metaentrenamiento y blandas del maestro -----------------------------------------------------------------------
rm -rf "$META" "$BLANDAS"; mkdir -p "$META" "$BLANDAS"
HAY_META=0
echo "== meta $META_S3"
LISTA_META=$REPO/model/meta/resultados/conversion-20261027.json
if [ -f "$LISTA_META" ]; then
  # `ficheros`: rutas relativas a $META_S3 (<fuente>/<split>-NNNNN.jsonl.gz). Un fichero que falla se cuenta; con alguno bajado se sigue.
  "$PY" -I -c 'import json,sys; print("\n".join(json.load(open(sys.argv[1]))["ficheros"]))' "$LISTA_META" > "$BASE/meta.lista" \
    || fallo "no se pudo leer la lista de ficheros de meta"
  NMETA=0; NFALLA=0
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    mkdir -p "$META/$(dirname "$f")"
    if s3cp "$META_S3/$f" "$META/$f" 2>/dev/null; then NMETA=$((NMETA+1)); else NFALLA=$((NFALLA+1)); echo "aviso: no se pudo bajar $f"; fi
  done < "$BASE/meta.lista"
  echo "meta: $NMETA ficheros bajados, $NFALLA con fallo"
  [ "$NFALLA" -gt 0 ] && [ "${CHISPA_LOCAL:-}" != 1 ] && fallo "meta: $NFALLA ficheros sin bajar"
  [ "$NMETA" -gt 0 ] && HAY_META=1
else
  echo "aviso: sin $LISTA_META, sin metaentrenamiento"
fi
if s3cp "$BLANDAS_S3/blandas.tgz" "$BASE/blandas.tgz" 2>/dev/null; then
  tar -xzf "$BASE/blandas.tgz" -C "$BLANDAS" || fallo "blandas.tgz no se pudo extraer"
else
  echo "aviso: sin $BLANDAS_S3/blandas.tgz (sin blandas del maestro)"
fi
find "$META" "$BLANDAS" -type f | head -40; du -sh "$META" "$BLANDAS" "$DATOS"

# --- entrenamiento sin las tareas excluidas -------------------------------------------------------------------------
ARGS=(--salida "$CKPT" --datos "$DATOS" --herramientas --blandas "$BLANDAS" --s3 "$CHISPA_S3/ckpt" --max-filas 600000 --excluir-tareas "$EXCLUIR")
[ $HAY_META = 1 ] && ARGS+=(--meta "$META")
read -ra L2A <<< "$EPIS"
ARGS+=("${L2A[@]}")
if [ "${CHISPA_LOCAL:-}" = 1 ]; then
  ARGS+=(--pasos "${CHISPA_PASOS:-50}" --device cpu --max-filas 2000 --ckpt-cada 60 --eval-cada 25 --dev-max 200)
else
  # Reserva: 45 min (evaluar el modelo y la referencia con k = 8 y 32, subir y margen sobre el apagado a los 150).
  MIN=$(awk -v t="$(( $(date +%s) - T0 ))" 'BEGIN{m=150-t/60-45; if (m<5) m=5; printf "%d", m}')
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
# la exclusión debe constar en el log del entrenamiento (si no, esto no mide nada)
grep -q '"excluir"' "$OUT/entrenamiento.json" 2>/dev/null || echo "aviso: entrenamiento.json sin «excluir»"

# --- evaluación con k = 8 y 32: el modelo y la referencia (T2.1b) ---------------------------------------------------------
evaluar() {   # evaluar CKPT DIR
  for k in 8 32; do
    mkdir -p "$2/k$k"
    EV=(--ckpt "$1" --salida "$2/k$k" --datos "$DATOS" --soporte "$k")
    [ "${CHISPA_LOCAL:-}" = 1 ] && EV+=(--device cpu --max-filas 200)
    "$PY" -u -m model.l2.evaluar "${EV[@]}" || fallo "evaluar $2 k=$k"
  done
}
echo "== evaluar $(date -u +%T)"
evaluar "$CKPT/mejor.pt" "$OUT"
mkdir -p "$REF"
if [ "${CHISPA_LOCAL:-}" = 1 ]; then cp "$CKPT/mejor.pt" "$REF/mejor.pt"   # en seco: la «referencia» es el mismo checkpoint
elif ! s3cp "$REF_S3" "$REF/mejor.pt"; then echo "aviso: sin referencia $REF_S3"; rm -f "$REF/mejor.pt"; fi
[ -f "$REF/mejor.pt" ] && evaluar "$REF/mejor.pt" "$REF"

# --- comparación (H1) --------------------------------------------------------------------------------------------------
"$PY" -I - "$OUT" "$REF" "$EXCLUIR" <<'PYEOF' || fallo "comparación"
import json, os, sys
out, ref, excl = sys.argv[1], sys.argv[2], sys.argv[3].split(",")
T21B_K32 = {"massive": 0.636, "hatecheck": 0.630, "clinc150": 0.776, "inyecciones": 0.922, "herramientas": 0.504}   # resultados/ronda2
T21B_K0 = {"massive": 0.487, "hatecheck": 0.610, "clinc150": 0.544, "inyecciones": 0.862, "herramientas": 0.328}
def f1(d, k, soporte):
    p = os.path.join(d, "k%d" % k, "resultados_soporte.json" if soporte else "resultados.json")
    if not os.path.exists(p):
        return {}
    return {t: r["global"]["macro_f1"] for t, r in json.load(open(p)).items()}
tiene_ref = os.path.exists(os.path.join(ref, "k32", "resultados.json"))
n0, n8, n32 = f1(out, 8, False), f1(out, 8, True), f1(out, 32, True)
r0, r8, r32 = (f1(ref, 8, False), f1(ref, 8, True), f1(ref, 32, True)) if tiene_ref else (T21B_K0, {}, T21B_K32)
v = lambda d, t: "%.3f" % d[t] if t in d else "-"
lin = ["| tarea | excluida | zero-shot | T2.1b zero-shot | razón | k=8 | T2.1b k=8 | k=32 | T2.1b k=32 | Δ k=32 |", "|" + "---|" * 10]
ok0 = ok32 = True
for t in ["massive", "hatecheck", "inyecciones", "clinc150", "herramientas"]:
    if t not in n0:
        continue
    e = t in excl
    raz = n0[t] / r0[t] if r0.get(t) else None
    d32 = n32[t] - r32[t] if t in n32 and t in r32 else None
    if e:
        ok0 &= raz is not None and raz >= 0.9
        ok32 &= d32 is not None and d32 >= -0.03
    lin.append("| %s | %s | %.3f | %s | %s | %s | %s | %s | %s | %s |" % (t, "sí" if e else "no (control)", n0[t], v(r0, t),
               "-" if raz is None else "%.2f" % raz, v(n8, t), v(r8, t), v(n32, t), v(r32, t), "-" if d32 is None else "%+.3f" % d32))
lin += ["", "Referencia: " + ("T2.1b evaluado aquí (mismo soporte)" if tiene_ref else "cifras de resultados/ronda2 (sin k=8)"),
        "H1 zero-shot ≥ 0,9 × T2.1b en todas las excluidas: " + ("se cumple" if ok0 else "SE REFUTA"),
        "H1 k=32 a ≤ 3 puntos en todas las excluidas: " + ("se cumple" if ok32 else "SE REFUTA")]
open(os.path.join(out, "comparacion.md"), "w").write("\n".join(lin) + "\n")
print("\n".join(lin))
PYEOF
cierre
