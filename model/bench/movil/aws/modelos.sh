#!/bin/bash
CHISPA_S3=__CHISPA_S3__
# user-data (≤ 16 KB) de una c6a.2xlarge bajo demanda (Amazon Linux 2023, x86_64, 8 vCPU, sin GPU), root, con internet y rol con s3:GetObject y
# s3:PutObject (sin ListBucket), sin SSH. W13: los ficheros que lee la pantalla «Medir» de la demo Android (sdk/android/demo, Medidor.kt) para los
# dos perfiles móviles, con el ajuste 1 (línea base oficial, texto de torre v1). El orquestador sustituye __CHISPA_S3__ y sube UN paquete:
#   $CHISPA_S3/codigo.tgz    CHISPA_GOMOD_PROXY=1 bash model/l2/aws/empaquetar_estabilidad.sh <sha> > codigo.tgz   (trae model, runtime, server, format, sdk)
# Sube a $CHISPA_S3/movil/ (solo si TODA la validación pasó; un fichero roto no se sube):
#   modelo-fp16.chispa  modelo-int8.chispa   L0 + L1 (potion) + L2 + ESQUEMAS + CALIB + TORR, `chispa train --perfil movil|movil-int8 --torre`
#   e5.chispa-tok                              runtime/tok/exportar.py
#   esquema.json                               el few-shot que lee Medidor.esquemaDelModelo: {question, kind, options[{id, description}]}
#   manifiesto.json                            tamaño, sha256, perfil, checkpoint (+ sha256), texto de torre y si trae TORR
# Medidor.kt: «L0/L1» y «L2 con torre en caché» usan la pregunta de esquema.json (la misma del entrenamiento: 3 opciones × 10 ejemplos, el mínimo
# para que haya L0); «L2 con esquema nuevo» usa Medidor.ZERO_SHOT, escrito en el código de la app y que el .chispa NO trae: la torre se calcula al vuelo.
# Por eso la poda de vocabulario de la torre se amplía con los textos de ZERO_SHOT y de Textos.ES (extraídos de los .kt del paquete).
# Pasos: 1 entorno (Go, Python, torch CPU, ORT) · 2 paquete, checkpoint, e5 y potion · 3 tokenizador, L1, esquema y ejemplos · 4 por perfil: torre
# ONNX + chispa train · 5 validación con chispa-server (-tags ort): /healthz (L0, L1, L2, torre_al_vuelo) y una decisión por escenario · 6 manifiesto
# y subida. Cada paso deja OK/FALLO en estado.tsv; al salir (trap) sube resultados.tgz, estado.tsv y log.txt a $CHISPA_S3/ y apaga (shutdown -h +60).
# Tiempo ≈ 35 min (entorno y descargas ~10, exportar + train de dos perfiles ~15, validación ~5). Coste declarado ≈ 0,15 USD (c6a.2xlarge ≈ 0,31 USD/h).
# Opcionales: CHISPA_CKPT_S3 (ajuste-80ab8ef), CHISPA_ORT_VERSION (1.31.1).
# CHISPA_LOCAL=1: prueba en seco sin dnf, pip, descargas, aws ni shutdown, con checkpoint aleatorio y fixtures; sin ORT (~/ort) ni gcc, la validación es OMITIDO.
CKPT_S3=${CHISPA_CKPT_S3:-s3://chispa-pruebas-879381269751/ajuste-80ab8ef/ckpt/mejor.pt}
LOCAL=${CHISPA_LOCAL:-0}
AQUI=$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)   # solo para la prueba en seco
if [ "$LOCAL" = 1 ]; then [ "${CHISPA_S3#__}" != "$CHISPA_S3" ] && CHISPA_S3=s3://local/modelos-movil; else shutdown -h +60; fi
set -uo pipefail
export HOME="${HOME:-/root}"
T0=$(date +%s); TOPE=60; ORT_VERSION=${CHISPA_ORT_VERSION:-1.31.1}; PUERTO=8097
if [ "$LOCAL" = 1 ]; then BASE=${CHISPA_BASE:-/tmp/chispa-movil-modelos}; else BASE=/opt/chispa; fi
mkdir -p "$BASE"
exec > >(tee -a "$BASE/log.txt") 2>&1
echo "== arranque modelos móviles $(date -u +%FT%TZ) local=$LOCAL base=$BASE"
REPO=$BASE/repo RES=$BASE/resultados OUT=$BASE/movil
FALLO=""
PY=${CHISPA_PY:-$HOME/venv/bin/python}

