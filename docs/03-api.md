# API HTTP

Tres rutas (`POST /v1/decide`, `GET /healthz`, `GET /metrics`). **Contrato formal: [`server/api/openapi.yaml`](../server/api/openapi.yaml)** (OpenAPI 3.1, con ejemplos; `server/decide/contrato_test.go` manda cada ejemplo al handler y valida la respuesta contra sus esquemas). Código: [`server/decide/http.go`](../server/decide/http.go).

## `POST /v1/decide`

### Petición
Ejemplo real: [`choice.req.json`](../server/decide/testdata/choice.req.json).

```json
{"state":"Mensaje urgente: no me ha llegado el pedido y lo necesito hoy",
 "questions":[{"id":"u1","question":"¿Qué tan urgente es?","kind":"choice",
   "options":[{"id":"alta","description":"Requiere atención inmediata"},{"id":"baja","description":"Puede esperar"}],"nonce":"abc-1"}]}
```

| Campo | Regla |
|---|---|
| `state` | texto que se clasifica; el mismo para todas las preguntas; ≤ `max_estado` |
| `questions` | de 1 a 256 |
| `questions[].id` | obligatorio; único en la petición |
| `questions[].question` | obligatorio |
| `questions[].kind` | `choice`, `score` o `noul` |
| `questions[].options` | `choice`: ≥ 2 y ≤ 256, con `id` único y `description` opcional. `score`: ≥ 2; el servidor no exige ids concretos: L0 y L1 aceptan ids libres, y la cabeza CORAL de L2 solo opina si los ids son `"1"` … `"K"` en orden. `noul`: opcional; si va, solo `"false"` y `"true"` |
| `questions[].nonce` | opcional; clave de idempotencia |

Los campos desconocidos dan 400.

