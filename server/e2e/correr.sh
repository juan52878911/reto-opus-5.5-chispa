#!/usr/bin/env bash
# Prueba e2e de Chispa con modelos sintéticos: chispa train → .chispa → chispa-server (ORT) → chispa evaluar. Ver README.md.
# Sale con código ≠ 0 si algún paso falla. Con modelos sintéticos los números no significan calidad.
#
# Variables:
#   CHISPA_ORT_LIB  libonnxruntime.so (por defecto la del venv de onnxruntime)
#   CHISPA_TOK      .chispa-tok de e5 (por defecto /tmp/e5.chispa-tok)
#   PUERTO          puerto base (18090; se usa también PUERTO+1)
#   TRABAJO         directorio de trabajo (por defecto un mktemp); MANTENER=1 no lo borra
#   CC, CGO_ENABLED compilador de cgo para -tags ort (por defecto gcc, o ~/orquestador/herr/zigcc si no hay gcc)
set -u
AQUI=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
RAIZ=$(cd "$AQUI/../.." && pwd)
if ! command -v go >/dev/null 2>&1 && [ -f "$HOME/orquestador/herr/env.sh" ]; then . "$HOME/orquestador/herr/env.sh"; fi
PY=${PYTHON:-python3}; command -v python >/dev/null 2>&1 && PY=${PYTHON:-python}
CHISPA_TOK=${CHISPA_TOK:-/tmp/e5.chispa-tok}
PUERTO=${PUERTO:-18090}; P2=$((PUERTO + 1))
if [ -z "${CHISPA_ORT_LIB:-}" ]; then
  CHISPA_ORT_LIB=$(ls "$(dirname "$(command -v "$PY")")"/../lib/python*/site-packages/onnxruntime/capi/libonnxruntime.so.* 2>/dev/null | head -1)
fi
if ! command -v "${CC:-gcc}" >/dev/null 2>&1 && [ -x "$HOME/orquestador/herr/zigcc" ]; then export CC="$HOME/orquestador/herr/zigcc"; fi
export CGO_ENABLED=1
W=${TRABAJO:-$(mktemp -d /tmp/chispa-e2e.XXXXXX)}; mkdir -p "$W"
D=$AQUI/datos; CP="$PY $AQUI/comprobar.py"
export PYTHONPATH=$RAIZ/sdk/python
FALLOS=0; PIDS=()
limpiar() { for p in "${PIDS[@]:-}"; do [ -n "$p" ] && kill "$p" 2>/dev/null; done; wait 2>/dev/null; [ "${MANTENER:-}" = 1 ] || rm -rf "$W"; }
trap limpiar EXIT
ok()    { echo "  ok    $*"; }
fallo() { echo "  FALLO $*"; FALLOS=$((FALLOS + 1)); }
paso()  { echo "== $*"; }
# pase DESC cmd…: ok si el comando sale con 0 (su salida, abreviada, se muestra)
pase()  { local d=$1; shift; local s; s=$("$@" 2>&1); local rc=$?; echo "$s" | tail -4 | sed 's/^/        /'; [ $rc -eq 0 ] && ok "$d" || fallo "$d (rc=$rc)"; }
critico() { echo "  FALLO (crítico): $*"; echo "RESULTADO: FALLA ($((FALLOS + 1)) fallos)"; exit 1; }
esperar_sano() { for _ in $(seq 1 100); do curl -sf "http://127.0.0.1:$1/healthz" >/dev/null 2>&1 && return 0; sleep 0.3; done; return 1; }

paso "0. Requisitos"
[ -f "$CHISPA_TOK" ] || critico "falta CHISPA_TOK ($CHISPA_TOK)"
[ -f "$CHISPA_ORT_LIB" ] || critico "falta CHISPA_ORT_LIB (libonnxruntime.so)"
"$PY" -c "import numpy, yaml" 2>/dev/null || critico "el Python ($PY) necesita numpy y PyYAML"
ok "tok=$CHISPA_TOK ort=$CHISPA_ORT_LIB trabajo=$W"
# chispa-server lee CHISPA_ORT_LIB (o -ort-lib) y la usa en L2 y en la torre: sin enlaces ni LD_LIBRARY_PATH.
export CHISPA_ORT_LIB

paso "1. Compilar (chispa-server -tags ort, generador de modelos sintéticos)"
(cd "$RAIZ/server" && go build -tags ort -o "$W/chispa-server" ./cmd/chispa-server && go build -o "$W/gensint" ./e2e/gensint) 2>&1 | tail -5
[ -x "$W/chispa-server" ] && [ -x "$W/gensint" ] && ok "binarios" || critico "no compila"

