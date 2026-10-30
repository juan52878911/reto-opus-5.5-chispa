# Despliegue

`chispa-server` es un binario de Go. L0, L1 y los stubs corren sin nada más. L2 y L2c necesitan ONNX Runtime y un tokenizador.

## Compilar
| Variante | Comando | Capas |
|---|---|---|
| Sin ORT | `cd server && go build ./cmd/chispa-server` | L0 y L1; L2 en stub |
| Con ORT | `cd server && go build -tags ort ./cmd/chispa-server` | L0, L1, L2 y L2c |

- `-tags ort` necesita cgo, `libonnxruntime.so` (1.17 o más nueva) y el módulo `github.com/yalue/onnxruntime_go`.
  La ruta de la `.so`, de mayor a menor precedencia: `chispa-server -ort-lib /ruta/libonnxruntime.so` > variable `CHISPA_ORT_LIB` >
  `-ldflags -X …/server/decide.RutaORT=/ruta/libonnxruntime.so` > búsqueda del sistema. Vale para L2 y para la torre. Si el `.chispa` trae L2 o TORR
  y ORT no carga, el arranque lo avisa en el log.
- Sin red: `GOFLAGS=-mod=mod GOPROXY=off`, con la caché de módulos ya llena ([`server/Makefile`](../server/Makefile)).
- Los módulos locales (`format/chispa3`, `runtime/l1`) entran por `replace` en `server/go.mod`.
- Versiones de ORT: **hay dos pares y no coinciden.** `server/go.mod` pide `onnxruntime_go v1.38.0` y los tests de ORT se probaron con `libonnxruntime.so.1.31.1`
  ([`server/README.md`](../server/README.md#compilar-y-probar-con-ort)). Los Dockerfile (`server/deploy`, `deploy/kindling`) fijan `ORT_VERSION` 1.22.0 y
  `ORT_GO_VERSION` v1.19.0 y ejecutan `go get` de esa versión al construir. Regla: `onnxruntime_go` no debe pedir una API mayor que la de la `.so`.
- Con ORT, el servidor calcula las torres de L2 al vuelo si el `.chispa` trae `TORR` y pasas `-tok`
  ([`server/torre`](../server/torre/README.md), [08-esquemas-nuevos.md](08-esquemas-nuevos.md)). La caché de torres y el tope por petición se fijan con
  `cache_torres` (por defecto 16 384) y `max_torres_nuevas` (por defecto 64; por encima, L2 no opina) en `-config`.
- Soporte few-shot: si el `.chispa` trae `SOPL1`, L1 mezcla el soporte con `l1_shrinkage_lambda` = 4 **por defecto** (sin tocar la config). Para el comportamiento de antes, `"l1_shrinkage_apagado": true` en `-config` (o `--sin-soporte` al entrenar para no escribir `SOPL1`). `l2_shrinkage_lambda` sigue apagado si falta. Cifras de `model/l2/resultados/barrido-20261029/LEEME.md` (rama de modelos; G.8b, checkpoint de G.8): con `l1_shrinkage_lambda` = 4 frente a sin soporte: massive 0,395 frente a 0,266, inyecciones 0,740 frente a 0,326, hatecheck 0,492 frente a 0,224; en JevBench cuesta 2 puntos (0,379 frente a 0,398). Detalle: [03-api.md](03-api.md#configuración--config).
- `tau_l2_esquema_nuevo`: default 0,846 (ausente en `-config` y en `CALIB`); prioridad `-config` > `CALIB` > 0,846; apagarlo con `"tau_l2_esquema_nuevo_apagado": true`. Medido sobre tareas no vistas (`model/l2/resultados/barrido-20261029/LEEME.md`, rama de modelos; G.8b, checkpoint de G.8): τ = 0,846 da precisión 0,95 con ~97 % de escalado; τ = 0,276 escala ≤ 20 % con precisión ~0,53. Se eligió 0,846 como default por prudente: ante un esquema que L2 no ha visto, prefiere escalar a acertar a medias (decisión del dueño del producto); 0,276 queda como alternativa si se prioriza no escalar.
- Probar con ORT sin red (nodo con Go y la `.so`): `cd server && CHISPA_ORT_LIB=/ruta/libonnxruntime.so go test -tags ort -race -count=1 ./...`. Sin ejecutar en este nodo.

## Flags
De [`main.go`](../server/cmd/chispa-server/main.go):

| Flag | Qué hace |
|---|---|
| `-addr` | dirección de escucha; por defecto `127.0.0.1:8090` |
| `-modelo` | un `.chispa` v3 (o v2) del que armar las capas |
| `-config` | JSON con capas, τ, modelos y cachés ([03-api.md](03-api.md#configuración--config)) |
| `-tok` | `.chispa-tok` de e5; sin él, L2 queda en stub aunque se compile con `ort`, y con `TORR` no hay torres al vuelo (el servidor lo avisa en el log) |
| `-hash-clave` | lee una clave de la entrada estándar, imprime su SHA-256 (el `hash_sha256` de `api_keys`) y sale sin arrancar el servidor; ver [Claves de API](#claves-de-api) |
| `-timeout` | tope de tiempo por petición (30 s por defecto); al pasarlo responde 503 con `{"error":{"code":"timeout"}}`; 0 = sin tope |

## Recarga en caliente del `.chispa`
Tras reentrenar (few-shot o `--conjunta`) y sustituir el fichero de `-modelo` (escríbelo aparte y renómbralo, `mv` es atómico),
recarga sin reiniciar:

- `kill -HUP <pid de chispa-server>`, o
- `POST /v1/admin/recargar` con `Authorization: Bearer <token>`, solo si el JSON de `-config` trae `"admin_token_sha256"` (o `"admin_token"` en claro, ≥ 32 bytes); sin ellos la
  ruta responde 404. Token incorrecto o ausente: 401; demasiados intentos: 429. Éxito: `{"status":"ok","generation":N}`; fallo: 500 `reload_failed`.

La recarga relee `-config`, `-modelo` y `-tok`, arma un modelo completo y lo sustituye de golpe. Las peticiones en vuelo
terminan sobre el modelo viejo (el fichero viejo se cierra cuando acaba la última). Si el `.chispa` nuevo no abre o no valida, se
queda el viejo, se escribe el error en el log y sube `chispa_recargas_total{resultado="error"}` (`ok` si prospera). Las cachés
(esquemas, torres al vuelo y nonces) pertenecen al modelo: el nuevo empieza con ellas vacías, así que un nonce de antes no
devuelve la respuesta del modelo anterior y la primera tanda de esquemas nuevos recalcula sus torres. Los contadores de
`/metrics` no se reinician. `-addr`, `-admin-addr` y el hecho de tener ruta de admin solo se leen al arrancar; `api_keys` y el token de
admin (`admin_token_sha256`/`admin_token`) sí se releen en cada recarga: **rotar el token = cambiar la config y recargar** (con SIGHUP).

**Sustituya el `.chispa` con `mv`, nunca con `cp`.** `cp` escribe en sitio sobre el fichero que el servidor tiene abierto: con `Limites.Mmap`
(mapeado) el proceso muere con SIGBUS al truncarlo, y con el defecto (lee el fichero al heap) una recarga o un reinicio a mitad de la copia
lee un fichero a medias. Escriba el nuevo con otro nombre en el mismo directorio y `mv nuevo.chispa modelo.chispa` (el `rename` es atómico;
el proceso conserva el inodo viejo hasta recargar).

### Admin: token, intentos y listener aparte
- `admin_token_sha256` (SHA-256 en hex, el mismo que `chispa-server -hash-clave`): recomendado. El token en claro (`admin_token`) se sigue
  aceptando durante la transición, con `AVISO` en el log, y debe tener **≥ 32 bytes**; no pueden ir los dos a la vez.
  `printf '%s' "$(head -c 32 /dev/urandom | base64 | tr -d '=+/\n')" | chispa-server -hash-clave` (guarde el token, ponga el hash).
- Intentos: cubo propio de 1 intento/s (ráfaga de 10). Cada intento gasta una ficha y un acierto la devuelve; con el cubo vacío responde
  429 `rate_limited` con `Retry-After` sin mirar el token (bajo ataque, el operador también espera unos segundos). Cada 401 o 429 suma a
  `chispa_admin_rechazos_total`.
- `-admin-addr 127.0.0.1:8091`: sirve `/v1/admin/recargar` en un listener aparte y el público la deja en 404. Por defecto (vacío) comparte
  `-addr` como antes, con un `AVISO` si `-addr` no es loopback.
- Con solo `admin_token_sha256`, `-metricas-protegidas` no acepta el admin en `/metrics` (solo `api_keys`).

## Topes de memoria y de entrada (flags y config)
| Opción | Defecto | Qué hace |
|---|---|---|
| `cache_esquemas_mb` (config) | 0 = 64 MiB | Tope en bytes de la caché de esquemas de L1 (además de `cache_esquemas` entradas) |
| `cache_respuestas_mb` (config) | 0 = 48 MiB | Tope en bytes de la caché de nonces (además de `cache_respuestas` entradas) |
| `-max-en-curso N` | 64 | Peticiones a `/v1/decide` a la vez; al llenarse, 503 `overloaded` con `Retry-After` |
| `-plazo-cuerpo D` | 0 = 10 s | Plazo para recibir el cuerpo entero de `/v1/decide` (negativo = sin plazo) |
| `-metricas-protegidas` | apagado | `/metrics` exige `Authorization: Bearer` con una `api_key` (o el `admin_token` en claro); sin ninguna, 401 siempre |
| `-admin-addr` | vacío | Listener aparte de la ruta de admin (arriba) |
Gauge `chispa_cache_bytes{cache="l1"|"nonces"|"torres"}` en `/metrics`. Los defaults en bytes ya venían de la revisión R7 (hallazgo 7); estas
claves solo los hacen ajustables, y no cambian el comportamiento si no se tocan. `-timeout`, `-max-conexiones` y `-apagado` siguen como en `-h`.

## Claves de API
Por defecto `/v1/decide` está abierto. Para un piloto en casa del cliente, ponga `api_keys` en `-config` ([03-api.md](03-api.md#configuración--config)):
cada cliente recibe una clave y un límite de tasa propio (`rps` sostenidas, `rafaga` de golpe), y el servidor responde 401 `unauthorized` o 429 `rate_limited` con `Retry-After`.

1. Genere una clave larga y aleatoria y guárdela donde guarde secretos; el servidor solo necesita su hash:
   ```
   CLAVE=$(head -c 32 /dev/urandom | base64 | tr -d '=+/\n')
   printf '%s' "$CLAVE" | chispa-server -hash-clave      # imprime los 64 hex
   ```
   `-hash-clave` lee la clave de la entrada estándar (así no queda en el historial del shell ni en `ps`) y sale. Un salto de línea final se ignora, así que `echo` también sirve.
2. Pegue el hash en `api_keys` (`{"id":"piloto-banco","hash_sha256":"…","rps":20,"rafaga":40}`) y recargue (SIGHUP) o reinicie. Entregue la clave en claro al cliente, que la manda como `Authorization: Bearer <clave>` (SDK: `api_key` en Python, `apiKey` en JS).
3. Rotar: añada la clave nueva con otro `id`, recargue, mueva al cliente y quite la vieja.

La clave en claro no se guarda ni se registra en ningún sitio; ninguna métrica la lleva (solo el `id`). Sin TLS la clave viaja en claro por la red: ponga el servidor detrás de un
proxy TLS o en la red local. **Sin clave (por diseño):** `/healthz` y `/metrics`. **Con `admin_token_sha256`/`admin_token`:** `/v1/admin/recargar` (limitada a 1 intento/s; mejor en `-admin-addr` loopback).
Los cubos viven en memoria del proceso: con varias réplicas, cada una aplica su propio límite.

## El tokenizador `-tok`
L2 recibe ids de e5. El tokenizador está en Go puro ([`runtime/tok`](../runtime/tok/README.md)) y lee un `.chispa-tok`.

```
python runtime/tok/exportar.py <directorio-del-modelo-e5> e5.chispa-tok      # 12 MB, no va a git
chispa-server -modelo modelo.chispa -tok e5.chispa-tok
```

Usa el mismo tokenizador de e5 con que se entrenó el modelo.

### Textos largos (`texto_largo`)
Por defecto un texto que pasa de `max_len` (L2) o de `max_tokens` (L1) se trunca por la cabeza. Con `texto_largo` en `-config` se puede probar `cabeza_cola` o `trozos` (agregación `max` o `media`); la referencia de campos está en [03-api.md](03-api.md#configuración--config). Para dimensionar: con `trozos` cada texto largo cuesta hasta `max_trozos` (8 por defecto) pasadas de ONNX en L2 en lugar de una, así que mira `chispa_texto_largo_total{capa="L2"}` frente a `chispa_preguntas_total` (qué parte del tráfico es larga) y `chispa_texto_largo_trozos_total` (cuántas pasadas extra) antes de activarlo, y baja `max_trozos` si la latencia p99 de L2 sube. Con `cabeza_cola` el coste no cambia (una ventana). Una recarga en caliente aplica la config nueva.

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
- Los README de `server/deploy` dicen que «L2 no responde aún» por falta de tokenizador: está desfasado. `main.go` ya acepta `-tok`; manda el código.

## Imagen de kindling
[`deploy/kindling/`](../deploy/kindling/README.md): `Dockerfile` con dos destinos, `imagen-cpu` (binario estático `CGO_ENABLED=0`, sin L2) e `imagen-ort`
(`-tags ort`, con `libonnxruntime.so`), para linux/amd64 y arm64. Base `debian:bookworm-slim` (no distroless: `entrada.sh` necesita shell), usuario 10001,
`HEALTHCHECK` con el binario `sondeo`.

```
docker buildx build --platform linux/amd64,linux/arm64 -f deploy/kindling/Dockerfile --target imagen-ort -t chispa-server:ort .
```

- `entrada.sh` traduce variables a flags: `CHISPA_PUERTO` (8090), `CHISPA_MODELO` (`/modelos/modelo.chispa`), `CHISPA_TOK` (`/modelos/e5.chispa-tok`, solo si el fichero existe)
  y `CHISPA_CONFIG`. No pasa `-timeout`; se puede añadir como argumento.
- Para torres al vuelo con `TORR`, monta `/modelos/e5.chispa-tok` junto al modelo (solo lectura).
- Memoria orientativa, **sin medir en kindling**: `imagen-cpu` 256M (512M con el potion de 155 MB), `imagen-ort` `-mem 1G`, `-mem-max 2G`; `GOMEMLIMIT` va fijado a 400MiB.
- Comprobación sin contenedor: `deploy/kindling/comprobar.sh [modelo.chispa]`.
- Nada de esto se ha construido ni lanzado: los comandos de `kling` del README están **por confirmar con `kling --help`**.

## Carga
El arnés [`server/carga/`](../server/carga/README.md) mide decisiones/s, p50 y p99 por modo y concurrencia, y escribe `resultados-<host>-<fecha>.md` y `.csv`:

```
cd server && carga/correr.sh -t carga/textos-es-co.txt
cd server && carga/correr.sh -O -M /ruta/modelo.chispa -T /ruta/e5.chispa-tok -t carga/textos-es-co.txt -m l2
go run ./cmd/carga -url http://127.0.0.1:18090/v1/decide -textos carga/textos-es-co.txt -c 16 -d 30s -lote 4 -capas -csv
make -C server carga-arnes ARGS="-d 10s -n 1"
```

- `correr.sh` (opciones `-m` modo `l1`|`l2`, `-c` concurrencias, `-d`, `-n` tandas, `-t` textos, `-M` modelo, `-T` tokenizador, `-O` compila con ORT, `-o`, `-p`) arranca el servidor
  en el puerto 18090. `cmd/carga` tiene los flags `-url -c -d -lote -textos -csv -timeout -capas`; el arnés admite como máximo 64 conexiones.
- `textos-es-co.txt`: 2 400 mensajes inventados en español de Colombia, 8 dominios; `textos.txt`: 260 frases sintéticas.
- `esquemas-carga.json`: 8 preguntas zero-shot y 4 lotes. **`cmd/carga` aún no los manda** (`-lote N` repite la pregunta fija); el README trae un `curl` a mano.
- Objetivos del plan: `l1` ≥ 5 000 dec/s con p99 < 20 ms; `l2` ≥ 300 dec/s. Cifras medidas: [07-rendimiento-y-limites.md](07-rendimiento-y-limites.md#carga-del-arnés).
- `-O`, `-M` y `-T` no se ejecutaron en este nodo (sin ORT ni modelos).
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

## L3: Ollama local o un LLM remoto
L3 es opcional y viene apagada. Para activarla con Ollama en la misma máquina (modelo ya descargado con `ollama pull qwen3:4b-instruct`;
Ollama sirve la API compatible con OpenAI en `http://127.0.0.1:11434/v1`), añada a la config de `-config`:
```json
"l3": {"url": "http://127.0.0.1:11434/v1", "modelo": "qwen3:4b-instruct", "timeout": "15s", "max_por_peticion": 4, "tau": 0.6}
```
Con un servicio remoto compatible, ponga su `url` y `"api_key_env": "NOMBRE_DE_LA_VARIABLE"` y exporte esa variable en el entorno del servicio (la clave no va en el fichero).
Se aplica en el arranque y en cada recarga (SIGHUP o `/v1/admin/recargar`); una `l3` mal escrita, o con `api_key_env` vacía, rechaza la recarga y sigue sirviendo la anterior.
Referencia de claves y del contrato: [03-api.md](03-api.md#l3-escalado-opcional-a-un-llm).

- **Privacidad:** con L3 activa, el texto del cliente (`state`) y la pregunta con sus opciones **salen del servidor hacia el endpoint configurado**, solo para lo que L0–L2 escalan. Con Ollama local no salen de la máquina; con un endpoint remoto sí, y el contrato con el cliente debe decirlo. Chispa no escribe esos textos en logs ni en errores ni en métricas; lo que registre el endpoint es cosa suya.
- **Latencia y carga:** cada pregunta escalada espera a una inferencia (cientos de ms a segundos en CPU). Suba `-timeout` por encima de `timeout` × el número de preguntas escaladas por petición que espere, y use `max_por_peticion` para acotarlo; `timeout` del cliente > `-timeout`.
- **Vigile** `chispa_l3_llamadas_total{resultado}` (`invalida` alto = el modelo no sigue el JSON; `timeout`/`error` = endpoint caído o lento; `presupuesto` = peticiones con demasiadas escaladas) y `chispa_l3_latencia_segundos`.
- **Sin verificar:** no se ha probado contra un Ollama ni un LLM real, solo contra un servidor falso en los tests; la calidad y la calibración de `qwen3:4b-instruct` en este contrato están por medir.

## Observabilidad
Usa `/healthz` como sonda de vida y `/metrics` para Prometheus. Vigila `chispa_escalados_total` frente a `chispa_preguntas_total`
([03-api.md](03-api.md#get-metrics)) y `chispa_capa_errores_total`.

CALIB visible: `chispa_calib{capa,tipo,origen,param}`, `chispa_calib_tau`, `chispa_calib_sin_tipo` y `chispa_calib_defecto_total{capa,tipo}`
([03-api.md](03-api.md#calib-visible)). Un `chispa_calib_defecto_total` que crece indica un tipo de petición sin CALIB en el `.chispa` en servicio:
la probabilidad y el τ de esa capa no valen para ese tipo. Al arrancar y recargar, el log avisa (`AVISO: CALIB de L1 sin los tipos […]`).

Contadores de lo nuevo (torres al vuelo, esquemas nuevos, nonces y plazos):

| Métrica | Tipo | Qué cuenta |
|---|---|---|
| `chispa_auth_rechazos_total` | counter | 401 de `/v1/decide` por clave ausente o mala (solo con `api_keys`) |
| `chispa_clave_peticiones_total{clave,resultado}` | counter | Peticiones por id de clave y resultado (`ok`, `limitada`) |
| `chispa_torres_calculadas_total` | counter | Torres de opción calculadas al vuelo (esquema que el `.chispa` no trae; hace falta la sección TORR) |
| `chispa_torres_cache_aciertos_total` | counter | Torres servidas de la caché de torres |
| `chispa_torres_esperas_total` | counter | Torres que esperaron a otra petición que ya las calculaba (singleflight) |
| `chispa_torres_errores_total` | counter | Cálculos de torre fallidos (error o pánico del codificador) |
| `chispa_torres_presupuesto_agotado_total` | counter | Preguntas en las que L2 no opinó por agotar el tope de torres nuevas de la petición |
| `chispa_torre_latencia_segundos` | histogram | Duración de cada cálculo de torre (mismos buckets que `chispa_capa_latencia_segundos`, sin etiqueta) |
| `chispa_esquema_nuevo_preguntas_total` | counter | Preguntas que L2 puntuó con torres al vuelo |
| `chispa_esquema_nuevo_decididas_total` | counter | De ellas, las que L2 resolvió con el τ de esquema nuevo (el resto sube de capa o escala) |
| `chispa_esquema_nuevo_tau` | gauge | τ de L2 para esquemas nuevos; solo aparece si la config lo fija (`tau_l2_esquema_nuevo`) |
| `chispa_texto_largo_total{capa}` | counter | Peticiones cuyo texto superó el truncado de la capa (`L1`: `max_tokens`; `L2`: `max_len` del ONNX, 128 por defecto) |
| `chispa_texto_largo_trozos_total{capa}` | counter | Ventanas decididas en esos textos (1 por petición con `cabeza`/`cabeza_cola`; hasta `max_trozos` con `trozos`) |
| `chispa_cache_nonce_aciertos_total` | counter | Respuestas repetidas servidas de la caché de nonces |
| `chispa_l3_llamadas_total{resultado}` | counter | Llamadas de L3 al LLM: `ok`, `invalida`, `error`, `timeout`, `presupuesto` |
| `chispa_l3_latencia_segundos` | histogram | Latencia de cada llamada de L3 (mismos buckets que las demás) |
| `chispa_timeouts_total` | counter | Peticiones cuyo plazo venció (no cuenta cancelaciones del cliente) |
| `chispa_recargas_total{resultado}` | counter | Recargas del modelo (SIGHUP o `/v1/admin/recargar`): `ok` o `error` (se queda el modelo anterior) |

Pistas: un `chispa_torres_cache_aciertos_total` bajo frente a `chispa_torres_calculadas_total` pide una caché de torres mayor;
`chispa_torres_presupuesto_agotado_total` > 0 indica clientes que mandan esquemas con demasiadas opciones; `chispa_timeouts_total`
creciendo junto a `chispa_torre_latencia_segundos` alto apunta a torres lentas.
