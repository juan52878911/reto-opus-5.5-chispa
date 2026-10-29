#!/usr/bin/env bash
# Lo corre extra.sh del perfil personal al hornear el dorado de kindling (con internet), en ~/<repo>.
# Deja Go, un venv de Python con torch CPU y los codificadores de la fase 0 ya descargados.
set -uo pipefail

GO=1.27.1
curl -fsSL "https://go.dev/dl/go${GO}.linux-amd64.tar.gz" | tar -C "$HOME" -xz && mv "$HOME/go" "$HOME/go-sdk" \
  || echo "aviso: no se pudo instalar Go ${GO}"
# Módulos de Go del repo (kindling v0.17.0 entre ellos) en la caché: en las VM no hay red.
for m in go.mod arena/go.mod server/go.mod sdk/go/go.mod; do
  [ -f "$m" ] && (cd "$(dirname "$m")" && GOTOOLCHAIN=local "$HOME/go-sdk/bin/go" mod download) \
    || true
done
"$HOME/go-sdk/bin/go" env GOMODCACHE
# ONNX Runtime para `-tags ort` (server/go.mod usa onnxruntime_go v1.38.0, probado con la 1.31.1); gcc para cgo.
ORT=1.31.1
mkdir -p "$HOME/ort" && curl -fsSL "https://github.com/microsoft/onnxruntime/releases/download/v${ORT}/onnxruntime-linux-x64-${ORT}.tgz" \
  | tar -xz -C "$HOME/ort" --strip-components=1 || echo "aviso: no se pudo bajar ONNX Runtime ${ORT}"
command -v gcc >/dev/null || { sudo -n apt-get install -y -q gcc >/dev/null 2>&1 || echo "aviso: sin gcc (cgo)"; }

python3 -m venv "$HOME/venv"
# Sin optimum: su 1.17 no importa con transformers 5 (se exporta con torch.onnx).
# Una sola llamada: si torch se instala aparte, las dependencias lo reemplazan por el de CUDA (6 GB).
"$HOME/venv/bin/pip" install -q --no-cache-dir --index-url https://download.pytorch.org/whl/cpu \
  --extra-index-url https://pypi.org/simple torch transformers sentence-transformers onnx onnxruntime \
  datasets scikit-learn pandas huggingface_hub model2vec pytest
"$HOME/venv/bin/python" -c "import torch; assert not torch.version.cuda, torch.version.cuda; print('torch', torch.__version__)"

