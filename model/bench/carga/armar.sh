#!/bin/bash
# Arma, dentro de la VM, todo lo que necesita la prueba de carga en DIR (por defecto /tmp/carga):
#   ejemplos.csv/mensajes.txt/esquema.json (MASSIVE es de ~/hf), potion.chispa-l1, l01.chispa (L0+L1 con `chispa train`),
#   l2.chispa (e5 int8 + cabeza aleatoria de semilla 0), completo.chispa (L0+L1+L2), e5.chispa-tok, bin/{chispa-server,carga,cargamsg}.
# Si `go build -tags ort` compila, deja DIR/ORT y el servidor con ORT en bin/chispa-server-ort.
# Uso, desde la raíz del repo: bash model/bench/carga/armar.sh [DIR]
set -eu
D=${1:-/tmp/carga}
R=$(git rev-parse --show-toplevel)
AQUI=$R/model/bench/carga
source ~/.profile
export PYTHONPATH=$R:$R/sdk/python GOFLAGS=-mod=mod GOPROXY=off HF_HUB_OFFLINE=1
mkdir -p "$D/bin"
E5=$(ls -d ~/hf/hub/models--intfloat--multilingual-e5-small/snapshots/*)
POTION=$(ls -d ~/hf/hub/models--minishlab--potion-multilingual-128M/snapshots/*)

python "$AQUI/preparar.py" "$D"
python "$R/runtime/l1/exportar.py" "$POTION" "$D/potion.chispa-l1"
python -m chispa train --ejemplos "$D/ejemplos.csv" --esquema "$D/esquema.json" --salida "$D/l01.chispa" --l1 "$D/potion.chispa-l1"
python "$AQUI/crear_l2.py" "$D"                       # → l2.chispa (cabeza aleatoria, semilla 0)
python -m chispa train --ejemplos "$D/ejemplos.csv" --esquema "$D/esquema.json" --salida "$D/completo.chispa" \
  --l1 "$D/potion.chispa-l1" --l2 "$D/l2.chispa"
python "$R/runtime/tok/exportar.py" "$E5" "$D/e5.chispa-tok"

(cd "$R/server" && go build -o "$D/bin/chispa-server" ./cmd/chispa-server && go build -o "$D/bin/carga" ./cmd/carga)
(cd "$AQUI/cargamsg" && go build -o "$D/bin/cargamsg" main.go)
rm -f "$D/ORT"
if (cd "$R/server" && go build -tags ort -o "$D/bin/chispa-server-ort" ./cmd/chispa-server 2> "$D/ort-build.log"); then
  touch "$D/ORT"; cp "$D/bin/chispa-server-ort" "$D/bin/chispa-server"; echo "ORT: compilado"
else
  echo "ORT: no compila (L2 queda en stub): $(head -2 "$D/ort-build.log")"
fi
