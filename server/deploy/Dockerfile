# Imagen del servidor de Chispa con L2 vía ONNX Runtime (-tags ort).
# El contexto es la raíz del repo (o lo que saca aws/empaquetar.sh): hacen falta server/, runtime/l1/ y
# format/chispa3/ por los `replace` de server/go.mod, y gomod-proxy/ con la caché de módulos de kindling.
#   docker build -f server/deploy/Dockerfile -t chispa-server .
ARG GO_VERSION=1.27
ARG ORT_VERSION=1.22.0
# onnxruntime_go pide a la biblioteca una versión de API y una .so más nueva la cumple: ORT_GO_VERSION debe ser
# de una versión de ORT <= ORT_VERSION. Sin verificar contra una compilación real hasta la prueba en AWS.
ARG ORT_GO_VERSION=v1.19.0

FROM golang:${GO_VERSION}-bookworm AS build
ARG ORT_VERSION
ARG ORT_GO_VERSION
WORKDIR /src
# kindling sale de la caché empaquetada; el resto (onnxruntime_go) de proxy.golang.org.
COPY gomod-proxy /gomod-proxy
ENV GOPROXY=file:///gomod-proxy,https://proxy.golang.org \
    GONOSUMDB=github.com/juan52878911/* \
    GOFLAGS=-mod=mod \
    GOTOOLCHAIN=local \
    CGO_ENABLED=1
COPY format/chispa3 format/chispa3
COPY runtime/l1 runtime/l1
COPY runtime/tok runtime/tok
COPY server server
RUN curl -fsSL -o /tmp/ort.tgz \
      https://github.com/microsoft/onnxruntime/releases/download/v${ORT_VERSION}/onnxruntime-linux-x64-${ORT_VERSION}.tgz \
 && mkdir /ort && tar -xzf /tmp/ort.tgz -C /ort --strip-components=1
WORKDIR /src/server
RUN go get github.com/yalue/onnxruntime_go@${ORT_GO_VERSION} \
 && go build -tags ort -trimpath \
      -ldflags "-s -w -X github.com/juan52878911/chispa/server/decide.RutaORT=/usr/lib/libonnxruntime.so" \
      -o /out/chispa-server ./cmd/chispa-server \
 && go build -trimpath -ldflags "-s -w" -o /out/carga ./cmd/carga

# libstdc++ y libgcc que pide libonnxruntime.so, sin shell ni gestor de paquetes.
FROM gcr.io/distroless/cc-debian12:nonroot
ARG ORT_VERSION
COPY --from=build /ort/lib/libonnxruntime.so.${ORT_VERSION} /usr/lib/libonnxruntime.so
COPY --from=build /out/chispa-server /out/carga /usr/local/bin/
# Modelo: monta un .chispa en /modelos/modelo.chispa (v3, o v2 solo con L0).
EXPOSE 8090
ENTRYPOINT ["/usr/local/bin/chispa-server", "-addr", "0.0.0.0:8090"]
CMD ["-modelo", "/modelos/modelo.chispa"]
