#!/bin/bash
CHISPA_S3=__CHISPA_S3__
# user-data (≤ 16 KB) de una g5.xlarge BAJO DEMANDA (AMI DLAMI GPU PyTorch 2.10, Amazon Linux 2023, root, internet, rol con s3:Get/PutObject sin
# ListBucket). W3: ajuste fino de G.8 con aumento de datos y más español. El orquestador sustituye __CHISPA_S3__ y sube $CHISPA_S3/codigo.tgz
# (`bash model/l2/aws/empaquetar_ajuste.sh <sha> > codigo.tgz`). Patrón de general.sh. Pasos, cada uno deja OK/FALLO en estado.tsv:
#   1 entorno · 2 código, G.8 (general-20261029b), HF y JevBench · 3 model.datos (con sib200 y pawsx de train) y meta de tsjev solo (sin synzs ni
#   los pawsx/sib200 del meta, que repetirían filas) · 3b recuento del orden de score (R16) · 4 `entrenar --desde G.8 --aumento --episodios` (reparto de G.8, sin massive, hatecheck ni
#   inyecciones; lr 3e-5/1e-5; 50 min) · 5 mide el nuevo Y G.8 en la misma máquina: JevBench k=0, M3 (robustez), M4 (español) · 6 comparacion.md.
# Sube ckpt/mejor.pt, resultados.tgz, estado.tsv, comparacion.md y log.txt. Coste ≈ 1,5 USD: g5.xlarge 1,01 USD/h × ≈ 90 min (entorno 15, ajuste 50,
# medidas 20, subida 3); el techo es `shutdown -h +120` = 2,0 USD. Opcionales: CHISPA_{G8,META,BLANDAS}_S3, CHISPA_MINUTOS, CHISPA_MAX_FILAS_M3/M4.
# CHISPA_LOCAL=1: prueba en seco (G.8 aleatorio, fixtures, CHISPA_PASOS=6, max_tok 48; sin pip, descargas ni shutdown; «s3» = /tmp/chispa/s3/).
EXCLUIR=${CHISPA_EXCLUIR:-massive,hatecheck,inyecciones}
G8_S3=${CHISPA_G8_S3:-s3://chispa-pruebas-879381269751/general-20261029b/ckpt/mejor.pt}
META_S3=${CHISPA_META_S3:-s3://chispa-pruebas-879381269751/meta-20261027/meta}
BLANDAS_S3=${CHISPA_BLANDAS_S3:-s3://chispa-pruebas-879381269751/maestro-20261027/ronda1}
EPIS="--episodios --k-min 4 --k-max 32 --frac-meta 0.5 --frac-zeroshot 0.25"
G8="--tope-tarea 2000 --alfa 0.3 --max-tok 256 --excluir-fuera"
LOCAL=${CHISPA_LOCAL:-0}
AQUI=$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)   # solo para la prueba en seco
if [ "$LOCAL" = 1 ]; then [ "${CHISPA_S3#__}" != "$CHISPA_S3" ] && CHISPA_S3=s3://local/ajuste; else shutdown -h +120; fi
set -uo pipefail
export HOME="${HOME:-/root}"
T0=$(date +%s); TOPE=120
if [ "$LOCAL" = 1 ]; then BASE=${CHISPA_BASE:-/tmp/chispa-ajuste}; else BASE=/opt/chispa; fi
mkdir -p "$BASE"
exec > >(tee -a "$BASE/log.txt") 2>&1
echo "== arranque ajuste $(date -u +%FT%TZ) local=$LOCAL base=$BASE excluir=$EXCLUIR"
export HF_HOME="$HOME/hf"; mkdir -p "$HF_HOME"
REPO=$BASE/repo DATOS=$BASE/datos OUT=$BASE/resultados META=$BASE/meta BLANDAS=$BASE/blandas JEV=$BASE/jevbench NUEVO=$BASE/nuevo
G8CK=$BASE/g8.pt POTION=$BASE/potion.chispa-l1
FALLO=""

s3cp() {
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
  cp "$BASE/log.txt" "$OUT/log.txt" 2>/dev/null
  rm -f "$BASE/resultados.tgz"
  ( cd "$BASE" && find resultados -type f -size -20000k | LC_ALL=C sort > "$BASE/resultados.lista" && tar -czf "$BASE/resultados.tgz" -T "$BASE/resultados.lista" ) \
    || echo "no se pudo crear resultados.tgz"
  [ -f "$BASE/resultados.tgz" ] && { s3cp "$BASE/resultados.tgz" "$CHISPA_S3/resultados.tgz" || echo "no se pudo subir resultados.tgz"; }
  [ -f "$OUT/estado.tsv" ] && { s3cp "$OUT/estado.tsv" "$CHISPA_S3/estado.tsv" || echo "no se pudo subir estado.tsv"; }
  [ -f "$OUT/comparacion.md" ] && { s3cp "$OUT/comparacion.md" "$CHISPA_S3/comparacion.md" || echo "no se pudo subir comparacion.md"; }
  [ -f "$NUEVO/mejor.pt" ] && { s3cp "$NUEVO/mejor.pt" "$CHISPA_S3/ckpt/mejor.pt" || echo "no se pudo subir mejor.pt"; }
  s3cp "$BASE/log.txt" "$CHISPA_S3/log.txt" || echo "no se pudo subir log.txt"
  [ "$LOCAL" = 1 ] || shutdown -h now
}
trap subir_y_apagar EXIT
trap 'exit 143' TERM INT HUP
mkdir -p "$OUT"
estado() { printf '%s\t%s\n' "$1" "$2" >> "$OUT/estado.tsv"; echo "[$1] $2"; }
fallo() { echo "FALLO: $*"; FALLO="${FALLO:+$FALLO; }$*"; }
cierre() { echo "== listo $(date -u +%FT%TZ) fallo=${FALLO:-no} ($(( $(date +%s) - T0 )) s)"; echo "== estado.tsv"; cat "$OUT/estado.tsv" 2>/dev/null; exit 0; }
quedan_min() { echo $(( TOPE - ($(date +%s) - T0) / 60 )); }
tope() { local m=$(( $(quedan_min) - 8 )); [ "$m" -gt "$1" ] && m=$1; [ "$m" -lt 2 ] && m=2; echo $m; }   # el tope propio o lo que quede menos 8 min
[ "$LOCAL" = 1 ] && export ONEDNN_MAX_CPU_ISA=${ONEDNN_MAX_CPU_ISA:-AVX2}   # torch CPU muere a veces con SIGILL (rc 132)
reint() { local n=0 rc; while :; do "$@"; rc=$?; n=$((n+1)); { [ "$rc" = 132 ] && [ "$LOCAL" = 1 ] && [ $n -lt 4 ]; } || return $rc; echo "SIGILL: se repite $*" >&2; done; }

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
  "$PY" -m pip install -q --no-cache-dir -U transformers accelerate huggingface_hub pyyaml pyarrow numpy scipy scikit-learn tokenizers datasets \
    || { fallo "pip install"; estado entorno "FALLO pip"; cierre; }
  DEV=cuda
fi
estado entorno "OK $("$PY" -c "import torch; print('torch', torch.__version__, 'cuda', torch.cuda.is_available())") dispositivo $DEV"

# --- 2. código, G.8, modelos, datasets y JevBench
echo "== 2. código y datos $(date -u +%T)"
if [ "$LOCAL" = 1 ]; then
  d=/tmp/chispa/s3/${CHISPA_S3#s3://}; mkdir -p "$d"
  bash "$AQUI/empaquetar_ajuste.sh" HEAD --fixtures > "$d/codigo.tgz" || { fallo "empaquetar"; estado paquete "FALLO empaquetar"; cierre; }
fi
rm -rf "$REPO" "$JEV" "$META" "$DATOS" "$NUEVO"; mkdir -p "$REPO" "$DATOS" "$NUEVO" "$META"
for _ in $(seq 1 90); do
  s3cp "$CHISPA_S3/codigo.tgz" "$BASE/codigo.tgz" 2>/dev/null && tar -tzf "$BASE/codigo.tgz" >/dev/null 2>&1 && break
  rm -f "$BASE/codigo.tgz"; [ "$LOCAL" = 1 ] && break; sleep 30
done
tar -xzf "$BASE/codigo.tgz" -C "$REPO" && estado paquete "OK" || { fallo "no llegó un codigo.tgz válido"; estado paquete "FALLO sin codigo.tgz"; cierre; }
cd "$REPO" || cierre
export PYTHONPATH=$REPO:$REPO/sdk/python
if [ "$LOCAL" = 1 ]; then
  "$PY" -I -c "import sys; sys.path.insert(0, sys.argv[1]); import torch; from model.l2.exportar import modelo_aleatorio
torch.save({'modelo': modelo_aleatorio().state_dict(), 'cabezas': [], 'max_tok': 128}, sys.argv[2])" "$REPO" "$G8CK" \
    && estado g8 "OK aleatorio" || { fallo "checkpoint aleatorio"; estado g8 "FALLO"; cierre; }
else s3cp "$G8_S3" "$G8CK" && estado g8 "OK $(stat -c %s "$G8CK") bytes de $G8_S3" || { fallo "G.8 $G8_S3"; estado g8 "FALLO"; cierre; }
fi
if [ "$LOCAL" != 1 ]; then
  "$PY" -I - <<'PYEOF' || fallo "descarga de modelos y datasets de HF"
import glob, os, shutil, sys
from huggingface_hub import snapshot_download as s
fallos = []
def intenta(*a, opcional=False, **k):
    try:
        s(*a, **k)
    except Exception as e:
        if not opcional:
            fallos.append(a[0])
        print("aviso: no se pudo bajar", a[0], e)
intenta("intfloat/multilingual-e5-small", allow_patterns=["*.json", "*.safetensors", "*.txt", "*.model", "tokenizer*"])
intenta("minishlab/potion-multilingual-128M")   
intenta("mteb/amazon_massive_intent", repo_type="dataset", allow_patterns=["*es*", "*/en.json.gz", "*.json", "*.md", "*.csv"])
intenta("Paul/hatecheck-spanish", repo_type="dataset", allow_patterns=["*es*", "*.json", "*.md", "*.csv"])
for d in ("PolyAI/banking77", "clinc/clinc_oos", "deepset/prompt-injections", "SINAI/ALIA-es-discriminative-hate-speech",
          "Multilingual-Perspectivist-NLU/MultiPICo", "bgonzalezbustamante/toxicity-protests-ES",
          "bgonzalezbustamante/toxicity-Constitution-ES", "mrm8488/go_emotions-es-mt",
          "tanaos/synthetic-spam-detection-dataset-spanish", "tasksource/it-support-tickets",
          "FelipeGuerra/Colombian_Spanish_Cyberbullying_Dataset_1", "FelipeGuerra/Colombian_Spanish_Cyberbullying_Dataset_2",
          "somosnlp/spa_climate_detection", "somosnlp/suicide-comments-es"):
    intenta(d, repo_type="dataset")
intenta("PolyAI/banking77", repo_type="dataset", revision="refs/convert/parquet")
intenta("tasksource/tasksource-jev-typed-decisions", repo_type="dataset", allow_patterns=["sources.yaml", "README.md"])   # para --excluir-fuera
intenta("facebook/xnli", repo_type="dataset", allow_patterns=["es/*", "en/test-*", "*.md"])
intenta("google-research-datasets/paws-x", repo_type="dataset", allow_patterns=["es/*", "en/test-*", "README.md"])
intenta("Davlan/sib200", repo_type="dataset", allow_patterns=["data/spa_Latn/*", "data/eng_Latn/*", "README.md"])
snaps = glob.glob(os.path.expanduser("~/hf/hub/datasets--PolyAI--banking77/snapshots/*"))
con_datos = [d for d in snaps if glob.glob(d + "/**/*.parquet", recursive=True)]
for d in snaps:
    if con_datos and d not in con_datos:
        shutil.rmtree(d)
print("descargas con fallo:", fallos or "ninguna")
sys.exit(1 if fallos else 0)
PYEOF
  git clone -q https://github.com/fstandhartinger/jevbench "$JEV" || { fallo "git clone de JevBench"; estado jevbench "FALLO clone"; cierre; }
else cp -r "$REPO/model/evaluacion/tests/fixtures/jevbench" "$JEV" || { fallo "sin JevBench local"; cierre; }; fi
ls "$HF_HOME"/hub/models--intfloat--multilingual-e5-small/snapshots/*/config.json >/dev/null 2>&1 || { fallo "e5 no está en $HF_HOME"; estado modelos "FALLO sin e5"; cierre; }
export HF_HUB_OFFLINE=1
estado jevbench "OK $(cat "$JEV"/datasets/public/*.jsonl | wc -l) casos"

# --- 3. datos
echo "== 3. datos $(date -u +%T)"
CONV=(--salida "$DATOS"); [ "$LOCAL" = 1 ] && CONV+=(--fixtures)
if "$PY" -m model.datos.convertir "${CONV[@]}" > "$OUT/convertir.log" 2>&1; then
  estado datos "OK $(grep -c convertida "$OUT/convertir.log") fuentes convertidas ($(grep -E '^(sib200|pawsx|odio_alia|toxicidad_[a-z]+) ' "$OUT/convertir.log" | cut -d' ' -f1 | tr '\n' ' '))"
else tail -8 "$OUT/convertir.log"; estado datos "FALLO ver convertir.log"; fallo "convertir"; cierre; fi
rm -rf "$BLANDAS"; mkdir -p "$BLANDAS"
if s3cp "$BLANDAS_S3/blandas.tgz" "$BASE/blandas.tgz" 2>/dev/null; then tar -xzf "$BASE/blandas.tgz" -C "$BLANDAS" || fallo "blandas.tgz"; fi
HAY_META=0
if [ "$LOCAL" = 1 ]; then
  "$PY" -I - "$META" <<'PYEOF' && HAY_META=1
import gzip, json, os, sys
os.makedirs(sys.argv[1] + "/tsjev")
with gzip.open(sys.argv[1] + "/tsjev/train-00000.jsonl.gz", "wt", encoding="utf-8") as f:
    for tarea, n in (("demo/a", 60), ("demo/b", 40)):
        for i in range(n):
            ops = ["x", "y", "z"]
            f.write(json.dumps({"id": "tsjev:train:%s-%d" % (tarea[-1], i), "split": "train", "uso_comercial": True, "tarea": tarea, "tipo": "choice",
              "pregunta": "¿Cuál?", "texto": "texto inventado %d de %s" % (i, tarea), "opciones": ops, "descripciones": {o: "desc " + o for o in ops},
              "etiqueta": ops[i % 3], "idioma": "en", "fuente": "x", "licencia": "mit"}) + "\n")
PYEOF
  [ $HAY_META = 1 ] && estado meta "OK inventado"
else   # solo tsjev
  "$PY" -I -c 'import json,sys; print("\n".join(f for f in json.load(open(sys.argv[1]))["ficheros"] if f.startswith("tsjev/")))' \
    "$REPO/model/meta/resultados/conversion-20261027.json" > "$BASE/meta.lista"
  NM=0; NF=0
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    mkdir -p "$META/$(dirname "$f")"
    if s3cp "$META_S3/$f" "$META/$f" 2>/dev/null; then NM=$((NM+1)); else NF=$((NF+1)); echo "aviso: no se pudo bajar $f"; fi
  done < "$BASE/meta.lista"
  if [ "$NF" = 0 ] && [ "$NM" -gt 0 ]; then HAY_META=1; estado meta "OK $NM ficheros de tsjev"; else estado meta "FALLO $NF de $((NM+NF)) ficheros (se ajusta sin meta)"; fallo "meta de tsjev"; fi
fi
[ $HAY_META = 1 ] && "$PY" -m model.meta.muestreo "$META" > "$OUT/fuera.json"

# --- 3b. recuento de filas score con orden no ascendente o ids fuera de 1..K (R16), antes de entrenar: los cargadores descartan las segundas
echo "== 3b. orden de score $(date -u +%T)"
CONT=(--salida "$OUT/orden-score" --datos "$DATOS"); [ $HAY_META = 1 ] && CONT+=(--meta "$META")
if "$PY" -m model.l2.contar_orden_score "${CONT[@]}" > "$OUT/orden-score.log" 2>&1 && [ -f "$OUT/orden-score/orden-score.json" ]; then
  estado orden_score "OK $("$PY" -I -c 'import json,sys; t=json.load(open(sys.argv[1]))["total"]; print("score %d, no ascendente %d, fuera de 1..K %d (descartadas al cargar)" % (t["score"], t["no_ascendente"], t["fuera_de_1k"]))' "$OUT/orden-score/orden-score.json")"
else tail -5 "$OUT/orden-score.log"; estado orden_score "FALLO ver orden-score.log"; fallo "recuento de orden de score"; fi

# --- 4. ajuste fino
echo "== 4. ajuste fino $(date -u +%T)"
ARGS=(--salida "$NUEVO" --datos "$DATOS" --herramientas --blandas "$BLANDAS" --s3 "$CHISPA_S3/ckpt" --max-filas 300000 --excluir-tareas "$EXCLUIR"
      --desde "$G8CK" --aumento)
[ $HAY_META = 1 ] && ARGS+=(--meta "$META")
read -ra L2A <<< "$EPIS $G8"
ARGS+=("${L2A[@]}")
if [ "$LOCAL" = 1 ]; then
  ARGS+=(--pasos "${CHISPA_PASOS:-6}" --device cpu --max-filas 2000 --ckpt-cada 60 --eval-cada 3 --dev-max 100 --lote 16 --max-tok 48)
else ARGS+=(--minutos "$(( ${CHISPA_MINUTOS:-50} < $(tope 50) ? ${CHISPA_MINUTOS:-50} : $(tope 50) ))" --epocas 1 --device cuda); fi
OK=0
for intento in 1 2; do
  reint "$PY" -u -m model.l2.entrenar "${ARGS[@]}" > "$OUT/entrenar-$intento.log" 2>&1 && { OK=1; break; }
  echo "entrenar intento $intento falló (rc=$?)"; tail -5 "$OUT/entrenar-$intento.log"
done
cp "$NUEVO/entrenamiento.json" "$OUT/" 2>/dev/null
if [ $OK = 1 ] && [ -f "$NUEVO/mejor.pt" ]; then
  estado ajuste "OK $("$PY" -m model.l2.comparar_ajuste --una ajuste "$OUT/entrenamiento.json" 2>/dev/null || echo 'ver entrenar-*.log')"
else estado ajuste "FALLO dos intentos, ver entrenar-*.log"; fallo "entrenar falló dos veces"; fi

# --- 5. medidas: el nuevo y G.8 en la misma máquina
MAXTOK=(); [ "$LOCAL" = 1 ] && MAXTOK=(--max-tok 48)
HF4=(); [ "$LOCAL" = 1 ] && HF4=(--hf "$REPO/model/l2/tests/fixtures_espanol")
JD=(--device "$DEV"); [ "$LOCAL" = 1 ] && JD+=(--max-casos 40)
F3=(--max-filas "${CHISPA_MAX_FILAS_M3:-150}"); F4=(--max-filas "${CHISPA_MAX_FILAS_M4:-400}"); [ "$LOCAL" = 1 ] && { F3=(--max-filas 30); F4=(--max-filas 30); }
echo "== 5. medidas $(date -u +%T)"
if "$PY" "$REPO/runtime/l1/exportar.py" "$(ls -d "$HF_HOME"/hub/models--minishlab--potion-multilingual-128M/snapshots/* | head -1)" "$POTION" > "$OUT/potion.log" 2>&1; then
  estado potion "OK $(stat -c %s "$POTION") bytes"
else tail -5 "$OUT/potion.log"; estado potion "FALLO ver potion.log (sin M3)"; fallo "potion"; fi
medir() {
  local n=$1 ck=$2 d=$OUT/$1; mkdir -p "$d"
  if reint timeout "$(tope 8)m" "$PY" -u -m model.evaluacion.jevbench_l2 --ckpt "$ck" --jevbench "$JEV" --salida "$d/jev" --k 0 "${JD[@]}" "${MAXTOK[@]}" > "$d/jev.log" 2>&1; then
    estado "jev_$n" "OK $(grep -o 'L2 k=0: exactitud [0-9.]*, macro-F1 [0-9.]*' "$d/jev.log" | tail -1)"
  else tail -8 "$d/jev.log"; estado "jev_$n" "FALLO ver $n/jev.log"; fallo "JevBench $n"; fi
  if [ -s "$POTION" ] && reint timeout "$(tope 12)m" "$PY" -u -m model.l2.robustez --ckpt "$ck" --potion "$POTION" --datos "$DATOS" --salida "$d/m3" --device "$DEV" \
       "${F3[@]}" "${MAXTOK[@]}" > "$d/m3.log" 2>&1 && [ -f "$d/m3/robustez.json" ]; then
    estado "m3_$n" "OK $("$PY" -m model.l2.comparar_ajuste --una m3 "$d/m3/robustez.json")"
  else tail -8 "$d/m3.log" 2>/dev/null; estado "m3_$n" "FALLO ver $n/m3.log"; fallo "M3 $n"; fi
  if reint timeout "$(tope 8)m" "$PY" -u -m model.l2.espanol --ckpt "$ck" --salida "$d/m4" --device "$DEV" "${F4[@]}" "${HF4[@]}" "${MAXTOK[@]}" > "$d/m4.log" 2>&1 \
     && [ -f "$d/m4/espanol.json" ]; then
    estado "m4_$n" "OK $("$PY" -m model.l2.comparar_ajuste --una m4 "$d/m4/espanol.json")"
  else tail -8 "$d/m4.log"; estado "m4_$n" "FALLO ver $n/m4.log"; fallo "M4 $n"; fi
}
if [ -f "$NUEVO/mejor.pt" ]; then medir nuevo "$NUEVO/mejor.pt"; else for p in jev m3 m4; do estado "${p}_nuevo" "OMITIDO sin checkpoint nuevo"; done; fi
medir g8 "$G8CK"

# --- 6. comparación
"$PY" -m model.l2.comparar_ajuste "$OUT" > "$OUT/comparacion.md"
estado comparacion "$([ -s "$OUT/comparacion.md" ] && echo 'OK comparacion.md' || echo 'FALLO')"
cierre
