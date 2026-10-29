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

# Contexto mínimo con lo que copian los Dockerfiles (sus líneas COPY): si falta un módulo del `replace` de
# server/go.mod en un COPY, aquí no compila, como en `docker build`.
mkdir "$T/ctx"
for df in "$RAIZ/deploy/kindling/Dockerfile" "$RAIZ/server/deploy/Dockerfile"; do
  for src in $(awk '$1=="COPY" && $2 !~ /^--/ && $2 != "gomod-proxy" && $2 !~ /entrada\.sh$/ {print $2}' "$df"); do
    [ -d "$RAIZ/$src" ] || fallo "$df copia $src, que no existe"
    mkdir -p "$T/ctx/$src" && cp -R "$RAIZ/$src/." "$T/ctx/$src/"
  done
done
(cd "$T/ctx/server" && GOFLAGS=-mod=readonly go build -o "$T/chispa-server" ./cmd/chispa-server) \
  || fallo "no compila chispa-server con el contexto de los Dockerfiles (¿falta un COPY?)"
(cd "$T/ctx/deploy/kindling/sondeo" && go build -o "$T/sondeo" .) || fallo "no compila sondeo"
# Mismo punto de entrada que la imagen; la ruta del binario se redirige al compilado aquí.
sed "s#/usr/local/bin/chispa-server#$T/chispa-server#" "$RAIZ/deploy/kindling/entrada.sh" >"$T/entrada.sh"

# entrada.sh sin CHISPA_CONFIG ni -abierto debe negarse a arrancar (hallazgo 9).
if CHISPA_PUERTO=$PUERTO CHISPA_MODELO=$MODELO CHISPA_TOK=$T/no-hay sh "$T/entrada.sh" >"$T/log-sin" 2>&1; then
  fallo "entrada.sh arrancó sin CHISPA_CONFIG ni -abierto"
fi
grep -q CHISPA_CONFIG "$T/log-sin" || fallo "entrada.sh no explica que falta CHISPA_CONFIG"
echo "entrada.sh se niega sin config: OK"

# Config con api_keys en una ruta con espacio y comodín (hallazgo 15); la clave va como Bearer.
CLAVE=clave-de-prueba
HASH=$(printf %s "$CLAVE" | sha256sum | cut -d' ' -f1)
mkdir "$T/dir con espacio *"
CFG="$T/dir con espacio */config piloto.json"
printf '{"api_keys":[{"id":"prueba","hash_sha256":"%s"}]}\n' "$HASH" >"$CFG"
CHISPA_PUERTO=$PUERTO CHISPA_MODELO=$MODELO CHISPA_TOK=$T/no-hay CHISPA_CONFIG=$CFG sh "$T/entrada.sh" >"$T/log" 2>&1 &
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
CODE=$(curl -s -o "$T/resp.json" -H "Authorization: Bearer $CLAVE" -w '%{http_code}' -X POST -H 'Content-Type: application/json' \
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
# Sin clave, /v1/decide debe responder 401.
CODE=$(curl -s -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' --data @"$T/req.json" "http://127.0.0.1:$PUERTO/v1/decide")
[ "$CODE" = 401 ] || fallo "/v1/decide sin clave respondió HTTP $CODE, esperaba 401"
curl -sf "http://127.0.0.1:$PUERTO/metrics" | grep -q . || fallo "/metrics vacío"
echo "comprobar.sh: TODO OK"