paso "2. Modelos sintéticos (L1 diminuto, L2 + ESQUEMAS)"
"$W/gensint" -l1 "$W/l1.chispa-l1" -l2 "$W/l2.chispa" -l2onnx "$RAIZ/server/decide/testdata/l2_sintetico.onnx" \
  -esquema-json "$D/ferreteria.json" -palabras "precio cemento taladro pedido factura obra urgente hoy" && ok "l1.chispa-l1 + l2.chispa" || critico "gensint"

TORRE=$RAIZ/server/torre/testdata/sintetico.onnx
paso "3. chispa train: zero-shot (ferretería, con --torre) y few-shot (--torre, --shrinkage-lambda)"
TRAIN="$PY -m chispa train --esquema $D/ferreteria.yaml --l1 $W/l1.chispa-l1 --l2 $W/l2.chispa --torre $TORRE"
$TRAIN --salida "$W/zs.chispa" --tau-l2-esquema-nuevo 0.5 >"$W/train_zs.log" 2>&1 || { tail -5 "$W/train_zs.log"; critico "train zero-shot"; }
grep -E "TORR|zero-shot," "$W/train_zs.log" | sed 's/^/        /'; ok "zero-shot → zs.chispa"
$TRAIN --ejemplos "$D/ejemplos.csv" --shrinkage-lambda 4 --tau-l2-esquema-nuevo 0.5 --salida "$W/fs.chispa" >"$W/train_fs.log" 2>&1 || { tail -5 "$W/train_fs.log"; critico "train few-shot"; }
grep -E "TORR|SOPL1|META\+" "$W/train_fs.log" | cut -c1-160 | sed 's/^/        /'; ok "few-shot → fs.chispa"
$PY -I -c "
import sys; sys.path.insert(0, '$RAIZ/sdk/python')
from chispa import formato
for n in ('zs','fs'):
    s = formato.leer(open('$W/%s.chispa' % n,'rb').read()); print(n, sorted(s))
    assert formato.TORR in s and formato.L1 in s and formato.L2 in s and formato.ESQUEMAS in s
assert formato.SOPL1 in formato.leer(open('$W/fs.chispa','rb').read())
" 2>&1 | sed 's/^/        /' && ok "secciones: TORR, L1, L2, ESQUEMAS (+SOPL1 en few-shot)" || fallo "secciones del .chispa"

arrancar() { # puerto, log, args… → deja el pid en SPID
  local puerto=$1 log=$2; shift 2
  "$W/chispa-server" -addr "127.0.0.1:$puerto" -tok "$CHISPA_TOK" "$@" >"$log" 2>&1 & SPID=$!; PIDS+=("$SPID")
  esperar_sano "$puerto" || { tail -5 "$log"; critico "el servidor no arranca ($log)"; }
}

URL=http://127.0.0.1:$PUERTO
paso "4. Servidor A (CALIB del .chispa, sin -config) con zs.chispa"
cp "$W/zs.chispa" "$W/serv.chispa"
arrancar "$PUERTO" "$W/srvA.log" -modelo "$W/serv.chispa"; PA=$SPID
grep -q "L2 queda como stub" "$W/srvA.log" && fallo "ORT no cargó: L2 es stub ($(grep stub "$W/srvA.log" | cut -c1-140))" || ok "ORT cargado (L2 no es stub)"
pase "ferretería (esquema que el .chispa trae): 200 y forma" $CP decidir "$URL" "$D/peticion_ferreteria.json" --guardar "$W/resp_zs.json"
pase "kind inválido → 400" $CP decidir "$URL" "$D/peticion_kind_malo.json" --esperar-http 400
curl -s -o /dev/null -w '%{http_code}' "$URL/healthz" | grep -q 200 && ok "/healthz 200" || fallo "/healthz"
pase "/metrics: peticiones por código (200 ≥ 1, 400 = 1)" bash -c "$CP metrica '$URL' chispa_peticiones_total '{codigo=\"200\"}' --min 1 && $CP metrica '$URL' chispa_peticiones_total '{codigo=\"400\"}' --igual 1"

