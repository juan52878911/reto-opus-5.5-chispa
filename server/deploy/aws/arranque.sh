#!/bin/bash
CHISPA_S3=__CHISPA_S3__
# user-data de una Amazon Linux 2023 x86_64 recién creada (root): construye la imagen OCI de chispa-server
# (server/deploy/Dockerfile, con ONNX Runtime), la arranca con un .chispa, comprueba el contrato, mide decisiones/s y
# compila/prueba también `-tags ort` fuera de docker. Deja /opt/chispa/resultados.tgz y /opt/chispa/LISTO.
# El orquestador sustituye __CHISPA_S3__ por un prefijo s3://bucket/ruta y sube ahí:
#   codigo.tgz              (bash server/deploy/aws/empaquetar.sh > codigo.tgz), obligatorio;
#   modelos/l0l1.chispa     (v3 con L0 y L1), opcional;
#   modelos/l2.chispa       (v3 con L2 y ESQUEMAS), opcional. Cada fichero se busca por separado y, si hay los dos,
#                           se fusionan (mkmodelo -unir; si una sección está en ambos, gana l0l1). Sin ninguno, se
#                           genera uno pequeño con L0 de server/testdata y un L1 diminuto.
# La instancia (rol con s3:GetObject y s3:PutObject, sin SSH) sube log.txt y resultados.tgz al mismo prefijo y se apaga.
# CHISPA_LOCAL=1: prueba en seco en kindling: sin dnf, docker, ORT ni shutdown; compila SIN la etiqueta ort y corre los
# pasos 4 a 6 con el binario nativo (~/go-sdk, /tmp/chispa-srv). El "s3" es /tmp/chispa/s3/<prefijo sin s3://>.
[ "${CHISPA_LOCAL:-}" = 1 ] || shutdown -h +90   # apagado forzoso: la instancia se termina al apagarse
set -uo pipefail
export HOME="${HOME:-/root}"

GO_VERSION=1.27.1        # tar de go.dev para el Go del anfitrión
ORT_VERSION=1.22.0       # release de microsoft/onnxruntime (la misma que pasa al Dockerfile)
ORT_GO_VERSION=v1.19.0   # github.com/yalue/onnxruntime_go; tiene que ser de una API <= ORT_VERSION
PUERTO=8090

if [ "${CHISPA_LOCAL:-}" = 1 ]; then BASE=/tmp/chispa-srv; else BASE=/opt/chispa; fi
mkdir -p "$BASE"
exec > >(tee -a "$BASE/log.txt") 2>&1
echo "== arranque $(date -u +%FT%TZ) local=${CHISPA_LOCAL:-0} base=$BASE"

