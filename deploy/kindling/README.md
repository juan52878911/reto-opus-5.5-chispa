# chispa-server en una microVM de kindling

Construido y arrancado con Docker 29 (amd64, builder clásico, sin buildx): `imagen-cpu` 133 MB y `imagen-ort` 221 MB (tamaño en disco). arm64 no se construyó (sin buildx). Con kling solo se leyó `--help`.

## Qué hay
- `Dockerfile`: dos destinos. `imagen-cpu` (binario estático `CGO_ENABLED=0`, linux/amd64 y arm64, sin L2 ONNX) e
  `imagen-ort` (`-tags ort`, cgo, con `libonnxruntime.so` de las releases de Microsoft y `libstdc++`/`libgcc_s`; x64 y aarch64).
  Usuario 10001, `HEALTHCHECK` con `sondeo` (binario Go, sin shell ni curl), puerto por `CHISPA_PUERTO`.
- `entrada.sh` (pasa `-apagado 35s`; la gracia de parada de Docker debe ser >= 40 s: `--stop-timeout 40` o `terminationGracePeriodSeconds: 40`): traduce variables de entorno a flags de `chispa-server` (`CHISPA_PUERTO`, `CHISPA_MODELO`, `CHISPA_TOK`, `CHISPA_CONFIG`). Exige `CHISPA_CONFIG` con `api_keys` (sale con 64 si falta); sin claves solo arranca con `CHISPA_ABIERTO=1` o `-abierto`. Rutas citadas, sin comodines.
- `comprobar.sh`: valida el servicio sin contenedor ni kindling.
- Base `debian:bookworm-slim` (no distroless) porque `entrada.sh` necesita `/bin/sh`.

## Construir (contexto = raíz del repo; requiere `gomod-proxy/`, igual que `server/deploy/Dockerfile`)
`GOPROXY` es solo `file:///gomod-proxy` (`-mod=readonly`, sin `GONOSUMDB`): `gomod-proxy/` debe traer todos los módulos de `server/go.sum`.
Bases por digest y SHA-256 de ORT 1.31.1 ya fijados como `ARG` por defecto (x64 `c849e36a…bdc9`, aarch64 `5317505e…0c78`; el build los verifica con `sha256sum -c`).
`gomod-proxy/` se arma desde la caché de módulos (`$(go env GOMODCACHE)/cache/download/github.com`, con kindling v0.17.0 y onnxruntime_go v1.38.0; sin `*.lock`).
Sin buildx (builder clásico), las variables automáticas llegan vacías: pásalas a mano.
```
docker build --build-arg TARGETOS=linux --build-arg TARGETARCH=amd64 -f deploy/kindling/Dockerfile --target imagen-cpu -t chispa-server:cpu .
docker build --build-arg TARGETOS=linux --build-arg TARGETARCH=amd64 -f deploy/kindling/Dockerfile --target imagen-ort -t chispa-server:ort .
# con buildx (no probado aquí): docker buildx build --platform linux/amd64,linux/arm64 -f deploy/kindling/Dockerfile --target imagen-ort -t chispa-server:ort .
```
Arranque verificado: `docker run -d --stop-timeout 40 -p 127.0.0.1:8090:8090 -v DIR:/modelos:ro -e CHISPA_CONFIG=/modelos/config.json chispa-server:ort`
(`DIR` con `modelo.chispa` y `config.json` legibles por el uid 10001), o `-e CHISPA_ABIERTO=1` sin config. `/healthz` 200 y decisión zero-shot (`layer: escalar` con `intencion.chispa`, sin L1).
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
`CHISPA_IMAGEN=chispa-server:ort deploy/kindling/comprobar.sh` hace lo mismo contra un contenedor Docker de la imagen (healthz, sondeo dentro, decisión, 401 sin clave, `/metrics`) y lo borra al salir.
`. ~/orquestador/herr/env.sh && deploy/kindling/comprobar.sh [modelo.chispa]` compila `chispa-server` y `sondeo`, arranca con
`entrada.sh`, espera el healthcheck, comprueba que el sondeo falla sin servidor y manda una decisión zero-shot a `/v1/decide`.
Con `server/testdata/intencion.chispa` (sin L1/L2/TORR) la respuesta correcta es escalar (`layer: escalar`): valida el contrato, no la calidad.

## Flags y claves de la config (R7)
`entrada.sh` pasa sus argumentos extra a `chispa-server` (`"$@"`), así que los flags nuevos se añaden después de `kling run … --`:
`-admin-addr 127.0.0.1:8091` (ruta de admin en un listener aparte; dentro de la microVM, solo alcanzable desde ella), `-metricas-protegidas`,
`-plazo-cuerpo 10s`, `-max-en-curso 64`. Claves nuevas del JSON de `CHISPA_CONFIG`: `admin_token_sha256` (hash de `chispa-server -hash-clave`;
el `admin_token` en claro pide ≥ 32 bytes y avisa), `cache_esquemas_mb` y `cache_respuestas_mb` (topes en bytes de las cachés; defaults 64 y 48 MiB,
pensados para `GOMEMLIMIT` 400 MiB / `-mem 512M`). Detalle en [`docs/06-despliegue.md`](../../docs/06-despliegue.md).
Para cambiar el modelo dentro de la VM: `mv` del `.chispa` nuevo sobre el de `CHISPA_MODELO` y `kill -HUP`; **nunca `cp`** sobre el fichero en uso.
