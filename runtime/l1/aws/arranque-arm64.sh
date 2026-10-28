#!/bin/bash
CHISPA_S3=__CHISPA_S3__
# user-data de una Amazon Linux 2023 arm64 (t4g/c7g) recién creada (root): exporta el .chispa-l1, comprueba el
# hash del cuerpo, corre el test dorado de runtime/l1 y cmd/l1medir, y deja resultados.tgz y LISTO.
# El orquestador sustituye __CHISPA_S3__ por un prefijo s3://bucket/ruta y sube ahí codigo.tgz
# (bash runtime/l1/aws/empaquetar.sh); la instancia (rol con s3:GetObject y s3:PutObject, sin SSH) lo baja, y al
# terminar sube log.txt y resultados.tgz al mismo prefijo y se apaga.
# CHISPA_LOCAL=1: prueba en seco en kindling (sin dnf, pip, descargas ni shutdown; ~/go-sdk, ~/venv, ~/hf, /tmp/chispa);
# el "s3" es el directorio /tmp/chispa/s3/<prefijo sin s3://> y se copia con cp en vez de aws s3 cp.
GO_VERSION=${GO_VERSION:-1.27.1}
HASH_CUERPO=01fe1e57dc1bb1917757723e35264b146c25c4d81a3950a8ec7bb0f6a4ba8808
[ "${CHISPA_LOCAL:-}" = 1 ] || shutdown -h +60   # apagado forzoso: la instancia se termina al apagarse
set -uo pipefail
export HOME="${HOME:-/root}"

if [ "${CHISPA_LOCAL:-}" = 1 ]; then
  BASE=/tmp/chispa; VENV="$HOME/venv"; export HF_HOME="$HOME/hf"; GOROOT="$HOME/go-sdk"
else
  BASE=/opt/chispa; VENV=$BASE/venv; export HF_HOME=$BASE/hf; GOROOT=/usr/local/go
fi
mkdir -p "$BASE"
exec > >(tee -a "$BASE/log.txt") 2>&1
echo "== arranque $(date -u +%FT%TZ) local=${CHISPA_LOCAL:-0} base=$BASE arch=$(uname -m)"

