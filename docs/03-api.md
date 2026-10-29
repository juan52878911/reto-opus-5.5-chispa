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
| `questions[].kind` | `choice`, `score`, `noul` o `multi` |
| `questions[].options` | `choice`: ≥ 2 y ≤ 256, con `id` único y `description` opcional. `score`: ≥ 2; el servidor no exige ids concretos: L0 y L1 aceptan ids libres, y la cabeza CORAL de L2 solo opina si los ids son `"1"` … `"K"` en orden. `multi`: ≥ 2 y ≤ 256, con `id` único y `description` opcional; cada opción es una etiqueta que puede estar activa o no. `noul`: opcional; si va, solo `"false"` y `"true"` |
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
- `answer`: el id de la opción elegida (en `multi`, la activa de mayor probabilidad, o `""` si no hay ninguna).
- `answers`: **solo en `multi`** (y siempre en `multi`): los ids de las opciones activas, en el orden de la pregunta; `[]` si ninguna. Campo aditivo: los demás tipos no lo llevan.
- `probs`: probabilidad calibrada de cada opción, la de la capa que respondió. Suman 1 en `choice`, `score` y `noul`; en `multi` cada opción lleva la suya, en [0, 1], y **no** suman 1.
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
- **L0:** el clasificador entrenado con los ejemplos; `probs` es su distribución sobre los niveles y `answer` la **mediana**, como en L1 y L2.
- **L3:** `answer` es la mediana de las `probs` normalizadas.

En todos los casos, la confianza que se compara con τ es la probabilidad de `answer` en `probs`.

### Un ejemplo por tipo
Petición y respuesta de cada `kind` (la de `multi` está también en [`openapi.yaml`](../server/api/openapi.yaml), validada contra su esquema por `server/decide/contrato_test.go`):

```json
{"id":"u1","kind":"choice","answer":"alta","probs":{"alta":0.9,"baja":0.1},"layer":"L1","escalate":false,"ms":0.3}
{"id":"n1","kind":"noul","answer":"true","probs":{"false":0.1,"true":0.9},"layer":"L1","escalate":false,"ms":0.2}
{"id":"s1","kind":"score","answer":"2","probs":{"1":0.1,"2":0.6,"3":0.3},"layer":"L1","escalate":false,"ms":0.3}
{"id":"t1","kind":"multi","answer":"cobro","answers":["cobro","atencion"],"probs":{"cobro":0.93,"atencion":0.81,"fraude":0.07},"layer":"L1","escalate":false,"ms":0.5}
```

La petición de `multi` es la de `choice` con `"kind": "multi"`:

```json
{"state":"Me cobraron dos veces y nadie contesta el telefono","questions":[{"id":"t1","question":"Que temas toca el mensaje?","kind":"multi",
  "options":[{"id":"cobro","description":"Habla de un cobro"},{"id":"atencion","description":"Se queja de la atencion"},{"id":"fraude","description":"Sospecha de fraude"}]}]}
```

### `multi`: varias etiquetas a la vez
Cada opción es un sí/no **independiente** sobre «pregunta · opción · descripción».

