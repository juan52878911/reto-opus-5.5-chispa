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
set -u -o pipefail  # sin pipefail, `cmd | sed && ok || fallo` toma el código de sed y nunca falla
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
assert formato.SOPL1 in formato.leer(open('$W/fs.chispa','rb').read()), 'fs.chispa sin SOPL1'
" 2>&1 | sed 's/^/        /' && ok "secciones: TORR, L1, L2, ESQUEMAS (+SOPL1 en few-shot)" || fallo "secciones del .chispa"

# H8: la CALIB de l2.chispa (gensint: choice T=0,02, τ=0,37) debe llegar al .chispa final como tipos_l2 y tau_escalate_l2, distintos de los de L1.
$PY -I -c "
import sys, json; sys.path.insert(0, '$RAIZ/sdk/python')
from chispa import formato
for n in ('zs', 'fs'):
    c = json.loads(formato.leer(open('$W/%s.chispa' % n, 'rb').read())[formato.CALIB])
    assert 'tipos_l2' in c and 'tau_escalate_l2' in c, (n, sorted(c))
    assert c['tipos_l2']['choice']['T'] == 0.02 and c['tau_escalate_l2'] == 0.37, (n, c['tipos_l2'], c['tau_escalate_l2'])
    assert c['tipos_l2'] != c['tipos'], (n, 'tipos_l2 igual que los tipos de L1')
    print(n, 'L1 choice.T=%s τ=%s | L2 choice.T=%s τ=%s' % (c['tipos'].get('choice', {}).get('T'), c['tau_escalate'], c['tipos_l2']['choice']['T'], c['tau_escalate_l2']))
" 2>&1 | sed 's/^/        /' && ok "CALIB final: tipos_l2 y tau_escalate_l2 de l2.chispa, distintos de los de L1 (zs, fs)" || fallo "CALIB final sin tipos_l2/tau_escalate_l2 de L2"
grep -q "AVISO: --l2 sin CALIB" "$W"/train_*.log && fallo "train avisa «--l2 sin CALIB» aunque l2.chispa trae CALIB"

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
assert j['n'] == 15 and j['errores'] == 0, (j['n'], j['errores'])
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

paso "7b. L2 lee tipos_l2 (H8): el mismo fs.chispa con y sin tipos_l2, con L2 decidiendo siempre (L0 y L1 con τ=1, L2 con τ=0)"
cat > "$W/cfg_l2.json" <<JSON
{"capas":[{"nombre":"L0","tau":1.0},{"nombre":"L1","tau":1.0},{"nombre":"L2","tau":0.0},{"nombre":"L3","tau":0.6}],
 "tau_l2_esquema_nuevo":0.5, "l1_shrinkage_lambda":4, "cache_esquemas":64}
JSON
$PY -I -c "
import sys, json; sys.path.insert(0, '$RAIZ/sdk/python')
from chispa import formato
s = formato.leer(open('$W/fs.chispa', 'rb').read())
c = json.loads(s[formato.CALIB]); del c['tipos_l2']; del c['tau_escalate_l2']; s[formato.CALIB] = json.dumps(c).encode()
open('$W/sin_l2.chispa', 'wb').write(formato.escribir(s))
"
P4=$((P2 + 2))
for n in fs sin_l2; do
  arrancar "$P4" "$W/srvT_$n.log" -modelo "$W/$n.chispa" -config "$W/cfg_l2.json"; PT=$SPID
  $CP decidir "http://127.0.0.1:$P4" "$D/peticion_ferreteria.json" --capa L2 --guardar "$W/resp_t_$n.json" >/dev/null || fallo "ferretería con $n.chispa no decide en L2"
  kill "$PT"; wait "$PT" 2>/dev/null
done
$PY -I -c "
import json; a=json.load(open('$W/resp_t_fs.json'))['results'][0]; b=json.load(open('$W/resp_t_sin_l2.json'))['results'][0]
print('con tipos_l2', a['layer'], {k: round(v,3) for k,v in a['probs'].items()}); print('sin tipos_l2', b['layer'], {k: round(v,3) for k,v in b['probs'].items()})
assert a['layer'] == b['layer'] == 'L2'
assert max(abs(a['probs'][k] - b['probs'][k]) for k in a['probs']) > 0.01, 'L2 no usa tipos_l2: mismas probabilidades'
" 2>&1 | sed 's/^/        /' && ok "L2 usa tipos_l2 (probabilidades distintas a las que daría con los tipos de L1)" || fallo "L2 no lee tipos_l2"

