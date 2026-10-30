#!/usr/bin/env bash
# Uso: scripts/smoke-repetido.sh [N] [busy]
# Corre el smoke N veces (receta de `make smoke`). Con «busy» ocupa antes el
# puerto 8089 y el 9300 a propósito y comprueba que el smoke pasa igual.
# Al salir mata lo que arrancó y comprueba que no quedan procesos `arena`.
set -u
cd "$(dirname "$0")/.."
N=${1:-20}
BUSY=${2:-}
pids=()
cleanup() { for p in "${pids[@]}"; do kill "$p" 2>/dev/null; done; }
trap cleanup EXIT INT TERM
if [ "$BUSY" = busy ]; then
  for port in 8089 9300; do
    python3 -c "
import socket,time,sys
s=socket.socket(); s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
s.bind(('127.0.0.1',$port)); s.listen(); time.sleep(3600)" &
    pids+=($!)
  done
  sleep 1
fi
ok=0
for i in $(seq 1 "$N"); do
  if out=$("$PWD/arena" run -smoke -max-attacks 50 -addr 127.0.0.1:0 2>&1) && grep -q "smoke OK" <<<"$out"; then
    ok=$((ok+1)); echo "run $i: OK"
  else
    echo "run $i: FALLO"; echo "$out" | tail -15
  fi
done
left=$(pgrep -f "$PWD/arena (detector|run)" | wc -l)
echo "resultado: $ok/$N OK, procesos arena que quedan: $left"
[ "$ok" = "$N" ] && [ "$left" = 0 ]
