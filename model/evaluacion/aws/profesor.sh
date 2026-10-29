#!/bin/bash
CHISPA_S3=__CHISPA_S3__
# user-data (≤ 16 KB) de una c6a.2xlarge spot (Amazon Linux 2023, x86_64, 8 vCPU, SIN GPU: todo en CPU), root, con internet y rol con
# s3:GetObject/PutObject (sin List), sin SSH. G.9: techo del profesor zero-shot MoritzLaurer/bge-m3-zeroshot-v2.0-c (MIT, comercial, destilable)
# y -v2.0 (MIT, datos de licencia mixta: solo referencia) por NLI (model.evaluacion.profesor) en JevBench entero y en las tareas no vistas
# (massive, hatecheck, inyecciones y el 10 % de tasksource apartado, ≤ 300 filas por tarea). Mismo patrón que jevbench.sh y barrido.sh.
# El orquestador sustituye __CHISPA_S3__ y sube $CHISPA_S3/codigo.tgz (bash model/evaluacion/aws/empaquetar_profesor.sh > codigo.tgz).
# Opcionales: CHISPA_FUERA_S3 (por defecto s3://chispa-pruebas-879381269751/general-20261029b/fuera.json), CHISPA_META_S3 (por defecto
# s3://chispa-pruebas-879381269751/meta-20261027/meta; solo se bajan tsjev/dev y tsjev/test), CHISPA_JEV_REF, CHISPA_MAX_FILAS (300).
# Pasos: 1. venv con torch CPU; 2. código; 3. los dos modelos de HF, datasets, JevBench, fuera.json y meta tsjev; model.datos.convertir;
# 4. `profesor preparar` (recorta) y `profesor medir` por modelo (plantilla elegida en dev); 5. `profesor_informe` → informe.md.
# Al salir (trap) sube informe.md, resultados.tgz y log.txt y apaga. Apagado forzoso a los 150 min (≈ 0,5 USD como mucho a ~0,2 USD/h spot).
# CHISPA_LOCAL=1: prueba en seco sin dnf, pip, descargas ni shutdown: ~/venv, fixtures, NLI diminuto aleatorio con el tokenizador de e5 y
# fuera.json inventado; el "s3" es /tmp/chispa/s3/<prefijo>.
LOCAL=${CHISPA_LOCAL:-0}
MAX_FILAS=${CHISPA_MAX_FILAS:-300}
FUERA_S3=${CHISPA_FUERA_S3:-s3://chispa-pruebas-879381269751/general-20261029b/fuera.json}
META_S3=${CHISPA_META_S3:-s3://chispa-pruebas-879381269751/meta-20261027/meta}
MODELOS_HF=("bge-m3-zeroshot-c=MoritzLaurer/bge-m3-zeroshot-v2.0-c" "bge-m3-zeroshot=MoritzLaurer/bge-m3-zeroshot-v2.0")
AQUI=$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)   # solo para la prueba en seco
if [ "$LOCAL" = 1 ]; then
  MAX_FILAS=${CHISPA_MAX_FILAS:-40}
  [ "${CHISPA_S3#__}" != "$CHISPA_S3" ] && CHISPA_S3=s3://local/profesor
else shutdown -h +150; fi
set -uo pipefail
export HOME="${HOME:-/root}"
T0=$(date +%s)
if [ "$LOCAL" = 1 ]; then BASE=/tmp/chispa/profesor; else BASE=/opt/chispa; fi
mkdir -p "$BASE"
exec > >(tee -a "$BASE/log.txt") 2>&1
echo "== arranque profesor $(date -u +%FT%TZ) local=$LOCAL base=$BASE max_filas=$MAX_FILAS"
REPO=$BASE/repo DATOS=$BASE/datos RES=$BASE/resultados JEV=$BASE/jevbench META=$BASE/meta MOD=$BASE/modelos PREP=$BASE/prep
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
  mkdir -p "$RES"
  [ -n "$FALLO" ] && echo "$FALLO" > "$RES/FALLO"
  cp "$BASE/log.txt" "$RES/log.txt" 2>/dev/null
  rm -f "$BASE/resultados.tgz"
  ( cd "$BASE" && tar -czf resultados.tgz resultados ) || echo "no se pudo crear resultados.tgz"
  [ -f "$BASE/resultados.tgz" ] && { s3cp "$BASE/resultados.tgz" "$CHISPA_S3/resultados.tgz" || echo "no se pudo subir resultados.tgz"; }
  [ -f "$RES/informe.md" ] && { s3cp "$RES/informe.md" "$CHISPA_S3/informe.md" || echo "no se pudo subir informe.md"; }
  s3cp "$BASE/log.txt" "$CHISPA_S3/log.txt" || echo "no se pudo subir log.txt"
  [ "$LOCAL" = 1 ] || shutdown -h now
}
trap subir_y_apagar EXIT
trap 'exit 143' TERM INT HUP
fallo() { echo "FALLO: $*"; FALLO="${FALLO:+$FALLO; }$*"; }
cierre() { df -h "$BASE" | tail -1; echo "== listo $(date -u +%FT%TZ) fallo=${FALLO:-no} ($(( $(date +%s) - T0 )) s)"; exit 0; }
quedan_min() { echo $(( 150 - ($(date +%s) - T0) / 60 )); }

