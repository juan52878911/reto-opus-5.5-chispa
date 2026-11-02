#!/bin/bash
# user-data de una Amazon Linux 2023 arm64 (Graviton, p. ej. c7g.large spot): corre en arm64 nativo los dorados de
# determinismo (BD) y los tests de chispamovil, para comparar con amd64 dentro de las tolerancias de
# docs/07-rendimiento-y-limites.md (sección Determinismo). Los propios tests comparan con testdata/dorados/esperado.json y
# ort.json, generados en amd64: si pasan, arm64 da lo mismo que amd64.
# El orquestador sustituye __CHISPA_S3__ y sube codigo.tgz (model/bench/torre/empaquetar.sh); al terminar sube log.txt,
# estado.tsv y resultados.tgz al mismo prefijo y se apaga.
set -u
CHISPA_S3=__CHISPA_S3__
GO_VERSION=1.27.1; ORT_VERSION=1.31.1
BASE=/opt/chispa REPO=/opt/chispa/repo RES=/opt/chispa/resultados
mkdir -p "$REPO" "$RES"; exec > >(tee -a "$RES/log.txt") 2>&1
shutdown -h +30
T0=$(date +%s)
estado() { printf '%s\t%s\n' "$1" "$2" >> "$RES/estado.tsv"; echo "[$1] $2"; }
cierre() {
  echo "== listo $(date -u +%FT%TZ) ($(( $(date +%s) - T0 )) s)"
  tar -czf "$BASE/resultados.tgz" -C "$BASE" resultados
  for f in log.txt estado.tsv; do aws s3 cp --only-show-errors "$RES/$f" "$CHISPA_S3/$f"; done
  aws s3 cp --only-show-errors "$BASE/resultados.tgz" "$CHISPA_S3/resultados.tgz"
  shutdown -h now; exit 0
}
echo "== arranque $(date -u +%FT%TZ) arch=$(uname -m)"
{ lscpu; nproc; } > "$RES/hardware.txt"
dnf install -y -q gcc tar gzip || { estado instalar "FALLO dnf"; cierre; }
curl -fsSL "https://go.dev/dl/go${GO_VERSION}.linux-arm64.tar.gz" | tar -xzC /usr/local || { estado instalar "FALLO Go"; cierre; }
mkdir -p /opt/ort && curl -fsSL "https://github.com/microsoft/onnxruntime/releases/download/v${ORT_VERSION}/onnxruntime-linux-aarch64-${ORT_VERSION}.tgz" \
  | tar -xzC /opt/ort --strip-components=1 || { estado instalar "FALLO ORT aarch64"; cierre; }
export PATH=/usr/local/go/bin:$PATH HOME=/root GOPATH=/root/go GOCACHE=/root/.cache/go-build CGO_ENABLED=1
export LD_LIBRARY_PATH=/opt/ort/lib CHISPA_ORT_LIB=/opt/ort/lib/libonnxruntime.so.${ORT_VERSION}
estado instalar "OK go $(go version | cut -d' ' -f3) ort $ORT_VERSION"
for i in $(seq 1 60); do aws s3 cp --only-show-errors "$CHISPA_S3/codigo.tgz" "$BASE/codigo.tgz" && break; sleep 30; done
tar -xzf "$BASE/codigo.tgz" -C "$REPO" || { estado codigo "FALLO sin codigo.tgz"; cierre; }
export GOPROXY=file://$REPO/gomod-proxy,https://proxy.golang.org GOFLAGS=-mod=mod
cd "$REPO/server" || { estado codigo "FALLO sin server/"; cierre; }
paso() {   # clave comando...: corre, guarda la salida y anota OK/FALLO con el resumen de go test
  local k=$1; shift
  "$@" > "$RES/$k.txt" 2>&1; local rc=$?
  local ok=$(grep -c -- '^--- PASS' "$RES/$k.txt"); local ko=$(grep -c -- '^--- FAIL' "$RES/$k.txt")
  [ $rc = 0 ] && estado "$k" "OK $ok PASS" || estado "$k" "FALLO rc=$rc $ok PASS $ko FAIL: $(grep -m3 -- '--- FAIL' "$RES/$k.txt" | tr '\n' ' ' | cut -c1-200)"
}
paso dorados go test -count=1 -v ./decide -run 'Dorados'
paso dorados_ort go test -count=1 -v -tags ort ./decide -run 'DoradosORT'
paso concurrencia go test -count=1 -v ./decide -run 'Concurrencia'
paso decide_todo go test -count=1 ./decide/...
cd "$REPO/sdk/movil/chispamovil" && paso chispamovil go test -count=1 -v ./...
cierre
