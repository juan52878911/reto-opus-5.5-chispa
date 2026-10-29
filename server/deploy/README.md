# Imagen OCI de chispa-server (T4.4)

`Dockerfile` multietapa: `golang:1.27-bookworm` compila `chispa-server -tags ort` (cgo, `onnxruntime_go`) y la
imagen final es `gcr.io/distroless/cc-debian12:nonroot` + `libonnxruntime.so` de la release oficial de ORT +
los binarios `chispa-server` y `carga`. Versiones fijadas en `ARG`: `GO_VERSION` (1.27), `ORT_VERSION` (1.22.0) y
`ORT_GO_VERSION` (v1.19.0, de `github.com/yalue/onnxruntime_go`; hay que mantenerlo en una API ≤ `ORT_VERSION`).
La ruta de la `.so` entra con `-ldflags -X …/decide.RutaORT=/usr/lib/libonnxruntime.so`.
Objetivo: ≤ 150 MB (estimado ~60 MB; **sin medir**: aquí no hay docker, lo mide `arranque.sh` en AWS).

## Construir
El contexto necesita `server/`, `runtime/l1/`, `format/chispa3/` (los `replace` de `server/go.mod`) y `gomod-proxy/`,
la caché de módulos de `kindling` (`bash server/deploy/aws/empaquetar.sh > codigo.tgz` lo prepara todo):
```
mkdir ctx && tar -xzf codigo.tgz -C ctx
docker build -f ctx/server/deploy/Dockerfile --build-arg ORT_VERSION=1.22.0 -t chispa-server ctx
```
Hace falta red (descarga ORT de GitHub y `onnxruntime_go` de proxy.golang.org).

## Usar
```
docker run --rm --stop-timeout 40 -p 8090:8090 -v /ruta/modelos:/modelos:ro -v /ruta/config.json:/etc/chispa/config.json:ro \
  chispa-server -modelo /modelos/modelo.chispa -config /etc/chispa/config.json   # producción: config con api_keys (cada una con rps > 0)
docker run --rm --stop-timeout 40 -p 8090:8090 -v /ruta/modelos:/modelos:ro chispa-server -abierto   # SOLO pruebas: sin autenticación
# La imagen drena con -apagado 35s (>= -timeout 30s): la gracia de parada debe ser >= 40 s (--stop-timeout 40; en Kubernetes terminationGracePeriodSeconds: 40).
curl -s localhost:8090/healthz
curl -s localhost:8090/v1/decide -d @server/decide/testdata/choice.req.json
```
`CMD` es `-modelo /modelos/modelo.chispa` (un `.chispa` v3, o v2 con solo L0); se puede sustituir por `-config …`.
Contrato y endpoints: `server/README.md`. `carga` va en la imagen (`--entrypoint carga`).

## Limitaciones
- **L2 responde si se pasa `-tok`** (`.chispa-tok` de e5, `runtime/tok/exportar.py`; `main.go`); sin él, L2 queda en stub.
  Otros flags: `-addr`, `-config`, `-modelo` y `-timeout` (tope por petición, 30 s por defecto; responde 503; 0 = sin tope). `chispa-server` solo admite un `-modelo`;
  `arranque.sh` fusiona `l0l1.chispa` y `l2.chispa` con `deploy/mkmodelo -unir` (gana el primero si repiten sección).
- `go build -tags ort` está **sin compilar**: `l2_ort.go` se escribió de memoria contra `onnxruntime_go`. La prueba
  en AWS lo decide; si falla, `FALLO` en el log lo dice con el error del compilador.
- Nix: `nix build ./nix#chispa-server` (variante sin cgo ni ORT). No probado (sin nix aquí); `vendorHash` es un marcador.

## Prueba en AWS (`aws/`)
- `empaquetar.sh` → `codigo.tgz` (a `$CHISPA_S3/codigo.tgz`). Opcionales: `$CHISPA_S3/modelos/l0l1.chispa` y `l2.chispa`, por fichero.
- `arranque.sh` es el user-data de una Amazon Linux 2023 x86_64 (c6a.xlarge): sustituir `__CHISPA_S3__` por `s3://bucket/ruta`.
  Rol con `s3:GetObject`/`s3:PutObject`. Apagado a los 90 min; al salir sube `log.txt` y `resultados.tgz`.
  Pasos: docker + Go + ORT → `docker build` → tamaño (`tamano.txt`) → arranque con el modelo → 20 peticiones de contrato
  (`contrato.py`: 18 a `/v1/decide`, `/healthz`, `/metrics`) → `carga` lote 1 y 16 (`carga.txt`) → `go build/test -tags ort` fuera de docker.
- `CHISPA_LOCAL=1`: prueba en seco sin docker ni ORT (pasos 4 a 6, binario nativo sin etiqueta).
- `mkmodelo`: genera el `.chispa` pequeño de reserva (L0 de `testdata` + L1 diminuto) y fusiona ficheros.