# --- 1. entorno -------------------------------------------------------------------------------------------------------------
export HF_HOME="$HOME/hf"; mkdir -p "$HF_HOME" "$RES"
if [ "$LOCAL" = 1 ]; then PY=${CHISPA_PY:-$HOME/venv/bin/python}
else
  echo "== 1. entorno $(date -u +%T)"
  dnf install -y -q gcc tar gzip git python3.11 python3.11-pip || { fallo "dnf install"; cierre; }
  python3.11 -m venv "$BASE/venv" || { fallo "venv"; cierre; }
  PY=$BASE/venv/bin/python
  "$PY" -m pip install -q --no-cache-dir -U pip \
    && "$PY" -m pip install -q --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && "$PY" -m pip install -q --no-cache-dir numpy scikit-learn transformers tokenizers sentencepiece protobuf huggingface_hub pyyaml pyarrow datasets \
    || { fallo "pip install"; cierre; }
fi
"$PY" -c "import sys, numpy, torch, transformers; print(sys.version.split()[0], 'torch', torch.__version__, 'hilos', torch.get_num_threads(), 'transformers', transformers.__version__)" \
  || { fallo "imports de Python"; cierre; }

# --- 2. código --------------------------------------------------------------------------------------------------------------
echo "== 2. código $(date -u +%T)"
rm -rf "$REPO" "$DATOS" "$JEV" "$META" "$MOD" "$PREP"; mkdir -p "$REPO" "$DATOS" "$META" "$MOD" "$PREP"
if [ "$LOCAL" = 1 ]; then bash "$AQUI/empaquetar_profesor.sh" --fixtures > "$BASE/codigo.tgz" || { fallo "empaquetar_profesor.sh"; cierre; }
else
  for _ in $(seq 1 90); do   # 90 × 30 s = 45 min
    s3cp "$CHISPA_S3/codigo.tgz" "$BASE/codigo.tgz" 2>/dev/null && tar -tzf "$BASE/codigo.tgz" >/dev/null 2>&1 && break
    rm -f "$BASE/codigo.tgz"; sleep 30
  done
fi
tar -xzf "$BASE/codigo.tgz" -C "$REPO" || { fallo "no llegó un codigo.tgz válido"; cierre; }
cd "$REPO" || { fallo "sin repo"; cierre; }
export PYTHONPATH=$REPO
[ -f model/evaluacion/profesor.py ] && [ -f model/meta/muestreo.py ] || { fallo "el código no trae profesor.py o muestreo.py"; cierre; }
{ lscpu; echo "nproc: $(nproc)"; } > "$RES/hardware.txt"