paso "8. Recarga con torres al vuelo en curso (las sesiones ORT se cierran y se reabren)"
pase "3 SIGHUP con 8 hilos de esquema nuevo: ninguna petición falla" $CP recarga "$URL" "$D/peticion_nueva.json" --pid "$PB" --hups 3 --hilos 8 --segundos 1.5
pase "recargas_total{ok} = 3 y torres sin errores" bash -c "$CP metrica '$URL' chispa_recargas_total '{resultado=\"ok\"}' --igual 3 && $CP metrica '$URL' chispa_torres_errores_total --igual 0"
pase "tras recargar, L2 con torre al vuelo sigue decidiendo" $CP decidir "$URL" "$D/peticion_nueva.json" --capa L2

paso "9. multi (multietiqueta): zero-shot en el servidor B y few-shot con chispa train (etiqueta con «|»)"
TORRES_ANTES=$($CP metrica "$URL" chispa_torres_calculadas_total --valor) || critico "no se pudo leer chispa_torres_calculadas_total"
pase "zero-shot: 200, answers y una p por opción (esquema nuevo, torre al vuelo)" $CP decidir "$URL" "$D/peticion_multi.json" --multi-con-probs --guardar "$W/resp_multi_zs.json"
# Sin multi_l2 en CALIB, L2 no opina en multi y no gasta torres (R11-3): el aumento debe ser exactamente 0.
pase "multi sin multi_l2 no calcula torres (aumento 0) y sin errores" bash -c "$CP metrica '$URL' chispa_torres_calculadas_total --base '$TORRES_ANTES' --igual 0 && $CP metrica '$URL' chispa_torres_errores_total --igual 0"
$TRAIN --esquema "$D/temas.yaml" --ejemplos "$D/ejemplos_multi.csv" --tau-l2-esquema-nuevo 0.5 --salida "$W/ms.chispa" >"$W/train_ms.log" 2>&1 || { tail -5 "$W/train_ms.log"; critico "train multi few-shot"; }
grep -iE "multi|SOPL1" "$W/train_ms.log" | cut -c1-160 | sed 's/^/        /'; ok "few-shot multi → ms.chispa"
$PY -I -c "
import sys; sys.path.insert(0, '$RAIZ/sdk/python')
from chispa import formato
import json
s = formato.leer(open('$W/ms.chispa','rb').read()); print(sorted(s)); assert formato.SOPL1 in s and formato.CALIB in s, 'ms.chispa sin SOPL1 o CALIB'
c = json.loads(s[formato.CALIB]); assert c.get('tipos_l2', {}).get('choice', {}).get('T') == 0.02 and c.get('tau_escalate_l2') == 0.37, ('ms.chispa sin tipos_l2/tau_escalate_l2 de L2', sorted(c))
" 2>&1 | sed 's/^/        /' && ok "ms.chispa trae SOPL1 y CALIB" || fallo "ms.chispa sin SOPL1 o CALIB"
grep -q "sin SOPL1" "$W/train_ms.log" && fallo "multi few-shot sin SOPL1 (HALLAZGOS.md H2)"
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
# La comparación zero-shot/few-shot se hace donde la CALIB de multi y SOPL1 se aplican: L1 (τ=0 para que decida). En L2 ambos usan la CALIB de noul
# (sin `maxsim_l2` no hay multi_l2) y las probabilidades coinciden por diseño; comparar ahí no prueba nada.
cat > "$W/cfg_l1.json" <<JSON
{"capas":[{"nombre":"L0","tau":0.8},{"nombre":"L1","tau":0.0},{"nombre":"L2","tau":0.5},{"nombre":"L3","tau":0.6}],
 "tau_l2_esquema_nuevo":0.5, "l1_shrinkage_lambda":4, "cache_esquemas":64}
