#!/bin/bash
CHISPA_S3=__CHISPA_S3__
# user-data de una Amazon Linux 2023 x86_64 recién creada (root; pide ≥ 30 GB de disco y ≥ 4 vCPU/8 GB, p. ej. c7i.xlarge):
# instala JDK 17, Android cmdline-tools, SDK 34, NDK, Go y gomobile; construye el AAR de sdk/movil/chispamovil
# (gomobile bind -target=android), corre `./gradlew test assembleDebug` en sdk/android y sube el AAR, el APK y los
# informes de test.
# El orquestador sustituye __CHISPA_S3__ por un prefijo s3://bucket/ruta y sube ahí codigo.tgz
# (bash sdk/android/aws/empaquetar.sh); la instancia (rol con s3:GetObject y s3:PutObject, sin SSH) lo baja, y al
# terminar sube log.txt y resultados.tgz al mismo prefijo y se apaga.
# CHISPA_LOCAL=1: prueba en seco en kindling (sin dnf, descargas, NDK, Gradle ni shutdown; ~/go-sdk): corre solo
# los pasos de Go (go test, go vet con GOOS=android/arm64) y deja LISTO; el "s3" es /tmp/chispa/s3/<prefijo sin s3://>.
GO_VERSION=${GO_VERSION:-1.27.1}
GRADLE_VERSION=${GRADLE_VERSION:-8.9}
CMDLINE_TOOLS=${CMDLINE_TOOLS:-11076708}        # commandlinetools-linux-<n>_latest.zip
NDK_VERSION=${NDK_VERSION:-26.1.10909125}
ANDROID_API=24                                  # minSdk de la biblioteca y de gomobile -androidapi
[ "${CHISPA_LOCAL:-}" = 1 ] || shutdown -h +120   # apagado forzoso: la instancia se termina al apagarse
set -uo pipefail
export HOME="${HOME:-/root}"

if [ "${CHISPA_LOCAL:-}" = 1 ]; then
  BASE=/tmp/chispa-android; GOROOT="$HOME/go-sdk"
else
  BASE=/opt/chispa; GOROOT=/usr/local/go
fi
mkdir -p "$BASE"
exec > >(tee -a "$BASE/log.txt") 2>&1
echo "== arranque $(date -u +%FT%TZ) local=${CHISPA_LOCAL:-0} base=$BASE arch=$(uname -m)"

export ANDROID_HOME=$BASE/android-sdk ANDROID_SDK_ROOT=$BASE/android-sdk
export ANDROID_NDK_HOME=$ANDROID_HOME/ndk/$NDK_VERSION
export GOPATH=$BASE/gopath GOCACHE=$BASE/gocache GOTOOLCHAIN=local GOFLAGS=-mod=mod GONOSUMDB='github.com/juan52878911/*'
export PATH="$GOROOT/bin:$GOPATH/bin:$BASE/gradle/bin:$ANDROID_HOME/cmdline-tools/latest/bin:$PATH"
REPO=$BASE/repo RES=$BASE/resultados
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

