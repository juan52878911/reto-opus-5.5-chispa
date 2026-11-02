# Guía de despliegue de un piloto

De cero a producción en un servidor del cliente: imagen, claves de API, configuración, arranque, prueba de humo, métricas,
actualización del modelo, apagado y privacidad. No hay código nuevo: reúne lo que ya dicen [06-despliegue.md](06-despliegue.md),
[03-api.md](03-api.md) y [`pilotos/operacion.md`](../pilotos/operacion.md), **comprobado contra**
[`main.go`](../server/cmd/chispa-server/main.go), [`config.go`](../server/decide/config.go), [`l3.go`](../server/decide/l3.go),
[`auth.go`](../server/decide/auth.go) y [`entrada.sh`](../deploy/kindling/entrada.sh).

Lo que no funciona tal como estaba escrito, o no existe, va marcado **pendiente de producto**. Los comandos de esta guía no se
ejecutaron en el nodo de redacción (sin Go, Docker ni modelos): la [lista de verificación](#verificación-pendiente) dice qué correr en otro nodo.

## 1. Qué necesitas antes
- El `.chispa` v3 del cliente (`chispa train`, ver [02-inicio-rapido.md](02-inicio-rapido.md)); guarda su `sha256sum`.
- Si trae `L2` o `TORR`: el `e5.chispa-tok` (12 MB, `runtime/tok/exportar.py`) y una imagen con ORT.
- Un directorio de solo lectura para el modelo, p. ej. `/srv/chispa/modelos/` con `modelo.chispa`, `config.json` y, si procede, `e5.chispa-tok`.
  Debe ser legible por el uid del contenedor (10001 en la imagen de kindling; `nonroot`, 65532, en la de `server/deploy`).
- Docker en el servidor, o kindling (`kling`).
- Un proxy TLS delante, si la red entre cliente y servidor no es de confianza: el servidor **no trae TLS** y la clave de API viaja en claro (**pendiente de producto**).

## 2. Elegir la imagen
| Imagen | Qué trae | Cuándo |
|---|---|---|
| `deploy/kindling` `imagen-cpu` (133 MB) | binario estático, L0 y L1; **L2 en stub** | El `.chispa` solo decide con L0/L1 y el resto escala |
| `deploy/kindling` `imagen-ort` (221 MB) | `-tags ort` + `libonnxruntime.so`; L0, L1, L2 y torres al vuelo | Esquemas nuevos sin reentrenar (zero-shot con `TORR`) o L2 |
| `server/deploy/Dockerfile` | `-tags ort` sobre distroless; `chispa-server` y `carga` | Docker puro, sin `entrada.sh` ni `HEALTHCHECK` |

Regla práctica: **si el piloto decide sobre esquemas que el `.chispa` no trae, usa `ort`**; con `cpu` esos esquemas escalan siempre
(`chispa_torres_calculadas_total` se queda en 0). Construcción y versiones de ORT: [06-despliegue.md](06-despliegue.md#imagen-oci)
y [`deploy/kindling/README.md`](../deploy/kindling/README.md). Hace falta `gomod-proxy/` para construir; el servidor del cliente no necesita red.
Las dos recetas son distintas (las versiones de ORT no coinciden entre ellas, ver `06`): no mezcles sus parámetros.

```
docker build --build-arg TARGETOS=linux --build-arg TARGETARCH=amd64 -f deploy/kindling/Dockerfile --target imagen-ort -t chispa-server:ort .
docker save chispa-server:ort | gzip > chispa-ort.tar.gz     # para llevarla al servidor sin registro
docker load < chispa-ort.tar.gz                                # en el servidor del cliente
```

## 3. Generar las claves de API
Sin `api_keys`, `/v1/decide` queda abierto. Fuera de loopback el servidor **se niega a arrancar sin claves**
(`exigirClaves` en `main.go`) salvo `-abierto` o `"api_keys_abierto": true`; `entrada.sh` exige además `CHISPA_CONFIG` con `api_keys`.

`-hash-clave` lee **la clave de la entrada estándar**, imprime su SHA-256 y sale. Con la imagen, sin instalar nada:
```
CLAVE=$(head -c 32 /dev/urandom | base64 | tr -d '=+/\n')
printf '%s' "$CLAVE" | docker run --rm -i --entrypoint /usr/local/bin/chispa-server chispa-server:ort -hash-clave
```
(La imagen de kindling tiene `ENTRYPOINT entrada.sh`: por eso el `--entrypoint`. Con el binario suelto: `printf '%s' "$CLAVE" | ./chispa-server -hash-clave`.)
Guarda `$CLAVE` en el gestor de secretos del cliente y entrégala por un canal aparte; en la config va solo el hash. Una clave por consumidor
(`id`: `[A-Za-z0-9_.-]`, 1 a 64), cada una con su `rps` y su `rafaga`. Repite lo mismo para el token de administración (§4).
Rotar: añade la clave nueva con otro `id`, recarga (§9), mueve al consumidor y quita la vieja.

## 4. Configuración completa de ejemplo
`config.json`. **Claves desconocidas hacen fallar el arranque** (`DisallowUnknownFields`), así que una errata no pasa en silencio.
Lo que no escribas queda en el valor por defecto de `ConfigPorDefecto()`. Sin comentarios: JSON estricto.

```json
{
  "capas": [{"nombre":"L0","tau":0.80},{"nombre":"L1","tau":0.80},{"nombre":"L2","tau":0.70},{"nombre":"L3","tau":0.60}],
  "limites": {"max_cuerpo": 1048576, "max_preguntas": 256, "max_opciones": 256, "max_estado": 262144, "max_texto": 4096, "max_id": 256},
  "cache_esquemas": 1024, "cache_respuestas": 4096,
  "cache_esquemas_mb": 64, "cache_respuestas_mb": 48,
  "cache_torres": 16384, "max_torres_nuevas": 256, "torres_por_segundo": 400,
  "tau_l2_esquema_nuevo": 0.846,
  "l1_shrinkage_lambda": 4,
  "api_keys": [
    {"id": "piloto-app",  "hash_sha256": "<64 hex de -hash-clave>", "rps": 20, "rafaga": 40, "torres_por_segundo": 100},
    {"id": "piloto-back", "hash_sha256": "<64 hex de -hash-clave>", "rps": 5}
  ],
  "admin_token_sha256": "<64 hex de -hash-clave sobre el token de admin>"
}
```

| Clave | Notas comprobadas en `config.go` |
|---|---|
| `capas[].tau` | En [0,1], nombres únicos. **Con `-config`, estos τ pisan los de `CALIB` del `.chispa`**; sin `-config`, L1 y L2 usan `CALIB`. Si solo quieres fijar límites o claves, mantén los valores por defecto de arriba o acepta que `CALIB` deja de aplicar a L0–L2 |
| `limites.*` | Bytes UTF-8; negativo = error de arranque. Los valores del ejemplo son los por defecto |
| `cache_esquemas`, `cache_respuestas` | ≥ 1. `cache_*_mb`: 0 = 64 y 48 MiB; máximo 1 048 576 |
| `cache_torres`, `max_torres_nuevas`, `torres_por_segundo` | 0 = 16 384 y 256 (`torres_por_segundo`: por defecto 400, 0 = sin tope global, si no ≥ 1). `cache_torres` ≥ 384 (1,5 × `max_opciones`) o no arranca. Si se pasa el tope por petición, L2 cachea las torres que caben y escala con `sin_presupuesto_torres` |
| `tau_l2_esquema_nuevo` | Por defecto 0,846 (prioridad config > `CALIB` > 0,846). Es prudente: precisión 0,95 con ~97 % de escalado en tareas no vistas ([06](06-despliegue.md)). `"tau_l2_esquema_nuevo_apagado": true` lo quita; **no puede ir junto a un τ** |
| `l1_shrinkage_lambda` | Ausente = 4. `"l1_shrinkage_apagado": true` lo apaga (no junto a un λ). `l2_shrinkage_lambda` ausente = sin mezcla. Solo tiene efecto si el `.chispa` trae `SOPL1` |
| `api_keys` | `rps` > 0; `rafaga` 0 = ceil(rps); `id` y hash únicos; `torres_por_segundo` opcional (0 o ≥ 1) es un tope de torres al vuelo propio de la clave, además del global. Se relee en cada recarga |

Ejemplo: en el bloque de arriba, `piloto-app` tiene `"torres_por_segundo": 100` y `piloto-back` no tiene tope propio (solo el global de 400). Si `piloto-app` manda preguntas de esquemas nuevos con textos únicos a más de ~100 torres/s sostenidas (ráfaga: `max(100, max_torres_nuevas, 1)` = 256), al agotar su cubo sus esquemas nuevos escalan con `escalate_reason: "sin_presupuesto_torres"` (HTTP 200, no 429) hasta que el cubo se rellene; los esquemas ya cacheados o de `ESQUEMAS` siguen respondiendo, y `piloto-back` no nota nada (a `piloto-app` no se le gastan fichas del global cuando su propio cubo lo rechaza). Se ve en `chispa_torres_presupuesto_agotado_total` y en la proporción de `sin_presupuesto_torres`. La suma de los topes por clave puede pasar del global: manda el que se agote primero.
| `admin_token_sha256` | Hash de un token ≥ 32 bytes; abre `POST /v1/admin/recargar`. No pongas `admin_token` en claro (da `AVISO`; no pueden ir los dos) |
| `api_keys_abierto` | Solo si una recarga debe poder dejar el servicio sin claves. Una recarga sin `api_keys` sobre un servidor que las tenía **se rechaza** si falta esto |

Genera el token de admin como una clave más (§3) y guarda el original donde guardes secretos.

### 4.1 L3 apagada (por defecto)
No pongas la sección `l3`. L3 es un stub sin opinión: lo que L0–L2 no resuelven sale como `"layer":"escalar"`. Puedes dejar `{"nombre":"L3",…}` en `capas`.

### 4.2 L3 encendida
Añade a `config.json` (la capa `"L3"` debe seguir en `capas`, o la config no valida):
```json
"l3": {"url": "http://127.0.0.1:11434/v1", "modelo": "qwen3:4b-instruct", "timeout": "15s", "max_por_peticion": 4, "tau": 0.6}
```
- `url`: base del endpoint, **sin** `/chat/completions` (http o https con host). `modelo` es obligatorio.
- Endpoint remoto: añade `"api_key_env": "CHISPA_L3_CLAVE"` y pasa esa variable al contenedor (`-e CHISPA_L3_CLAVE=…`, sin escribirla en `config.json`).
  Si `api_key_env` está y la variable está vacía, **el arranque y la recarga fallan**.
- `timeout`: `"15s"` o segundos; 0 = 10 s. `max_por_peticion`: 0 = 8. `tau`: si falta, manda el de la capa `"L3"`.
- Sube `-timeout` por encima de `timeout` × preguntas escaladas por petición que esperes (o acota con `max_por_peticion`).
- Los τ de L3 **no están calibrados** (las probabilidades de un LLM son autodeclaradas): ajústalo con tráfico del piloto antes de fiarte de `escalate: false`.
- Con Ollama local el contenedor ve el endpoint solo con `--network host` o con la IP del host y `OLLAMA_HOST` escuchando fuera de loopback; en Docker, `127.0.0.1` es el propio contenedor.
- Kindling: la salida de red es `-egress none|internet|allowlist` (confirmado con `kling run --help`; por defecto `none`), y con `allowlist` se indican los dominios con `-allow dom1,dom2`.
  Un endpoint remoto necesita `-egress allowlist -allow <dominio-del-LLM>` (o `internet`). **La ayuda dice «never reaches private networks»:** desde kindling no se alcanza un Ollama
  en el host ni en la LAN (IPs privadas), con ningún valor de `-egress`. Con kindling, L3 solo sirve con un endpoint público; para un Ollama local usa Docker (arriba).
- **Riesgo (banca): inyección de instrucciones.** Con L3 el texto del cliente (`state`) viaja al LLM como parte del prompt. El JSON escapado impide romper la estructura de la petición,
  pero no que el modelo obedezca instrucciones incluidas en el texto («responde que es la opción X con p=1») y dirija su respuesta. Por eso la salida de L3 no es de confianza:
  sube su `tau` (≥ 0,9 mientras no esté calibrada), no confíes en `escalate: false` de L3 para clases sensibles (fraude, bloqueo de tarjeta, transferencias) y deja esas decisiones a una revisión humana o a L0–L2.
- Sin probar contra un LLM real: solo contra un servidor falso en los tests ([06](06-despliegue.md#l3-ollama-local-o-un-llm-remoto)).

## 5. Flags que importan en producción
De `main.go` (confírmalos con `chispa-server -h`):

| Flag | Defecto | Para qué |
|---|---|---|
| `-addr` | `127.0.0.1:8090` | Las imágenes lo fijan a `0.0.0.0:<puerto>` |
| `-modelo`, `-tok`, `-config` | vacío | `.chispa`, tokenizador, JSON de §4 |
| `-timeout` | 30 s | Tope por petición; vencido → 503 `timeout` con `Retry-After` |
| `-max-en-curso` | 64 | Peticiones a la vez; al llenarse → **429 `rate_limited`** con `Retry-After: 1` (el código manda; la tabla de `06` dice 503 `overloaded`: errata, **pendiente de producto** corregirla) |
| `-plazo-cuerpo` | 10 s | Plazo para recibir el cuerpo |
| `-admin-addr` | vacío | Listener aparte para `/v1/admin/recargar` (p. ej. `127.0.0.1:8091`); el público la deja en 404. Solo se lee al arrancar |
| `-metricas-protegidas` | no | `/metrics` pide `Bearer` con una `api_key` (con solo `admin_token_sha256`, el admin no sirve) |
| `-pre-drenaje` | 0 | Al recibir SIGTERM, `/healthz` responde 503 `shutting_down` este tiempo con los puertos abiertos, para que el balanceador retire el nodo |
| `-apagado` | 25 s | Plazo para terminar peticiones en vuelo (las imágenes lo ponen a 35 s) |
| `-ort-lib` | vacío | Ruta de `libonnxruntime.so` (o `CHISPA_ORT_LIB`); `imagen-ort` ya la trae |

## 6. Arrancar
Prepara el directorio y **valida antes**: el servidor sale con `FATAL` si la config no valida, y esa es la mejor prueba.

### 6.1 Docker, imagen de kindling (recomendada: exige claves y tiene `HEALTHCHECK`)
```
docker run -d --name chispa --restart unless-stopped --stop-timeout 40 \
  -p 127.0.0.1:8090:8090 \
  -v /srv/chispa/modelos:/modelos:ro \
  -e CHISPA_CONFIG=/modelos/config.json \
  chispa-server:ort -timeout 30s -max-en-curso 64 -metricas-protegidas
```
`entrada.sh` añade `-addr 0.0.0.0:8090 -modelo $CHISPA_MODELO -apagado 35s` y `-tok` si existe `/modelos/e5.chispa-tok`; los argumentos tras la imagen pasan tal cual.
`CHISPA_PUERTO` cambia el puerto interno. `-p 127.0.0.1:…` deja el servicio solo para el proxy del servidor; usa `-p 8090:8090` solo si no hay proxy delante.
**`--stop-timeout 40` es obligatorio** (35 s de `-apagado` + margen; el defecto de Docker, 10 s, mataría peticiones en vuelo).
Admin aparte: añade `-admin-addr 127.0.0.1:8091`; ojo, dentro del contenedor ese loopback no se publica con `-p`, así que la recarga por HTTP se hace con `docker exec`
(la imagen no trae `curl`; **usa `SIGHUP`**, §9) o sin `-admin-addr`, protegida por el proxy.

### 6.2 Docker, imagen de `server/deploy`
```
docker run -d --name chispa --restart unless-stopped --stop-timeout 40 -p 127.0.0.1:8090:8090 \
  -v /srv/chispa/modelos:/modelos:ro chispa-server:oci \
  -modelo /modelos/modelo.chispa -tok /modelos/e5.chispa-tok -config /modelos/config.json -timeout 30s
```
Los argumentos **sustituyen el `CMD`** entero: repite `-modelo`. El `ENTRYPOINT` fija `-addr 0.0.0.0:8090 -apagado 35s`.
Sin `HEALTHCHECK` en la imagen: sondea `/healthz` desde fuera.

### 6.3 Kindling (`kling`)
```
docker save chispa-server:ort -o chispa-ort.tar
kling image import -archive chispa-ort.tar -name chispa-server-ort
kling run -name chispa -image chispa-server-ort -mem 1G -mem-max 2G -cpus 2 \
  -share /srv/chispa/modelos:/modelos:ro -e CHISPA_CONFIG=/modelos/config.json -e CHISPA_PUERTO=8090 -wait-ready
```
Flags confirmados con `kling run --help` (`-name -image -cpus -mem -mem-max -share -e -wait-ready`). Sin `-egress` la salida es `none`: con L3 apagada no hace falta.
Con L3 remota añade `-egress allowlist -allow <dominio>`; **no llega a redes privadas** (un Ollama en el host o la LAN es inalcanzable desde kindling). Faltan por confirmar también: cómo se llega al puerto desde fuera, la
parada ordenada (la gracia debe ser ≥ 40 s) y la RAM real (`GOMEMLIMIT` va fijado a 400 MiB: súbelo a ~75 % de `-mem`). Los flags extra van tras `--`.
Sin `-e CHISPA_CONFIG=…`, `entrada.sh` sale con código 64: es a propósito.

El log de arranque debe decir `arranque: N claves de API activas` y `chispa-server en 0.0.0.0:8090: N modelos en L0`, y **no** `AVISO: ONNX Runtime no carga`,
ni `falta -tok`, ni `sin claves de API`.

## 7. Prueba de humo
```
URL=http://127.0.0.1:8090
curl -fsS $URL/healthz                                                  # {"status":"ok"}  (solo dice que el proceso vive)
curl -fsS -H "Authorization: Bearer $CLAVE" $URL/metrics | grep -E '^chispa_(peticiones|preguntas|escalados)_total'   # sin -metricas-protegidas, sin cabecera
curl -s -o /dev/null -w '%{http_code}\n' $URL/v1/decide -d '{}'         # 401 sin clave
curl -fsS $URL/v1/decide -H "Authorization: Bearer $CLAVE" -d '{"state":"Me cobraron dos veces la cuota y quiero que me devuelvan la plata","questions":[{"id":"q1","question":"¿Qué tipo de PQRS es este mensaje?","kind":"choice","options":[{"id":"peticion","description":"la persona solicita algo que la empresa puede hacer"},{"id":"queja","description":"la persona expresa inconformidad por el trato recibido"},{"id":"reclamo","description":"la persona exige que se corrija algo que falló"},{"id":"sugerencia","description":"la persona propone una mejora"},{"id":"felicitacion","description":"la persona agradece o elogia la atención"}]}]}'
```
Espera 200 con `results[0]` (`layer`, `answer`, `probs`, `escalate`). **`"layer":"escalar"` en todo no es un éxito**: valida el contrato, no la calidad
(modelo sin L1/L2, ORT sin cargar o L3 apagada). Con el `.chispa` del cliente, algunas decisiones deben salir de L0/L1/L2 (`chispa_decididas_total{capa}`).

**`chispa decide` y `chispa evaluar` no envían clave de API** (la CLI no tiene `--api-key`; solo el SDK, `Chispa(url, api_key=…)`). Contra un servidor con `api_keys` dan 401.
Esto es **pendiente de producto** (`checklist-despliegue.md` y `operacion.md §7` lo daban por válido). Mientras tanto, evalúa contra una **instancia auxiliar en loopback sin
`api_keys`**, que `exigirClaves` permite:
```
# config-humo.json = config.json sin "api_keys" ni "admin_token_sha256"
docker run -d --name chispa-humo --entrypoint /usr/local/bin/chispa-server --network host -v /srv/chispa/modelos:/modelos:ro \
  chispa-server:ort -addr 127.0.0.1:18090 -modelo /modelos/modelo.chispa -tok /modelos/e5.chispa-tok -config /modelos/config-humo.json
docker rm -f chispa-humo        # al acabar
```
(`--entrypoint` evita `entrada.sh`, que fija `-addr 0.0.0.0` y exige claves; con `--network host`, el loopback del contenedor es el del host.
Para probar un modelo nuevo, cambia `-modelo` por `/modelos/modelo-AAAAMMDD.chispa`.)
Luego, desde `sdk/python`:
```
python -m chispa decide --url http://127.0.0.1:18090 --estado "¿cuánto vale el cemento?" --pregunta "¿Qué necesita?" --opciones cotizacion pedido factura
python -m chispa evaluar --url http://127.0.0.1:18090 --esquema pqrs.yaml --datos muestra.csv --precision-objetivo 0.95 --concurrencia 4 --salida humo-AAAAMMDD
```
`evaluar` escribe `humo-AAAAMMDD.md` y `.json`; compara con la línea base ([`pilotos/metrica.md`](../pilotos/metrica.md), ≥ 300 filas para cifras del piloto).
Para la instancia de producción, repite solo las pruebas con `curl` de arriba. (`chispa` solo existe como comando si instalaste el wheel; si no, `python -m chispa`.)

## 8. Qué vigilar
`/metrics` (formato Prometheus; con `-metricas-protegidas`, el scraper manda `Authorization: Bearer <api_key>`). Alertas *(sugerencias, no compromisos del producto)*:

| Señal | Métrica | Alerta |
|---|---|---|
| Escalado | `chispa_escalados_total / chispa_preguntas_total` | > 20 % durante 15 min (sin L3 es lo normal para esquemas nuevos: compara con la línea base) |
| Errores | `chispa_peticiones_total{codigo}` | 4xx > 5 % en 10 min; cualquier 5xx sostenido |
| Tiempo | `chispa_timeouts_total`, `chispa_capa_latencia_segundos` | timeouts creciendo; p99 > 2× la línea base |
| Capas | `chispa_capa_errores_total`, `chispa_torres_errores_total` | > 0 sostenido |
| Saturación | `chispa_peticiones_total{codigo="429"}` | sube = `-max-en-curso` lleno o claves limitadas |
| Claves | `chispa_clave_peticiones_total{clave,resultado}`, `chispa_auth_rechazos_total` | `limitada` alto = subir `rps`; rechazos = clave mala o ataque |
| Admin | `chispa_admin_rechazos_total` | > 0 sin que nadie recargue |
| Esquemas nuevos | `chispa_torres_calculadas_total`, `chispa_esquema_nuevo_decididas_total / …_preguntas_total` | 0 con ORT = L2 en stub; decididas ≪ preguntas = τ de esquema nuevo prudente (esperable con 0,846) |
| Torres | `chispa_torres_cache_aciertos_total`, `chispa_torres_presupuesto_agotado_total` | pocos aciertos → subir `cache_torres`; presupuesto > 0 → clientes con demasiadas opciones |
| Memoria | `chispa_cache_bytes{cache}` | cachés + torres ≲ un tercio de `GOMEMLIMIT`; RAM y CPU del proceso con las herramientas del sistema (no están en `/metrics`) |
| Recargas | `chispa_recargas_total{resultado="error"}` | cualquier subida |
| L3 | `chispa_l3_llamadas_total{resultado}`, `chispa_l3_latencia_segundos` | `invalida` alto = el LLM no sigue el JSON; `timeout`/`error` = endpoint caído; `presupuesto` = demasiadas escaladas por petición |

No hay log de peticiones: stderr trae el arranque, avisos y recargas (`docker logs chispa`). Anota la línea base de la semana 1.

## 9. Actualizar el modelo, la config y las claves
No hace falta reiniciar. Lo que solo se lee al arrancar: `-addr`, `-admin-addr`, activar la ruta de admin si arrancó sin ella, y el binario o la imagen.
1. Escribe el modelo nuevo **con otro nombre en el mismo directorio** (`modelo-AAAAMMDD.chispa`), con las mismas preguntas y ids de opciones que manda el cliente.
2. Pruébalo en la instancia auxiliar de §7 (humo + `chispa evaluar`).
3. **`mv`, nunca `cp`**: `mv modelo-AAAAMMDD.chispa modelo.chispa`. `cp` escribe sobre el fichero abierto; con mmap el proceso muere con SIGBUS y sin él una recarga lee un fichero a medias.
   Si el volumen está montado `:ro`, haz el `mv` en el host (el contenedor ve el inodo nuevo en el mismo directorio, pero **un montaje de un solo fichero no sigue el `mv`**: monta el directorio, no el fichero).
4. Recarga: `docker kill --signal=HUP chispa` (equivale a `kill -HUP`), o `curl -X POST -H "Authorization: Bearer $TOKEN" $URL_ADMIN/v1/admin/recargar` si hay `admin_token_sha256`
   (éxito: `{"status":"ok","generation":N}`; 401 token malo; 429 más de ~1 intento/s; 500 `reload_failed` deja el modelo viejo; 404 si no hay admin o si va en `-admin-addr` y llamas al público).
5. Comprueba: `chispa_recargas_total{resultado="ok"}` sube y el log dice `recarga: modelo N en servicio, M claves de API activas`. Un fallo deja el modelo viejo y escribe `recarga fallida, sigue el modelo N: …`
   (con SIGHUP no hay respuesta: mira el log). Repite el humo de §7.
6. Marcha atrás: `mv` del `.chispa` anterior sobre `modelo.chispa` y recarga.

La recarga relee también `-config` y `-tok`, así que rotar claves o el token de admin es editar `config.json` y recargar. Una config nueva sin `api_keys` se rechaza si
antes había (a menos que traiga `api_keys_abierto`). Las cachés son del modelo: el nuevo empieza vacío (salvo las fichas de los cubos de torres por segundo, que se heredan) y la primera tanda de esquemas nuevos recalcula torres. Los contadores no se reinician.

## 10. Apagado ordenado
`docker stop chispa` (o `kill -TERM`): el servidor pone `/healthz` en 503 `shutting_down`, espera `-pre-drenaje` (si lo hay), deja de aceptar, espera las peticiones en vuelo hasta `-apagado`
(35 s en las imágenes; 25 s si arrancas el binario sin flag), cierra los modelos y sale con 0. Si el plazo se agota, corta lo que quede y sale con **1**.
- La gracia del orquestador debe ser mayor que `-pre-drenaje` + `-apagado`: `--stop-timeout 40` solo cubre 35 s **sin** pre-drenaje. Con balanceador, añade `-pre-drenaje 5s` y sube la gracia a ≥ 45 s.
- El cliente reintenta el 503 de apagado con `Retry-After`; no reintenta el 503 `timeout` ni el 504.
- Antes: `operacion.md §6` decía «apagado ordenado, pendiente de producto»: ya existe (`main.go`); lo que sigue pendiente es medirlo bajo carga.

## 11. Privacidad: qué sale del servidor
- **L3 apagada (por defecto):** nada sale. El servidor no hace llamadas salientes, no guarda `state` en logs ni en métricas (estas llevan `id` de clave, nunca el secreto ni textos).
  Las cachés de nonces y esquemas son memoria del proceso y se pierden al apagar.
- **L3 encendida:** por cada pregunta que L0–L2 escalan, se envía al endpoint de `l3.url` un mensaje de sistema fijo y un JSON con el texto del usuario (`state`) y la pregunta,
  su tipo y las opciones (`id` y descripción). No se envían claves de API, `nonce` ni identificadores del cliente de Chispa. Chispa no registra esos textos (ni en errores ni en logs); **lo que registre el endpoint es cosa suya**.
- El texto del cliente puede influir en la respuesta del LLM (inyección de instrucciones, §4.2): trata la salida de L3 como no fiable.
- Con Ollama en la misma máquina, no salen de ella. Con un endpoint remoto sí: dilo en el contrato con el cliente y avisa a su responsable de datos **antes** de activar L3. La clave del endpoint va por variable de entorno, nunca en `config.json`.
- Datos del piloto y consentimiento: [`pilotos/datos-y-consentimiento.md`](../pilotos/datos-y-consentimiento.md).

## 12. Pendiente de producto
- CLI `chispa decide` / `chispa evaluar` sin clave de API (§7).
- TLS en el servidor (lo pone el proxy, §1).
- Errata en [06-despliegue.md](06-despliegue.md#topes-de-memoria-y-de-entrada-flags-y-config): `-max-en-curso` responde 429 `rate_limited`, no 503 `overloaded`.
- Tamaño y RAM reales de las imágenes bajo kindling, y los comandos de `kling` (por confirmar con `kling --help`).
- Calibración de τ de L3 y calidad de `qwen3:4b-instruct` en este contrato.

## Verificación pendiente
En un nodo con Go, Docker y un `.chispa` (no hay nada de esto ejecutado):
```
cd server && go build ./cmd/chispa-server && ./chispa-server -h 2>&1 | grep -E 'hash-clave|pre-drenaje|admin-addr|max-en-curso'   # flags de §5
printf '%s' abc | ./chispa-server -hash-clave                                       # 64 hex (§3)
./chispa-server -addr 127.0.0.1:18090 -modelo m.chispa -config config.json &           # config válida (§4); {"l3":…} sin la capa "L3" debe fallar
. ~/orquestador/herr/env.sh && CHISPA_IMAGEN=chispa-server:ort deploy/kindling/comprobar.sh   # imagen: healthz, 401 sin clave, decisión, /metrics
docker run … ; docker stop chispa; docker inspect chispa --format '{{.State.ExitCode}}'      # §10: 0 con --stop-timeout 40
```
