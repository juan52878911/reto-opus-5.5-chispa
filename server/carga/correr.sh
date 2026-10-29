#!/usr/bin/env bash
# Mide decisiones/s y p50/p99 de chispa-server con L1 (modo l1) y con L2 forzado (modo l2).
# Uso: carga/correr.sh [-m "l1 l2"] [-c "1 4 16 64"] [-d 30s] [-n 3] [-t textos] [-M modelo.chispa] [-T tok] [-o dir] [-p puerto] [-O]
#   -O  compila con -tags ort (hace falta libonnxruntime; ver README); sin -O, L2 va en stub y se dice.
#   -M  modelo .chispa v3 (L0/L1/L2 desde sus secciones); sin él, solo los .chispa de testdata (L1 y L2 en stub).
set -euo pipefail
SRV="$(cd "$(dirname "$0")/.." && pwd)"
[ -f "${HOME}/orquestador/herr/env.sh" ] && . "${HOME}/orquestador/herr/env.sh"
export GOFLAGS=-mod=mod GOPROXY=off

MODOS="l1 l2"; CONCS="1 4 16 64"; DUR=30s; TANDAS=3; TEXTOS="$SRV/carga/textos.txt"
MODELO=""; TOK=""; OUT="$SRV/carga/resultados"; PUERTO=18090; ORT=0
while getopts "m:c:d:n:t:M:T:o:p:O" o; do case $o in
  m) MODOS=$OPTARG;; c) CONCS=$OPTARG;; d) DUR=$OPTARG;; n) TANDAS=$OPTARG;; t) TEXTOS=$OPTARG;;
  M) MODELO=$OPTARG;; T) TOK=$OPTARG;; o) OUT=$OPTARG;; p) PUERTO=$OPTARG;; O) ORT=1;;
  *) sed -n 2,6p "$0"; exit 2;; esac; done
for c in $CONCS; do [ "$c" -le 64 ] || { echo "máximo 64 conexiones (nodo compartido)"; exit 2; }; done
[ "$PUERTO" != 8090 ] || { echo "usa un puerto propio, no 8090"; exit 2; }
[ -f "$TEXTOS" ] || { echo "no existe $TEXTOS"; exit 2; }
SEG=${DUR%s}

TMP=$(mktemp -d); SPID=""; LPID=""
parar() { [ -n "$LPID" ] && kill "$LPID" 2>/dev/null || true; [ -n "$SPID" ] && kill "$SPID" 2>/dev/null && wait "$SPID" 2>/dev/null || true; rm -rf "$TMP"; }
trap parar EXIT

TAGS=(); ORTVER="no (stub)"
if [ "$ORT" = 1 ]; then
  TAGS=(-tags ort)
  LIB=$(ldconfig -p 2>/dev/null | awk '/libonnxruntime\.so /{print $NF; exit}' || true)
  ORTVER="ort; lib=${LIB:-¿?}; $(cd "$SRV" && go list -m -f '{{.Path}} {{.Version}}' github.com/yalue/onnxruntime_go 2>/dev/null || echo 'onnxruntime_go ?')"
fi
(cd "$SRV" && go build "${TAGS[@]}" -o "$TMP/chispa-server" ./cmd/chispa-server && go build -o "$TMP/carga" ./cmd/carga)

HOST=$(hostname -s); FECHA=$(date +%Y%m%d-%H%M%S)
MD="$OUT/resultados-$HOST-$FECHA.md"; CSV="${MD%.md}.csv"; mkdir -p "$OUT"
CPU=$(awk -F: '/model name/{gsub(/^ +/,"",$2); print $2; exit}' /proc/cpuinfo)
NUC=$(nproc); GMP=${GOMAXPROCS:-"(sin fijar = $NUC)"}
LOAD0=$(cut -d' ' -f1-3 /proc/loadavg)
echo "modo,concurrencia,tanda,decisiones_s,peticiones_s,p50_ms,p99_ms,peticiones,errores,capas" > "$CSV"

# config del modo: l1 = cascada normal; l2 = L0 y L1 con τ=1 (no aceptan) y L2 con τ=0 (acepta siempre que opine)
cfg() {
  local mods='["testdata/intencion.chispa","testdata/injection.chispa","testdata/urgencia.chispa"]'
  [ -n "$MODELO" ] && mods='[]'
  if [ "$1" = l1 ]; then
    echo "{\"capas\":[{\"nombre\":\"L0\",\"tau\":0.8},{\"nombre\":\"L1\",\"tau\":0.8},{\"nombre\":\"L2\",\"tau\":1},{\"nombre\":\"L3\",\"tau\":0.6}],\"modelos\":$mods}"
  else
    echo "{\"capas\":[{\"nombre\":\"L0\",\"tau\":1},{\"nombre\":\"L1\",\"tau\":1},{\"nombre\":\"L2\",\"tau\":0},{\"nombre\":\"L3\",\"tau\":0.6}],\"modelos\":[]}"
  fi
}

