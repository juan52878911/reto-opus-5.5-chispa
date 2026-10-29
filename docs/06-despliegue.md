# Despliegue

`chispa-server` es un binario de Go. L0, L1 y los stubs corren sin nada más. L2 y L2c necesitan ONNX Runtime y un tokenizador.

## Compilar
| Variante | Comando | Capas |
|---|---|---|
| Sin ORT | `cd server && go build ./cmd/chispa-server` | L0 y L1; L2 en stub |
| Con ORT | `cd server && go build -tags ort ./cmd/chispa-server` | L0, L1, L2 y L2c |

- `-tags ort` necesita cgo, `libonnxruntime.so` (1.17 o más nueva) y el módulo `github.com/yalue/onnxruntime_go`.
  La ruta de la `.so` se fija con `-ldflags -X …/decide.RutaORT=/ruta/libonnxruntime.so`.
- Sin red: `GOFLAGS=-mod=mod GOPROXY=off`, con la caché de módulos ya llena ([`server/Makefile`](../server/Makefile)).
- Los módulos locales (`format/chispa3`, `runtime/l1`) entran por `replace` en `server/go.mod`.
- `-tags ort` compila con `onnxruntime_go v1.19.0` y ORT 1.22.0 ([`server/README.md`](../server/README.md#t45-tokenizador-de-e5-en-go-simproto-entero-y-e2e)).

## Flags
De [`main.go`](../server/cmd/chispa-server/main.go):

| Flag | Qué hace |
|---|---|
| `-addr` | dirección de escucha; por defecto `127.0.0.1:8090` |
| `-modelo` | un `.chispa` v3 (o v2) del que armar las capas |
| `-config` | JSON con capas, τ, modelos y cachés ([03-api.md](03-api.md#configuración--config)) |
| `-tok` | `.chispa-tok` de e5; sin él, L2 queda en stub aunque se compile con `ort` |

## El tokenizador `-tok`
L2 recibe ids de e5. El tokenizador está en Go puro ([`runtime/tok`](../runtime/tok/README.md)) y lee un `.chispa-tok`.

```
python runtime/tok/exportar.py <directorio-del-modelo-e5> e5.chispa-tok      # 12 MB, no va a git
chispa-server -modelo modelo.chispa -tok e5.chispa-tok
```

Usa el mismo tokenizador de e5 con que se entrenó el modelo.

## Imagen OCI
[`server/deploy/Dockerfile`](../server/deploy/Dockerfile), multietapa:

1. `golang:1.27-bookworm` compila `chispa-server -tags ort`.
2. La imagen final es `gcr.io/distroless/cc-debian12:nonroot` con `libonnxruntime.so` y los binarios `chispa-server` y `carga`.

Versiones en `ARG`: `GO_VERSION` 1.27, `ORT_VERSION` 1.22.0 y `ORT_GO_VERSION` v1.19.0. Mantén `ORT_GO_VERSION` en una API ≤ `ORT_VERSION`.

```
bash server/deploy/aws/empaquetar.sh > codigo.tgz      # server/, runtime/l1, format/chispa3 y la caché de módulos
mkdir ctx && tar -xzf codigo.tgz -C ctx
docker build -f ctx/server/deploy/Dockerfile --build-arg ORT_VERSION=1.22.0 -t chispa-server ctx
docker run --rm -p 8090:8090 -v /ruta/modelos:/modelos:ro chispa-server
```

- `ENTRYPOINT` es `chispa-server -addr 0.0.0.0:8090`. `CMD` es `-modelo /modelos/modelo.chispa`. Sustitúyelo para añadir `-tok` o `-config`.
- La imagen no lleva el `.chispa-tok`: móntalo en `/modelos` y pasa `-tok /modelos/e5.chispa-tok`.
- Hace falta red al construir: descarga ORT de GitHub y `onnxruntime_go` de proxy.golang.org.
- El objetivo de tamaño es ≤ 150 MB. **No hay medida de la imagen en el repo.**
  Ver [`server/deploy/README.md`](../server/deploy/README.md).
- Nix: `nix build ./nix#chispa-server` (sin cgo ni ORT). Sin probar.

## Un solo `-modelo`
Si tienes `l0l1.chispa` y `l2.chispa` por separado, únelos con `cd server && go run ./deploy/mkmodelo -unir l0l1.chispa,l2.chispa -out modelo.chispa`. Gana el primero si repiten sección.

## El patrón de AWS
Todo lo medido de punta a punta corrió así, en una c6a.xlarge (spot):

1. `empaquetar.sh` → `codigo.tgz` en `$CHISPA_S3`.
2. `arranque.sh` es el user-data de una Amazon Linux 2023 x86_64. Sustituye `__CHISPA_S3__` por `s3://bucket/ruta`.
3. La instancia necesita un rol con `s3:GetObject` y `s3:PutObject`.
4. Instala docker, Go y ORT; construye la imagen; arranca con el modelo; lanza 20 peticiones de contrato
   (`contrato.py`: 18 a `/v1/decide`, `/healthz` y `/metrics`); corre `carga` con lotes de 1 y de 16.
5. Se apaga a los 90 minutos. Al salir sube `log.txt` y `resultados.tgz` a S3.

Prueba en seco, sin docker ni ORT: `CHISPA_LOCAL=1`. La prueba de punta a punta con modelos es `server/deploy/aws/e2e.sh`
(`empaquetar_e2e.sh > codigo.tgz`; pasos en la cabecera del script).

## Observabilidad
Usa `/healthz` como sonda de vida y `/metrics` para Prometheus. Vigila `chispa_escalados_total` frente a `chispa_preguntas_total`
([03-api.md](03-api.md#get-metrics)) y `chispa_capa_errores_total`.
