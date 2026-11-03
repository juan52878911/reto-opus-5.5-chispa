# Compilación del SDK de Android y del APK de demo en un contenedor (linux/amd64: aapt2 solo existe para x86_64; en un Mac
# con Apple Silicon corre con Rosetta). Misma receta y versiones que sdk/android/aws/arranque.sh.
#   docker build --platform linux/amd64 -t chispa-android sdk/android/docker
#   bash sdk/android/docker/compilar.sh       # ver ese script
FROM --platform=linux/amd64 eclipse-temurin:17-jdk
ARG GO_VERSION=1.27.1
ARG GRADLE_VERSION=8.9
ARG CMDLINE_TOOLS=11076708
ARG NDK_VERSION=26.1.10909125
ENV ANDROID_HOME=/opt/android-sdk ANDROID_SDK_ROOT=/opt/android-sdk GOROOT=/usr/local/go GOPATH=/cache/go \
    GRADLE_USER_HOME=/cache/gradle GOFLAGS=-buildvcs=false
ENV PATH=/usr/local/go/bin:/cache/go/bin:/opt/gradle/bin:/opt/android-sdk/cmdline-tools/latest/bin:/opt/android-sdk/platform-tools:$PATH
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends unzip curl ca-certificates git python3 && rm -rf /var/lib/apt/lists/*
# tar de GNU falla bajo la emulación amd64 de Docker Desktop («Function not implemented» en algunos ficheros): se extrae con Python
RUN curl -fsSL -o /tmp/go.tgz "https://go.dev/dl/go${GO_VERSION}.linux-amd64.tar.gz" \
 && python3 -c "import tarfile; tarfile.open('/tmp/go.tgz').extractall('/usr/local', filter='tar')" && rm /tmp/go.tgz
RUN mkdir -p $ANDROID_HOME/cmdline-tools && curl -fsSL -o /tmp/c.zip "https://dl.google.com/android/repository/commandlinetools-linux-${CMDLINE_TOOLS}_latest.zip" \
 && unzip -q /tmp/c.zip -d $ANDROID_HOME/cmdline-tools && mv $ANDROID_HOME/cmdline-tools/cmdline-tools $ANDROID_HOME/cmdline-tools/latest && rm /tmp/c.zip \
 && yes | sdkmanager --licenses >/dev/null 2>&1; sdkmanager "platform-tools" "platforms;android-34" "build-tools;34.0.0" "ndk;${NDK_VERSION}" >/dev/null
RUN curl -fsSL -o /tmp/g.zip "https://services.gradle.org/distributions/gradle-${GRADLE_VERSION}-bin.zip" && unzip -q /tmp/g.zip -d /opt \
 && mv /opt/gradle-${GRADLE_VERSION} /opt/gradle && rm /tmp/g.zip
ENV ANDROID_NDK_HOME=/opt/android-sdk/ndk/${NDK_VERSION}
WORKDIR /src
