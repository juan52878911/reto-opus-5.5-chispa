#!/usr/bin/env bash
# Empaqueta chispa-server (linux/amd64, -tags ort) + libonnxruntime.so + el entrenador de Go precompilado (linux/amd64)
# + el SDK de Python (sdk/python/chispa) + demos/caida en un tar.gz FUERA del repo.
# Uso: demos/caida/empaquetar.sh [directorio-de-salida]   (por defecto, el directorio padre del worktree)
# Necesita Go (~/orquestador/herr/env.sh) y CHISPA_ORT_LIB apuntando a la libonnxruntime.so. Con -tags ort hay cgo:
# define CC (p. ej. export CC=~/orquestador/herr/zigcc CGO_ENABLED=1) si el compilador por defecto no sirve.
set -euo pipefail
AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RAIZ="$(cd "$AQUI/../.." && pwd)"
SALIDA="${1:-$(dirname "$RAIZ")}"
[ -n "${CHISPA_ORT_LIB:-}" ] && [ -f "$CHISPA_ORT_LIB" ] || { echo "CHISPA_ORT_LIB no apunta a un fichero (la libonnxruntime.so)" >&2; exit 1; }
case "$SALIDA/" in "$RAIZ"/*) echo "el tar debe quedar FUERA del repo: $SALIDA" >&2; exit 1;; esac
command -v go >/dev/null || { echo "no hay go en el PATH (. ~/orquestador/herr/env.sh)" >&2; exit 1; }
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
P="$TMP/chispa-caida"
mkdir -p "$P/bin" "$P/lib" "$P/sdk/python"
( cd "$RAIZ/server" && GOOS=linux GOARCH=amd64 CGO_ENABLED=1 go build -tags ort -o "$P/bin/chispa-server" ./cmd/chispa-server )
# entrenador de `chispa train` sin Go en el destino: se usa con CHISPA_ENTRENADOR=bin/chispa-entrenador
( cd "$RAIZ/sdk/python/chispa/entrenador_go" && GOOS=linux GOARCH=amd64 CGO_ENABLED=0 GOFLAGS=-mod=mod GOPROXY="${GOPROXY:-off}" go build -o "$P/bin/chispa-entrenador" . )
tar -C "$RAIZ/sdk/python" --exclude='__pycache__' --exclude='vendor' --exclude='*_test.go' -cf - chispa | tar -C "$P/sdk/python" -xf -
cp -L "$CHISPA_ORT_LIB" "$P/lib/$(basename "$CHISPA_ORT_LIB")"
tar -C "$AQUI" --exclude='__pycache__' --exclude='.pytest_cache' -cf - . | { mkdir -p "$P/demos/caida" && tar -C "$P/demos/caida" -xf -; }
cat > "$P/LEEME.txt" <<TXT
bin/chispa-server   servidor (linux/amd64, -tags ort); lib/$(basename "$CHISPA_ORT_LIB")   ONNX Runtime
bin/chispa-entrenador   entrenador de Go de «chispa train» (linux/amd64, estático); sdk/python/chispa   SDK de Python
Arranque: bin/chispa-server -modelo X.chispa -tok e5.chispa-tok -ort-lib=lib/$(basename "$CHISPA_ORT_LIB") -addr 127.0.0.1:8090
Prueba:   demos/caida/correr.sh --url http://127.0.0.1:8090 --salida salida/ [--decidir argmax|tau]
Entrenar sin Go: export CHISPA_ENTRENADOR="\$PWD/bin/chispa-entrenador"; PYTHONPATH=sdk/python python3 -m chispa train --help
TXT
OUT="$SALIDA/chispa-caida-linux-amd64.tar.gz"
tar -C "$TMP" -czf "$OUT" chispa-caida
echo "$OUT"; ls -l "$OUT"; sha256sum "$OUT"