s3cp() {   # un fichero (el rol no lista el bucket)
  if [ "$LOCAL" = 1 ]; then
    local o=$1 d=$2
    case $o in s3://*) o=/tmp/chispa/s3/${o#s3://};; esac
    case $d in s3://*) d=/tmp/chispa/s3/${d#s3://}; mkdir -p "$(dirname "$d")";; esac
    cp "$o" "$d"
  else aws s3 cp --only-show-errors "$1" "$2"
  fi
}
subir_y_apagar() {
  trap - EXIT
  sleep 1
  mkdir -p "$RES"
  [ -n "$FALLO" ] && echo "$FALLO" > "$RES/FALLO"
  cp "$BASE/log.txt" "$RES/log.txt" 2>/dev/null
  rm -f "$BASE/resultados.tgz"
  ( cd "$BASE" && find resultados -type f -size -20000k | LC_ALL=C sort > "$BASE/resultados.lista" && tar -czf "$BASE/resultados.tgz" -T "$BASE/resultados.lista" ) \
    || echo "no se pudo crear resultados.tgz"
  [ -f "$BASE/resultados.tgz" ] && { s3cp "$BASE/resultados.tgz" "$CHISPA_S3/resultados.tgz" || echo "no se pudo subir resultados.tgz"; }
  [ -f "$RES/estado.tsv" ] && { s3cp "$RES/estado.tsv" "$CHISPA_S3/estado.tsv" || echo "no se pudo subir estado.tsv"; }
  s3cp "$BASE/log.txt" "$CHISPA_S3/log.txt" || echo "no se pudo subir log.txt"
  [ "$LOCAL" = 1 ] || shutdown -h now
}
trap subir_y_apagar EXIT
trap 'exit 143' TERM INT HUP
mkdir -p "$RES" "$OUT"
estado() { printf '%s\t%s\n' "$1" "$2" >> "$RES/estado.tsv"; echo "[$1] $2"; }   # clave "OK detalle" | "FALLO detalle" | "OMITIDO motivo"
fallo() { echo "FALLO: $*"; FALLO="${FALLO:+$FALLO; }$*"; }
cierre() { echo "== listo $(date -u +%FT%TZ) fallo=${FALLO:-no} ($(( $(date +%s) - T0 )) s)"; echo "== estado.tsv"; cat "$RES/estado.tsv" 2>/dev/null; exit 0; }
quedan_min() { echo $(( TOPE - ($(date +%s) - T0) / 60 )); }
tope() { local m=$(( $(quedan_min) - 6 )); [ "$m" -gt "$1" ] && m=$1; [ "$m" -lt 2 ] && m=2; echo $m; }   # minutos de un paso: el tope propio o lo que quede menos 6
# microVM de kindling: torch CPU muere a veces con SIGILL (rc 132); solo en seco se limita a AVX2 y se repite hasta 3 veces
[ "$LOCAL" = 1 ] && export ONEDNN_MAX_CPU_ISA=${ONEDNN_MAX_CPU_ISA:-AVX2}
reint() { local n=0 rc; while :; do "$@"; rc=$?; n=$((n+1)); { [ "$rc" = 132 ] && [ "$LOCAL" = 1 ] && [ $n -lt 4 ]; } || return $rc; echo "SIGILL: se repite $*" >&2; done; }

# --- 1. entorno ---------------------------------------------------------------------------------------------------------------------
export HF_HOME="${HF_HOME:-$HOME/hf}"; mkdir -p "$HF_HOME"
if [ "$LOCAL" != 1 ]; then
  echo "== 1. entorno $(date -u +%T)"
  dnf install -y -q gcc tar gzip git python3.11 python3.11-pip || { fallo "dnf install"; estado entorno "FALLO dnf"; cierre; }
  curl -fsSL "https://go.dev/dl/go1.27.1.linux-amd64.tar.gz" | tar -xzC /usr/local || { fallo "descarga de Go"; estado entorno "FALLO Go"; cierre; }
  python3.11 -m venv "$BASE/venv" || { fallo "venv"; estado entorno "FALLO venv"; cierre; }
  PY=$BASE/venv/bin/python
  "$PY" -m pip install -q --no-cache-dir -U pip \
    && "$PY" -m pip install -q --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && "$PY" -m pip install -q --no-cache-dir numpy scipy scikit-learn transformers tokenizers huggingface_hub pyyaml pyarrow datasets onnx onnxscript onnxruntime \
    || { fallo "pip install"; estado entorno "FALLO pip"; cierre; }
  ORT_DIR=/opt/ort; mkdir -p "$ORT_DIR" && curl -fsSL "https://github.com/microsoft/onnxruntime/releases/download/v${ORT_VERSION}/onnxruntime-linux-x64-${ORT_VERSION}.tgz" \
    | tar -xzC "$ORT_DIR" --strip-components=1 || { fallo "descarga de ORT $ORT_VERSION"; estado entorno "FALLO ORT"; cierre; }