export HF_HOME="$HOME/hf"
for m in intfloat/multilingual-e5-small jhu-clsp/mmBERT-small minishlab/potion-multilingual-128M \
         knowledgator/gliclass-modern-base-v3.0 SupersonicLabs/Julia-1 doofz/THX-01 \
         convaiinnovations/laya-multilingual; do
  "$HOME/venv/bin/python" -c "import sys; from huggingface_hub import snapshot_download as s; \
s(sys.argv[1], allow_patterns=['*.json','*.safetensors','*.txt','*.model','*.py','tokenizer*'])" "$m" \
    && { ls "$HF_HOME"/hub/models--${m//\//--}/snapshots/*/*.safetensors >/dev/null 2>&1 \
         || "$HOME/venv/bin/python" -c "import sys; from huggingface_hub import hf_hub_download as h; \
h(sys.argv[1], 'pytorch_model.bin')" "$m"; } \
    || echo "aviso: no se pudo bajar $m"
done

# Datos públicos de la fase 0 (sondeo en español), también sin red en las VM.
for d in mteb/amazon_massive_intent Paul/hatecheck-spanish; do
  "$HOME/venv/bin/python" -c "import sys; from huggingface_hub import snapshot_download as s; \
s(sys.argv[1], repo_type='dataset', allow_patterns=['*es*','*.json','*.md','*.csv'])" "$d" \
    || echo "aviso: no se pudo bajar $d"
done

# Datos de la fase 1 (conversor T1.1): pequeños, enteros; de XNLI solo el español.
for d in PolyAI/banking77 clinc/clinc_oos deepset/prompt-injections; do
  "$HOME/venv/bin/python" -c "import sys; from huggingface_hub import snapshot_download as s; \
s(sys.argv[1], repo_type='dataset')" "$d" || echo "aviso: no se pudo bajar $d"
done
# banking77 en main es un script que baja de GitHub: se toma la conversión a parquet del Hub.
"$HOME/venv/bin/python" -c "from huggingface_hub import snapshot_download as s; \
s('PolyAI/banking77', repo_type='dataset', revision='refs/convert/parquet')" || echo "aviso: no se pudo bajar banking77 (parquet)"
"$HOME/venv/bin/python" -c "from huggingface_hub import snapshot_download as s; \
s('facebook/xnli', repo_type='dataset', allow_patterns=['es/*','*.md'])" || echo "aviso: no se pudo bajar facebook/xnli"

# Datos de libre uso (bóveda 17-chispa/01-investigacion/07-datos-de-libre-uso.md). Pequeños y enteros, o solo español.
for d in SINAI/ALIA-es-discriminative-hate-speech Multilingual-Perspectivist-NLU/MultiPICo \
         bgonzalezbustamante/toxicity-protests-ES bgonzalezbustamante/toxicity-Constitution-ES \
         mrm8488/go_emotions-es-mt tanaos/synthetic-spam-detection-dataset-spanish tasksource/it-support-tickets \
         FelipeGuerra/Colombian_Spanish_Cyberbullying_Dataset_1 FelipeGuerra/Colombian_Spanish_Cyberbullying_Dataset_2 \
         somosnlp/suicide-comments-es somosnlp/spa_climate_detection MoritzLaurer/synthetic_zeroshot_mixtral_v0.1; do
  "$HOME/venv/bin/python" -c "import sys; from huggingface_hub import snapshot_download as s; \
s(sys.argv[1], repo_type='dataset')" "$d" || echo "aviso: no se pudo bajar $d"
done
for d in "Davlan/sib200 *spa_Latn*" "google-research-datasets/paws-x es/*" "google-research-datasets/go_emotions raw/*"; do
  set -- $d
  "$HOME/venv/bin/python" -c "import sys; from huggingface_hub import snapshot_download as s; \
s(sys.argv[1], repo_type='dataset', allow_patterns=[sys.argv[2], '*.md', '*.yaml', '*.json'])" "$1" "$2" \
    || echo "aviso: no se pudo bajar $1"
done
# tasksource-jev-typed-decisions: solo la tarjeta, sources.yaml y un fragmento de 'default' (la conversión entera va en AWS).
"$HOME/venv/bin/python" - <<'PY' || echo "aviso: no se pudo bajar tasksource-jev-typed-decisions"
from huggingface_hub import HfApi, snapshot_download
r = "tasksource/tasksource-jev-typed-decisions"
fs = sorted(f for f in HfApi().list_repo_files(r, repo_type="dataset") if f.endswith(".parquet") and "default" in f)
snapshot_download(r, repo_type="dataset", allow_patterns=["*.md", "*.yaml", "*.json"] + fs[:1])
print("tasksource-jev: fragmento", fs[:1], "de", len(fs))
PY

# PQRS reales de datos.gov.co (CC BY-SA 4.0). Traen datos personales: nunca a git ni a informes.
mkdir -p "$HOME/datos/datosgov"
for id in gb9w-jt96 m3mt-c275 e86p-frfd xtj2-ipwy; do
  curl -fsSL --max-time 300 -o "$HOME/datos/datosgov/$id.csv" "https://www.datos.gov.co/api/views/$id/rows.csv?accessType=DOWNLOAD" \
    && curl -fsSL --max-time 60 -o "$HOME/datos/datosgov/$id.meta.json" "https://www.datos.gov.co/api/views/$id.json" \
    || echo "aviso: no se pudo bajar datos.gov.co $id"
done

cat >> "$HOME/.profile" <<'X'
export PATH="$HOME/go-sdk/bin:$HOME/venv/bin:$PATH"
export HF_HOME="$HOME/hf"
export GOTOOLCHAIN=local
X
cat >> "$HOME/.claude/CLAUDE.md" <<'X'

## Chispa en kindling
Python: `~/venv` (torch CPU ya instalado). Go: `~/go-sdk/bin`. Modelos en `HF_HOME=~/hf`.
Antes de cualquier comando: `source ~/.profile`. No hay red salvo la API de Claude: usa solo los modelos de ~/hf.
X
du -sh "$HOME/venv" "$HOME/hf" "$HOME/go-sdk" 2>/dev/null
