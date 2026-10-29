#!/usr/bin/env bash
# Mide L3 contra un LLM OpenAI-compatible ya existente. No instala ni descarga nada. Ver README.md.
#   CHISPA_L3_URL      base del endpoint, sin /chat/completions (p. ej. http://127.0.0.1:11434/v1)   [obligatoria]
#   CHISPA_L3_MODELO   nombre del modelo en ese endpoint (p. ej. qwen3:4b-instruct)                  [obligatoria]
#   CHISPA_L3_API_KEY  clave del endpoint (opcional; solo se pasa por entorno, nunca a disco)
#   CHISPA_JEVBENCH    clon de JevBench, su datasets/public o un .jsonl (opcional; sin él, solo casos-respaldo.jsonl)
#   CHISPA_L3_N        casos a mandar (50); CHISPA_L3_SEMILLA (0); CHISPA_L3_TIMEOUT por llamada (60s)
#   CHISPA_L3_SALIDA   JSONL con el detalle por caso (opcional); CHISPA_L3_SERVER: chispa-server ya compilado (opcional)
set -euo pipefail
aqui="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
: "${CHISPA_L3_URL:?falta CHISPA_L3_URL}" "${CHISPA_L3_MODELO:?falta CHISPA_L3_MODELO}"
n="${CHISPA_L3_N:-50}"
tmp="$(mktemp -d)"; pid=""
trap '[ -n "$pid" ] && kill "$pid" 2>/dev/null; rm -rf "$tmp"' EXIT

bin="${CHISPA_L3_SERVER:-}"
if [ -z "$bin" ]; then
  [ -f "$aqui/../go.mod" ] || { echo "no encuentro server/go.mod; define CHISPA_L3_SERVER" >&2; exit 2; }
  bin="$tmp/chispa-server"
  (cd "$aqui/.." && go build -o "$bin" ./cmd/chispa-server)
fi

# τ=0 en todas las capas de arriba no hace falta: la pregunta debe escalar sola a L3 (los .chispa de testdata no conocen
# estos esquemas) y el τ de L3 va a 0 para que "válida" no se confunda con "poco segura".
api_env=""; [ -n "${CHISPA_L3_API_KEY:-}" ] && api_env='"api_key_env":"CHISPA_L3_API_KEY",'
modelos="[$(printf '"%s",' "$aqui"/../testdata/{intencion,injection,urgencia}.chispa | sed 's/,$//')]"
cat >"$tmp/config.json" <<JSON
{"modelos":$modelos,
 "capas":[{"nombre":"L0","tau":0.8},{"nombre":"L1","tau":0.8},{"nombre":"L2","tau":0.7},{"nombre":"L3","tau":0}],
 "l3":{"url":"$CHISPA_L3_URL","modelo":"$CHISPA_L3_MODELO",$api_env"timeout":"${CHISPA_L3_TIMEOUT:-60s}","max_por_peticion":1,"tau":0}}
JSON

puerto="$(python3 -I -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1])')"
"$bin" -addr "127.0.0.1:$puerto" -config "$tmp/config.json" -timeout 0 >"$tmp/server.log" 2>&1 & pid=$!
for _ in $(seq 50); do curl -fs "http://127.0.0.1:$puerto/healthz" >/dev/null 2>&1 && break; kill -0 "$pid" 2>/dev/null || { cat "$tmp/server.log" >&2; exit 1; }; sleep 0.2; done
curl -fs "http://127.0.0.1:$puerto/healthz" >/dev/null || { cat "$tmp/server.log" >&2; echo "chispa-server no arrancó" >&2; exit 1; }

args=(--base "http://127.0.0.1:$puerto" --respaldo "$aqui/casos-respaldo.jsonl" -n "$n" --semilla "${CHISPA_L3_SEMILLA:-0}")
[ -n "${CHISPA_JEVBENCH:-}" ] && args+=(--jevbench "$CHISPA_JEVBENCH")
[ -n "${CHISPA_L3_SALIDA:-}" ] && args+=(--salida "$CHISPA_L3_SALIDA")
echo "L3: $CHISPA_L3_URL modelo=$CHISPA_L3_MODELO"
python3 -I "$aqui/medir.py" "${args[@]}"
