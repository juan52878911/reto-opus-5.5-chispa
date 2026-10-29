# chispa-server en una microVM de kindling

Solo ficheros: nada de esto se ha lanzado ni construido aquí (sin red, y kling solo se usó con `--help`).

## Qué hay
- `Dockerfile`: dos destinos. `imagen-cpu` (binario estático `CGO_ENABLED=0`, linux/amd64 y arm64, sin L2 ONNX) e
  `imagen-ort` (`-tags ort`, cgo, con `libonnxruntime.so` de las releases de Microsoft y `libstdc++`/`libgcc_s`; x64 y aarch64).
  Usuario 10001, `HEALTHCHECK` con `sondeo` (binario Go, sin shell ni curl), puerto por `CHISPA_PUERTO`.
- `entrada.sh`: traduce variables de entorno a flags de `chispa-server` (`CHISPA_PUERTO`, `CHISPA_MODELO`, `CHISPA_TOK`, `CHISPA_CONFIG`). Exige `CHISPA_CONFIG` con `api_keys` (sale con 64 si falta); sin claves solo arranca con `CHISPA_ABIERTO=1` o `-abierto`. Rutas citadas, sin comodines.
- `comprobar.sh`: valida el servicio sin contenedor ni kindling.
- Base `debian:bookworm-slim` (no distroless) porque `entrada.sh` necesita `/bin/sh`.

## Construir (contexto = raíz del repo; requiere `gomod-proxy/`, igual que `server/deploy/Dockerfile`)
`GOPROXY` es solo `file:///gomod-proxy` (`-mod=readonly`, sin `GONOSUMDB`): `gomod-proxy/` debe traer todos los módulos de `server/go.sum`.
Rellena antes de construir (vacíos, el build falla): `--build-arg GO_DIGEST=sha256:… DEBIAN_DIGEST=sha256:…` y, para ort,
`ORT_SHA256_X64=… ORT_SHA256_AARCH64=…` (sha256 de los `.tgz` de la release de ORT).
```
docker buildx build --platform linux/amd64,linux/arm64 -f deploy/kindling/Dockerfile --target imagen-cpu -t chispa-server:cpu .
docker buildx build --platform linux/amd64,linux/arm64 -f deploy/kindling/Dockerfile --target imagen-ort -t chispa-server:ort .
```
`ORT_VERSION` (1.31.1, la libonnxruntime con la que se probó; `--build-arg`) debe ser compatible con `onnxruntime_go` v1.38.0, que fija `server/go.mod`; el build no hace `go get`. Para ort, cgo compila
en la plataforma destino (qemu o builder arm64 nativo). Para kling, una arquitectura por vez (`--load` / `--output type=oci`).

## Volúmenes
- `/modelos/modelo.chispa` (v3) y, para torres al vuelo con TORR, `/modelos/e5.chispa-tok` (`runtime/tok/exportar.py`);
  se monta de solo lectura. Sin el tokenizador, L2 decide solo esquemas de ESQUEMAS.

## Memoria recomendada (orientativa, sin medir en kindling)
- `imagen-cpu` (L0 y L1): `-mem 256M` basta para los `.chispa` de prueba; con un L1 grande (Potion 155 MB) usa 512M.
- `imagen-ort` (L2 e5-small int8 + torres): `-mem 1G`, `-mem-max 2G`. `GOMEMLIMIT` va fijado a 400MiB: súbelo a ~75 % del `-mem`.
- `CHISPA_ORT_LIB` (o `-ort-lib` como argumento) fija la `libonnxruntime.so` de L2 y de la torre; `imagen-ort` la trae en `/usr/lib/libonnxruntime.so`.

## Lanzar con kling
Flags tomados de `kling help image` y `kling help run` (leídos; no ejecutados). Sin verificar que kling acepte la imagen,
que `-volume` sirva para un fichero de modelo (la ayuda habla de almacenamiento persistente; `-share SRC:DST:ro` lo
monta desde el host) ni que respete el `HEALTHCHECK` (la ayuda dice «the image's own probe»). **Comando por confirmar con `kling --help`.**
```
docker save chispa-server:ort -o chispa-ort.tar
kling image import -archive chispa-ort.tar -name chispa-server-ort
kling run -name chispa -image chispa-server-ort -mem 1G -mem-max 2G -cpus 2 \
  -share /ruta/modelos:/modelos:ro -e CHISPA_PUERTO=8090 -wait-ready
```
Nota: `-egress` por defecto es `none`; el servidor no necesita red saliente. Cómo se llega al puerto 8090 desde fuera lo decide
kindling (no está en lo leído). Alternativa a la ruta de Docker: `kling image import <ref de registro>`.

## Comprobar sin kindling
`. ~/orquestador/herr/env.sh && deploy/kindling/comprobar.sh [modelo.chispa]` compila `chispa-server` y `sondeo`, arranca con
`entrada.sh`, espera el healthcheck, comprueba que el sondeo falla sin servidor y manda una decisión zero-shot a `/v1/decide`.
Con `server/testdata/intencion.chispa` (sin L1/L2/TORR) la respuesta correcta es escalar (`layer: escalar`): valida el contrato, no la calidad.
