#!/bin/bash
CHISPA_S3=__CHISPA_S3__
# Hito 4, alternativa (b). OK de Juan al gasto el 2026-11-03 («Has el entrenamiento en la g5»): tope 3 USD spot, e5-small y mmBERT-small.
# Los datos se bajan y convierten en la propia g5 (HF + meta de tsjev en S3, como model/l2/aws/ajuste.sh); al terminar sube y espera
# $CHISPA_S3/terminar hasta CHISPA_ESPERA_MIN (20) para que el orquestador traiga y verifique antes de apagar.
# user-data (≤ 16 KB) de una g5.xlarge SPOT (AMI DLAMI GPU PyTorch, Amazon Linux 2023, root, internet, rol con s3:Get/PutObject sin ListBucket).
# El orquestador sustituye __CHISPA_S3__ y sube $CHISPA_S3/codigo.tgz (`bash model/alt/aws/empaquetar.sh <sha> > codigo.tgz`: model/alt, model/{datos,meta,evaluacion} y model/l2/datos.py;
# además datos.tgz (carpeta datos/ con los ficheros del manifiesto, tsjev/ con los trozos convertidos y bateria/ con las filas test), jevbench.tgz) y los datos en $CHISPA_S3/
# (los ficheros del manifiesto: toxicidad_*, goemociones_es, spam_tanaos, soporte_ti, ciberacoso y el tsjev convertido, que este script filtra).
# Lanzamiento (lo hace el orquestador, no este script):
#   aws ec2 run-instances --instance-type g5.xlarge --instance-market-options 'MarketType=spot,SpotOptions={SpotInstanceType=one-time,InstanceInterruptionBehavior=terminate}' \
#     --instance-initiated-shutdown-behavior terminate --user-data file://entrenar.sh ...
# Con `terminate`, el `shutdown -h` de abajo TERMINA la instancia: no queda disco ni máquina parada cobrando.
# Pasos, cada uno deja OK/FALLO en estado.tsv: 1 entorno · 2 código y datos · 3 tsjev filtrado y manifiesto validado · 4 entrenar (e5-small y,
# si CHISPA_MMBERT=1, mmBERT-small después) · 5 evaluar JevBench + batería + latencia (CPU 4 hilos, en la misma máquina: la g5.xlarge tiene 4 vCPU;
# la referencia del i7 se repite aparte con el mismo checkpoint) · 6 subir checkpoint `mejor/` (con su manifiesto-entrenamiento.json), resultados y log.
# Coste estimado (sin medir; hay que contrastarlo con la primera época): g5.xlarge spot ≈ 0,40–0,50 USD/h (bajo demanda 1,01). Con
# `--tope-tarea 1000` el train es ≲ 300 000 filas, 2 épocas, ≈ 90–120 min por codificador → ≈ 1–1,5 USD el primero. Techo duro: SHUTDOWN_MIN = 180 min
# → ≤ 3 USD spot (≤ 3,05 a precio bajo demanda). Con mmBERT-small añade ≈ 1,5 USD y sube el techo a 300 min.
# CHISPA_LOCAL=1: solo comprueba los pasos 1-3 en esta máquina (sin pip, descargas ni shutdown); las pruebas en seco del entrenamiento son los tests de model/alt.
LOCAL=${CHISPA_LOCAL:-0}
MMBERT=${CHISPA_MMBERT:-0}
META_S3=${CHISPA_META_S3:-s3://chispa-pruebas-879381269751/meta-20261027/meta}
MIN_E5=${CHISPA_MIN_E5:-110}   # con mmBERT detrás, e5 no puede comerse todo el techo
ESPERA_MIN=${CHISPA_ESPERA_MIN:-20}   # tras subir, espera $CHISPA_S3/terminar (el orquestador ya trajo y verificó) antes de apagar
SHUTDOWN_MIN=$([ "$MMBERT" = 1 ] && echo 300 || echo 180)
if [ "$LOCAL" = 1 ]; then case $CHISPA_S3 in __*) CHISPA_S3=/tmp/chispa-alt-s3; mkdir -p "$CHISPA_S3/ckpt";; esac
else shutdown -h +$SHUTDOWN_MIN; fi   # apagado forzoso: con terminate la instancia desaparece
set -uo pipefail
export HOME="${HOME:-/root}"
T0=$(date +%s)
BASE=${CHISPA_BASE:-/opt/chispa}; [ "$LOCAL" = 1 ] && BASE=${CHISPA_BASE:-/tmp/chispa-alt}
mkdir -p "$BASE"
exec > >(tee -a "$BASE/log.txt") 2>&1
echo "== arranque alt $(date -u +%FT%TZ) local=$LOCAL mmbert=$MMBERT tope=${SHUTDOWN_MIN} min"
export HF_HOME="$HOME/hf"; mkdir -p "$HF_HOME"
REPO=$BASE/repo DATOS=$BASE/datos OUT=$BASE/resultados CK=$BASE/ck JEV=$BASE/jevbench
FALLO=""
quedan_min() { echo $(( SHUTDOWN_MIN - ($(date +%s) - T0) / 60 )); }
s3cp() { if [ "$LOCAL" = 1 ]; then cp "$1" "$2"; else aws s3 cp --only-show-errors "$1" "$2"; fi; }
estado() { printf '%s\t%s\n' "$1" "$2" >> "$OUT/estado.tsv"; echo "[$1] $2"; }
fallo() { echo "FALLO: $*"; FALLO="${FALLO:+$FALLO; }$*"; }
mkdir -p "$OUT"

