#!/usr/bin/env bash
# Regresión de correr.sh (hallazgos 10 y 11). Uso: bash carga/prueba.sh
set -u
D="$(cd "$(dirname "$0")" && pwd)"; fallos=0
ck() { [ "$2" = "$3" ] || { echo "FALLA $1: esperado «$2», obtenido «$3»"; fallos=1; }; }
# 11: tanda fallida no cuenta como 0 errores ni entra en la media
csv=$(printf 'h\nl1,1,1,100,1,1,1,1,0,"-"\nl1,1,2,0,0,0,0,0,-1,"-"\nl2,4,1,0,0,0,0,0,-1,"-"\n')
t=$(echo "$csv" | awk -F, -v stub=0 -f "$D/tabla.awk")
ck media "$(echo "$t" | sed -n 1p | cut -d'|' -f4)" " 100 "
echo "$t" | sed -n 1p | grep -q "FALLÓ 1 tanda" || { echo "FALLA: fila l1 sin FALLÓ"; fallos=1; }
echo "$t" | sed -n 2p | grep -q "| FALLÓ |" || { echo "FALLA: fila l2 sin FALLÓ"; fallos=1; }
# 10: puerto ocupado
P=18391; python3 -m http.server "$P" --bind 127.0.0.1 >/dev/null 2>&1 & SP=$!
trap 'kill $SP 2>/dev/null' EXIT
for i in $(seq 25); do curl -s -o /dev/null -m1 "http://127.0.0.1:$P/healthz" && break; sleep 0.2; done
out=$(bash "$D/correr.sh" -p "$P" -m l1 -c 1 -d 1s -n 1 -o "$(mktemp -d)" 2>&1); rc=$?
ck "rc puerto ocupado" 1 "$rc"
echo "$out" | grep -q "ocupado" || { echo "FALLA: sin mensaje de puerto ocupado"; fallos=1; }
[ $fallos = 0 ] && echo OK; exit $fallos
