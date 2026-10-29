#!/bin/bash
# Prueba de carga de chispa-server: 3 tandas × modos × concurrencias 1/4/16/64 × 30 s, con la carga de server/cmd/carga
# (sin cambiar) y con cargamsg (mensajes reales de massive). Uso: medir.sh DIR_TRABAJO DIR_SALIDA [TANDAS] [SEGUNDOS]
#   DIR_TRABAJO: lo que dejó armar.sh (bin/, completo.chispa, e5.chispa-tok, mensajes.txt). DIR_SALIDA: crudo (logs).
set -u
D=${1:?}; OUT=${2:?}; TANDAS=${3:-3}; SEG=${4:-30}
AQUI=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$OUT"
source ~/.profile
PY=~/venv/bin/python
MODOS="l0l1 l1-forzado"
[ -f "$D/ORT" ] && MODOS="$MODOS l2-forzado"

carga_load() { # loadavg cada 5 s mientras corre el punto
  while true; do echo "$(date +%T) $(cut -d' ' -f1-3 /proc/loadavg)"; sleep 5; done
}
{ echo "inicio $(date -Is)"; grep -m1 'model name' /proc/cpuinfo; nproc; grep -E 'MemTotal|MemAvail' /proc/meminfo
  echo "loadavg antes: $(cat /proc/loadavg)"; } > "$OUT/entorno-medir.txt"

for T in $(seq 1 "$TANDAS"); do
  for M in $MODOS; do
    ARGS=(-addr 127.0.0.1:8090 -modelo "$D/completo.chispa" -tok "$D/e5.chispa-tok")
    [ "$M" != l0l1 ] && ARGS+=(-config "$AQUI/config-$M.json")
    "$D/bin/chispa-server" "${ARGS[@]}" > "$OUT/servidor-t$T-$M.log" 2>&1 &
    SP=$!
    for i in $(seq 1 60); do curl -sf http://127.0.0.1:8090/healthz >/dev/null && break; sleep 1; done
    [ "$T" = 1 ] && $PY "$AQUI/capas.py" http://127.0.0.1:8090/v1/decide "$D/mensajes.txt" 200 > "$OUT/capas-$M.json"
    for GEN in carga cargamsg; do
      for C in 1 4 16 64; do
        echo "loadavg antes: $(cat /proc/loadavg)" > "$OUT/t$T-$M-$GEN-c$C.txt"
        carga_load > "$OUT/t$T-$M-$GEN-c$C.load" & LP=$!
        if [ $GEN = carga ]; then "$D/bin/carga" -c $C -d ${SEG}s >> "$OUT/t$T-$M-$GEN-c$C.txt" 2>&1
        else "$D/bin/cargamsg" -c $C -d ${SEG}s -mensajes "$D/mensajes.txt" >> "$OUT/t$T-$M-$GEN-c$C.txt" 2>&1; fi
        kill $LP 2>/dev/null; wait $LP 2>/dev/null
        echo "rss_servidor_kb: $(grep VmRSS /proc/$SP/status | awk '{print $2}')" >> "$OUT/t$T-$M-$GEN-c$C.txt"
      done
    done
    kill $SP; wait $SP 2>/dev/null
  done
done
echo "fin $(date -Is)" >> "$OUT/entorno-medir.txt"
