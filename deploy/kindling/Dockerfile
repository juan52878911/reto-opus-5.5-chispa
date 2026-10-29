# Imagen de chispa-server para microVM de kindling (rootfs OCI). Contexto = raíz del repo:
#   docker buildx build --platform linux/amd64,linux/arm64 -f deploy/kindling/Dockerfile --target imagen-cpu \
#     -t chispa-server:cpu .      # sin ONNX Runtime: binario estático (CGO_ENABLED=0)
#   ... --target imagen-ort -t chispa-server:ort .   # con -tags ort: enlaza libonnxruntime.so (glibc)
# Hacen falta format/chispa3, runtime/l1, runtime/tok y server por los `replace` de server/go.mod, y gomod-proxy/
# con la caché de módulos de kindling (como server/deploy/Dockerfile). No construida aquí (sin red).
ARG GO_VERSION=1.27
ARG ORT_VERSION=1.31.1

FROM --platform=$BUILDPLATFORM golang:${GO_VERSION}-bookworm AS cpu
ARG TARGETOS TARGETARCH
WORKDIR /src
COPY gomod-proxy /gomod-proxy
ENV GOPROXY=file:///gomod-proxy,https://proxy.golang.org GONOSUMDB=github.com/juan52878911/* \
    GOFLAGS=-mod=mod GOTOOLCHAIN=local CGO_ENABLED=0
COPY format/chispa3 format/chispa3
COPY runtime/l1 runtime/l1
COPY runtime/tok runtime/tok
COPY server server
COPY deploy/kindling/sondeo deploy/kindling/sondeo
RUN cd server && GOOS=$TARGETOS GOARCH=$TARGETARCH go build -trimpath -ldflags "-s -w" -o /out/chispa-server ./cmd/chispa-server
RUN cd deploy/kindling/sondeo && GOOS=$TARGETOS GOARCH=$TARGETARCH go build -trimpath -ldflags "-s -w" -o /out/sondeo .

# ORT=1: cgo exige compilar en la plataforma destino (buildx con qemu o un builder nativo arm64).
FROM golang:${GO_VERSION}-bookworm AS ort
ARG TARGETARCH ORT_VERSION
WORKDIR /src
COPY gomod-proxy /gomod-proxy
ENV GOPROXY=file:///gomod-proxy,https://proxy.golang.org GONOSUMDB=github.com/juan52878911/* \
    GOFLAGS=-mod=mod GOTOOLCHAIN=local CGO_ENABLED=1
COPY format/chispa3 format/chispa3
COPY runtime/l1 runtime/l1
COPY runtime/tok runtime/tok
COPY server server
COPY deploy/kindling/sondeo deploy/kindling/sondeo
# Release de Microsoft: onnxruntime-linux-x64-V.tgz o onnxruntime-linux-aarch64-V.tgz.
RUN case "$TARGETARCH" in amd64) A=x64;; arm64) A=aarch64;; *) exit 1;; esac \
 && curl -fsSL -o /tmp/ort.tgz https://github.com/microsoft/onnxruntime/releases/download/v${ORT_VERSION}/onnxruntime-linux-${A}-${ORT_VERSION}.tgz \
 && mkdir /ort && tar -xzf /tmp/ort.tgz -C /ort --strip-components=1
# onnxruntime_go lo fija server/go.mod (v1.38.0); no se hace `go get` al construir.
RUN cd server && go build -tags ort -trimpath -ldflags "-s -w -X github.com/juan52878911/chispa/server/decide.RutaORT=/usr/lib/libonnxruntime.so" \
      -o /out/chispa-server ./cmd/chispa-server
RUN cd deploy/kindling/sondeo && CGO_ENABLED=0 go build -trimpath -ldflags "-s -w" -o /out/sondeo .
# libstdc++ y libgcc_s (las pide libonnxruntime.so) salen del builder: su ruta depende de la arquitectura.
RUN mkdir -p /ortlib && cp /ort/lib/libonnxruntime.so.${ORT_VERSION} /ortlib/libonnxruntime.so \
 && cp /usr/lib/*-linux-gnu/libstdc++.so.6 /usr/lib/*-linux-gnu/libgcc_s.so.1 /ortlib/

# Base con /bin/sh (entrada.sh lee las variables de entorno); usuario sin privilegios 10001.
FROM debian:bookworm-slim AS base
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin chispa \
 && mkdir /modelos && chmod 755 /modelos
COPY deploy/kindling/entrada.sh /usr/local/bin/entrada.sh
ENV CHISPA_PUERTO=8090 CHISPA_MODELO=/modelos/modelo.chispa CHISPA_TOK=/modelos/e5.chispa-tok GOMEMLIMIT=400MiB
USER 10001:10001
VOLUME /modelos
EXPOSE 8090
ENTRYPOINT ["/usr/local/bin/entrada.sh"]

FROM base AS imagen-cpu
COPY --from=cpu /out/chispa-server /out/sondeo /usr/local/bin/
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=3 CMD ["/usr/local/bin/sondeo"]

FROM base AS imagen-ort
USER root
COPY --from=ort /ortlib/ /usr/lib/chispa/
COPY --from=ort /out/chispa-server /out/sondeo /usr/local/bin/
# libonnxruntime.so debe estar en /usr/lib (RutaORT); las dos libs de C++ van junto a ella.
RUN mv /usr/lib/chispa/libonnxruntime.so /usr/lib/chispa/libstdc++.so.6 /usr/lib/chispa/libgcc_s.so.1 /usr/lib/ \
 && rmdir /usr/lib/chispa && ldconfig
# Misma ruta que el -ldflags; chispa-server la lee (CHISPA_ORT_LIB o -ort-lib) para L2 y la torre. Se puede cambiar al ejecutar.
ENV CHISPA_ORT_LIB=/usr/lib/libonnxruntime.so
USER 10001:10001
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=3 CMD ["/usr/local/bin/sondeo"]
