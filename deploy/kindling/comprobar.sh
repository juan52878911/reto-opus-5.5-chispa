#!/bin/sh
# Valida chispa-server como lo arrancaría la imagen (entrada.sh + sondeo), sin contenedor ni kindling.
#   deploy/kindling/comprobar.sh [modelo.chispa]   (por defecto server/testdata/intencion.chispa)
set -eu
RAIZ=$(cd "$(dirname "$0")/../.." && pwd)
MODELO=${1:-$RAIZ/server/testdata/intencion.chispa}
PUERTO=${CHISPA_PUERTO:-$((20000 + $$ % 20000))}
T=$(mktemp -d)
trap 'kill "${PID:-}" 2>/dev/null || true; rm -rf "$T"' EXIT
fallo() { echo "FALLO: $*" >&2; [ -f "$T/log" ] && sed 's/^/  log: /' "$T/log" >&2; exit 1; }

(cd "$RAIZ/server" && go build -o "$T/chispa-server" ./cmd/chispa-server) || fallo "no compila chispa-server"
(cd "$RAIZ/deploy/kindling/sondeo" && go build -o "$T/sondeo" .) || fallo "no compila sondeo"
# Mismo punto de entrada que la imagen; la ruta del binario se redirige al compilado aquí.
sed "s#/usr/local/bin/chispa-server#$T/chispa-server#" "$RAIZ/deploy/kindling/entrada.sh" >"$T/entrada.sh"
CHISPA_PUERTO=$PUERTO CHISPA_MODELO=$MODELO CHISPA_TOK=$T/no-hay sh "$T/entrada.sh" >"$T/log" 2>&1 &
PID=$!

ok=0
for _ in $(seq 1 50); do
  kill -0 "$PID" 2>/dev/null || fallo "chispa-server murió al arrancar"
  if CHISPA_PUERTO=$PUERTO "$T/sondeo" 2>/dev/null; then ok=1; break; fi
  sleep 0.2
done
[ "$ok" = 1 ] || fallo "el healthcheck no pasó en 10 s"
echo "healthcheck OK (puerto $PUERTO)"

# Sondeo negativo: un puerto sin servidor debe fallar (el healthcheck no puede pasar siempre).
if CHISPA_PUERTO=$((PUERTO + 1)) "$T/sondeo" 2>/dev/null; then fallo "el sondeo da OK sin servidor"; fi
echo "sondeo falla sin servidor: OK"

# Decisión zero-shot: esquema y opciones que el modelo no ha visto.
cat >"$T/req.json" <<'J'
{"state":"Necesito cambiar la dirección de entrega de mi pedido, por favor",
 "questions":[{"id":"q1","question":"¿Qué quiere el cliente?","kind":"choice",
  "options":[{"id":"cambio_direccion","description":"Cambiar la dirección de entrega"},
             {"id":"cancelar","description":"Cancelar el pedido"},
             {"id":"queja","description":"Presentar una queja"}]}]}
J
CODE=$(curl -s -o "$T/resp.json" -w '%{http_code}' -X POST -H 'Content-Type: application/json' \
  --data @"$T/req.json" "http://127.0.0.1:$PUERTO/v1/decide")
cat "$T/resp.json"; echo
[ "$CODE" = 200 ] || fallo "/v1/decide respondió HTTP $CODE"
python3 -I - "$T/resp.json" <<'P' || fallo "respuesta no válida"
import json, sys
r = json.load(open(sys.argv[1]))["results"]
assert len(r) == 1 and r[0]["id"] == "q1" and r[0]["kind"] == "choice", r
assert r[0]["layer"], r
assert r[0]["escalate"] or r[0]["answer"] in {"cambio_direccion", "cancelar", "queja"}, r
print("decisión válida: capa", r[0]["layer"], "escalate", r[0]["escalate"], "answer", r[0].get("answer"))
P
curl -sf "http://127.0.0.1:$PUERTO/metrics" | grep -q . || fallo "/metrics vacío"
echo "comprobar.sh: TODO OK"