L2STUB=0; { [ "$ORT" = 0 ] || [ -z "$TOK" ] || [ -z "$MODELO" ]; } && L2STUB=1
for modo in $MODOS; do
  cfg "$modo" > "$TMP/cfg-$modo.json"
  args=(-addr "127.0.0.1:$PUERTO" -config "$TMP/cfg-$modo.json")
  [ -n "$MODELO" ] && args+=(-modelo "$MODELO"); [ -n "$TOK" ] && args+=(-tok "$TOK")
  (cd "$SRV" && exec "$TMP/chispa-server" "${args[@]}") > "$TMP/srv-$modo.log" 2>&1 & SPID=$!
  for i in $(seq 50); do curl -s -o /dev/null "http://127.0.0.1:$PUERTO/healthz" -m1 && break; kill -0 $SPID 2>/dev/null || { cat "$TMP/srv-$modo.log"; exit 1; }; sleep 0.2; done
  "$TMP/carga" -url "http://127.0.0.1:$PUERTO/v1/decide" -c 4 -d 2s -textos "$TEXTOS" >/dev/null 2>&1 || true   # calentamiento
  for c in $CONCS; do for t in $(seq "$TANDAS"); do
    ( while :; do echo "$(cut -d' ' -f1 /proc/loadavg)" >> "$TMP/load-$modo-$c-$t"; sleep 2; done ) & LPID=$!
    salida=$("$TMP/carga" -url "http://127.0.0.1:$PUERTO/v1/decide" -c "$c" -d "$DUR" -textos "$TEXTOS" -csv -capas 2>&1 || true)
    kill $LPID 2>/dev/null; wait $LPID 2>/dev/null || true; LPID=""
    linea=$(echo "$salida" | grep -E '^[0-9.]+,[0-9.]+,[0-9.]+,[0-9.]+,[0-9]+,[0-9]+$' || echo "0,0,0,0,0,?")
    capas=$(echo "$salida" | sed -n 's/^capas=//p')
    echo "$modo,$c,$t,$linea,\"${capas:--}\"" >> "$CSV"
    echo "$modo c=$c tanda=$t -> $linea ${capas:-}" >&2
  done; done
  grep -i "stub\|ort\|L2" "$TMP/srv-$modo.log" | head -3 > "$TMP/avisos-$modo" || true
  kill $SPID; wait $SPID 2>/dev/null || true; SPID=""
done
LOADMAX=$(cat "$TMP"/load-* 2>/dev/null | sort -n | tail -1)

{
echo "# Carga de chispa-server — $HOST — $FECHA"
echo
echo "## Entorno"
echo "- CPU: $CPU · núcleos lógicos: $NUC · GOMAXPROCS: $GMP"
echo "- loadavg antes (1/5/15 min): $LOAD0 · máximo de loadavg(1 min) durante: ${LOADMAX:--}"
echo "- Go: $(go version) · ORT: $ORTVER"
echo "- Parámetros: modos=[$MODOS] concurrencias=[$CONCS] duración=$DUR por punto · tandas=$TANDAS · textos=$(grep -cv '^#' "$TEXTOS") líneas ($TEXTOS)"
echo "- Modelo: ${MODELO:-ninguno (solo .chispa de testdata en L0)} · tok: ${TOK:-ninguno} · commit: $(git -C "$SRV" rev-parse --short HEAD 2>/dev/null)"
if [ "$L2STUB" = 1 ]; then echo "- **L2 en stub** (sin ORT/modelo/tok): el modo l2 mide la cascada con L2 sin opinión, que acaba en «escalar»; no es la cifra de L2 real."; fi
echo
echo "## Resultados (media de tandas; p50 = media, p99 = peor tanda)"
echo
echo "Objetivos: l1 ≥ 5000 dec/s con p99 < 20 ms · l2 ≥ 300 dec/s."
echo
echo "| modo | c | dec/s | p50 ms | p99 ms | errores | tandas | objetivo |"
echo "|---|---|---|---|---|---|---|---|"
awk -F, 'NR>1{k=$1","$2; n[k]++; d[k]+=$4; p5[k]+=$6; if($7>p9[k])p9[k]=$7; e[k]+=$9; if(!(k in ord)){ord[k]=++m; key[m]=k}}
 END{for(i=1;i<=m;i++){k=key[i]; split(k,a,","); dd=d[k]/n[k]; ok="-";
  if(a[1]=="l1") ok=(dd>=5000&&p9[k]<20)?"cumple":"NO cumple"; else if(a[1]=="l2") ok=(dd>=300)?"cumple":"NO cumple";
  printf "| %s | %s | %.0f | %.3f | %.3f | %d | %d | %s |\n",a[1],a[2],dd,p5[k]/n[k],p9[k],e[k],n[k],ok}}' "$CSV"
echo
echo "Capas que decidieron (última tanda de cada punto) y datos por tanda: ver \`$(basename "$CSV")\`."
for m in $MODOS; do echo; echo "Log del servidor ($m):"; echo '```'; cat "$TMP/avisos-$m" 2>/dev/null; echo '```'; done
} > "$MD"
echo "Escrito $MD y $CSV" >&2