subir_y_apagar() {
  trap - EXIT
  [ -n "$FALLO" ] && echo "$FALLO" > "$OUT/FALLO"
  cp "$BASE/log.txt" "$OUT/log.txt" 2>/dev/null
  ( cd "$BASE" && tar -czf resultados.tgz resultados ) || echo "no se pudo crear resultados.tgz"
  [ -f "$BASE/resultados.tgz" ] && { s3cp "$BASE/resultados.tgz" "$CHISPA_S3/resultados.tgz" || echo "no se pudo subir resultados.tgz"; }
  for m in e5-small mmbert-small; do   # el mejor de cada codificador, con su manifiesto-entrenamiento.json dentro
    [ -d "$CK/$m/mejor" ] && { ( cd "$CK/$m" && tar -czf "$BASE/mejor-$m.tgz" mejor ) && s3cp "$BASE/mejor-$m.tgz" "$CHISPA_S3/ckpt/mejor-$m.tgz" \
      || echo "no se pudo subir mejor-$m"; }
  done
  s3cp "$BASE/log.txt" "$CHISPA_S3/log.txt" || echo "no se pudo subir log.txt"
  if [ "$LOCAL" != 1 ]; then   # sin ListBucket: GetObject de la marca; el shutdown -h +$SHUTDOWN_MIN sigue siendo el techo
    echo listo > "$BASE/listo"; s3cp "$BASE/listo" "$CHISPA_S3/listo" || true
    for _ in $(seq $((ESPERA_MIN * 2))); do aws s3 cp --only-show-errors "$CHISPA_S3/terminar" "$BASE/terminar" 2>/dev/null && break; sleep 30; done
    shutdown -h now
  fi
}
trap subir_y_apagar EXIT
trap 'exit 143' TERM INT HUP
cierre() { echo "== listo $(date -u +%FT%TZ) fallo=${FALLO:-no} ($(( $(date +%s) - T0 )) s)"; exit 0; }

# Watcher de tope: a 10 min del techo manda TERM al entrenamiento (guarda la época en curso con --minutos) y deja tiempo para subir.
( while sleep 60; do [ "$(quedan_min)" -le $((10 + ESPERA_MIN)) ] && { echo "== tope: quedan $(quedan_min) min, se cierra"; pkill -TERM -f "model.alt.entrenar" ; pkill -TERM -f "model.alt.evaluar"; break; }; done ) &
VIGILANTE=$!

# --- 1. entorno
echo "== 1. entorno $(date -u +%T)"
if [ "$LOCAL" = 1 ]; then PY=${CHISPA_PY:-$HOME/venv/bin/python}; DEV=cpu
else
  PY=""
  for c in /opt/pytorch/bin/python /opt/conda/envs/pytorch/bin/python /opt/conda/bin/python /usr/bin/python3; do
    [ -x "$c" ] && "$c" -c "import torch" 2>/dev/null && { PY=$c; break; }
  done
  [ -n "$PY" ] || { fallo "ningún Python de la AMI importa torch"; estado entorno "FALLO sin torch"; cierre; }
  "$PY" -c "import torch; assert torch.cuda.is_available()" || { fallo "torch no ve la GPU"; estado entorno "FALLO sin GPU"; cierre; }
  "$PY" -m pip install -q --no-cache-dir -U transformers huggingface_hub pyyaml pyarrow numpy \
    || { fallo "pip install"; estado entorno "FALLO pip"; cierre; }
  DEV=cuda
