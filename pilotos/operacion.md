# Operación de `chispa-server` en casa del cliente (runbook del piloto)

Para el integrador de TI del cliente y para SDK. Explica cómo desplegar, vigilar y recuperar `chispa-server`. La integración y la métrica
están en [`guia-integracion.md`](guia-integracion.md) y [`metrica.md`](metrica.md); la lista de una página, en [`checklist-despliegue.md`](checklist-despliegue.md).

**Cómo leer este documento.** Las cifras llevan su fichero. «Sin medir» significa que el repo no tiene la medida. Lo marcado *(sugerencia)* es un
valor de partida de este runbook, no un compromiso del producto. Lo marcado **«pendiente de producto»** no existe en el código y no se promete al cliente.
Nada de lo de aquí se ejecutó en el nodo donde se escribió (sin Go, sin Docker, sin modelos): los comandos están leídos contra `main.go` y `cli.py`, y la
sección [Verificación pendiente](#verificación-pendiente) dice cómo comprobarlos.

## 1. Requisitos de máquina
| Recurso | Qué dice el repo | Fuente |
|---|---|---|
| CPU | Cota medida en 4 vCPU (Xeon 3,3 GHz): 1 891–2 176 decisiones/s por HTTP con 1 pregunta por petición y 11 323–13 011 con 16, con L0 y L1–L3 en stub. Con L1 real, sin HTTP, ≈ 24 000/s con 1 núcleo. Los 4 vCPU de esa VM no escalaron y el ruido es de ±30 %. Con ORT y L2: sin cifra de servidor en el repo; el objetivo del plan es ≥ 300 dec/s | `server/README.md` (Medidas); `docs/06-despliegue.md` (Carga) |
| Latencia | L2: p99 de 20 ms a 64 tokens en AVX2 (criterio de fase 2). Servidor completo en la infraestructura del cliente: **sin medir** | `docs/07-rendimiento-y-limites.md` |
| RAM, `imagen-cpu` (L0 + L1) | Orientativa y **sin medir en kindling**: 256 MB con los `.chispa` de prueba; 512 MB con el potion de 155 MB | `deploy/kindling/README.md` |
| RAM, `imagen-ort` (L2 + torres) | Orientativa y **sin medir**: `-mem 1G`, `-mem-max 2G`; `GOMEMLIMIT` fijado a 400MiB, a subir hasta ~75 % del `-mem` | `deploy/kindling/README.md` |
| Caché de torres | Una torre pesa ≈ 0,3 KB; las 16 384 por defecto son «pocos MB» | `server/decide/config.go` |
| Disco: modelo | Potion (L1): 155 MB (el `.chispa` con L1 pesó 154,9 MB). L0: tope de 48 MB por defecto (`chispa train --l0-max-mb`; kindling rechaza > 64 MiB). L2 e5-small int8: 48 MB. Un `.chispa` completo = suma de las secciones que traiga (sin medir el total) | `docs/02-inicio-rapido.md`; `docs/07`; `sdk/python/chispa/cli.py` |
| Disco: tokenizador | `e5.chispa-tok`: 12 MB (no va a git) | `docs/06-despliegue.md` |
| Disco: imagen | Objetivo ≤ 150 MB; **no hay medida de la imagen** | `server/deploy/README.md` |
| Red | El servidor no necesita red saliente (kindling: `-egress` por defecto `none`). Hace falta red solo para construir la imagen | `deploy/kindling/README.md` |
| ORT | `libonnxruntime.so` compatible con `onnxruntime_go` (ver el desacuerdo de versiones en `docs/06-despliegue.md`) | `docs/06-despliegue.md` |

El `.chispa` se abre con `mmap` de solo lectura (`format/chispa3/mmap_unix.go`): su tamaño cuenta como memoria de páginas del fichero, no como montón de Go,
y el sistema puede descargarlas. Por eso `GOMEMLIMIT` no lo cubre. *(Sugerencia: dimensione la RAM como el tamaño del `.chispa` + el del `.chispa-tok` +
el límite de montón + margen, y mida con el piloto; el repo no trae esa medida.)*

## 2. Despliegue
Tres rutas. Todas arrancan el mismo binario; mire `chispa-server -h` para confirmar los flags de su versión.

### 2.1 Binario
```
cd server && go build ./cmd/chispa-server                 # L0 y L1; L2 en stub
cd server && go build -tags ort ./cmd/chispa-server       # con L2 y L2c (cgo + libonnxruntime.so)
./chispa-server -addr 0.0.0.0:8090 -modelo /srv/chispa/modelo.chispa -tok /srv/chispa/e5.chispa-tok -config /srv/chispa/config.json -timeout 30s
```
Flags reales de [`main.go`](../server/cmd/chispa-server/main.go): `-addr` (por defecto `127.0.0.1:8090`: **solo local**, para servir a otras máquinas use `0.0.0.0:PUERTO`
detrás del balanceador o cortafuegos del cliente), `-modelo`, `-config`, `-tok`, `-timeout` (30 s; 0 = sin tope). No hay flag de versión, de TLS ni de autenticación.
Sin `-tags ort`, o sin `-tok`, L2 queda en stub (el servidor lo avisa en el log).

**Pendiente de producto:** TLS, autenticación y límite de tasa en el servidor. El cliente los pone delante (proxy inverso o malla); el kit no los trae.

### 2.2 Contenedor (imagen de `server/deploy`)
```
docker run -d --name chispa --restart unless-stopped -p 8090:8090 -v /ruta/modelos:/modelos:ro chispa-server
```
`ENTRYPOINT` es `chispa-server -addr 0.0.0.0:8090` y `CMD` es `-modelo /modelos/modelo.chispa`. Para añadir `-tok` y `-config`, sustituya el `CMD` entero:
```
docker run -d --name chispa --restart unless-stopped -p 8090:8090 -v /ruta/modelos:/modelos:ro chispa-server \
  -modelo /modelos/modelo.chispa -tok /modelos/e5.chispa-tok -config /modelos/config.json -timeout 30s
```
Construcción, versiones de ORT y tamaño: [`docs/06-despliegue.md`](../docs/06-despliegue.md#imagen-oci). Hace falta red al construir. La imagen no se ha construido en este repo.

### 2.3 Kindling (imagen de `deploy/kindling`)
`entrada.sh` traduce variables a flags: `CHISPA_PUERTO` (8090), `CHISPA_MODELO` (`/modelos/modelo.chispa`), `CHISPA_TOK` (`/modelos/e5.chispa-tok`, solo si el
fichero existe) y `CHISPA_CONFIG`. **No pasa `-timeout`**: se añade como argumento. Comandos de `kling` (por confirmar con `kling --help`, no ejecutados):
```
kling image import -archive chispa-ort.tar -name chispa-server-ort
kling run -name chispa -image chispa-server-ort -mem 1G -mem-max 2G -cpus 2 \
  -share /ruta/modelos:/modelos:ro -e CHISPA_PUERTO=8090 -wait-ready
```
Imagen con `HEALTHCHECK` (binario `sondeo`). Cómo se llega al puerto desde fuera lo decide kindling: **sin confirmar**. Ver [`deploy/kindling/README.md`](../deploy/kindling/README.md).

## 3. Configuración (`-config`)
JSON; lo que no pone, queda en el valor por defecto (`decide/config.go`). Referencia: [`docs/03-api.md`](../docs/03-api.md#configuración--config).
```json
{
  "capas": [{"nombre":"L0","tau":0.8},{"nombre":"L1","tau":0.8},{"nombre":"L2","tau":0.7},{"nombre":"L3","tau":0.6}],
  "cache_esquemas": 1024, "cache_respuestas": 4096,
  "cache_torres": 16384, "max_torres_nuevas": 64,
  "limites": {"max_cuerpo": 1048576, "max_preguntas": 256, "max_opciones": 256, "max_estado": 262144, "max_texto": 4096, "max_id": 256},
  "l1_shrinkage_lambda": 5.0,
  "tau_l2_esquema_nuevo": 0.7
}
```
(Los valores son los por defecto salvo `l1_shrinkage_lambda` y `tau_l2_esquema_nuevo`, que se ponen solo si se usan; el 5.0 de arriba es un ejemplo, no una recomendación.)

| Clave | Efecto | Cuidado |
|---|---|---|
| `capas[].tau` | τ por capa: se pasa a la siguiente si la confianza top-1 < τ. Subir τ → más escalado y más precisión de lo aceptado; bajarlo, al revés | Debe estar en [0,1]; nombres únicos. Con `-modelo` **y sin** `-config`, τ de L1 y L2 sale de `CALIB`; **con** `-config` manda la config (y pisa el `CALIB` calibrado en el entrenamiento) |
| `limites.*` | Topes de entrada. 0 u omitido = por defecto; negativo = error de arranque. Son bytes UTF-8 | Pasarse da 400 (`too_many_questions`, `state_too_long`…) o 413 |
| `cache_esquemas`, `cache_respuestas` | LRU de esquemas y de nonces (≥ 1) | Fragmentados en 16: tamaño aproximado |
| `cache_torres`, `max_torres_nuevas` | Torres al vuelo de L2 (0 = por defecto 16 384 / 64); por encima del tope por petición, L2 no opina | Solo con `-tags ort`, `-tok` y sección `TORR` |
| `l1_shrinkage_lambda`, `l2_shrinkage_lambda` | λ ≥ 0 del encogimiento del soporte (sección `SOPL1`); ausente = ∞ = sin mezcla | Solo few-shot con `SOPL1`. Un λ inválido es error de arranque |
| `tau_l2_esquema_nuevo` | τ de L2 para esquemas cuya torre salió al vuelo; en [0,1] | Si falta, con `-modelo` y sin `-config` se toma de `CALIB` |

El `-timeout` es un flag, no una clave de la config. Al vencer, responde 503 `timeout` con `Retry-After: 5` (`chispa_timeouts_total` lo cuenta).
Sin `-timeout` (0) no hay tope. *(Sugerencia: déjelo en 30 s; para el piloto un valor más bajo, p. ej. 5 s, evita que una torre lenta acapare conexiones; los SDK no reintentan este 503; un cliente propio debe respetar `Retry-After`.)*

**Valide la config antes de reiniciar:** el servidor la valida al arrancar y sale con error si no es válida (`log.Fatal`). Con el modelo en uso, arranque una copia en otro puerto
(`-addr 127.0.0.1:18090`) y pruebe antes de tocar la de producción.

## 4. Qué vigilar en `/metrics`
Texto Prometheus ([`openapi.yaml`](../server/api/openapi.yaml), [`docs/03-api.md`](../docs/03-api.md#get-metrics), [`docs/06`](../docs/06-despliegue.md#observabilidad)).
Los buckets de latencia son fijos: 10 µs, 50 µs, 0,1 ms, 0,5 ms, 1 ms, 5 ms, 10 ms, 50 ms, 0,1 s, 0,5 s, 1 s (`decide/metricas.go`).

| Serie | Qué mirar | Umbral de alerta *(sugerencia)* |
|---|---|---|
| `chispa_escalados_total` / `chispa_preguntas_total` | Tasa de escalado. El objetivo del producto es ≤ 20 % con tráfico normal (`docs/07`), **no cumplido** con el τ medido antes de T4.6b | > 20 % durante 15 min, o el doble de la línea base de la semana 1 |
| `chispa_peticiones_total{codigo}` | 4xx y 5xx sobre el total | 4xx > 5 % en 10 min (integración rota); cualquier 5xx sostenido 5 min |
| `chispa_timeouts_total` | Peticiones que vencieron `-timeout` | Crece > 0 durante 5 min |
| `chispa_capa_latencia_segundos{capa}` | Histograma por capa; use `histogram_quantile(0.99, …)` | p99 de L2 > 20 ms (referencia de fase 2) o p99 total > 2× la línea base |
| `chispa_capa_errores_total{capa}` | Fallos internos de una capa: la capa se salta, la respuesta sale igual, pero peor | Cualquier incremento sostenido |
| `chispa_decididas_total{capa}` | Reparto por capa. Si de repente todo cae en `escalar`, el modelo no trae las capas o L2 está en stub | Cambio brusco de reparto frente a la línea base |
| `chispa_torres_errores_total`, `chispa_torres_presupuesto_agotado_total` | Torres fallidas; clientes que mandan esquemas con demasiadas opciones | > 0 sostenido |
| `chispa_torres_cache_aciertos_total` vs `chispa_torres_calculadas_total` | Pocos aciertos → caché de torres pequeña (`cache_torres`) | Aciertos < calculadas de forma sostenida |
| `chispa_torre_latencia_segundos` | Duración de cada cálculo de torre | p99 en subida junto con `chispa_timeouts_total` |
| `chispa_cache_esquemas_total{resultado}` | Fallos de caché de esquemas | Muchos fallos → `cache_esquemas` pequeña o esquemas que cambian por petición |
| `chispa_cache_nonce_aciertos_total` | Reintentos idempotentes servidos | Informativo |

`/healthz` devuelve `{"status":"ok"}`: solo dice que el proceso responde, **no** qué capas hay cargadas. No lo use como único criterio de salud; combínelo con la prueba de humo (§7)
y con `chispa_decididas_total`. **Pendiente de producto:** un `/readyz` que compruebe las capas, y métricas de memoria o de tamaño de caché propias (no están en `/metrics`: mire el proceso con las herramientas del sistema).

Línea base: tome las cifras de la semana 1 con tráfico real y sáquelas de ahí; el repo no trae umbrales de operación para tráfico de empresas colombianas.

## 5. Registros
`chispa-server` escribe con `log` estándar de Go a **stderr**, sin niveles ni formato estructurado. Qué sale (de `main.go`):
- `chispa-server en <addr>: N modelos en L0` al arrancar.
- Avisos de armado: «el .chispa trae TORR pero falta -tok…», L2 en stub sin ORT, secciones que faltan.
- Recarga en caliente (§6): `SIGHUP: recargando el modelo`, `recarga: modelo N en servicio` si prospera, `recarga fallida, sigue el modelo N: <error>` si no, y `recarga: cerrar el modelo N: <error>` si el fichero viejo no cierra limpio.
- Errores fatales de arranque (`log.Fatal`): modelo, `-tok` o config inválidos.

**No hay registro de peticiones ni de decisiones** (ni de textos): es deliberado para el piloto; ver [`datos-y-consentimiento.md`](datos-y-consentimiento.md).
El historial de uso sale de `/metrics`. **Pendiente de producto:** log de acceso, de errores 4xx/5xx por petición y rotación; lo hace el proxy del cliente.
Docker: `docker logs chispa`; systemd: `journalctl -u chispa`. Guarde al menos el log de arranque: es la única pista de que L2 quedó en stub.

## 6. Actualizar el modelo, la config y el binario
**No hace falta reiniciar** para cambiar el `.chispa`, el `-tok` ni la config: el servidor recarga en caliente (`server/decide/recarga.go`). Lo que sí exige reinicio: `-addr`, `admin_token` y cambiar el binario. Apagado ordenado sigue **pendiente de producto**.

1. Entrene el nuevo `.chispa` con `chispa train` (ver [`guia-integracion.md`](guia-integracion.md)) y déjelo con otro nombre: `modelo-AAAAMMDD.chispa`. Nunca sobrescriba en sitio el fichero abierto: está mapeado en memoria.
2. Pruebe el nuevo en otro puerto: `./chispa-server -addr 127.0.0.1:18090 -modelo modelo-AAAAMMDD.chispa …` y pase la prueba de humo (§7) y `chispa evaluar` contra esa URL.
3. Sustitúyalo con un `mv` atómico sobre la ruta de `-modelo` (`mv modelo-AAAAMMDD.chispa modelo.chispa`; o `ln -sfn` sobre el enlace) y recargue:
   - `kill -HUP <pid de chispa-server>`, o
   - `curl -X POST -H "Authorization: Bearer $TOKEN" $URL/v1/admin/recargar`, solo si la config trae `"admin_token"`. Sin él la ruta da 404; token ausente o incorrecto, 401. Éxito: `{"status":"ok","generation":N}`.
4. Compruebe el resultado. Si el `.chispa` nuevo no abre o no valida, el POST responde 500 `reload_failed`, el servidor **sigue con el modelo viejo** y el error queda en el log (§5); con SIGHUP no hay respuesta, así que mire el log. `chispa_recargas_total{resultado="ok"|"error"}` cuenta ambos casos. Repita la prueba de humo.
5. Las peticiones en vuelo terminan sobre el modelo viejo. Las cachés (esquemas, torres y nonces) son del modelo: el nuevo empieza vacío, así que la primera tanda de esquemas recalcula torres. Los contadores de `/metrics` no se reinician.
6. La recarga relee también `-config` y `-tok`: una config que no valida es un fallo de recarga (el viejo sigue), no impide el servicio. Para un cambio de `-addr` o de `admin_token`, reinicie.

El `.chispa` nuevo debe llevar las mismas preguntas y opciones que el cliente manda: L0 elige el modelo por conjunto de ids de opciones (`server/README.md`); si cambia los ids, cambia el comportamiento.

## 7. Prueba de humo después de desplegar
Sustituya `$URL` (p. ej. `http://127.0.0.1:8090`). Cada paso debe dar lo indicado; si no, no pase al siguiente.
```
URL=http://127.0.0.1:8090
curl -fsS $URL/healthz                                  # {"status":"ok"}
curl -fsS $URL/metrics | grep -E '^chispa_(peticiones|preguntas|escalados)_total'
curl -fsS $URL/v1/decide -d '{"state":"Me cobraron dos veces la cuota y quiero que me devuelvan la plata","questions":[{"id":"q1","question":"¿Qué tipo de PQRS es este mensaje?","kind":"choice","options":[{"id":"peticion","description":"la persona solicita algo que la empresa puede hacer"},{"id":"queja","description":"la persona expresa inconformidad por el trato recibido"},{"id":"reclamo","description":"la persona exige que se corrija algo que falló"},{"id":"sugerencia","description":"la persona propone una mejora"},{"id":"felicitacion","description":"la persona agradece o elogia la atención"}]}]}'
chispa decide --url $URL --estado "¿cuánto vale el cemento?" --pregunta "¿Qué necesita?" --opciones cotizacion pedido factura
```
Qué esperar: `/v1/decide` da 200 con `results[0]` con `layer`, `answer`, `probs` y `escalate`. **`"layer":"escalar"` con `"escalate":true` en todas las preguntas no es un éxito:** con un modelo sin
secciones de L1/L2 o con L2 en stub la respuesta correcta es escalar y valida solo el contrato, no la calidad (`deploy/kindling/README.md`). Pruebe con el `.chispa` del cliente y compruebe que algunas decisiones salen de L0/L1/L2.

Después, mida sobre su muestra etiquetada (métricas en [`metrica.md`](metrica.md)):
```
chispa evaluar --url $URL --esquema pqrs.yaml --datos muestra.csv --precision-objetivo 0.95 --concurrencia 4 --salida humo-AAAAMMDD
```
Escribe `humo-AAAAMMDD.md` y `humo-AAAAMMDD.json`. Flags de [`cli.py`](../sdk/python/chispa/cli.py): `--url`, `--esquema`, `--datos` (obligatorios), `--pregunta`, `--precision-objetivo` (0,95),
`--concurrencia` (4), `--timeout` (10 s), `--reintentos` (3), `--salida`, `--filas`. Cada fila es una petición. Para una verificación rápida basta una muestra de unas decenas de filas; las cifras del piloto piden ≥ 300 ([`metrica.md`](metrica.md)).
Compare con la línea base de la semana 1.

## 8. Copia de seguridad
Lo que hay que guardar, porque sin ello no se restaura el servicio:
- El `.chispa` en uso y los dos anteriores (ficheros de solo lectura; nombre con fecha).
- `config.json`, el `.chispa-tok` (12 MB, no va a git) y el esquema (`pqrs.yaml`) con que se entrenó.
- La línea de arranque (unidad systemd, `docker run` o variables de kindling), la versión del binario o de la imagen y la versión de ORT.
- La muestra etiquetada (la custodia el cliente; no sale de su entorno, ver [`datos-y-consentimiento.md`](datos-y-consentimiento.md)).

```
sha256sum modelo-*.chispa e5.chispa-tok config.json > SHA256SUMS      # tras guardar
sha256sum -c SHA256SUMS                                               # al restaurar
```
Restaurar = poner el `.chispa` anterior con `mv`, recargar (§6) y pasar la prueba de humo. El servidor no tiene estado propio que respaldar: las cachés (esquemas, nonces, torres) viven en memoria y se vacían al reiniciar o recargar.
Sin medir cuánto tarda en arrancar con un L1 de 155 MB.

## 9. Qué hacer ante…
Cada punto: síntoma → comprobar → actuar. Si una misma causa falla dos veces seguidas, pare y escale a SDK.

### Latencia alta
1. `chispa_capa_latencia_segundos` por capa: ¿qué capa sube? L0 debería estar en µs (p99 0,2 ms con L0 real, `docs/07`); L2 ronda 10–20 ms.
2. Si es L2 y hay `chispa_torres_calculadas_total` creciendo: esquemas nuevos por petición. Revise `chispa_torres_cache_aciertos_total`; suba `cache_torres` o mande esquemas estables.
3. Peticiones grandes (`max_preguntas` 256, `state` 256 KiB): el coste crece con los bytes del estado (tokenizador de L1). Mande lotes menores.
4. CPU o RAM saturadas en la máquina (misma VM que otras cargas, mmap fuera de RAM → fallos de página): mire `top`/`vmstat`; más núcleos no ayudaron en la cota medida (±30 % de ruido).
5. Si `chispa_timeouts_total` crece, el 503 lleva `Retry-After: 5`: los clientes Python y JS **no** reintentan el 503 `timeout` (cuerpo `error.code == "timeout"`, aunque traiga `Retry-After`) ni el 504: repetirlos vuelve a gastar la cascada. Sí reintentan los demás 503 (p. ej. de un proxy en un reinicio), con backoff, respetando `Retry-After` con tope de 30 s.

### Mucho escalado
1. Compare con la línea base: ¿subió de repente (cambio de modelo, de config, de texto) o siempre fue alto?
2. `chispa_decididas_total{capa}`: si casi todo cae en `escalar` y ninguna capa decide, mire el log de arranque: L2 en stub (sin `-tags ort` o sin `-tok`), o modelo sin secciones.
3. `chispa_capa_errores_total{capa}`: una capa con errores se salta y todo sube de capa.
4. ¿Cambió `-config`? Con `-config`, los τ de la config pisan el `CALIB`. Revise `capas[].tau`.
5. ¿Cambiaron los ids de las opciones? L0 no opina sin modelo para ese conjunto de ids.
6. Si el escalado es real (esquema nuevo, mensajes distintos): mida con `chispa evaluar` y, si es el caso, agregue ejemplos y reentrene. Bajar τ reduce el escalado y baja la precisión de lo aceptado: decídalo con el cliente y con la cobertura de [`metrica.md`](metrica.md).

### Errores 4xx
`chispa_peticiones_total{codigo}` dice cuántos; el cuerpo trae `error.code`, `message` con la ruta del campo y `question_id` ([`docs/03-api.md`](../docs/03-api.md)). Como no hay log de peticiones, reproduzca con `curl` y el cuerpo del cliente.
| Código | Causa | Acción |
|---|---|---|
| 400 `invalid_json` / `invalid_kind` / `missing_*` / `duplicate_*` | Cuerpo mal formado o campo desconocido | Corregir al cliente; la validación es todo o nada |
| 400 `too_many_questions` / `too_many_options` / `state_too_long` / `field_too_long` | Pasa un tope de `limites` | Partir la petición, o subir el tope en `-config` y recargar (§6) |
| 404 `not_found` | Ruta mal escrita (solo existen `/v1/decide`, `/healthz`, `/metrics`) | Corregir la URL |
| 405 `method_not_allowed` | Método ≠ POST en `/v1/decide` | Usar POST |
| 413 `request_too_large` | Cuerpo > `max_cuerpo` (1 MiB) | Partir o subir `max_cuerpo` |

### Errores 5xx
- **503 `timeout`**: ver «Latencia alta». Los SDK no lo reintentan; si reintenta a mano, espere al menos `Retry-After`. Un 503 sin ese código (proxy o balanceador) sí es transitorio y los SDK lo reintentan.
- **Conexión rechazada, 502/504 del proxy**: proceso caído o arrancando. Mire `docker ps` o `systemctl status`, el log de arranque (§5) y la memoria (abajo). Reinicie y haga la prueba de humo.
- **500 o capas con error**: el código recupera pánicos solo en algunas rutas (L2); un fallo interno de capa se cuenta en `chispa_capa_errores_total` y la respuesta sale sin esa capa. Guarde el log y escale a SDK.
- Si arranca y se cae a los segundos: config o modelo inválidos (`log.Fatal` con el motivo en stderr), `libonnxruntime.so` ausente o incompatible (imagen `ort`), o falta del `.chispa-tok`.

### Memoria
1. Mire la memoria residente del proceso y del contenedor (`docker stats`, `ps -o rss`). El `.chispa` mapeado cuenta como páginas del fichero (§1).
2. En contenedor: sin límite de memoria o con un `GOMEMLIMIT` mayor que el límite del contenedor, el OOM mata el proceso. Fije `GOMEMLIMIT` a ~75 % del límite (kindling: 400MiB por defecto, valores sin medir).
3. Las cachés (`cache_esquemas`, `cache_respuestas`, `cache_torres`) crecen hasta su tope y no más; bájelas si el RSS es el problema. Una torre pesa ≈ 0,3 KB, el resto de entradas no se midió.
4. Peticiones grandes (`max_estado` 256 KiB × concurrencia): baje `limites` si el cliente no necesita tanto.
5. Si el RSS sube sin parar con tráfico estable: **no hay medida de fugas en el repo**; escale a SDK con las series de `/metrics` y el RSS. Mientras, reinicie en la ventana de menos tráfico.

## Verificación pendiente
Nada de esto se ejecutó en el nodo de redacción. En un nodo con Go, ORT y modelos:
```
cd server && go build ./cmd/chispa-server && ./chispa-server -h 2>&1 | head -20       # confirma flags de §2
. ~/orquestador/herr/env.sh && deploy/kindling/comprobar.sh server/testdata/intencion.chispa   # arranca y manda una decisión
python3 -m chispa.cli evaluar -h | head -30                                            # confirma flags de §7 (desde sdk/python)
```
Sin confirmar: las órdenes de `kling` (§2.3), el tamaño real de la imagen y la RAM de las imágenes (§1), que la imagen de `server/deploy` y la de kindling construyan, y el comportamiento de un `.chispa` sobrescrito en sitio (§6, tomado de cómo funciona `mmap`, no probado).