JSON
kill "$PC"; wait "$PC" 2>/dev/null
for n in zs ms; do
  P3=$((P2 + 1)); arrancar "$P3" "$W/srvL1_$n.log" -modelo "$W/$n.chispa" -config "$W/cfg_l1.json"; PL=$SPID
  pase "multi en L1 ($n): 200, una p por opción" $CP decidir "http://127.0.0.1:$P3" "$D/peticion_multi.json" --multi-con-probs --capa L1 --guardar "$W/resp_multi_l1_$n.json"
  kill "$PL"; wait "$PL" 2>/dev/null
done
# Tres comprobaciones, con margen MARGEN (0,02) para distinguir efecto de ruido de flotantes:
#  1) ms.chispa trae CALIB «multi@<hash del esquema>» y «multi@<hash>#<opción>» (a, b y θ);
#  2) con λ ausente en -config (sin SOPL1 efectivo) las p de ms siguen a σ(a·cos+b) de CALIB multi@<hash>: logit(p) = a·cos+b con cos∈[-1,1];
#  3) λ=4 (SOPL1) mueve las p de ms ≥ MARGEN frente a λ ausente, y ms difiere del zero-shot (zs) ≥ MARGEN.
cat > "$W/cfg_l1_sinl.json" <<JSON
{"capas":[{"nombre":"L0","tau":0.8},{"nombre":"L1","tau":0.0},{"nombre":"L2","tau":0.5},{"nombre":"L3","tau":0.6}],
 "tau_l2_esquema_nuevo":0.5, "cache_esquemas":64}
JSON
P3=$((P2 + 1)); arrancar "$P3" "$W/srvL1_ms_sinl.log" -modelo "$W/ms.chispa" -config "$W/cfg_l1_sinl.json"; PL=$SPID
pase "multi en L1 (ms, λ ausente): 200, una p por opción" $CP decidir "http://127.0.0.1:$P3" "$D/peticion_multi.json" --multi-con-probs --capa L1 --guardar "$W/resp_multi_l1_ms0.json"
kill "$PL"; wait "$PL" 2>/dev/null
$PY -I -c "
import sys, json, math; sys.path.insert(0, '$RAIZ/sdk/python')
from chispa import formato
MARGEN = 0.02
W = '$W'
cal = json.loads(formato.leer(open(W + '/ms.chispa', 'rb').read())[formato.CALIB])['tipos']
esq = sorted(k for k in cal if k.startswith('multi@') and '#' not in k)
assert len(esq) == 1 and any(k.startswith(esq[0] + '#') for k in cal), sorted(cal)
a, b = cal[esq[0]]['a'], cal[esq[0]]['b']
assert a > 0, cal[esq[0]]
p = lambda n: json.load(open(W + '/resp_multi_l1_%s.json' % n))['results'][0]['probs']
zs, ms, ms0 = p('zs'), p('ms'), p('ms0')
assert len(ms) == 4 and set(ms) == set(ms0) == set(zs)
for k, v in ms0.items():
    cos = (math.log(v / (1 - v)) - b) / a
    assert -1.0001 <= cos <= 1.0001, ('p de L1 sin λ no sigue σ(a·cos+b)', k, v, cos)
d = lambda x, y: max(abs(x[k] - y[k]) for k in x)
print('a=%.3f b=%.3f  |ms-ms0|=%.3f  |ms-zs|=%.3f' % (a, b, d(ms, ms0), d(ms, zs)))
assert d(ms, ms0) >= MARGEN, 'λ=4 (SOPL1) no mueve las p de L1'
assert d(ms, zs) >= MARGEN, 'few-shot igual que zero-shot en L1'
" 2>&1 | sed 's/^/        /' && ok "few-shot: CALIB multi (σ(a·cos+b)) y SOPL1 mueven las p de L1 ≥ 0,02 frente a λ ausente y a zero-shot" || fallo "comparación zero/few-shot en L1"
URL=http://127.0.0.1:$P2
arrancar "$P2" "$W/srvC2.log" -modelo "$W/serv3.chispa" -config "$W/cfg.json"; PC=$SPID
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