export PATH="$GOROOT/bin:$PATH" GOPATH=$BASE/gopath GOCACHE=$BASE/gocache GOTOOLCHAIN=local GOPROXY=off
REPO=$BASE/repo RES=$BASE/resultados
PY=$VENV/bin/python
MODELO=$BASE/potion.chispa-l1
FALLO=""
S3LOCAL=/tmp/chispa/s3/${CHISPA_S3#s3://}

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

# Al salir, bien o mal: sube el log y, si existe, resultados.tgz; después apaga (salvo en local).
subir_y_apagar() {
  trap - EXIT
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

# --- entorno -----------------------------------------------------------------------------------------------
instalar() {
  dnf install -y python3.11 python3.11-pip tar gzip || return 1
  [ "$(uname -m)" = aarch64 ] || { echo "no es arm64: $(uname -m)"; return 1; }
  curl -fsSL "https://go.dev/dl/go${GO_VERSION}.linux-arm64.tar.gz" -o "$BASE/go.tgz" || return 1
  rm -rf /usr/local/go && tar -C /usr/local -xzf "$BASE/go.tgz" || return 1
  python3.11 -m venv "$VENV" || return 1
  "$VENV/bin/pip" install -q --no-cache-dir model2vec numpy safetensors tokenizers huggingface_hub || return 1
}
bajar() {
  "$PY" -I -c 'from huggingface_hub import snapshot_download as s; print(s("minishlab/potion-multilingual-128M", allow_patterns=["*.json","*.txt","*.safetensors"]))' || return 1
}

if [ "${CHISPA_LOCAL:-}" != 1 ]; then
  instalar || { fallo "dnf/go/venv/pip"; cierre; }
  bajar || { fallo "descarga de potion-multilingual-128M"; cierre; }
fi
go version || { fallo "sin go en $GOROOT"; cierre; }

# --- código en S3, subido por el orquestador (reintenta cada 30 s hasta 45 min) -------------------------------
echo "bajando $CHISPA_S3/codigo.tgz"
for _ in $(seq 1 90); do   # 90 × 30 s = 45 min
  s3cp "$CHISPA_S3/codigo.tgz" "$BASE/codigo.tgz" 2>/dev/null && tar -tzf "$BASE/codigo.tgz" >/dev/null 2>&1 && break
  rm -f "$BASE/codigo.tgz"
  sleep 30
done
rm -rf "$REPO"; mkdir -p "$REPO"
tar -xzf "$BASE/codigo.tgz" -C "$REPO" || { fallo "no llegó un codigo.tgz válido en 45 min"; cierre; }

# --- hardware -------------------------------------------------------------------------------------------------
mkdir -p "$RES"
uname -m | tee "$RES/uname-m.txt"
lscpu > "$RES/lscpu.txt"; nproc > "$RES/nproc.txt"
go env GOARCH GOVERSION > "$RES/go-env.txt"
if [ "${CHISPA_LOCAL:-}" != 1 ]; then   # tipo de instancia (IMDSv2); si falla, no pasa nada
  t=$(curl -sf -m 3 -X PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 60') &&
    curl -sf -m 3 -H "X-aws-ec2-metadata-token: $t" http://169.254.169.254/latest/meta-data/instance-type > "$RES/instance-type.txt"
fi
grep -E 'Model name|Architecture|^CPU\(s\)' "$RES/lscpu.txt"
df -h "$BASE" | tail -1

# --- exportar y comprobar el hash del cuerpo --------------------------------------------------------------------
L1=$REPO/runtime/l1
[ -d "$L1" ] || { fallo "no existe runtime/l1 en codigo.tgz"; cierre; }
DIR=$("$PY" -I -c 'from huggingface_hub import snapshot_download as s; print(s("minishlab/potion-multilingual-128M", allow_patterns=["*.json","*.txt","*.safetensors"], local_files_only=True))') \
  || { fallo "modelo no está en $HF_HOME"; cierre; }
echo "== exportar $(date -u +%T) desde $DIR"
"$PY" -I "$L1/exportar.py" "$DIR" "$MODELO" || { fallo "exportar.py"; cierre; }
export CHISPA_L1=$MODELO
# el cuerpo es lo que sigue a la cabecera de 256 bytes
got=$(tail -c +257 "$MODELO" | sha256sum | cut -d' ' -f1)
echo "hash del cuerpo: $got"
echo "esperado:        $HASH_CUERPO"
[ "$got" = "$HASH_CUERPO" ] && echo "HASH_CUERPO: IGUAL" || fallo "hash del cuerpo distinto en $(uname -m)"
echo "$got" > "$RES/hash-cuerpo.txt"

# --- tests y latencia -------------------------------------------------------------------------------------------
cd "$L1" || { fallo "cd $L1"; cierre; }
echo "== test dorado $(date -u +%T)"
go test -count=1 -v -run 'Hash|Dorado|Sondeo' ./... 2>&1 | tee "$RES/test-dorado.txt"
[ "${PIPESTATUS[0]}" = 0 ] && ! grep -q -- '--- SKIP' "$RES/test-dorado.txt" || fallo "go test Dorado (fallo o test saltado)"
grep -E -- '^(--- |ok|FAIL|PASS)' "$RES/test-dorado.txt"
echo "== go test ./... $(date -u +%T)"
go test -count=1 ./... 2>&1 | tee "$RES/test-todo.txt"
[ "${PIPESTATUS[0]}" = 0 ] || fallo "go test ./..."
echo "== l1medir $(date -u +%T)"
go run ./cmd/l1medir "$MODELO" 2>&1 | tee "$RES/l1medir.txt"
[ "${PIPESTATUS[0]}" = 0 ] || fallo "l1medir"
cierre