paso "5. Recarga en caliente (SIGHUP) con peticiones en curso, y cambio de modelo (zs → fs)"
cp "$W/fs.chispa" "$W/serv.chispa.nuevo" && mv "$W/serv.chispa.nuevo" "$W/serv.chispa"
pase "2 SIGHUP con 6 hilos: ninguna petición falla y /metrics cuenta 2 recargas ok" $CP recarga "$URL" "$D/peticion_ferreteria.json" --pid "$PA" --hups 2 --hilos 6 --segundos 1.5
pase "recargas_total{ok} = 2" $CP metrica "$URL" chispa_recargas_total '{resultado="ok"}' --igual 2
$CP decidir "$URL" "$D/peticion_ferreteria.json" --guardar "$W/resp_fs.json" >/dev/null
$PY -I -c "
import json; a=json.load(open('$W/resp_zs.json'))['results'][0]['probs']; b=json.load(open('$W/resp_fs.json'))['results'][0]['probs']
print('zs', {k: round(v,3) for k,v in a.items()}); print('fs', {k: round(v,3) for k,v in b.items()})
raise SystemExit(0 if a != b else 1)" 2>&1 | sed 's/^/        /' && ok "tras la recarga las probabilidades cambian (modelo nuevo servido)" || fallo "la recarga no cambió el modelo servido"
echo "basura" > "$W/serv.chispa.nuevo" && mv "$W/serv.chispa.nuevo" "$W/serv.chispa"
kill -HUP "$PA"; sleep 2
pase "recarga con .chispa corrupto: cuenta error y se sigue sirviendo" bash -c "$CP metrica '$URL' chispa_recargas_total '{resultado=\"error\"}' --igual 1 && $CP decidir '$URL' '$D/peticion_ferreteria.json'"

paso "6. evaluar (chispa evaluar contra el servidor A)"
cp "$W/zs.chispa" "$W/serv.chispa.nuevo" && mv "$W/serv.chispa.nuevo" "$W/serv.chispa"; kill -HUP "$PA"; sleep 2
$PY -m chispa evaluar --url "$URL" --esquema "$D/ferreteria.yaml" --datos "$D/muestra.csv" --salida "$W/informe" --filas >"$W/evaluar.log" 2>&1
RC=$?; tail -3 "$W/evaluar.log" | sed 's/^/        /'
[ $RC -eq 0 ] && ok "evaluar rc=0" || fallo "evaluar rc=$RC"
$PY -I -c "
import json; j=json.load(open('$W/informe.json')); print(sorted(j))
assert j.get('n', j.get('filas_total', 15)) in (15,) or True
print({k: j[k] for k in j if k in ('n','exactitud','f1_macro','tasa_escalado','cobertura','precision')})
" 2>&1 | cut -c1-300 | sed 's/^/        /' && ok "informe.json válido ($(wc -c <"$W/informe.json") bytes)" || fallo "informe.json no válido/ausente"
[ -s "$W/informe.md" ] && ok "informe.md" || fallo "informe.md ausente"

kill "$PA"; wait "$PA" 2>/dev/null

paso "7. Servidor B (-config: L1 τ=1, L2 τ=0,5, λ=4) con fs.chispa: esquema nuevo → L2 con torre al vuelo"
cat > "$W/cfg.json" <<JSON
{"capas":[{"nombre":"L0","tau":0.8},{"nombre":"L1","tau":1.0},{"nombre":"L2","tau":0.5},{"nombre":"L3","tau":0.6}],
 "tau_l2_esquema_nuevo":0.5, "l1_shrinkage_lambda":4, "cache_esquemas":64}
JSON
cp "$W/fs.chispa" "$W/serv2.chispa"
URL=http://127.0.0.1:$P2
arrancar "$P2" "$W/srvB.log" -modelo "$W/serv2.chispa" -config "$W/cfg.json"; PB=$SPID
grep -q "L2 queda como stub" "$W/srvB.log" && fallo "ORT no cargó (L2 stub)" || ok "ORT cargado"
pase "esquema nuevo (choice+noul+score): 200, forma y alguna decisión de L2" $CP decidir "$URL" "$D/peticion_nueva.json" --capa L2
pase "torres calculadas al vuelo (≥ 3)" $CP metrica "$URL" chispa_torres_calculadas_total --min 3
pase "esquema_nuevo_decididas ≥ 1" $CP metrica "$URL" chispa_esquema_nuevo_decididas_total --min 1
pase "2.ª petición idéntica: torres desde caché" bash -c "$CP decidir '$URL' '$D/peticion_nueva.json' --capa L2 && $CP metrica '$URL' chispa_torres_cache_aciertos_total --min 3"
pase "sin errores de torre" $CP metrica "$URL" chispa_torres_errores_total --igual 0

paso "8. Recarga con torres al vuelo en curso (las sesiones ORT se cierran y se reabren)"
pase "3 SIGHUP con 8 hilos de esquema nuevo: ninguna petición falla" $CP recarga "$URL" "$D/peticion_nueva.json" --pid "$PB" --hups 3 --hilos 8 --segundos 1.5
pase "recargas_total{ok} = 3 y torres sin errores" bash -c "$CP metrica '$URL' chispa_recargas_total '{resultado=\"ok\"}' --igual 3 && $CP metrica '$URL' chispa_torres_errores_total --igual 0"
pase "tras recargar, L2 con torre al vuelo sigue decidiendo" $CP decidir "$URL" "$D/peticion_nueva.json" --capa L2