**El esquema viaja en la petición.** `question`, `kind` y las `options` con su `description` son el esquema completo; el servidor
no exige un `.chispa` entrenado para él. Un esquema nuevo lo decide L1 y, si el `.chispa` trae `TORR` y el servidor se compiló con `-tags ort` y corre con `-tok`, también L2 con torre al vuelo
([08-esquemas-nuevos.md](08-esquemas-nuevos.md)). Las `description` importan: en zero-shot son lo único que Chispa ve de tu tarea.
Ejemplo completo con un esquema inventado: [02-inicio-rapido.md](02-inicio-rapido.md#2-zero-shot-sin-ejemplos). Con L0 y L2c
(modo con datos del cliente), `question` y los ids deben ser los del entrenamiento.

### Respuesta (200)
Ejemplo real: [`choice.resp.json`](../server/decide/testdata/choice.resp.json). Los tests normalizan `ms` a 0.

```json
{"results": [
  {"id": "u1", "kind": "choice", "answer": "alta", "probs": {"alta": 0.9, "baja": 0.1},
   "layer": "L0", "escalate": false, "ms": 0, "nonce": "abc-1"}
]}
```

- Los resultados van en el orden de `questions`.
- `answer`: el id de la opción elegida.
- `probs`: probabilidad calibrada de cada opción, la de la capa que respondió.
- `layer`: la capa que contestó (`L0`…`L3`). Si `escalate` es true, vale `"escalar"`: ninguna capa llegó a su τ.
- `escalate`: ninguna capa llegó a su τ. `answer` y `probs` son entonces la mejor pista, o `""` y `{}` si nadie opinó.
- `ms`: tiempo de la cascada para esa pregunta. `nonce` vuelve tal cual.

Con `noul` y `score` ([`noul_score_escala.req.json`](../server/decide/testdata/noul_score_escala.req.json) y
[`resp`](../server/decide/testdata/noul_score_escala.resp.json)):

```json
{"results": [
  {"id":"n1","kind":"noul","answer":"false","probs":{"false":0.9,"true":0.1},"layer":"L0","escalate":false,"ms":0},
  {"id":"s1","kind":"score","answer":"1","probs":{"1":0.4,"2":0.6},"layer":"escalar","escalate":true,"ms":0}
]}
```
Este segundo ejemplo sale de un test con capas falsas: muestra el formato de un escalado, no cifras reales.

En `score`, `answer` depende de la capa que respondió:
- **L1:** `probs` es el softmax de los cosenos (/ T) entre el mensaje y cada «pregunta · nivel · descripción»; `answer` es
  la **mediana**: el primer nivel cuya probabilidad acumulada llega a 0,5.
- **L2:** cabeza CORAL (`server/decide/l2.go`, `score`). `answer` es la **mediana**: el nivel 1 + el número de umbrales
  con P(y > j) > 0,5, igual que en L1. `probs` sale de las diferencias entre las probabilidades acumuladas de sus
  umbrales, P(y = k) = P(y > k−1) − P(y > k), recortadas a ≥ 0; la confianza es `probs[answer]`.
- **L0:** el clasificador entrenado con los ejemplos; `answer` es su nivel más probable.

En los tres casos, la confianza que se compara con τ es la probabilidad de `answer` en `probs`.

### Clave de API (opcional)
Si la config trae `api_keys` (ver [Configuración](#configuración--config)), `POST /v1/decide` exige `Authorization: Bearer <clave>` y cada clave tiene
su propio límite de tasa. Sin `api_keys` la ruta está abierta, como siempre. `/healthz` y `/metrics` **nunca** piden clave (así los
ven la sonda de vida y Prometheus; el segundo solo lleva ids de clave, no claves ni hashes) y `/v1/admin/recargar` sigue con `admin_token`,
no con una clave de API (y viceversa).

La clave nunca está en claro en el servidor: la config guarda su SHA-256 y el servidor compara hashes en tiempo constante. Un 401 no dice si
faltaba la cabecera o si la clave era mala. El límite es un token bucket por clave: `rafaga` peticiones de golpe y `rps` por segundo sostenidas; cada
petición HTTP gasta un token, tenga las preguntas que tenga. Al agotarse responde 429 con `Retry-After` (segundos enteros, mínimo 1).

### Errores
Todo error lleva el mismo cuerpo tipado. `code` es estable y pensado para programas; `message` es para humanos (lleva la ruta del campo) y puede cambiar. `question_id` solo aparece cuando el error es de una pregunta con id.

```json
{"error": {"code": "invalid_kind", "message": "questions[0].kind: \"raro\" no válido (choice, score o noul)", "question_id": "1"}}
```
Ejemplo real: [`kind_invalido_400.resp.json`](../server/decide/testdata/kind_invalido_400.resp.json).

| HTTP | `code` | Cuándo |
|---|---|---|
| 400 | `invalid_json` | JSON ilegible, campo desconocido o datos tras el objeto |
| 400 | `empty_questions` | `questions` vacío o ausente |
| 400 | `too_many_questions` | más de `max_preguntas` |
| 400 | `state_too_long` | `state` > `max_estado` bytes |
| 400 | `missing_id` | pregunta sin `id` |
| 400 | `duplicate_question_id` | `id` de pregunta repetido |
| 400 | `missing_question` | pregunta sin `question` |
| 400 | `missing_kind` / `invalid_kind` | `kind` ausente / distinto de `choice`, `score`, `noul` |
| 400 | `too_few_options` | `choice` o `score` con menos de 2 opciones |
| 400 | `too_many_options` | más de `max_opciones` |
| 400 | `invalid_options` | `noul` con opciones distintas de `false` y `true` |
| 400 | `missing_option_id` / `duplicate_option_id` | opción sin `id` / `id` repetido |
| 400 | `field_too_long` | `question`, `description`, un `id` o el `nonce` por encima de `max_texto` / `max_id` |
| 401 | `unauthorized` | solo con `api_keys`: falta `Authorization: Bearer <clave>` o la clave es incorrecta (cabecera `WWW-Authenticate: Bearer`) |
| 404 | `not_found` | ruta que no existe |
| 405 | `method_not_allowed` | método distinto de POST en `/v1/decide` (cabecera `Allow: POST`) |
| 413 | `request_too_large` | cuerpo > `max_cuerpo` |
| 429 | `rate_limited` | solo con `api_keys`: la clave agotó su `rafaga` y su `rps`. Lleva `Retry-After` (segundos). Los SDK no lo reintentan solos: lanzan el error con la espera pedida |
| 503 | `timeout` | la petición superó `-timeout` (30 s por defecto). Lleva `Retry-After: 5` y `Content-Type: application/json`. Es sobrecarga: el cliente debe esperar ese plazo antes de reintentar. Los SDK no reintentan este 503 (ni el 504); sí reintentan otro 503 (proxy), esperando al menos `Retry-After` (tope 30 s). El `timeout` del cliente debe ser mayor que `-timeout`: con 35 s por defecto en Python, este 503 llega antes de que el cliente corte |

La validación es todo o nada: una pregunta mala rechaza la petición entera. Un fallo interno de una capa solo salta esa capa
(cuenta en `chispa_capa_errores_total`).

**Compatibilidad.** Antes el error era `{"error": "texto"}`; ahora `error` es un objeto. Los clientes que lo leen como string
(SDK Python: `ErrorSolicitud.mensaje` pasa a ser el dict; Android e iOS no consumen esta API HTTP, solo el JSON de `chispamovil`) siguen
funcionando por el código HTTP, que no cambia; quien muestre `error` tal cual verá el objeto. `server/deploy/aws/contrato.py` solo comprueba que `error` exista.

### Límites
Defaults y cómo cambiarlos: sección `limites` del JSON de `-config` (un campo a 0 u omitido deja el default; negativo es un error de arranque).

| Clave | Default | Qué limita |
|---|---|---|
| `max_cuerpo` | 1 MiB | bytes del cuerpo HTTP (413) |
| `max_preguntas` | 256 | preguntas por petición |
| `max_opciones` | 256 | opciones por pregunta |
| `max_estado` | 256 KiB | bytes de `state` |
| `max_texto` | 4096 | bytes de `question` y de cada `description` |
| `max_id` | 256 | bytes de cada `id` y del `nonce` |
| `max_torres_nuevas` (config) | 64 | torres de esquemas nuevos que calcula una **petición** entera (todas sus preguntas); agotado, L2 no opina |

Las longitudes son bytes UTF-8, no caracteres (en el OpenAPI, `x-max-bytes`; `maxLength` contaría caracteres).

### Nonce
Misma petición y mismo `nonce`: devuelve el resultado guardado sin decidir otra vez (`ms` incluido).
La clave es `nonce + estado + esquema + id`. Con otro estado u otra pregunta, se recalcula. Sin `nonce` no se guarda. Tampoco se guarda la respuesta de una pregunta de una petición cancelada ni la de una cuyas capas fallaron: el reintento decide de nuevo.
El LRU tiene `cache_respuestas` entradas.

### Límites
Constantes de [`server/decide/http.go`](../server/decide/http.go):

| Límite | Valor |
|---|---|
| `MaxCuerpo` | 1 MiB |
| `MaxPreguntas` | 256 por petición |
| `MaxOpciones` | 256 por pregunta (clinc150 trae 150 clases, 151 con `escalate`) |
| `MaxEstadoByte` | 256 KiB |

### Qué identifica a un esquema en las cachés
- **ESQUEMAS/CONJ (torres precalculadas en el `.chispa`)**: clave `HashEsquema(question, ids de opciones)`. **No** entran la `description` de las opciones ni el `kind`. Consecuencias: (a) si llega la misma pregunta con los mismos ids pero otras descripciones, L2 usa las torres precalculadas y no las descripciones nuevas; (b) un `choice` y un `score` con la misma pregunta e ids comparten clave. Para que L2 vea unas descripciones nuevas hay que usar otro texto de pregunta u otros ids. La clave es la del formato `.chispa` v3 y no cambia en esta versión.
- **Torres al vuelo (sección `TORR`)**: la clave sí incluye la descripción (`HashEsquema(question, [id, description])`, una por opción).
- **Caché de L1 (embeddings de opciones por esquema)** y **nonce**: ver `cache_esquemas` y `cache_respuestas` más abajo.

## Valores de `layer`
`L0`, `L1`, `L2`, `L3` y `escalar` (cuando `escalate` es true). El audio (`A1`) no entra por `/v1/decide`; ver `audio/README.md`.

## `GET /healthz`
```
{"status":"ok"}
```
Dice que el proceso responde. No dice qué capas están cargadas.

## `GET /metrics`
Texto Prometheus, escrito a mano. Series:

| Serie | Qué cuenta |
|---|---|
| `chispa_peticiones_total{codigo}` | peticiones por código HTTP |
| `chispa_preguntas_total` | preguntas decididas |
| `chispa_decididas_total{capa}` | preguntas contestadas por cada capa |
| `chispa_escalados_total` | preguntas escaladas |
| `chispa_capa_latencia_segundos` | histograma por capa |
| `chispa_capa_errores_total{capa}` | fallos internos de capa |
| `chispa_cache_esquemas_total{resultado}` | aciertos y fallos de la caché de esquemas |
| `chispa_cache_nonce_aciertos_total` | respuestas servidas por nonce |
| `chispa_auth_rechazos_total` | 401 de `/v1/decide` (clave ausente o mala); con `api_keys` |
| `chispa_clave_peticiones_total{clave,resultado}` | peticiones por **id** de clave (nunca la clave): `ok` o `limitada` (429) |

Tras una petición válida y una rota, el test de métricas
([`decide_test.go`](../server/decide/decide_test.go)) espera líneas como `chispa_peticiones_total{codigo="200"} 1`,
`chispa_peticiones_total{codigo="400"} 1` y `chispa_decididas_total{capa="L0"} 1`.

## Configuración (`-config`)
```json
{"capas": [{"nombre":"L0","tau":0.8},{"nombre":"L1","tau":0.8},{"nombre":"L2","tau":0.7},{"nombre":"L3","tau":0.6}],
 "modelos": ["testdata/intencion.chispa"], "cache_esquemas": 1024, "cache_respuestas": 4096}
```
El servidor valida la config al arrancar: una clave desconocida o mal escrita (también dentro de `limites`) es un error que nombra la clave, no se ignora.

`api_keys` (opcional): lista de claves de API de `/v1/decide`. Cada una es `{"id","hash_sha256","rps","rafaga"}`:

```json
"api_keys": [{"id": "piloto-banco", "hash_sha256": "<64 hex>", "rps": 20, "rafaga": 40}]
```
`id` (único) es la etiqueta de las métricas; `hash_sha256` es el SHA-256 de la clave en hex (se genera con `chispa-server -hash-clave`, ver
[06-despliegue.md](06-despliegue.md#claves-de-api)); `rps` > 0 y `rafaga` ≥ 0 (0 = `ceil(rps)`). Una clave en claro o un campo desconocido
dentro de la lista falla el arranque como cualquier clave desconocida. Vacío o ausente = sin autenticación. Se releen en cada recarga (SIGHUP o `/v1/admin/recargar`),
así que se rotan sin reiniciar; los cubos empiezan llenos tras una recarga.

Con `-modelo` y sin `-config`, el τ de L1 y L2 sale de `CALIB`. Con `-config`, manda la config.

`tau_l2_esquema_nuevo` (opcional, en [0,1]): τ de L2 solo para las preguntas cuyas torres no están en `ESQUEMAS` y salen al vuelo (sección `TORR`);
las que L2 conoce siguen con el τ de L2 de siempre. Ausente, no cambia nada. Si falta aquí se toma del campo
`tau_l2_esquema_nuevo` de `CALIB` (`chispa train --tau-l2-esquema-nuevo`), haya o no `-config` (la config no lo desactiva); si viene en la config, manda la config. Ojo: el de `CALIB` se calibró contra el τ base de `CALIB`, no contra el de la config. Es interno: la respuesta JSON no cambia.