REPO=$BASE/repo RES=$BASE/resultados
FALLO=""
S3LOCAL=/tmp/chispa/s3/${CHISPA_S3#s3://}
SRVPID=""

s3cp() {
  if [ "${CHISPA_LOCAL:-}" = 1 ]; then
    local o=$1 d=$2
    case $o in s3://*) o=/tmp/chispa/s3/${o#s3://};; esac
    case $d in s3://*) d=/tmp/chispa/s3/${d#s3://}; mkdir -p "$(dirname "$d")";; esac
    cp "$o" "$d"
  else
    aws s3 cp --only-show-errors "$1" "$2"
  fi
}

parar_servidor() {
  [ -n "$SRVPID" ] && kill "$SRVPID" 2>/dev/null
  SRVPID=""
  [ "${CHISPA_LOCAL:-}" = 1 ] || docker rm -f chispa >/dev/null 2>&1
  return 0
}

subir_y_apagar() {
  trap - EXIT
  parar_servidor
  sleep 1   # deja que tee vacíe el log
  s3cp "$BASE/log.txt" "$CHISPA_S3/log.txt" || echo "no se pudo subir log.txt"
  [ -f "$BASE/resultados.tgz" ] && { s3cp "$BASE/resultados.tgz" "$CHISPA_S3/resultados.tgz" || echo "no se pudo subir resultados.tgz"; }
  [ "${CHISPA_LOCAL:-}" = 1 ] || shutdown -h now
}
trap subir_y_apagar EXIT
trap 'exit 143' TERM INT HUP

fallo() { echo "FALLO: $*"; FALLO="${FALLO:+$FALLO; }$*"; }

cierre() {
  mkdir -p "$RES"
  [ -n "$FALLO" ] && echo "$FALLO" > "$BASE/FALLO" && cp "$BASE/FALLO" "$RES/"
  df -h "$BASE" | tail -1
  cp "$BASE/log.txt" "$RES/log.txt"
  tar -C "$BASE" -czf "$BASE/resultados.tgz" resultados
  touch "$BASE/LISTO"
  echo "== listo $(date -u +%FT%TZ) fallo=${FALLO:-no}"
  exit 0
}

# --- 1. entorno: docker, Go, gcc y la .so de ORT para la compilación del anfitrión ----------------------------
if [ "${CHISPA_LOCAL:-}" = 1 ]; then
  export PATH="$HOME/go-sdk/bin:$PATH"
else
  echo "== 1. instalar docker, gcc y Go $GO_VERSION $(date -u +%T)"
  dnf install -y docker gcc tar gzip python3 || { fallo "dnf install"; cierre; }
  systemctl start docker || { fallo "no arranca docker"; cierre; }
  curl -fsSL "https://go.dev/dl/go${GO_VERSION}.linux-amd64.tar.gz" | tar -xzC /usr/local || { fallo "descarga de Go"; cierre; }
  export PATH=/usr/local/go/bin:$PATH
  mkdir -p /opt/ort && curl -fsSL "https://github.com/microsoft/onnxruntime/releases/download/v${ORT_VERSION}/onnxruntime-linux-x64-${ORT_VERSION}.tgz" \
    | tar -xzC /opt/ort --strip-components=1 || fallo "descarga de ORT $ORT_VERSION"
fi
export GOTOOLCHAIN=local GOFLAGS=-mod=mod GONOSUMDB='github.com/juan52878911/*'
go version

# --- código en S3 (reintenta cada 30 s hasta 45 min) -----------------------------------------------------------
echo "bajando $CHISPA_S3/codigo.tgz"
for _ in $(seq 1 90); do
  s3cp "$CHISPA_S3/codigo.tgz" "$BASE/codigo.tgz" 2>/dev/null && tar -tzf "$BASE/codigo.tgz" >/dev/null 2>&1 && break
  rm -f "$BASE/codigo.tgz"
  sleep 30
done
rm -rf "$REPO"; mkdir -p "$REPO"
tar -xzf "$BASE/codigo.tgz" -C "$REPO" || { fallo "no llegó un codigo.tgz válido en 45 min"; cierre; }
mkdir -p "$RES"
{ lscpu; echo; echo "nproc: $(nproc)"; } > "$RES/hardware.txt"
grep -E 'Model name|^CPU\(s\)' "$RES/hardware.txt"
if [ "${CHISPA_LOCAL:-}" != 1 ]; then
  t=$(curl -sf -m 3 -X PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 60') &&
    curl -sf -m 3 -H "X-aws-ec2-metadata-token: $t" http://169.254.169.254/latest/meta-data/instance-type > "$RES/instance-type.txt"
fi

# Go del anfitrión: kindling sale de gomod-proxy/ del tgz; el resto, de proxy.golang.org (en local, sin red: la caché).
if [ "${CHISPA_LOCAL:-}" = 1 ]; then export GOPROXY=off; else export GOPROXY=file://$REPO/gomod-proxy,https://proxy.golang.org; fi
cd "$REPO/server" || { fallo "no existe server/ en codigo.tgz"; cierre; }

# --- 2. construir la imagen; 3. medir su tamaño -------------------------------------------------------------
IMAGEN=0
if [ "${CHISPA_LOCAL:-}" != 1 ]; then
  echo "== 2. docker build $(date -u +%T)"
  if docker build -f "$REPO/server/deploy/Dockerfile" --build-arg ORT_VERSION=$ORT_VERSION --build-arg ORT_GO_VERSION=$ORT_GO_VERSION \
       -t chispa-server "$REPO"; then
    IMAGEN=1
    echo "== 3. tamaño de la imagen"
    B=$(docker image inspect chispa-server -f '{{.Size}}')
    Z=$(docker save chispa-server | gzip -1 | wc -c)
    echo "imagen: $((B/1000000)) MB descomprimida, $((Z/1000000)) MB comprimida (objetivo <= 150 MB)" | tee "$RES/tamano.txt"
    [ "$B" -le 150000000 ] || fallo "imagen de $((B/1000000)) MB > 150 MB"
    docker history --no-trunc --format '{{.Size}}\t{{.CreatedBy}}' chispa-server | cut -c1-150 > "$RES/capas.txt"
  else
    fallo "docker build (¿compila -tags ort contra onnxruntime_go $ORT_GO_VERSION?)"
  fi
else
  echo "== 2-3. docker: saltado (CHISPA_LOCAL=1)"
fi

# --- 4. arrancar con un .chispa -------------------------------------------------------------------------------
echo "== 4. modelo y arranque $(date -u +%T)"
M=$BASE/modelos; rm -rf "$M"; mkdir -p "$M"
s3cp "$CHISPA_S3/modelos/l0l1.chispa" "$M/l0l1.chispa" 2>/dev/null || rm -f "$M/l0l1.chispa"
s3cp "$CHISPA_S3/modelos/l2.chispa" "$M/l2.chispa" 2>/dev/null || rm -f "$M/l2.chispa"
go build -o "$BASE/mkmodelo" ./deploy/mkmodelo || { fallo "go build mkmodelo"; cierre; }
PIEZAS=$(ls "$M"/l0l1.chispa "$M"/l2.chispa 2>/dev/null | paste -sd,)
if [ -z "$PIEZAS" ]; then
  echo "sin modelos en $CHISPA_S3/modelos/: modelo pequeño (L0 de testdata/injection.chispa + L1 diminuto)"
  "$BASE/mkmodelo" -l0 testdata/injection.chispa -out "$M/modelo.chispa" || { fallo "mkmodelo"; cierre; }
  ORIGEN=pequeno
elif [ "$PIEZAS" = "$M/l0l1.chispa" ] || [ "$PIEZAS" = "$M/l2.chispa" ]; then
  mv "${PIEZAS}" "$M/modelo.chispa"; ORIGEN=${PIEZAS##*/}
else
  "$BASE/mkmodelo" -unir "$PIEZAS" -out "$M/modelo.chispa" || { fallo "mkmodelo -unir"; cierre; }
  ORIGEN=l0l1+l2
fi
echo "modelo: $ORIGEN ($(stat -c %s "$M/modelo.chispa") bytes)" | tee "$RES/modelo.txt"
chmod 644 "$M/modelo.chispa"
go build -o "$BASE/carga" ./cmd/carga || { fallo "go build carga"; cierre; }

URL=http://127.0.0.1:$PUERTO
if [ "${CHISPA_LOCAL:-}" = 1 ]; then
  go build -o "$BASE/chispa-server" ./cmd/chispa-server || { fallo "go build chispa-server"; cierre; }
  "$BASE/chispa-server" -addr 127.0.0.1:$PUERTO -modelo "$M/modelo.chispa" > "$BASE/servidor.log" 2>&1 &
  SRVPID=$!
elif [ $IMAGEN = 1 ]; then
  docker run -d --name chispa -p $PUERTO:8090 -v "$M":/modelos:ro chispa-server >/dev/null || fallo "docker run"
fi
LISTO_SRV=0
if [ "${CHISPA_LOCAL:-}" = 1 ] || [ $IMAGEN = 1 ]; then
  for _ in $(seq 1 60); do curl -sf -m 2 $URL/healthz >/dev/null && { LISTO_SRV=1; break; }; sleep 1; done
  [ $LISTO_SRV = 1 ] || fallo "el servidor no responde en /healthz"
  if [ "${CHISPA_LOCAL:-}" = 1 ]; then tail -5 "$BASE/servidor.log"; else docker logs chispa 2>&1 | tail -5; fi
fi

# --- 5. contrato ------------------------------------------------------------------------------------------------
if [ $LISTO_SRV = 1 ]; then
  echo "== 5. contrato $(date -u +%T)"
  python3 -I "$REPO/server/deploy/aws/contrato.py" $URL "$REPO/server/decide/testdata" | tee "$RES/contrato.txt"
  [ "${PIPESTATUS[0]}" = 0 ] || fallo "contrato"
  curl -sf $URL/metrics > "$RES/metrics.txt"

# --- 6. decisiones/s (carga corre en la instancia; comparte CPU con el servidor) ------------------------------------
  echo "== 6. carga $(date -u +%T)"
  CD=${CHISPA_LOCAL:+3s}; CD=${CD:-15s}
  for lote in 1 16; do
    echo "-- lote=$lote c=8 d=$CD ($ORIGEN)"
    "$BASE/carga" -url $URL/v1/decide -c 8 -d $CD -lote $lote | tee -a "$RES/carga.txt" || fallo "carga lote=$lote"
  done
  parar_servidor
else
  fallo "pasos 5 y 6 saltados: no hay servidor"
fi

# --- 7. -tags ort fuera de docker ------------------------------------------------------------------------------------
if [ "${CHISPA_LOCAL:-}" = 1 ]; then
  echo "== 7. saltado (CHISPA_LOCAL=1: sin ORT)"
else
  echo "== 7. go build/test -tags ort $(date -u +%T)"
  export CGO_ENABLED=1 LD_LIBRARY_PATH=/opt/ort/lib
  if go get github.com/yalue/onnxruntime_go@$ORT_GO_VERSION && go build -tags ort ./... && go vet -tags ort ./decide; then
    echo "go build -tags ort ./...: OK"
    go test -tags ort -count=1 ./decide 2>&1 | tail -20 | tee "$RES/test-ort.txt"
    [ "${PIPESTATUS[0]}" = 0 ] || fallo "go test -tags ort ./decide"
  else
    fallo "go build -tags ort ./... (API de onnxruntime_go $ORT_GO_VERSION)"
  fi
fi
cierre
