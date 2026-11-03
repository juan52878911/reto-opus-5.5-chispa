#!/usr/bin/env bash
# Compila chispamovil.aar (gomobile) y el APK de demo en el contenedor `chispa-android` (ver Dockerfile), con las cachés de
# Gradle y Go en el volumen con nombre `chispa-android-cache`. El código entra como el paquete de sdk/android/aws/empaquetar.sh
# (con gomod-proxy), extraído en un directorio temporal: el árbol de trabajo no se toca.
#   bash sdk/android/docker/compilar.sh SALIDA_DIR        → SALIDA_DIR/{chispa-demo-debug.apk, chispamovil.aar, gradle.txt}
set -euo pipefail
RAIZ=$(cd "$(dirname "$0")/../../.." && pwd)
SALIDA=$(mkdir -p "${1:?uso: compilar.sh SALIDA_DIR}" && cd "$1" && pwd)
SRC=$(mktemp -d)
trap 'rm -rf "$SRC"' EXIT
( cd "$RAIZ" && COPYFILE_DISABLE=1 bash sdk/android/aws/empaquetar.sh ) | tar -xz -C "$SRC"
docker image inspect chispa-android >/dev/null 2>&1 || docker build --platform linux/amd64 -t chispa-android "$RAIZ/sdk/android/docker"
docker run --rm --platform linux/amd64 --name chispa-android-compilar -v chispa-android-cache:/cache -v "$SRC":/src -v "$SALIDA":/salida \
  chispa-android bash -euo pipefail -c '
    export GOPROXY=file:///src/gomod-proxy,https://proxy.golang.org
    cd /src/sdk/movil/chispamovil
    go install golang.org/x/mobile/cmd/gomobile@latest golang.org/x/mobile/cmd/gobind@latest
    gomobile init
    mkdir -p /src/sdk/android/chispa/libs
    gomobile bind -target=android/arm64,android/amd64 -androidapi 24 -o /src/sdk/android/chispa/libs/chispamovil.aar .
    cd /src/sdk/android && echo "sdk.dir=$ANDROID_HOME" > local.properties
    gradle --no-daemon -q wrapper --gradle-version 8.9
    ./gradlew --no-daemon --console=plain test assembleDebug 2>&1 | tee /salida/gradle.txt
    cp /src/sdk/android/chispa/libs/chispamovil.aar /salida/
    cp "$(find /src/sdk/android/demo/build/outputs/apk/debug -name "*.apk" | head -1)" /salida/chispa-demo-debug.apk'
ls -la "$SALIDA"