fi
estado entorno "OK dispositivo $DEV"

# --- 2. código, modelos, datos de HF, tsjev del meta y JevBench (todo se baja en la g5; nada de PQRS ni datos con nombres)
echo "== 2. código y datos $(date -u +%T)"
RAIZ=$DATOS/raiz   # raíz de --datos: los ficheros del manifiesto quedan en $RAIZ/datos/*.jsonl.gz
mkdir -p "$REPO" "$DATOS" "$RAIZ/datos"
if [ "$LOCAL" = 1 ]; then AQUI=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd); REPO=$(cd "$AQUI/../../.." && pwd); estado codigo "OK repo local $REPO"
else
  s3cp "$CHISPA_S3/codigo.tgz" "$BASE/codigo.tgz" && tar -xzf "$BASE/codigo.tgz" -C "$REPO" || { fallo "codigo.tgz"; estado codigo "FALLO"; cierre; }
  [ -f "$REPO/model/alt/manifiesto.py" ] || { fallo "codigo.tgz sin model/alt"; estado codigo "FALLO sin model/alt"; cierre; }
  estado codigo "OK"
  CHISPA_MMBERT=$MMBERT "$PY" -I - <<'PYEOF' || { fallo "descarga de HF"; estado hf "FALLO"; cierre; }
import os, sys
from huggingface_hub import snapshot_download as s
fallos = []
def intenta(*a, **k):
    try:
        s(*a, **k)
    except Exception as e:
        fallos.append(a[0]); print("aviso: no se pudo bajar", a[0], e)
intenta("intfloat/multilingual-e5-small", allow_patterns=["*.json", "*.safetensors", "*.txt", "*.model", "tokenizer*"])
if os.environ.get("CHISPA_MMBERT") == "1":
    intenta("jhu-clsp/mmBERT-small", allow_patterns=["*.json", "*.safetensors", "*.txt", "*.model", "tokenizer*"])
for d in ("bgonzalezbustamante/toxicity-protests-ES", "bgonzalezbustamante/toxicity-Constitution-ES", "mrm8488/go_emotions-es-mt",
          "tanaos/synthetic-spam-detection-dataset-spanish", "tasksource/it-support-tickets",
          "FelipeGuerra/Colombian_Spanish_Cyberbullying_Dataset_1", "FelipeGuerra/Colombian_Spanish_Cyberbullying_Dataset_2",
          "clinc/clinc_oos", "deepset/prompt-injections"):   # los dos últimos solo se miden (batería)
    intenta(d, repo_type="dataset")
intenta("mteb/amazon_massive_intent", repo_type="dataset", allow_patterns=["*es*", "*/en.json.gz", "*.json", "*.md", "*.csv"])
intenta("Paul/hatecheck-spanish", repo_type="dataset", allow_patterns=["*es*", "*.json", "*.md", "*.csv"])
print("descargas con fallo:", fallos or "ninguna")
sys.exit(1 if fallos else 0)
PYEOF
  estado hf "OK"
  git clone -q https://github.com/fstandhartinger/jevbench "$JEV" || { fallo "git clone de JevBench"; estado jevbench "FALLO clone"; cierre; }
  estado jevbench "OK $(cat "$JEV"/datasets/public/*.jsonl | wc -l) casos"
  mkdir -p "$DATOS/tsjev"; NM=0; NF=0   # solo train y dev del meta de tsjev (los test-* nunca se bajan)
  for f in $("$PY" -I -c 'import json,sys; print("\n".join(f for f in json.load(open(sys.argv[1]))["ficheros"] if f.startswith(("tsjev/train-", "tsjev/dev-"))))' \
      "$REPO/model/meta/resultados/conversion-20261027.json"); do
    if s3cp "$META_S3/$f" "$DATOS/$f"; then NM=$((NM+1)); else NF=$((NF+1)); echo "aviso: no se pudo bajar $f"; fi
  done
  [ "$NF" = 0 ] && [ "$NM" -gt 0 ] || { fallo "meta de tsjev: $NF de $((NM+NF)) ficheros sin bajar"; estado tsjev "FALLO"; cierre; }
  estado tsjev "OK $NM ficheros"
fi
cd "$REPO" || cierre
export PYTHONPATH="$REPO"
export HF_HUB_OFFLINE=1

