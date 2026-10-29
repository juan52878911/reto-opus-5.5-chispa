# API HTTP

Tres rutas. Fuente del contrato: [`server/README.md`](../server/README.md#contrato) y [`server/decide/http.go`](../server/decide/http.go).

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
| `state` | texto que se clasifica; el mismo para todas las preguntas; ≤ 256 KiB |
| `questions` | de 1 a 256 |
| `questions[].id` | obligatorio; único en la petición |
| `questions[].question` | obligatorio |
| `questions[].kind` | `choice`, `score` o `noul` |
| `questions[].options` | `choice`: ≥ 2 y ≤ 256, con `id` único y `description` opcional. `score`: ≥ 2, ids `"1"` … `"K"`. `noul`: opcional; si va, solo `"false"` y `"true"` |
| `questions[].nonce` | opcional; clave de idempotencia |

Los campos desconocidos dan 400.

**El esquema viaja en la petición.** `question`, `kind` y las `options` con su `description` son el esquema completo; el servidor
no exige un `.chispa` entrenado para él. Un esquema nuevo lo decide hoy L1 y L2 con torre al vuelo está **(en desarrollo)**
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
- `layer`: la capa que contestó. Si `escalate` es true, la última de la cascada.
- `escalate`: ninguna capa llegó a su τ. `answer` y `probs` son entonces la mejor pista, o `""` y `{}` si nadie opinó.
- `ms`: tiempo de la cascada para esa pregunta. `nonce` vuelve tal cual.

Con `noul` y `score` ([`noul_score_escala.req.json`](../server/decide/testdata/noul_score_escala.req.json) y
[`resp`](../server/decide/testdata/noul_score_escala.resp.json)):

```json
{"results": [
  {"id":"n1","kind":"noul","answer":"false","probs":{"false":0.9,"true":0.1},"layer":"L0","escalate":false,"ms":0},
  {"id":"s1","kind":"score","answer":"1","probs":{"1":0.4,"2":0.6},"layer":"L3","escalate":true,"ms":0}
]}
```
Este segundo ejemplo sale de un test con capas falsas: muestra el formato de un escalado, no cifras reales.

### Errores
`{"error": "..."}` con la ruta del campo. Ejemplo real
([`kind_invalido_400.resp.json`](../server/decide/testdata/kind_invalido_400.resp.json)):

```json
{"error": "questions[0].kind: \"raro\" no válido (choice, score o noul)"}
```

| Código | Cuándo |
|---|---|
| 400 | JSON no válido, campo desconocido o regla incumplida |
| 405 | método distinto de POST |
| 413 | cuerpo de más de 1 MiB |

La validación es todo o nada: una pregunta mala rechaza la petición entera. Un fallo interno de una capa solo salta esa capa
(cuenta en `chispa_capa_errores_total`).

### Nonce
Misma petición y mismo `nonce`: devuelve el resultado guardado sin decidir otra vez (`ms` incluido).
La clave es `nonce + estado + esquema + id`. Con otro estado u otra pregunta, se recalcula. Sin `nonce` no se guarda.
El LRU tiene `cache_respuestas` entradas.

### Límites
Constantes de [`server/decide/http.go`](../server/decide/http.go):

| Límite | Valor |
|---|---|
| `MaxCuerpo` | 1 MiB |
| `MaxPreguntas` | 256 por petición |
| `MaxOpciones` | 256 por pregunta (clinc150 trae 150 clases, 151 con `escalate`) |
| `MaxEstadoByte` | 256 KiB |

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

Tras una petición válida y una rota, el test de métricas
([`decide_test.go`](../server/decide/decide_test.go)) espera líneas como `chispa_peticiones_total{codigo="200"} 1`,
`chispa_peticiones_total{codigo="400"} 1` y `chispa_decididas_total{capa="L0"} 1`.

## Configuración (`-config`)
```json
{"capas": [{"nombre":"L0","tau":0.8},{"nombre":"L1","tau":0.8},{"nombre":"L2","tau":0.7},{"nombre":"L3","tau":0.6}],
 "modelos": ["testdata/intencion.chispa"], "cache_esquemas": 1024, "cache_respuestas": 4096}
```
Con `-modelo` y sin `-config`, el τ de L1 y L2 sale de `CALIB`. Con `-config`, manda la config.