# --- 3. modelos, datos, JevBench, fuera.json y meta -----------------------------------------------------------------------
echo "== 3. descargas $(date -u +%T)"
if [ "$LOCAL" = 1 ]; then
  E5=$(ls -d "$HF_HOME"/hub/models--intfloat--multilingual-e5-small/snapshots/*/ 2>/dev/null | head -1)
  [ -f "${E5}tokenizer.json" ] || { fallo "sin e5 local para el tokenizador"; cierre; }
  for m in "${MODELOS_HF[@]}"; do "$PY" -m model.evaluacion.profesor falso "$MOD/${m%%=*}" --tokenizador "$E5" || { fallo "modelo falso"; cierre; }; done
  cp -r "$REPO/model/evaluacion/tests/fixtures/jevbench" "$JEV"
  cat > "$BASE/fuera-fixture.py" <<'PYEOF'
import gzip, json, os, sys
d, f = sys.argv[1], sys.argv[2]
os.makedirs(d + "/tsjev", exist_ok=True)
for sp in ("dev", "test"):
    with gzip.open("%s/tsjev/%s-00000.jsonl.gz" % (d, sp), "wt", encoding="utf-8") as fh:
        for t in ("demo/a", "demo/b"):
            for i in range(12):
                ops = ["x", "y", "z"]
                fh.write(json.dumps({"id": "tsjev:%s:%s-%d" % (sp, t.replace("/", "_"), i), "split": sp, "uso_comercial": True, "tarea": t, "tipo": "choice",
                  "pregunta": "¿Cuál?", "texto": "texto inventado %d de %s" % (i, t), "opciones": ops, "descripciones": {o: "desc " + o for o in ops},
                  "etiqueta": ops[i % 3], "idioma": "en", "fuente": "x", "licencia": "mit"}) + "\n")
json.dump({"tareas_fuera": ["demo/a"]}, open(f, "w"))
PYEOF
  "$PY" -I "$BASE/fuera-fixture.py" "$META" "$BASE/fuera.json" || fallo "fixture de fuera"
else
  "$PY" -I - "$MOD" <<'PYEOF' || fallo "descarga de modelos (ver aviso)"
import sys
from huggingface_hub import snapshot_download as s
fallos = []
for n, r in (("bge-m3-zeroshot-c", "MoritzLaurer/bge-m3-zeroshot-v2.0-c"), ("bge-m3-zeroshot", "MoritzLaurer/bge-m3-zeroshot-v2.0")):
    try:
        s(r, local_dir=sys.argv[1] + "/" + n, allow_patterns=["*.json", "*.safetensors", "*.model", "*.txt", "tokenizer*"])
    except Exception as e:
        fallos.append(r); print("aviso: no se pudo bajar", r, e)
raise SystemExit(1 if fallos else 0)
PYEOF
  "$PY" -I - <<'PYEOF' || fallo "descarga de datasets (ver aviso)"
from huggingface_hub import snapshot_download as s
fallos = []
for r, pat in (("mteb/amazon_massive_intent", ["*es*", "*.json", "*.md", "*.csv"]), ("Paul/hatecheck-spanish", ["*es*", "*.json", "*.md", "*.csv"]), ("deepset/prompt-injections", None)):
    try:
        s(r, repo_type="dataset", **({"allow_patterns": pat} if pat else {}))
    except Exception as e:
        fallos.append(r); print("aviso: no se pudo bajar", r, e)
raise SystemExit(1 if fallos else 0)
PYEOF
  git clone -q https://github.com/fstandhartinger/jevbench "$JEV" && { [ -z "${CHISPA_JEV_REF:-}" ] || git -C "$JEV" checkout -q "$CHISPA_JEV_REF"; } \
    || { fallo "git clone de JevBench"; cierre; }
  s3cp "$FUERA_S3" "$BASE/fuera.json" || fallo "sin fuera.json: no hay tasksource apartado"
  for f in dev test; do
    mkdir -p "$META/tsjev"; s3cp "$META_S3/tsjev/$f-00000.jsonl.gz" "$META/tsjev/$f-00000.jsonl.gz" || fallo "sin meta tsjev/$f"
  done
  export HF_HUB_OFFLINE=1   # a partir de aquí todo sale de $HF_HOME y $MOD
fi
for m in "${MODELOS_HF[@]}"; do ls "$MOD/${m%%=*}"/config.json >/dev/null 2>&1 || fallo "sin modelo ${m%%=*}"; done
{ git -C "$JEV" rev-parse HEAD 2>/dev/null || echo "fixture"; } > "$RES/jevbench-sha.txt"
echo "== convertir $(date -u +%T)"
CONV=(--salida "$DATOS" --fuentes massive,hatecheck,inyecciones); [ "$LOCAL" = 1 ] && CONV+=(--fixtures)
"$PY" -m model.datos.convertir "${CONV[@]}" || fallo "convertir"

# --- 4. recorte y medida -----------------------------------------------------------------------------------------------------
echo "== 4. preparar $(date -u +%T)"
FU=(); [ -f "$BASE/fuera.json" ] && FU=(--meta "$META" --fuera "$BASE/fuera.json")
"$PY" -m model.evaluacion.profesor preparar --datos "$DATOS" "${FU[@]}" --salida "$PREP" --max-filas "$MAX_FILAS" || { fallo "preparar"; cierre; }
MJ=(); [ "$LOCAL" = 1 ] && MJ=(--max-jev 30)
for m in "${MODELOS_HF[@]}"; do   # el destilable primero; cada modelo en su proceso y con su tope
  n=${m%%=*}
  [ "$(quedan_min)" -lt 15 ] && { fallo "sin tiempo para $n"; continue; }
  echo "== medir $n $(date -u +%T): quedan $(quedan_min) min"
  timeout $(( ($(quedan_min) - 10) * 60 )) "$PY" -u -m model.evaluacion.profesor medir --modelo "$n=$MOD/$n" --conjuntos "$PREP" --jevbench "$JEV" \
    --salida "$RES" "${MJ[@]}" || fallo "medir $n"
done

# --- 5. informe ------------------------------------------------------------------------------------------------------------------------
echo "== 5. informe $(date -u +%T)"
MIN=$(( ($(date +%s) - T0) / 60 + 3 ))   # + subida y apagado
"$PY" -m model.evaluacion.profesor_informe "$RES" --minutos "$MIN" || fallo "informe"
cierre
