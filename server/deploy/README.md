# Imagen OCI de chispa-server (T4.4)

`Dockerfile` multietapa: `golang:1.27-bookworm` compila `chispa-server -tags ort` (cgo, `onnxruntime_go`) y la
imagen final es `gcr.io/distroless/cc-debian12:nonroot` + `libonnxruntime.so` de la release oficial de ORT +
los binarios `chispa-server` y `carga`. Versiones fijadas en `ARG`: `GO_VERSION` (1.27), `ORT_VERSION` (1.31.1; `onnxruntime_go` lo fija `server/go.mod`, v1.38.0). Bases por digest y SHA-256 del `.tgz` de ORT x64 (`c849e36a…bdc9`) fijados en los `ARG`; el build los verifica.
La ruta de la `.so` entra con `-ldflags -X …/decide.RutaORT=/usr/lib/libonnxruntime.so`.
Construida y arrancada con Docker 29 (amd64): 98.8 MB en disco, `/healthz` 200 y decisión zero-shot con `server/testdata/intencion.chispa`. Solo variante `-tags ort`; la de CPU sin cgo es el destino `imagen-cpu` de `deploy/kindling/Dockerfile`.

## Construir
El contexto necesita `server/`, `runtime/l1/`, `format/chispa3/` (los `replace` de `server/go.mod`) y `gomod-proxy/`,
la caché de módulos de `kindling` (`bash server/deploy/aws/empaquetar.sh > codigo.tgz` lo prepara todo):
```
mkdir ctx && tar -xzf codigo.tgz -C ctx
docker build -f ctx/server/deploy/Dockerfile -t chispa-server ctx
```
`empaquetar.sh` solo copia kindling a `gomod-proxy/`: el build también necesita `onnxruntime_go` v1.38.0; si falta, copia `$(go env GOMODCACHE)/cache/download/github.com` entero (sin `*.lock`) en `ctx/gomod-proxy/`. Así se construyó aquí, con `docker build -f server/deploy/Dockerfile -t chispa-server .` desde un contexto con `gomod-proxy/`.
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

## Varias preguntas few-shot + L2 de servidor

`-modelo servidor.chispa` (L0+L2+TORR+CALIB) y, en `-config`, `"modelos": ["colocacion.chispa", "riesgo.chispa", "completa.chispa"]` (v3 solo-L0 o v1/v2). Solo se usa el L0 de cada uno:
**la calibración es la del `-modelo`** (CALIB, SOPL1 y demás se ignoran con un aviso por fichero al arrancar); si traen L1, L2 o TORR el arranque falla; dos L0 con las mismas etiquetas (el del `-modelo` incluido) también, con un error que nombra los dos ficheros.
Detalle: `docs/06-despliegue.md`.

## Limitaciones
- **L2 responde si se pasa `-tok`** (`.chispa-tok` de e5, `runtime/tok/exportar.py`; `main.go`); sin él, L2 queda en stub.
  Otros flags: `-addr`, `-config`, `-modelo` y `-timeout` (tope por petición, 30 s por defecto; responde 503; 0 = sin tope). `chispa-server` solo admite un `-modelo`;
  `arranque.sh` fusiona `l0l1.chispa` y `l2.chispa` con `deploy/mkmodelo -unir` (gana el primero si repiten sección).
- `go build -tags ort` compila en la imagen (verificado en Docker local); L2 real con modelo e5 sin probar en contenedor.
- Nix: `nix build ./nix#chispa-server` (variante sin cgo ni ORT). No probado (sin nix aquí); `vendorHash` es un marcador.

## Prueba en AWS (`aws/`)
- `empaquetar.sh` → `codigo.tgz` (a `$CHISPA_S3/codigo.tgz`). Opcionales: `$CHISPA_S3/modelos/l0l1.chispa` y `l2.chispa`, por fichero.
- `arranque.sh` es el user-data de una Amazon Linux 2023 x86_64 (c6a.xlarge): sustituir `__CHISPA_S3__` por `s3://bucket/ruta`.
  Rol con `s3:GetObject`/`s3:PutObject`. Apagado a los 90 min; al salir sube `log.txt` y `resultados.tgz`.
  Pasos: docker + Go + ORT → `docker build` → tamaño (`tamano.txt`) → arranque con el modelo → 20 peticiones de contrato
  (`contrato.py`: 18 a `/v1/decide`, `/healthz`, `/metrics`) → `carga` lote 1 y 16 (`carga.txt`) → `go build/test -tags ort` fuera de docker.
- `CHISPA_LOCAL=1`: prueba en seco sin docker ni ORT (pasos 4 a 6, binario nativo sin etiqueta).
- `mkmodelo`: genera el `.chispa` pequeño de reserva (L0 de `testdata` + L1 diminuto) y fusiona ficheros.