else ORT_DIR=${CHISPA_ORT_DIR:-$HOME/ort}; fi
export PATH=/usr/local/go/bin:$HOME/go-sdk/bin:$PATH GOTOOLCHAIN=local GOFLAGS=-mod=mod GONOSUMDB='github.com/juan52878911/*'
[ "$LOCAL" = 1 ] && export GOPROXY=off
"$PY" -c "import sys, numpy, scipy, torch, transformers, onnx; print(sys.version.split()[0], 'torch', torch.__version__)" && go version \
  && estado entorno "OK $(nproc) vCPU" || { fallo "imports de Python o Go"; estado entorno "FALLO imports"; cierre; }

# --- 2. código, checkpoint, e5 y potion -----------------------------------------------------------------------------------------------
echo "== 2. código y modelos $(date -u +%T)"
if [ "$LOCAL" = 1 ]; then   # en seco lo empaqueta el propio script (con fixtures)
  d=/tmp/chispa/s3/${CHISPA_S3#s3://}; mkdir -p "$d"
  bash "$AQUI/../../../l2/aws/empaquetar_estabilidad.sh" HEAD --fixtures > "$d/codigo.tgz" || { fallo "empaquetar"; estado paquete "FALLO empaquetar"; cierre; }
fi
rm -rf "$REPO"; mkdir -p "$REPO"
for _ in $(seq 1 90); do   # un paquete a medias no se acepta: hasta 45 min de reintentos
  s3cp "$CHISPA_S3/codigo.tgz" "$BASE/codigo.tgz" 2>/dev/null && tar -tzf "$BASE/codigo.tgz" >/dev/null 2>&1 && break
  rm -f "$BASE/codigo.tgz"; [ "$LOCAL" = 1 ] && break; sleep 30
done
tar -xzf "$BASE/codigo.tgz" -C "$REPO" && estado paquete "OK" || { fallo "no llegó un codigo.tgz válido"; estado paquete "FALLO sin codigo.tgz"; cierre; }
cd "$REPO" || cierre
export PYTHONPATH=$REPO:$REPO/sdk/python CHISPA_REPO=$REPO
[ "$LOCAL" = 1 ] || export GOPROXY=file://$REPO/gomod-proxy,https://proxy.golang.org
CKPT=$BASE/mejor.pt
if [ "$LOCAL" = 1 ]; then   # checkpoint aleatorio, como estabilidad.sh
  "$PY" -I -c "import sys; sys.path.insert(0, sys.argv[1]); import torch; from model.l2.exportar import modelo_aleatorio
torch.save({'modelo': modelo_aleatorio().state_dict(), 'cabezas': [], 'max_tok': 128}, sys.argv[2])" "$REPO" "$CKPT" \
    && estado checkpoint "OK aleatorio" || { fallo "checkpoint aleatorio"; estado checkpoint "FALLO"; cierre; }
else s3cp "$CKPT_S3" "$CKPT" && estado checkpoint "OK $(stat -c %s "$CKPT") bytes" || { fallo "checkpoint $CKPT_S3"; estado checkpoint "FALLO"; cierre; }
fi
if [ "$LOCAL" != 1 ]; then
  "$PY" -I - <<'PYEOF' || { fallo "descarga de e5 y potion"; estado modelos "FALLO descarga"; cierre; }
from huggingface_hub import snapshot_download as s
s("intfloat/multilingual-e5-small", allow_patterns=["*.json", "*.safetensors", "*.txt", "*.model", "tokenizer*"])
s("minishlab/potion-multilingual-128M")
s("mteb/amazon_massive_intent", repo_type="dataset", allow_patterns=["validation/es.json.gz"])   # exportar --vocab-ampliar mide <unk> con él
PYEOF
fi
E5=$(ls -d "$HF_HOME"/hub/models--intfloat--multilingual-e5-small/snapshots/*/ 2>/dev/null | head -1)
POT=$(ls -d "$HF_HOME"/hub/models--minishlab--potion-multilingual-128M/snapshots/* 2>/dev/null | head -1)
[ -n "$E5" ] && [ -n "$POT" ] && estado modelos "OK e5 y potion en $HF_HOME" || { fallo "e5 o potion no están en $HF_HOME"; estado modelos "FALLO"; cierre; }
export HF_HUB_OFFLINE=1

# --- 3. tokenizador, L1, esquema, ejemplos y textos para ampliar la poda -------------------------------------------------------------
echo "== 3. tokenizador, L1 y esquema $(date -u +%T)"
TOK=$OUT/e5.chispa-tok POTION=$BASE/potion.chispa-l1 ESQ=$OUT/esquema.json EJ=$BASE/ejemplos.jsonl AMPLIAR=$BASE/ampliar.txt
if "$PY" -I "$REPO/runtime/tok/exportar.py" "$E5" "$TOK" > "$RES/tok.log" 2>&1 \
   && "$PY" -I "$REPO/runtime/l1/exportar.py" "$POT" "$POTION" >> "$RES/tok.log" 2>&1 && [ -s "$TOK" ] && [ -s "$POTION" ]; then
  estado tokenizador_l1 "OK e5.chispa-tok $(stat -c %s "$TOK") bytes, potion $(stat -c %s "$POTION") bytes"
else tail -8 "$RES/tok.log"; estado tokenizador_l1 "FALLO ver tok.log"; fallo "tokenizador o potion"; cierre; fi
# esquema.json (formato de Medidor.leerPregunta; `id` y `tipo` los lee chispa train) y 30 ejemplos inventados (10 por opción = MIN_L0_POR_OPCION);
# ampliar.txt = literales de Medidor.ZERO_SHOT y de Textos.ES, para que la poda de vocabulario no deje <unk> en lo que mide la app
"$PY" -I - "$ESQ" "$EJ" "$AMPLIAR" "$REPO/sdk/android/demo/src/main/kotlin/com/chispa/demo" <<'PYEOF' && estado esquema "OK $(wc -l < "$EJ") ejemplos, $(wc -l < "$AMPLIAR") textos para ampliar la poda" \
  || { fallo "esquema, ejemplos o textos"; estado esquema "FALLO"; cierre; }
import json, re, sys
esq, ej, ampliar, kt = sys.argv[1:5]
OPC = {"compra": "quiere comprar o preguntar por un producto o su precio", "soporte": "pide ayuda con algo que ya compró o con su cuenta",
       "queja": "presenta una queja o un reclamo por un mal servicio"}
P = "¿Qué quiere el cliente en este mensaje de WhatsApp?"   # una sola esquema.json para dos lectores: chispa train (pregunta, opciones) y Medidor.kt (question, options)
json.dump({"id": "movil-intencion", "tipo": "choice", "kind": "choice", "pregunta": P, "question": P,
           "options": [{"id": k, "description": v} for k, v in OPC.items()], "opciones": OPC},
          open(esq, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
EJ = {"compra": ["quiero comprar dos camisetas negras", "¿cuánto vale el celular A15?", "me interesa el pedido de cemento por mayor", "¿tienen disponible la talla M?",
                 "necesito una cotización de veinte sillas", "cuánto cuesta el envío a Cali", "quiero pedir tres cajas de tornillos", "¿hay descuento por comprar cinco?",
                 "me gustaría ordenar el combo familiar", "¿aceptan pago con Nequi para comprar hoy?"],
      "soporte": ["no puedo entrar a la app, me sale error", "olvidé mi clave y no me llega el correo", "necesito cambiar la dirección de mi pedido 4512",
                  "la factura electrónica no me descarga", "¿cómo actualizo mis datos de contacto?", "la aplicación se cierra cuando abro el carrito",
                  "no me aparece el seguimiento de mi paquete", "ayúdenme a activar mi cuenta", "me pueden reenviar el comprobante de pago",
                  "no sé cómo cancelar la suscripción"],
      "queja": ["me cobraron dos veces y nadie responde", "esto es una vergüenza, llegó roto", "pésimo servicio, llevo una semana esperando",
                "el producto no es el que pedí y quiero reclamar", "nunca contestan el teléfono, qué abuso", "me mandaron el pedido incompleto otra vez",
                "estoy muy molesto por la demora", "la atención fue grosera, exijo una disculpa", "llegó tarde y en mal estado, inaceptable",
                "es la tercera vez que me fallan con la entrega"]}
with open(ej, "w", encoding="utf-8") as f:
    for e, ts in EJ.items():
        for t in ts:
            f.write(json.dumps({"texto": t, "etiqueta": e}, ensure_ascii=False) + "\n")
lit = lambda s: [json.loads('"%s"' % m) for m in re.findall(r'"((?:[^"\\\n]|\\.)*)"', s)]
med = open(kt + "/Medidor.kt", encoding="utf-8").read()
zs = med[med.index("val ZERO_SHOT"):med.index("val FEW_SHOT_POR_DEFECTO")]
tx = open(kt + "/Textos.kt", encoding="utf-8").read()
tx = tx[tx.index("listOf("):]
textos = [t for t in lit(zs) + lit(tx) if t.strip()]
assert len(textos) > 20, "no se extrajeron los textos de los .kt (%d)" % len(textos)
open(ampliar, "w", encoding="utf-8").write("\n".join(dict.fromkeys(textos)) + "\n")
PYEOF

# --- 4. por perfil: torre ONNX y chispa train ---------------------------------------------------------------------------------------
echo "== 4. torre y chispa train $(date -u +%T)"
declare -A PERFIL=([fp16]=movil [int8]=movil-int8 [servidor]=servidor)
export VARIANTES=${CHISPA_VARIANTES:-fp16 int8}   # «servidor»: fp32 sin poda (perfil servidor), para chispa-server; sin --vocab-ampliar
for v in $VARIANTES; do
  p=${PERFIL[$v]}; M=$OUT/modelo-$v.chispa; TORRE=$BASE/torre-$v.onnx
  if reint timeout "$(tope 8)m" "$PY" -u -m model.l2.exportar --torre-onnx "$TORRE" --ckpt "$CKPT" --perfil "$p" $([ "$p" = servidor ] || echo --vocab-ampliar "$AMPLIAR" "$EJ") > "$RES/torre-$v.log" 2>&1 \
     && [ -s "$TORRE" ]; then estado "torre_$v" "OK $(stat -c %s "$TORRE") bytes (perfil $p)"
  else tail -10 "$RES/torre-$v.log"; estado "torre_$v" "FALLO ver torre-$v.log"; estado "train_$v" "FALLO sin torre"; fallo "torre $v"; continue; fi
  if reint timeout "$(tope 10)m" "$PY" -u -m chispa train --ejemplos "$EJ" --esquema "$ESQ" --salida "$M" --ckpt "$CKPT" --perfil "$p" --torre "$TORRE" \
       $([ "$p" = servidor ] || echo --l1 "$POTION") --repo "$REPO" > "$RES/train-$v.log" 2>&1 && [ -s "$M" ]; then   # servidor sin L1: con potion pasa del tope de format/chispa3
    estado "train_$v" "OK $(stat -c %s "$M") bytes"
  else tail -10 "$RES/train-$v.log"; estado "train_$v" "FALLO ver train-$v.log"; fallo "train $v"; fi
done

# --- 5. validación con chispa-server ---------------------------------------------------------------------------------------------------
echo "== 5. validación $(date -u +%T)"
SERV=$BASE/chispa-server ORT_LIB=$ORT_DIR/lib/libonnxruntime.so.$ORT_VERSION
SERV_OK=0
if [ ! -f "$ORT_LIB" ] || ! command -v gcc >/dev/null; then
  estado servidor "OMITIDO sin ORT ($ORT_LIB) o sin gcc"; [ "$LOCAL" = 1 ] || fallo "sin ORT para validar"
  for v in $VARIANTES; do estado "validacion_$v" "OMITIDO sin chispa-server"; done
else
  export CGO_ENABLED=1 LD_LIBRARY_PATH=$ORT_DIR/lib CHISPA_ORT_LIB=$ORT_LIB
  if ( cd "$REPO/server" && timeout "$(tope 7)m" go build -tags ort -ldflags "-X github.com/juan52878911/chispa/server/decide.RutaORT=$ORT_LIB" -o "$SERV" ./cmd/chispa-server ) \
       > "$RES/servidor-build.log" 2>&1 && [ -x "$SERV" ]; then SERV_OK=1; estado servidor "OK chispa-server -tags ort amd64"
  else tail -8 "$RES/servidor-build.log"; estado servidor "FALLO ver servidor-build.log"; fallo "build de chispa-server"; fi
  for v in $VARIANTES; do
    M=$OUT/modelo-$v.chispa
    if [ "$SERV_OK" != 1 ] || [ ! -s "$M" ]; then estado "validacion_$v" "FALLO sin servidor o sin modelo"; fallo "validación $v"; continue; fi
    "$SERV" -addr 127.0.0.1:$PUERTO -modelo "$M" -tok "$TOK" > "$RES/servidor-$v.log" 2>&1 & HP=$!
    for _ in $(seq 1 90); do curl -fsS http://127.0.0.1:$PUERTO/healthz > "$RES/healthz-$v.json" 2>/dev/null && break; sleep 1; done
    # una decisión por escenario de Medir: pregunta de esquema.json (L0/L1, y L2 con la torre en caché) y Medidor.ZERO_SHOT (L2 con esquema nuevo)
    if VARIANTE=$v "$PY" -I - "$RES/healthz-$v.json" "http://127.0.0.1:$PUERTO" "$ESQ" "$REPO/sdk/android/demo/src/main/kotlin/com/chispa/demo/Medidor.kt" "$RES/decisiones-$v.json" > "$RES/validacion-$v.txt" 2>&1 <<'PYEOF'
import json, os, re, sys, urllib.request
hz, url, esq, kt, salida = sys.argv[1:6]
h = json.load(open(hz)); capas = h.get("capas") or {}
faltan = [c for c in (("L0", "L2") if os.environ.get("VARIANTE") == "servidor" else ("L0", "L1", "L2")) if not capas.get(c)] + ([] if h.get("torre_al_vuelo") is True else ["torre_al_vuelo"])
if faltan:
    sys.exit("/healthz sin %s: %s" % (", ".join(faltan), json.dumps(h)[:300]))
e = json.load(open(esq, encoding="utf-8"))
med = open(kt, encoding="utf-8").read()
zs = med[med.index("val ZERO_SHOT"):med.index("val FEW_SHOT_POR_DEFECTO")]
q0 = re.search(r'Pregunta\(\s*"((?:[^"\\]|\\.)*)"', zs).group(1)
ops = re.findall(r'Opcion\("([^"]+)",\s*"((?:[^"\\]|\\.)*)"\)', zs)
assert len(ops) >= 3, "no se leyó ZERO_SHOT"
Q = {"few-shot (esquema.json)": ({"id": "movil-intencion", "question": e["question"], "kind": e.get("kind", "choice"),
                                  "options": [{"id": o["id"], "description": o["description"]} for o in e["options"]]}, "me cobraron dos veces y nadie responde"),
     "zero-shot (esquema nuevo, torre al vuelo)": ({"id": "zs-area", "question": q0, "kind": "choice", "options": [{"id": i, "description": d} for i, d in ops]},
                                                   "no me deja ingresar a la app, me sale error con la clave")}
res = {}
for nombre, (q, texto) in Q.items():
    for rep in (1, 2):   # la segunda lee la torre de la caché
        q["nonce"] = "%s-%d" % (q["id"], rep)
        r = json.loads(urllib.request.urlopen(urllib.request.Request(url + "/v1/decide", json.dumps({"state": texto, "questions": [q]}).encode(),
                                                                    {"Content-Type": "application/json"}), timeout=60).read())["results"][0]
        ids = [o["id"] for o in q["options"]]
        if r.get("error") or not (r.get("escalate") or any(r.get("probs", {}).get(i) is not None for i in ids)):
            sys.exit("%s: sin decisión ni escalada: %s" % (nombre, json.dumps(r)[:300]))
        res["%s #%d" % (nombre, rep)] = {"layer": r.get("layer"), "escalate": r.get("escalate"), "ms": r.get("ms")}
json.dump({"healthz": h, "decisiones": res}, open(salida, "w"), indent=1)
print("; ".join("%s → %s" % (k, v["layer"] or ("escala" if v["escalate"] else "?")) for k, v in res.items()))
PYEOF
    then estado "validacion_$v" "OK L0 L1 L2 torre_al_vuelo; $(cat "$RES/validacion-$v.txt" | tail -1 | cut -c1-300)"
    else cat "$RES/validacion-$v.txt" | tail -5; tail -5 "$RES/servidor-$v.log"; estado "validacion_$v" "FALLO $(tail -1 "$RES/validacion-$v.txt" | cut -c1-300)"; fallo "validación $v"; fi
    kill $HP 2>/dev/null; wait $HP 2>/dev/null
  done
fi

# --- 6. manifiesto y subida (solo sin FALLO) ---------------------------------------------------------------------------------------------
echo "== 6. manifiesto y subida $(date -u +%T)"
if [ -n "$FALLO" ]; then estado subida "OMITIDO hay FALLO (no se sube un fichero roto): $FALLO"; cierre; fi
"$PY" -I - "$OUT" "$CKPT" "$CKPT_S3" "$REPO" <<'PYEOF' && estado manifiesto "OK $(wc -c < "$OUT/manifiesto.json") bytes" || { fallo "manifiesto"; estado manifiesto "FALLO"; cierre; }
import hashlib, json, os, sys
out, ckpt, ckpt_s3, repo = sys.argv[1:5]
sys.path[:0] = [repo, repo + "/sdk/python"]
from chispa import formato
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
from model.l2.calibrar import cargar_modelo
modelo, _ = cargar_modelo(ckpt, "cpu")
texto_ckpt = getattr(modelo, "texto_torre", "v1")
nombres = {v: k for k, v in vars(formato).items() if k in ("META", "L0", "L1", "L2", "ESQUEMAS", "CALIB", "TORR", "SOPL1") and isinstance(v, int)}
perfiles = {"modelo-%s.chispa" % v: {"fp16": "movil", "int8": "movil-int8", "servidor": "servidor"}[v] for v in os.environ["VARIANTES"].split()}
man = {"checkpoint": {"s3": ckpt_s3, "sha256": sha(ckpt), "bytes": os.path.getsize(ckpt), "texto_torre": texto_ckpt}, "ficheros": {}}
for f in list(perfiles) + ["e5.chispa-tok", "esquema.json"]:
    p = os.path.join(out, f); d = {"bytes": os.path.getsize(p), "sha256": sha(p)}
    if f in perfiles:
        sec = formato.leer(open(p, "rb").read())
        meta = json.loads(sec[formato.META])
        d.update(perfil=perfiles[f], trae_torr=formato.TORR in sec, texto_torre=meta.get("texto_torre", "v1"), secciones=sorted(nombres[t] for t in sec if t in nombres),
                 checkpoint_sha256=man["checkpoint"]["sha256"])
        assert d["trae_torr"], f + " sin TORR"
        assert d["texto_torre"] == texto_ckpt, "texto_torre %s != checkpoint %s" % (d["texto_torre"], texto_ckpt)
    man["ficheros"][f] = d
json.dump(man, open(os.path.join(out, "manifiesto.json"), "w"), indent=1)
PYEOF
SUBIDOS=0
N=0; for v in $VARIANTES; do N=$((N+1)); done; N=$((N+3))
for f in $(for v in $VARIANTES; do echo modelo-$v.chispa; done) e5.chispa-tok esquema.json manifiesto.json; do
  s3cp "$OUT/$f" "$CHISPA_S3/movil/$f" && SUBIDOS=$((SUBIDOS+1)) || fallo "subida de $f"
done
for v in $VARIANTES; do   # la torre ONNX (con sus metadata_props) también: `chispa train --l2 … --torre` la pide para el few-shot
  [ -s "$BASE/torre-$v.onnx" ] && { s3cp "$BASE/torre-$v.onnx" "$CHISPA_S3/movil/torre-$v.onnx" && echo "torre-$v.onnx subida $(sha256sum "$BASE/torre-$v.onnx" | cut -c1-64)" || fallo "subida de torre-$v.onnx"; }
done
[ "$SUBIDOS" = "$N" ] && estado subida "OK $SUBIDOS ficheros en $CHISPA_S3/movil/" || estado subida "FALLO $SUBIDOS de $N"
cp "$OUT/manifiesto.json" "$RES/" 2>/dev/null
cierre
