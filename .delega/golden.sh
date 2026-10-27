#!/usr/bin/env bash
# Lo corre extra.sh del perfil personal al hornear el dorado de kindling (con internet), en ~/<repo>.
# Deja Go, un venv de Python con torch CPU y los codificadores de la fase 0 ya descargados.
set -uo pipefail

GO=1.27.1
curl -fsSL "https://go.dev/dl/go${GO}.linux-amd64.tar.gz" | tar -C "$HOME" -xz && mv "$HOME/go" "$HOME/go-sdk" \
  || echo "aviso: no se pudo instalar Go ${GO}"

python3 -m venv "$HOME/venv"
# Una sola llamada: si torch se instala aparte, las dependencias lo reemplazan por el de CUDA (6 GB).
"$HOME/venv/bin/pip" install -q --no-cache-dir --index-url https://download.pytorch.org/whl/cpu \
  --extra-index-url https://pypi.org/simple torch transformers sentence-transformers onnx onnxruntime \
  "optimum[onnxruntime]" datasets scikit-learn pandas huggingface_hub model2vec
"$HOME/venv/bin/python" -c "import torch; assert not torch.version.cuda, torch.version.cuda; print('torch', torch.__version__)"

export HF_HOME="$HOME/hf"
for m in intfloat/multilingual-e5-small jhu-clsp/mmBERT-small minishlab/potion-multilingual-128M \
         knowledgator/gliclass-modern-base-v3.0 SupersonicLabs/Julia-1 doofz/THX-01 \
         convaiinnovations/laya-multilingual; do
  "$HOME/venv/bin/python" -c "import sys; from huggingface_hub import snapshot_download as s; \
s(sys.argv[1], allow_patterns=['*.json','*.safetensors','*.txt','*.model','*.py','tokenizer*'])" "$m" \
    || echo "aviso: no se pudo bajar $m"
done

# Datos públicos de la fase 0 (sondeo en español), también sin red en las VM.
for d in mteb/amazon_massive_intent Paul/hatecheck-spanish; do
  "$HOME/venv/bin/python" -c "import sys; from huggingface_hub import snapshot_download as s; \
s(sys.argv[1], repo_type='dataset', allow_patterns=['*es*','*.json','*.md','*.csv'])" "$d" \
    || echo "aviso: no se pudo bajar $d"
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