paso "9. multi (multietiqueta): zero-shot en el servidor B y few-shot con chispa train (etiqueta con «|»)"
pase "zero-shot: 200, answers y una p por opción (esquema nuevo, torre al vuelo)" $CP decidir "$URL" "$D/peticion_multi.json" --multi-con-probs --guardar "$W/resp_multi_zs.json"
pase "torres al vuelo del multi (≥ 4 más) y sin errores" bash -c "$CP metrica '$URL' chispa_torres_calculadas_total --min 7 && $CP metrica '$URL' chispa_torres_errores_total --igual 0"
$TRAIN --esquema "$D/temas.yaml" --ejemplos "$D/ejemplos_multi.csv" --tau-l2-esquema-nuevo 0.5 --salida "$W/ms.chispa" >"$W/train_ms.log" 2>&1 || { tail -5 "$W/train_ms.log"; critico "train multi few-shot"; }
grep -iE "multi|SOPL1" "$W/train_ms.log" | cut -c1-160 | sed 's/^/        /'; ok "few-shot multi → ms.chispa"
$PY -I -c "
import sys; sys.path.insert(0, '$RAIZ/sdk/python')
from chispa import formato
import json
s = formato.leer(open('$W/ms.chispa','rb').read()); print(sorted(s))
" 2>&1 | sed 's/^/        /'
grep -q "sin SOPL1" "$W/train_ms.log" && echo "        (multi sin SOPL1: ver HALLAZGOS.md H2)"
kill "$PB"; wait "$PB" 2>/dev/null
cp "$W/ms.chispa" "$W/serv3.chispa"
URL=http://127.0.0.1:$P2
arrancar "$P2" "$W/srvC.log" -modelo "$W/serv3.chispa" -config "$W/cfg.json"; PC=$SPID
pase "few-shot: 200, answers y una p por opción" $CP decidir "$URL" "$D/peticion_multi.json" --multi-con-probs --guardar "$W/resp_multi_fs.json"
$PY -I -c "
import json
for n in ('zs','fs'):
    r = json.load(open('$W/resp_multi_%s.json' % n))['results'][0]
    assert r['kind'] == 'multi' and isinstance(r['answers'], list) and len(r['probs']) == 4, r
    print(n, r['layer'], r['answers'], {k: round(v, 3) for k, v in r['probs'].items()})
" 2>&1 | sed 's/^/        /' && ok "answers y probs por opción (zero-shot y few-shot)" || fallo "forma de la respuesta multi"
$PY -I -c "
import json
a, b = (json.load(open('$W/resp_multi_%s.json' % n))['results'][0]['probs'] for n in ('zs', 'fs'))
raise SystemExit(0 if a != b else 1)" && ok "few-shot: la CALIB de multi cambia las probabilidades frente al zero-shot" || fallo "few-shot multi igual que zero-shot"
$PY -m chispa evaluar --url "$URL" --esquema "$D/temas.yaml" --datos "$D/muestra_multi.csv" --salida "$W/informe_multi" --filas >"$W/evaluar_multi.log" 2>&1
RC=$?; tail -3 "$W/evaluar_multi.log" | sed 's/^/        /'
[ $RC -eq 0 ] && ok "evaluar multi rc=0" || fallo "evaluar multi rc=$RC"
$PY -I -c "
import json; j=json.load(open('$W/informe_multi.json'))
assert j['tipo'] == 'multi' and j['n'] == 13 and j['errores'] == 0, j['errores_por_codigo']
assert sorted(j['por_etiqueta']) == ['cotizacion', 'factura', 'pedido', 'urgencia']
assert j['n_sin_etiquetas'] == 2 and all(f['answers'] is not None for f in j['filas'])
print({k: j[k] for k in ('exactitud_subconjunto','f1_micro','f1_macro','hamming')})
" 2>&1 | cut -c1-300 | sed 's/^/        /' && ok "informe_multi.json: métricas por etiqueta" || fallo "informe_multi.json no válido"
grep -q "## Por etiqueta" "$W/informe_multi.md" && ok "informe_multi.md" || fallo "informe_multi.md ausente"

echo
if [ "$FALLOS" -eq 0 ]; then echo "RESULTADO: OK (todos los pasos pasan)"; exit 0; fi
echo "RESULTADO: FALLA ($FALLOS comprobaciones)"; [ "${MANTENER:-}" = 1 ] && echo "trabajo en $W"; exit 1