# --- 3. conversión de las fuentes del manifiesto y de la batería, tsjev filtrado por el manifiesto y manifiesto válido
echo "== 3. datos y manifiesto $(date -u +%T)"
"$PY" -m model.alt.manifiesto validar || { fallo "manifiesto no válido"; estado manifiesto "FALLO"; cierre; }
FUENTES=toxicidad_protestas,toxicidad_constitucion,goemociones,spam_tanaos,soporte_ti,ciberacoso,massive,hatecheck,clinc150,inyecciones
CONV=(--salida "$DATOS/conv" --fuentes "$FUENTES"); [ "$LOCAL" = 1 ] && CONV+=(--fixtures)
"$PY" -m model.datos.convertir "${CONV[@]}" > "$OUT/convertir.log" 2>&1 || { tail -8 "$OUT/convertir.log"; fallo "convertir"; estado datos "FALLO"; cierre; }
for par in toxicidad_protestas:toxicidad_protestas toxicidad_constitucion:toxicidad_constitucion goemociones:goemociones_es \
           spam_tanaos:spam_tanaos soporte_ti:soporte_ti ciberacoso:ciberacoso; do
  o=${par%%:*} d=${par#*:}
  [ -s "$DATOS/conv/$o.jsonl" ] || { fallo "sin filas de $o"; estado datos "FALLO $o"; cierre; }
  gzip -n -c "$DATOS/conv/$o.jsonl" > "$RAIZ/datos/$d.jsonl.gz"
done
mkdir -p "$DATOS/bateria"; for b in massive hatecheck clinc150 inyecciones spam_tanaos; do cp "$DATOS/conv/$b.jsonl" "$DATOS/bateria/" 2>/dev/null; done
estado datos "OK $(grep -c convertida "$OUT/convertir.log") fuentes convertidas"
if [ "$LOCAL" != 1 ]; then
  "$PY" -m model.alt.manifiesto filtrar --entrada "$DATOS/tsjev" --salida "$RAIZ/datos/tsjev-admitido.jsonl.gz" | tee "$OUT/tsjev-filtrado.txt" \
    || { fallo "filtrar tsjev"; estado tsjev "FALLO filtrar"; cierre; }
  grep -q "tsjev filtrado: [1-9]" "$OUT/tsjev-filtrado.txt" || { fallo "tsjev filtrado sin filas"; estado tsjev "FALLO 0 filas"; cierre; }
fi
estado manifiesto "OK $(cat "$OUT/tsjev-filtrado.txt" 2>/dev/null)"

# --- 4. entrenar (--sellar fija filas y sha256 de lo que se entrena; entrenar se niega si algo no valida)
entrenar_con() {  # $1 = alias del codificador
  local m=$1 min; min=$(( $(quedan_min) - 25 - ESPERA_MIN ))
  [ "$MMBERT" = 1 ] && [ "$m" = e5-small ] && [ "$min" -gt "$MIN_E5" ] && min=$MIN_E5
  [ "$min" -ge 5 ] || { fallo "sin tiempo para $m"; estado "entrenar-$m" "OMITIDO sin tiempo"; return 1; }
  [ "$LOCAL" = 1 ] && EXTRA="--pasos 2 --epocas 1 --lote 4 --max-tok 64" || EXTRA="--epocas 2 --lote 16 --max-tok 256 --lr 3e-5 --bf16 --tope-tarea 1000"
  "$PY" -m model.alt.entrenar --datos "$RAIZ" --salida "$CK/$m" --codificador "$m" --semilla 0 --sellar --minutos "$min" $EXTRA \
    || { fallo "entrenar $m"; estado "entrenar-$m" "FALLO"; return 1; }
  estado "entrenar-$m" "OK $(tr -d '\n ' < "$CK/$m/historial.json" | cut -c1-200)"
}
# --- 5. evaluar con el mismo arnés (JevBench, batería oficial test, latencia CPU 4 hilos)
evaluar_con() {
  local m=$1
  [ -d "$CK/$m/mejor" ] || return 1
  "$PY" -m model.alt.evaluar --ckpt "$CK/$m/mejor" --jevbench "$JEV" --bateria "$DATOS/bateria" --salida "$OUT/$m" \
    || { fallo "evaluar $m"; estado "evaluar-$m" "FALLO"; return 1; }
  estado "evaluar-$m" "OK"
}
CODS="e5-small"; [ "$MMBERT" = 1 ] && CODS="e5-small mmbert-small"
for m in $CODS; do
  echo "== 4/5. $m $(date -u +%T), quedan $(quedan_min) min"
  entrenar_con "$m" && evaluar_con "$m"
done
kill "$VIGILANTE" 2>/dev/null
cierre