# Al salir, bien o mal: sube el log, resultados.tgz y, si existen, el AAR y el APK (cada uno por separado); apaga.
subir_y_apagar() {
  trap - EXIT
  sleep 1   # deja que tee vacíe el log
  s3cp "$BASE/log.txt" "$CHISPA_S3/log.txt" || echo "no se pudo subir log.txt"
  [ -f "$BASE/resultados.tgz" ] && { s3cp "$BASE/resultados.tgz" "$CHISPA_S3/resultados.tgz" || echo "no se pudo subir resultados.tgz"; }
  for f in chispamovil.aar chispa-demo-debug.apk; do
    [ -f "$RES/$f" ] && { s3cp "$RES/$f" "$CHISPA_S3/$f" || echo "no se pudo subir $f"; }
  done
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

# --- 1. entorno: JDK 17, cmdline-tools, SDK 34, NDK, Go, Gradle ------------------------------------------------------
instalar() {
  [ "$(uname -m)" = x86_64 ] || { echo "no es x86_64: $(uname -m)"; return 1; }
  dnf install -y java-17-amazon-corretto-devel unzip tar gzip which || return 1
  curl -fsSL "https://go.dev/dl/go${GO_VERSION}.linux-amd64.tar.gz" -o "$BASE/go.tgz" || return 1
  rm -rf /usr/local/go && tar -C /usr/local -xzf "$BASE/go.tgz" || return 1
  curl -fsSL "https://dl.google.com/android/repository/commandlinetools-linux-${CMDLINE_TOOLS}_latest.zip" -o "$BASE/cmdline.zip" || return 1
  mkdir -p "$ANDROID_HOME/cmdline-tools" && unzip -q -o "$BASE/cmdline.zip" -d "$ANDROID_HOME/cmdline-tools" || return 1
  rm -rf "$ANDROID_HOME/cmdline-tools/latest" && mv "$ANDROID_HOME/cmdline-tools/cmdline-tools" "$ANDROID_HOME/cmdline-tools/latest" || return 1
  yes | sdkmanager --licenses >/dev/null 2>&1
  sdkmanager "platform-tools" "platforms;android-34" "build-tools;34.0.0" "ndk;${NDK_VERSION}" || return 1
  curl -fsSL "https://services.gradle.org/distributions/gradle-${GRADLE_VERSION}-bin.zip" -o "$BASE/gradle.zip" || return 1
  unzip -q -o "$BASE/gradle.zip" -d "$BASE" && rm -rf "$BASE/gradle" && mv "$BASE/gradle-${GRADLE_VERSION}" "$BASE/gradle" || return 1
}
if [ "${CHISPA_LOCAL:-}" != 1 ]; then
  echo "== 1. instalar $(date -u +%T)"
  instalar || { fallo "instalación (dnf/Go/SDK/NDK/Gradle)"; cierre; }
fi
go version || { fallo "sin go en $GOROOT"; cierre; }

# --- código en S3, subido por el orquestador (reintenta cada 30 s hasta 45 min) ---------------------------------------
echo "bajando $CHISPA_S3/codigo.tgz"
for _ in $(seq 1 90); do   # 90 × 30 s = 45 min
  s3cp "$CHISPA_S3/codigo.tgz" "$BASE/codigo.tgz" 2>/dev/null && tar -tzf "$BASE/codigo.tgz" >/dev/null 2>&1 && break
  rm -f "$BASE/codigo.tgz"
  sleep 30
done
rm -rf "$REPO"; mkdir -p "$REPO"
tar -xzf "$BASE/codigo.tgz" -C "$REPO" || { fallo "no llegó un codigo.tgz válido en 45 min"; cierre; }
mkdir -p "$RES"
{ uname -m; lscpu; echo "nproc: $(nproc)"; go env GOARCH GOVERSION; } > "$RES/hardware.txt" 2>&1
if [ "${CHISPA_LOCAL:-}" != 1 ]; then
  t=$(curl -sf -m 3 -X PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 60') &&
    curl -sf -m 3 -H "X-aws-ec2-metadata-token: $t" http://169.254.169.254/latest/meta-data/instance-type > "$RES/instance-type.txt"
fi
df -h "$BASE" | tail -1

# kindling sale de gomod-proxy/ del tgz; x/mobile y el resto, de proxy.golang.org (en local, sin red: solo gomod-proxy/)
if [ "${CHISPA_LOCAL:-}" = 1 ]; then export GOPROXY=file://$REPO/gomod-proxy; else export GOPROXY=file://$REPO/gomod-proxy,https://proxy.golang.org; fi

# --- 2. pruebas de Go y gomobile bind --------------------------------------------------------------------------------
MOVIL=$REPO/sdk/movil/chispamovil
AND=$REPO/sdk/android
cd "$MOVIL" || { fallo "no existe sdk/movil/chispamovil en codigo.tgz"; cierre; }
# Paridad del tokenizador de e5 (TestTokenizarE5ParidadConRuntimeTok): necesita el .chispa-tok de runtime/tok/exportar.py
# (tokenizer.json de Hugging Face + numpy y safetensors). Si no se puede construir, el test se salta y se avisa.
if [ "${CHISPA_LOCAL:-}" != 1 ]; then
  echo "== 2-tok. .chispa-tok de e5 $(date -u +%T)"
  mkdir -p "$BASE/e5"
  { python3 -m pip install --quiet numpy safetensors &&
    curl -fsSL -m 120 -o "$BASE/e5/tokenizer.json" https://huggingface.co/intfloat/multilingual-e5-small/resolve/main/tokenizer.json &&
    python3 "$REPO/runtime/tok/exportar.py" "$BASE/e5" "$BASE/e5.chispa-tok"; } 2>&1 | tail -3
  [ -s "$BASE/e5.chispa-tok" ] && export CHISPA_TOK="$BASE/e5.chispa-tok" || echo "AVISO: sin .chispa-tok; se salta la paridad del tokenizador"
fi
echo "== 2a. go test ./... $(date -u +%T)"
go test -count=1 -v ./... 2>&1 | tee "$RES/go-test-chispamovil.txt"
[ "${PIPESTATUS[0]}" = 0 ] || fallo "go test de chispamovil"
grep -E -- '^(--- |ok|FAIL|PASS)' "$RES/go-test-chispamovil.txt"
# TestMismaHuellaQueDemoWasm necesita el L1 recortado (no viaja en codigo.tgz): saltarlo no es un fallo, pero se avisa
grep -q -- '--- SKIP' "$RES/go-test-chispamovil.txt" && echo "AVISO: hay tests de Go saltados: $(grep -- '--- SKIP' "$RES/go-test-chispamovil.txt" | tr '\n' ' ')"
echo "== 2b. go vet GOOS=android GOARCH=arm64 $(date -u +%T)"
GOOS=android GOARCH=arm64 go vet ./... 2>&1 | tee "$RES/go-vet-android.txt"
[ "${PIPESTATUS[0]}" = 0 ] || fallo "go vet android/arm64"

if [ "${CHISPA_LOCAL:-}" = 1 ]; then
  echo "== local: sin gomobile, NDK ni Gradle"
  cierre
fi

echo "== 2c. gomobile $(date -u +%T)"
go get golang.org/x/mobile@latest 2>&1 | tail -3 || true
go install golang.org/x/mobile/cmd/gomobile@latest golang.org/x/mobile/cmd/gobind@latest || { fallo "go install gomobile"; cierre; }
gomobile init || { fallo "gomobile init"; cierre; }
mkdir -p "$AND/chispa/libs"
gomobile bind -v -target=android/arm64,android/amd64 -androidapi "$ANDROID_API" -o "$AND/chispa/libs/chispamovil.aar" . \
  || { fallo "gomobile bind -target=android"; cierre; }
ls -l "$AND/chispa/libs/chispamovil.aar" | tee "$RES/aar-tamano.txt"
unzip -l "$AND/chispa/libs/chispamovil.aar" > "$RES/aar-contenido.txt"
cp "$AND/chispa/libs/chispamovil.aar" "$RES/chispamovil.aar"

# --- 3. Gradle ---------------------------------------------------------------------------------------------------------
echo "== 3. gradle $(date -u +%T)"
cd "$AND" || { fallo "no existe sdk/android"; cierre; }
echo "sdk.dir=$ANDROID_HOME" > local.properties
gradle --no-daemon wrapper --gradle-version "$GRADLE_VERSION" || { fallo "gradle wrapper"; cierre; }
./gradlew --no-daemon --console=plain test assembleDebug 2>&1 | tee "$RES/gradle.txt"
[ "${PIPESTATUS[0]}" = 0 ] || fallo "./gradlew test assembleDebug"

# --- 4. resultados -------------------------------------------------------------------------------------------------------
echo "== 4. recoger $(date -u +%T)"
APK=$(find "$AND/demo/build/outputs/apk/debug" -name '*.apk' 2>/dev/null | head -1)
[ -n "$APK" ] && cp "$APK" "$RES/chispa-demo-debug.apk" && ls -l "$RES/chispa-demo-debug.apk" || fallo "no hay APK de demo"
[ -d "$AND/chispa/build/reports/tests" ] && cp -R "$AND/chispa/build/reports/tests" "$RES/informe-tests"
[ -d "$AND/chispa/build/test-results" ] && cp -R "$AND/chispa/build/test-results" "$RES/test-results"
n=$(grep -ho 'tests="[0-9]*"' "$RES"/test-results/*/*.xml 2>/dev/null | tr -dc '0-9\n' | awk '{s+=$1} END {print s+0}')
echo "tests JVM ejecutados: ${n:-0}"
[ "${n:-0}" -gt 0 ] || fallo "Gradle no ejecutó ningún test JVM"
cierre
