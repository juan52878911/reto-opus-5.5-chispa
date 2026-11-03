#!/bin/bash
CHISPA_S3=__CHISPA_S3__
# PREPARADO, NO EJECUTADO. Lo lanza el orquestador cuando Juan dé el OK al gasto (hito 4, alternativa b).
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
SHUTDOWN_MIN=$([ "$MMBERT" = 1 ] && echo 300 || echo 180)
if [ "$LOCAL" = 1 ]; then CHISPA_S3=${CHISPA_S3#__*}; [ -n "$CHISPA_S3" ] || CHISPA_S3=s3://local/alt
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
  [ "$LOCAL" = 1 ] || shutdown -h now
}
trap subir_y_apagar EXIT
trap 'exit 143' TERM INT HUP
cierre() { echo "== listo $(date -u +%FT%TZ) fallo=${FALLO:-no} ($(( $(date +%s) - T0 )) s)"; exit 0; }

# Watcher de tope: a 10 min del techo manda TERM al entrenamiento (guarda la época en curso con --minutos) y deja tiempo para subir.
( while sleep 60; do [ "$(quedan_min)" -le 10 ] && { echo "== tope: quedan $(quedan_min) min, se cierra"; pkill -TERM -f "model.alt.entrenar" ; pkill -TERM -f "model.alt.evaluar"; break; }; done ) &
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

# --- 2. código y datos
echo "== 2. código y datos $(date -u +%T)"
mkdir -p "$REPO" "$DATOS" "$JEV"
if [ "$LOCAL" = 1 ]; then AQUI=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd); REPO=$(cd "$AQUI/../../.." && pwd); estado codigo "OK repo local $REPO"
else
  s3cp "$CHISPA_S3/codigo.tgz" "$BASE/codigo.tgz" && tar -xzf "$BASE/codigo.tgz" -C "$REPO" || { fallo "codigo.tgz"; estado codigo "FALLO"; cierre; }
  [ -f "$REPO/model/alt/manifiesto.py" ] || { fallo "codigo.tgz sin model/alt"; estado codigo "FALLO sin model/alt"; cierre; }
  s3cp "$CHISPA_S3/datos.tgz" "$BASE/datos.tgz" && tar -xzf "$BASE/datos.tgz" -C "$DATOS" || { fallo "datos.tgz"; estado datos "FALLO"; cierre; }
  s3cp "$CHISPA_S3/jevbench.tgz" "$BASE/jevbench.tgz" && tar -xzf "$BASE/jevbench.tgz" -C "$JEV" || { fallo "jevbench.tgz"; estado datos "FALLO jevbench"; cierre; }
  estado codigo "OK"
fi
cd "$REPO" || cierre
export PYTHONPATH="$REPO"

# --- 3. tsjev filtrado por el manifiesto (solo tareas comerciales sin SA/NC/ND) y manifiesto válido
echo "== 3. manifiesto $(date -u +%T)"
"$PY" -m model.alt.manifiesto validar || { fallo "manifiesto no válido"; estado manifiesto "FALLO"; cierre; }
if [ "$LOCAL" != 1 ]; then
  "$PY" -m model.alt.manifiesto filtrar --entrada "$DATOS/tsjev" --salida "$DATOS/datos/tsjev-admitido.jsonl.gz" \
    || { fallo "filtrar tsjev"; estado tsjev "FALLO"; cierre; }
fi
estado manifiesto "OK"

# --- 4. entrenar (--sellar fija filas y sha256 de lo que se entrena; entrenar se niega si algo no valida)
entrenar_con() {  # $1 = alias del codificador
  local m=$1 min; min=$(( $(quedan_min) - 25 ))
  [ "$min" -ge 5 ] || { fallo "sin tiempo para $m"; estado "entrenar-$m" "OMITIDO sin tiempo"; return 1; }
  [ "$LOCAL" = 1 ] && EXTRA="--pasos 2 --epocas 1 --lote 4 --max-tok 64" || EXTRA="--epocas 2 --lote 16 --max-tok 256 --lr 3e-5 --bf16 --tope-tarea 1000"
  "$PY" -m model.alt.entrenar --datos "$DATOS/datos" --salida "$CK/$m" --codificador "$m" --semilla 0 --sellar --minutos "$min" $EXTRA \
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