paso "10. Que un .chispa sin torre no falle en silencio (train, servidor, métrica, batería) y, con torre, escale con probs"
$PY -m chispa train --esquema "$D/ferreteria.yaml" --l2 "$W/l2.chispa" --salida "$W/sin_torre.chispa" >"$W/train_sin_torre.log" 2>&1 || { tail -5 "$W/train_sin_torre.log"; critico "train sin --torre"; }
grep -q "^AVISO: sin TORR" "$W/train_sin_torre.log" && grep -q "capas del .chispa: L0 no, L1 no, L2 sí, torre al vuelo (TORR) no" "$W/train_sin_torre.log" \
  && ok "train sin --torre: avisa y resume las capas" || { cat "$W/train_sin_torre.log"; fallo "train sin --torre no avisa/resume"; }
$PY -m chispa train --esquema "$D/ferreteria.yaml" --l2 "$W/l2.chispa" --sin-torre --salida "$W/sin_torre2.chispa" >"$W/train_sin_torre2.log" 2>&1 || critico "train --sin-torre"
grep -q "^AVISO: sin TORR" "$W/train_sin_torre2.log" && fallo "train --sin-torre avisa aunque es explícito" || ok "train --sin-torre explícito: sin aviso"
PE=$((PUERTO + 5)); UE=http://127.0.0.1:$PE
arrancar "$PE" "$W/srvE.log" -modelo "$W/sin_torre.chispa"; PSE=$SPID
grep -q "capas efectivas: L2; sin modelo: L0, L1, L3; torre al vuelo (esquemas nuevos en L2): false" "$W/srvE.log" && grep -q "AVISO: sin torre al vuelo" "$W/srvE.log" \
  && ok "servidor: log de arranque con capas efectivas y aviso de torre" || { grep -i "capas" "$W/srvE.log"; fallo "log de arranque sin capas efectivas/aviso"; }
curl -s "$UE/healthz" | grep -q '"torre_al_vuelo":false' && ok "/healthz: torre_al_vuelo false" || fallo "/healthz sin capacidades"
pase "esquema nuevo sin torre: todo escala con escalate_reason sin_opinion y sin probs" $CP decidir "$UE" "$D/peticion_nueva.json" --razon sin_opinion
pase "métrica por capa y causa (L2, sin_torre = 3) y chispa_sin_opinion_total = 3" bash -c "$CP metrica '$UE' chispa_capa_no_opina_total '{capa=\"L2\",causa=\"sin_torre\"}' --igual 3 && $CP metrica '$UE' chispa_sin_opinion_total --igual 3"
pase "batería contra el servidor sin torre: nadie opinó = 100 %, alerta con la causa" $PY "$AQUI/bateria_nadie.py" "$UE" sin_torre
kill "$PSE"; wait "$PSE" 2>/dev/null
cat > "$W/cfg_esc.json" <<JSON
{"capas":[{"nombre":"L0","tau":1.0},{"nombre":"L1","tau":1.0},{"nombre":"L2","tau":1.0},{"nombre":"L3","tau":1.0}],
 "tau_l2_esquema_nuevo":1.0, "l1_shrinkage_lambda":4, "cache_esquemas":64}
JSON
arrancar "$PE" "$W/srvF.log" -modelo "$W/zs.chispa" -config "$W/cfg_esc.json"; PSF=$SPID
grep -q "torre al vuelo (esquemas nuevos en L2): true" "$W/srvF.log" && ok "servidor con TORR: el log dice torre al vuelo true" || fallo "log de arranque con torre"
grep -q "AVISO: sin torre al vuelo" "$W/srvF.log" && fallo "aviso de torre con TORR"
pase "con torre (τ=1): escala con probs y escalate_reason baja_confianza" $CP decidir "$UE" "$D/peticion_nueva.json" --razon baja_confianza
pase "batería con torre: escala con probs, las cuenta en exactitud, sin alerta" $PY "$AQUI/bateria_nadie.py" "$UE" con_torre
kill "$PSF"; wait "$PSF" 2>/dev/null

echo
if [ "$FALLOS" -eq 0 ]; then echo "RESULTADO: OK (todos los pasos pasan)"; exit 0; fi
echo "RESULTADO: FALLA ($FALLOS comprobaciones)"; [ "${MANTENER:-}" = 1 ] && echo "trabajo en $W"; exit 1