- **Cómo puntúa:** L1 usa el coseno entre el mensaje y la opción; L2, el MaxSim contra la torre de **esa** opción (una por opción, como en `choice`, y al vuelo con `TORR`). Cada una pasa por su sigmoide σ(a·s + b) con θ propio: `probs[id]` es esa p y la opción está activa si p ≥ θ.
- **Calibración:** `CALIB.tipos["multi@<hash>"]` trae (a, b, θ) de todas las opciones del esquema (`<hash>` = HashEsquema2 de pregunta, kind y opciones con descripción, en hex); `multi@<hash>#<id>` los de una opción (θ por opción). Los ficheros antiguos sin claves con `@` siguen usando `multi` y `multi#<id>`. Si L1 no encuentra ninguna, usa la calibración de `noul` como aproximación y, sin ninguna, la de por defecto (a = 4, b = −2, θ = 0,5). Zero-shot va, pues, sin calibrar para `multi` hasta que `chispa train` con ejemplos ajuste `multi@…`.
- **L2 en `multi` solo opina con `multi_l2@<hash>`** (y `multi_l2@<hash>#<id>`) en `CALIB` (en `tipos_l2` si el fichero lo trae, si no en `tipos`): el MaxSim de L2 tiene otra escala que el coseno de L1 y con la calibración de `noul` marcaría activas casi todas las opciones. Sin esas claves L2 **no opina** (confianza 0, aviso en el log) y la cascada escala. **`chispa train` hoy no calibra `multi_l2@…`** (no tiene tokenizador ni ONNX de L2): solo lo escribe un exportador de modelos que calibre L2 (o `multi.escribir_calib` con `maxsim_l2`), y va a `tipos_l2`. Con un `.chispa` entrenado por `chispa train`, en `multi` decide L1 (o L3, si está) y, si L1 no llega a τ, escala. Recomendación: fija en `multi` un τ de L1 propio (la `CALIB` de `multi@…` o `-config`) en vez de uno conservador pensado para `choice`; si no, casi toda pregunta `multi` escalará.
- **Servidor mínimo:** los ficheros con claves `multi@…` o `multi_l2@…` piden un servidor con la CALIB por esquema (commit `5b00084` o posterior). Uno anterior abre el fichero, **ignora en silencio** esas claves (solo busca `multi#<id>` y `multi`) y multi cae a la calibración de `noul`; no hay error. Ver [04](04-formato-chispa.md#claves-de-calib).
- **Confianza (la que se compara con τ):** la de la opción más dudosa, el mínimo de p (si está activa) o 1 − p (si no). Una capa solo acepta la respuesta si **todas** sus decisiones superan τ; si no, se pasa a la siguiente y, al final, escala.
- **Ninguna activa** es una respuesta válida: `answers: []`, `answer: ""` y `escalate: false`. Lo que sí es «sin respuesta» es `escalate: true` con `probs: {}`, y solo ocurre si ninguna capa opinó. Si alguna opinó pero ninguna llegó a su τ, `escalate: true` lleva la mejor pista: `answers` y `probs` (una p por opción) de la capa de mayor confianza, como en `choice`.
- **L0 no opina en `multi`**: el L0 entrenado es multiclase (probabilidades que suman 1) y no da una p por opción. Aunque haya un modelo con las mismas etiquetas, el servidor no lo usa para `multi`.

### Qué devuelve cada capa
Probabilidades en `probs` y respuesta por tipo y capa. «Zero-shot» es un esquema que solo llega en la petición; «few-shot» es un `.chispa` entrenado con pocos ejemplos (`chispa train --ejemplos`).

| Tipo | L0 | L1 (zero-shot y few-shot) | L2 / L2c | L3 (opcional) |
|---|---|---|---|---|
| `choice` | few-shot (≥ 10 por opción): softmax del modelo, suma 1. Zero-shot: no opina | softmax(cos / T), suma 1 | softmax(MaxSim / T), suma 1; con `CONJ` (L2c) la cabeza conjunta, suma 1 | normalizada, suma 1 |
| `noul` | few-shot: modelo `false`/`true`, suma 1. Zero-shot: no opina | σ(a·cos + b) con θ; `true` y `false` suman 1 | σ(a·MaxSim + b) con θ, suma 1 | normalizada, suma 1 |
| `score` | few-shot: distribución del modelo sobre los niveles, suma 1; `answer` = mediana. Zero-shot: no opina | softmax sobre los niveles en el orden de la pregunta, suma 1; `answer` = mediana | CORAL, solo con ids `"1"`…`"K"` en orden y `scoreK` en `CALIB`; si no, no opina. Suma 1 (se normaliza); `answer` = mediana | normalizada; `answer` = mediana |
| `multi` | **no opina** (el L0 es multiclase) | σ(a·cos + b) por opción con θ por opción; una p en [0,1] por opción | **solo con `multi_l2@<hash>` en `CALIB`** (σ(a·MaxSim + b) por opción, torre por opción); sin ella no opina y `chispa train` no la escribe | p por opción, sin normalizar |

«No opina» significa confianza 0: la cascada pasa a la siguiente capa. Con `SOPL1` (few-shot), L1 mezcla el prototipo de cada opción con la media de sus ejemplos en `choice`, `noul` y `score`. **En `multi` se ignora por defecto**: `chispa train` quita `l1_lambda_calib` de la CALIB de multi (se calibró con los prototipos de la descripción, sin encogimiento) y el servidor avisa de ello.

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
{"error": {"code": "invalid_kind", "message": "questions[0].kind: \"raro\" no válido (choice, score, noul o multi)", "question_id": "1"}}
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
| 400 | `missing_kind` / `invalid_kind` | `kind` ausente / distinto de `choice`, `score`, `noul`, `multi` |
| 400 | `too_few_options` | `choice`, `score` o `multi` con menos de 2 opciones |
| 400 | `too_many_options` | más de `max_opciones` |
| 400 | `invalid_options` | `noul` con opciones distintas de `false` y `true` |
| 400 | `missing_option_id` / `duplicate_option_id` | opción sin `id` / `id` repetido |
| 400 | `field_too_long` | `question`, `description`, un `id` o el `nonce` por encima de `max_texto` / `max_id` |
| 400 | `invalid_characters` | `question`, el `id` o la `description` de una opción con los caracteres de control U+001D–U+001F (separadores del hash del esquema) |
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

## L3: escalado opcional a un LLM
Apagada por defecto. Con la sección `l3` en la config, lo que L0, L1 y L2 no resuelven (confianza < su τ) se manda a un endpoint
compatible con OpenAI (`POST {url}/chat/completions`) y la respuesta mantiene el contrato: `layer: "L3"`, `answer` y `probs`
normalizadas (suma 1) por opción, para `choice`, `noul` (`false`/`true`) y `score` (`answer` = mediana, como en L1 y L2). En `multi` el LLM da una probabilidad independiente por opción (no se normaliza: cada una en [0,1], y deben venir todas); se activan las de p ≥ 0,5.

```json
"l3": {"url": "http://127.0.0.1:11434/v1", "modelo": "qwen3:4b-instruct", "api_key_env": "CHISPA_L3_CLAVE",
       "timeout": "10s", "max_por_peticion": 8, "tau": 0.6}
```
| Clave | Efecto |
|---|---|
| `url`, `modelo` | Obligatorios. `url` es la base (se añade `/chat/completions`); http o https |
| `api_key_env` | Nombre de la variable de entorno con la clave (`Authorization: Bearer`). La clave no va en la config; si el nombre está y la variable vacía, el arranque falla. Ollama no la necesita |
| `timeout` | Plazo de cada llamada: `"10s"` o segundos. 0/ausente = 10 s. Al vencer, L3 no opina y la pregunta sigue escalada (`chispa_l3_llamadas_total{resultado="timeout"}`, `chispa_capa_errores_total{capa="L3"}`) |
| `max_por_peticion` | Llamadas al LLM que una petición HTTP puede hacer entre todas sus preguntas. 0/ausente = 8. Pasado el tope, las preguntas restantes quedan escaladas sin llamar |
| `tau` | τ de L3; si falta, el de la capa `"L3"` de `capas` (0,60 por defecto). `capas` debe seguir incluyendo `"L3"` |

Qué se manda al LLM: un mensaje de sistema fijo y uno de usuario con un JSON `{"pregunta","tipo","opciones":[{"id","descripcion"}],"texto"}` (temperatura 0, `response_format: json_object`, `stream: false`).
Qué se espera: `{"probs": {"<id>": <p>, ...}}`. Se acepta con vallas ```` ``` ```` o texto alrededor; se valida (solo ids de las opciones, números finitos ≥ 0, suma > 0), las opciones que falten valen 0 y se normaliza a suma 1. Si no cumple, **L3 no opina** (sin error) y la respuesta queda `escalar`. Un fallo del endpoint (red, timeout, no 2xx) deja la respuesta igual y no se guarda bajo el `nonce`.

Límites que conviene saber: (1) las probabilidades de un LLM son **autodeclaradas, no calibradas**: τ de L3 no se ha calibrado contra datos y debe ajustarse con tráfico propio antes de fiarse de `escalate: false`; (2) no se usan `logprobs`: el contrato por opción se obtiene del JSON, que funciona igual en cualquier endpoint; (3) la caché de esquemas y las torres no intervienen: cada pregunta escalada es una llamada nueva (salvo un `nonce` repetido). **Privacidad:** el `state` y el esquema de las preguntas escaladas salen del servidor hacia el endpoint configurado; Chispa no los registra, pero el endpoint sí puede. Con Ollama local no salen de la máquina ([06-despliegue.md](06-despliegue.md#l3-ollama-local-o-un-llm-remoto)).

## Valores de `layer`
`L0`, `L1`, `L2`, `L3` y `escalar` (cuando `escalate` es true). `L3` solo sale si el servidor tiene la sección `l3` en la config (ver [L3](#l3-escalado-opcional-a-un-llm)); sin ella, L3 no opina nunca. El audio (`A1`) no entra por `/v1/decide`; ver `audio/README.md`.

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
| `chispa_l3_llamadas_total{resultado}` | llamadas de L3 al LLM: `ok`, `invalida` (respuesta que no sirve; L3 no opina), `error`, `timeout`, `presupuesto` (tope por petición agotado; no se llamó). Sin L3, todo 0 |
| `chispa_l3_latencia_segundos` | histograma de la latencia de cada llamada al LLM |

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

`l1_shrinkage_lambda` / `l1_shrinkage_apagado` / `l2_shrinkage_lambda` (soporte few-shot, sección `SOPL1`; sin ella no hacen nada):
- `l1_shrinkage_lambda` (número ≥ 0): **ausente = 4**; un valor explícito manda (0 = solo ejemplos, muy grande = solo descripción). Medido en `model/l2/resultados/barrido-20261029/LEEME.md` (rama de modelos; G.8b, checkpoint de G.8): con `l1_shrinkage_lambda` = 4 frente a sin soporte: massive 0,395 frente a 0,266, inyecciones 0,740 frente a 0,326, hatecheck 0,492 frente a 0,224; en JevBench cuesta 2 puntos (0,379 frente a 0,398).
- Apagado explícito de L1 (el comportamiento de antes del default): `"l1_shrinkage_apagado": true`. Es un booleano y no `null` porque `null` y ausente son indistinguibles para un número opcional; así el apagado queda escrito y la config estricta no cambia. Junto con `l1_shrinkage_lambda` es error de arranque.
- `l2_shrinkage_lambda`: **sin cambio**, ausente = apagado. El soporte de L2 solo entra por `CONJ` y se midió así.
- Con el default activo, un `SOPL1` ilegible no impide arrancar (se ignora con aviso); con un λ explícito sí es error. El τ de `CALIB` se calibró sin el encogimiento.

Con `-modelo` y sin `-config`, el τ de L1 sale de `CALIB.tau_escalate` y el de L2 de `CALIB.tau_escalate_l2` (si falta, `tau_escalate`; con `CONJ`, `tau_l2c` manda). L2 y L2c leen sus parámetros de `CALIB.tipos_l2` si existe y, si no, de `tipos`; L1 siempre de `tipos` (ver [04](04-formato-chispa.md#espacio-de-nombres-de-l2-en-calib)). Con `-config`, manda la config.

`tau_l2_esquema_nuevo` (opcional, en [0,1]): τ de L2 solo para las preguntas cuyas torres no están en `ESQUEMAS` y salen al vuelo (sección `TORR`);
las que L2 conoce siguen con el τ de L2 de siempre. **Default 0,846.** Prioridad: la config > el campo `tau_l2_esquema_nuevo` de `CALIB` (`chispa train --tau-l2-esquema-nuevo`), que se toma haya o no `-config` > 0,846. `"tau_l2_esquema_nuevo_apagado": true` vuelve a «sin τ propio» (L2 usa su τ de siempre) e ignora también `CALIB`; apagado + `tau_l2_esquema_nuevo` es error de arranque. Ojo: el de `CALIB` se calibró contra el τ base de `CALIB`, no contra el de la config. Es interno: la respuesta JSON no cambia. Medido sobre tareas no vistas (`model/l2/resultados/barrido-20261029/LEEME.md`, rama de modelos; G.8b, checkpoint de G.8): τ = 0,846 da precisión 0,95 con ~97 % de escalado; τ = 0,276 escala ≤ 20 % con precisión ~0,53. Se eligió 0,846 como default por prudente: ante un esquema que L2 no ha visto, prefiere escalar a acertar a medias (decisión del dueño del producto); 0,276 queda como alternativa si se prioriza no escalar.
