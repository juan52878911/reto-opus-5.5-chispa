# Servidor de Chispa (T4.1)

`POST /v1/decide` decide preguntas con una cascada de capas: L0 (Chispa lineal real, `pkg/chispa`
de kindling v0.17.0), L1 real (embedding estático de `runtime/l1`), L2 (ONNX, solo con la etiqueta `ort`) y L3 (un LLM
opcional, ver «L3»). Las capas sin sección en el modelo, y L3 sin config, son stubs «sin opinión» (confianza 0).
Tipos soportados: `choice`, `score`, `noul` y `multi` (ver la tabla de abajo). Esquema de preguntas: `model/esquema.md`;
contrato completo en [`docs/03-api.md`](../docs/03-api.md) y [`api/openapi.yaml`](api/openapi.yaml).

```
make -C server test     # go vet + go test -race
make -C server bench    # benchmarks (1 y 4 núcleos)
make -C server serve    # arranca con testdata/config.json (3 modelos de prueba)
make -C server carga    # generador de carga contra :8090
```

Módulos locales por `replace` en `go.mod`: `../format/chispa3` y `../runtime/l1` (sin red).
Sin red: `GOFLAGS=-mod=mod GOPROXY=off` (ya puesto en el Makefile). `go.sum` es el de `arena/`.

## Contrato

### Entrada
```json
{
  "state": "texto que se clasifica",
  "questions": [
    {"id": "u1", "question": "¿Qué tan urgente es?", "kind": "choice",
     "options": [{"id": "alta", "description": "Requiere atención inmediata"}, {"id": "baja"}],
     "nonce": "abc-1"}
  ]
}
```
- `state` (string, ≤ 256 KiB): el texto. Es el mismo para todas las preguntas de la petición.
- `questions` (1..256). Cada una: `id` (obligatorio, único en la petición), `question` (obligatorio),
  `kind` ∈ `choice|score|noul|multi`, `options` y `nonce` (opcional).
  - `choice`: ≥ 2 opciones (≤ 256; clinc150 trae 150) con `id` único y `description` opcional.
  - `score`: ≥ 2 opciones ordinales, ids `"1"…"K"`.
  - `noul`: opciones opcionales; si van, solo `"false"` y `"true"`. Por defecto las dos.
  - `multi` (multietiqueta): ≥ 2 opciones (≤ 256) con `id` único; cada una es una etiqueta que puede estar activa o no.
- Cuerpo ≤ 1 MiB; campos desconocidos → 400.

### Salida (200)
```json
{"results": [
  {"id": "u1", "kind": "choice", "answer": "alta", "probs": {"alta": 0.9, "baja": 0.1},
   "layer": "L0", "escalate": false, "ms": 0.012, "nonce": "abc-1"}
]}
```
- `answer`: id de la opción elegida (en `noul`, `"true"`/`"false"`; en `score`, `"1"…"K"`; en `multi`, la activa de mayor probabilidad, o `""` si no hay ninguna).
- `answers`: **solo en `multi`**: los ids de las opciones activas (p ≥ θ de la opción), en el orden de la pregunta; `[]` si ninguna
  (respuesta válida, con `escalate: false`).
- `probs`: id de opción → probabilidad calibrada (la de la capa que respondió). Suman 1 salvo en `multi`, donde cada opción lleva la suya en [0, 1].
- `layer`: la capa que contestó; si `escalate` es true, `"escalar"` (ninguna capa aceptó; `answer` y `probs` son la mejor respuesta vista).
- `escalate`: ninguna capa llegó a su τ. `answer`/`probs` son entonces la mejor pista vista
  (la capa con más confianza) y quedan vacíos (`""`, `{}`) si ninguna opinó.
- `ms`: tiempo de la cascada para esa pregunta. `nonce` se devuelve tal cual.
- Los resultados van en el orden de `questions`.

### Errores
`400 {"error": {"code": "invalid_kind", "message": "...", "question_id": "..."}}`: errores tipados, con la ruta del campo en `message` (`questions[2].kind: "raro" no válido (choice, score, noul o multi)`). Lista de códigos en [`docs/03-api.md`](../docs/03-api.md) y [`api/openapi.yaml`](api/openapi.yaml).
También 405 (método ≠ POST) y 413 (cuerpo > 1 MiB). No hay errores por pregunta: la validación es
todo o nada, y un fallo interno de una capa solo la salta (se cuenta en `chispa_capa_errores_total`).

### Nonce
Clave de idempotencia: la misma petición con el mismo `nonce` devuelve el resultado guardado sin
volver a decidir (`ms` incluido). La clave es `nonce + estado + esquema + id`: el mismo nonce con
otro estado o pregunta se recalcula. Sin `nonce` no se cachea. LRU de `cache_respuestas` entradas.

### Cascada
L0 → L1 → L2 → L3: se pasa a la siguiente mientras la confianza top-1 (en `multi`, la de la opción más dudosa) sea < τ de la capa (una capa
sin opinión o con error vale 0). Con confianza ≥ τ responde esa capa. Si la última no llega,
`escalate: true`. Capas y τ se leen del JSON de configuración (`-config`):

```json
{"capas": [{"nombre":"L0","tau":0.8},{"nombre":"L1","tau":0.8},{"nombre":"L2","tau":0.7},{"nombre":"L3","tau":0.6}],
 "modelos": ["testdata/intencion.chispa"], "cache_esquemas": 1024, "cache_respuestas": 4096}
```
Interfaz por capa: `type Decisor interface { Decidir(ctx, Pregunta) (Respuesta, error); Nombre() string }`
(`decide/types.go`). Para sustituir un stub basta pasar otro `Decisor` con el mismo nombre en `main.go`.

### Tipos soportados y qué capa opina en cada uno
| `kind` | L0 | L1 | L2 | L3 |
|---|---|---|---|---|
| `choice` | sí, si hay un modelo con las mismas etiquetas | softmax(coseno / T) | MaxSim contra la torre de cada opción, softmax | un LLM reparte la probabilidad entre opciones |
| `noul` | ídem | σ(a·coseno + b) sobre la opción `true` | σ(a·MaxSim + b) | ídem |
| `score` | ídem | softmax sobre los niveles; `answer` = nivel mediano | CORAL (solo con ids `"1"…"K"`) | ídem |
| `multi` | **no opina** (el L0 es multiclase) | σ(a·coseno + b) por opción, θ por opción | σ(a·MaxSim + b) por opción, una torre por opción | una p independiente por opción (se activan las de p ≥ 0,5) |

En `multi`, una capa solo acepta si **todas** sus decisiones por opción superan τ (confianza = la de la opción más dudosa: el mínimo de
p si está activa o 1 − p si no); si no, pasa a la siguiente y al final escala (`escalate: true`, `probs: {}`). Calibración en
`CALIB.tipos.multi` y `multi#<id>`; detalle en [`docs/03-api.md`](../docs/03-api.md).

### Esquemas nuevos: τ y λ
- **τ de esquema nuevo** (`tau_l2_esquema_nuevo`): τ de L2 solo para preguntas cuyas torres **no estaban** en `ESQUEMAS` (salieron al vuelo desde la
  sección `TORR`). Prioridad: la config > `tau_l2_esquema_nuevo` de `CALIB` (cuenta aunque haya `-config`) > 0,846 por defecto (precisión ≈ 0,95 con ≈ 97 % de escalado en tareas
  no vistas). `"tau_l2_esquema_nuevo_apagado": true` vuelve al τ normal de L2 (junto a un valor, error). Métricas: `chispa_esquema_nuevo_preguntas_total`,
  `chispa_esquema_nuevo_decididas_total`. Las torres al vuelo se cachean (`cache_torres`, por defecto 16384) y una petición calcula como mucho
  `max_torres_nuevas` (por defecto 256) sin cachear (el `.chispa` de `-modelo` puede pesar hasta `max_fichero` bytes, 1 GiB por defecto); si el tope corta, cachea las que caben y escala con `sin_presupuesto_torres` (`chispa_torres_*`).
- **λ** (`l1_shrinkage_lambda`, `l2_shrinkage_lambda`): encogimiento del soporte few-shot (sección `SOPL1`): w = k/(k+λ) mezcla la media de los k ejemplos con el
  prototipo de la descripción. L1: por defecto 4; `"l1_shrinkage_apagado": true` lo apaga. L2: sin valor, no hay mezcla (λ = ∞). Sin `SOPL1` en el `.chispa` no tiene efecto.
  Un λ negativo es error de config. Con `-config` hay que repetir los de `CALIB` que se quieran conservar.

### L3 (LLM opcional)
Con `"l3": {...}` en la config **y** una capa `"L3"` en `capas`, las preguntas que L0–L2 no resolvieron se mandan a un endpoint compatible con OpenAI
(`POST {url}/chat/completions`, p. ej. Ollama en `http://127.0.0.1:11434/v1`). Pide un JSON estricto con una probabilidad por opción, lo valida y lo normaliza (en `multi`
no normaliza y deben venir todas); si la respuesta no sirve, L3 no opina y la pregunta escala.
Campos de `l3`: `url`, `modelo`, `api_key_env` (nombre de la variable de entorno con la clave: nunca la clave en la config; si la variable está vacía, falla al armar),
`timeout` (`"10s"` o segundos; por defecto 10 s), `max_por_peticion` (llamadas al LLM por petición HTTP; por defecto 8) y `tau` (si falta, el de la capa `L3`).
**Los textos del cliente salen del servidor hacia ese endpoint**; L3 no los registra. Métrica: `chispa_l3_llamadas_total`.

### Flags de `chispa-server`
| flag | por defecto | uso |
|---|---|---|
| `-addr` | `127.0.0.1:8090` | dirección de escucha |
| `-config` | — | JSON de configuración (capas, τ, modelos, cachés, claves, L3) |
| `-modelo` | — | `.chispa` v3 (o v2 envuelto) del que armar L0, L1 y L2 |
| `-tok` | — | `.chispa-tok` de e5; sin él, L2 queda en stub |
| `-ort-lib` | — | `libonnxruntime.so` (precede a `CHISPA_ORT_LIB`) |
| `-timeout` | `30s` | tope por petición (503 `timeout` con `Retry-After`); 0 = sin tope |
| `-max-conexiones` | `1024` | conexiones TCP abiertas a la vez (0 = sin tope) |
| `-max-en-curso` | `64` | peticiones a `/v1/decide` en curso (0 = sin tope); al llenarse, 429 `rate_limited` |
| `-plazo-cuerpo` | `0` (= 10 s) | plazo para recibir el cuerpo de `/v1/decide`; negativo = sin plazo |
| `-pre-drenaje` | `0` | tras SIGTERM/SIGINT, `/healthz` responde 503 `shutting_down` este tiempo antes de apagar |
| `-apagado` | `25s` | plazo para terminar las peticiones en vuelo tras SIGTERM/SIGINT |
| `-abierto` | `false` | permite escuchar fuera de loopback sin `api_keys` (o `api_keys_abierto` en la config) |
| `-admin-addr` | — | listener aparte para `POST /v1/admin/recargar` (la pública deja de servirla: 404) |
| `-metricas-protegidas` | `false` | `/metrics` exige `Authorization: Bearer` con una api_key válida (o el `admin_token`) |
| `-hash-clave` | `false` | lee una clave de la entrada estándar, imprime su SHA-256 y sale |

### Claves de API
Con `api_keys` no vacío en la config, `/v1/decide` exige `Authorization: Bearer <clave>` (401 `unauthorized` si falta o no vale) y limita por clave con un cubo
de fichas (429 `rate_limited` con `Retry-After`). Cada entrada: `{"id": "cliente-a", "hash_sha256": "<64 hex>", "rps": 20, "rafaga": 40}`; el servidor solo guarda el SHA-256,
nunca la clave en claro: `printf '%s' "$CLAVE" | chispa-server -hash-clave`. `id` (`[A-Za-z0-9_.-]`, ≤ 64) es la etiqueta de las métricas (`chispa_clave_peticiones_total`,
`chispa_auth_rechazos_total`), nunca el secreto. `rafaga` 0 = ⌈rps⌉. Escuchar fuera de loopback sin claves exige `-abierto` o `api_keys_abierto`; una recarga sin claves
tampoco las quita sin `api_keys_abierto`.

### Recarga en caliente
Dos formas, ambas sin cortar peticiones en curso: `kill -HUP <pid>` o `POST /v1/admin/recargar` con `Authorization: Bearer <admin_token>`
(la ruta solo existe si la config trae `admin_token` —mínimo 32 bytes— o `admin_token_sha256`; si no, 404). Relee la config y el `.chispa`, arma un modelo completo nuevo
(con cachés nuevas: un nonce del modelo anterior no devuelve su respuesta) y lo sustituye cuando está listo; las peticiones que ya corrían terminan con el viejo.
Se relee también `api_keys` (los cubos de las claves que siguen se conservan) y el token de admin. Si algo falla (`.chispa` corrupto, config inválida) se sigue sirviendo el modelo
anterior y se cuenta `chispa_recargas_total{resultado="error"}`. Con `-admin-addr` el endpoint sale del puerto público. Cubierto por `server/e2e/correr.sh` (pasos 5 y 8).

### L0 y caché de esquemas
L0 carga uno o varios `.chispa` y elige el modelo cuyo **conjunto de etiquetas es igual al de ids de las
opciones** (un modelo por esquema; dos modelos con las mismas etiquetas se rechazan al cargar). Sin
modelo para el esquema, L0 no opina. El modelo ve solo `state` (no la pregunta ni las descripciones, y
sin `fields`). La clave de la caché es un hash FNV-128a estable de `kind + question + options`
(ordenadas por id, con descripciones); LRU de `cache_esquemas` entradas que guarda el modelo
resuelto (o «ninguno»). Los LRU están fragmentados en 16: el tamaño es aproximado.

### Otros endpoints
`GET /healthz` → `{"status":"ok"}`. `GET /metrics`: formato de texto Prometheus escrito a mano
(`prometheus/client_golang` no está en la caché de módulos): `chispa_peticiones_total{codigo}`,
`chispa_preguntas_total`, `chispa_decididas_total{capa}`, `chispa_escalados_total`,
`chispa_capa_latencia_segundos` (histograma por capa), `chispa_capa_errores_total{capa}`,
`chispa_cache_esquemas_total{resultado}`, `chispa_cache_nonce_aciertos_total`, y, según el caso, `chispa_recargas_total{resultado}`,
`chispa_torres_*`, `chispa_esquema_nuevo_*`, `chispa_l3_llamadas_total`, `chispa_clave_peticiones_total`, `chispa_auth_rechazos_total`, `chispa_timeouts_total`.

## Relación con `/v1/systemone` de Jev — SUPOSICIÓN, sin verificar
No tengo la especificación de `/v1/systemone`. Lo que supuse, por el encargo:
- Se parece: petición con `state` + lista `questions` de `{id, question, kind, options[{id, description}], nonce?}`,
  y `nonce` devuelto tal cual. Se parecen los tres `kind`.
- **Suposición**: la respuesta es una lista por pregunta con el mismo `id`. Aquí va envuelta en `{"results": [...]}`;
  si systemone devuelve un array desnudo o usa otra clave, hay que cambiar `respuestaHTTP` (`decide/http.go`).
- No se parece / es nuestro: `probs`, `layer`, `escalate`, `ms`, y el 400 todo-o-nada con `{"error": {"code", "message", "question_id"}}`.
  Los nombres de campo de salida (`answer`, `probs`) son los del encargo, no los de Jev.

## Pruebas y modelos de prueba
`decide/testdata/*.req.json|resp.json`: golden del contrato (`go test ./decide -update` los reescribe;
`ms` se normaliza a 0). `testdata/*.chispa` (`intencion`, `injection`, `urgencia`) son los
`*-chispa-words` que entrena la Arena (`arena dataset` + `arena train`, datos sintéticos) copiados tal cual;
el `.gitignore` de `server/` deshace el `*.chispa` de la raíz para ellos.

## Medidas (microVM kindling de 4 vCPU, Xeon 3,3 GHz; cota del i3, no el objetivo)
Modelo `intencion` (4 clases), un mensaje de ~70 caracteres, L1–L3 stubs, caché de esquemas caliente.
Servidor y generador comparten la misma VM (el generador, con GOMAXPROCS 1–2, también consume CPU).

| Prueba | Núcleos del servidor | decisiones/s | p50 | p99 |
|---|---|---|---|---|
| HTTP, 1 pregunta/petición, 8 conexiones | 1 | 2 176 | 2,6 ms | 17,0 ms |
| ídem | 4 | 1 891 | 3,1 ms | 18,8 ms |
| HTTP, 16 preguntas/petición, 8 conexiones | 1 | 11 323 | 9,6 ms | 38,1 ms |
| ídem | 4 | 13 011 | 6,9 ms | 60,2 ms |
| `go test -bench L0` (sin HTTP) | 1 | ~160 k (≈6 µs/op) | | |
| ídem | 4 | ~130 k (≈7–9 µs/op) | | |

Latencias de las filas HTTP: por petición (con 16 preguntas, p50 es de la petición entera).
Los 4 vCPU de la VM **no escalan**: el modelo suelto (`PredictFull` sin caché) hace ≈3,7 µs/op con 1 y
con 4 núcleos, así que «4 núcleos» aquí no es una medida fiable de paralelismo. Medidas ruidosas
(máquina compartida): ±30 % entre repeticiones. El coste lo dominan HTTP/JSON, no L0: con la
petición de 1 pregunta el servidor hace ≈2 k/s por conexión-ciclo; el lote amortiza. El objetivo del
plan (≥ 5 k/s con L1 en el i7) no se puede confirmar desde aquí.

## T4.1b: `--modelo x.chispa` (L1 real y L2)
`chispa-server --modelo x.chispa` abre un `.chispa` v3 (o un v2, que `format/chispa3` envuelve con solo L0) y
arma la cascada con las secciones presentes (`decide.ArmarDesde`); las que faltan quedan como stub.
- **L0**: la sección `L0` se añade a los modelos de `config.modelos`.
- **L1** (`decide/l1.go`, sección `L1` con `runtime/l1`): embedding del mensaje y de `pregunta · opción · descripción`
  de cada opción (cacheados por `ClaveEsquema`, por id de opción: la clave ignora el orden). `choice`: softmax(coseno / T)
  con la `T` de `CALIB.tipos.choice`. `noul`: la consulta es la opción `true`; p(true) = σ(a·coseno + b) con `a`, `b`, θ de
  `CALIB.tipos.noul`. `score`: L1 sí opina: softmax(coseno / T) sobre los niveles (`T` de `CALIB.tipos.score`, o la de choice si falta) y `answer` es el nivel mediano (primero con masa acumulada ≥ 0,5), con su probabilidad como `conf`; una masa repartida entre niveles lejanos baja la confianza y escala. Sin tipo en CALIB: T = 0,05, a = 4, b = −2, θ = 0,5.
- **τ**: sin `--config`, el τ de L1 y L2 es el `tau_escalate` de CALIB; con `--config`, manda la config.
- **L2** (`decide/l2.go` + `l2_ort.go`, secciones `L2` y `ESQUEMAS`): el ONNX da las ranuras S (K×d) del mensaje; la torre de cada
  opción sale de ESQUEMAS (`HashEsquema(pregunta, [id])` en `choice`; la lista completa de ids, `["false","true"]` en `noul`
  y `["1".."K"]` en `score`, para el vector de consulta). Puntuación MaxSim `max_k softplus(h·s_k)`, h = int8·escala;
  luego `choice` softmax(s/T), `noul` σ(a·s+b), `score` CORAL con `scoreK` / `scoreK#j` (`model/l2/README.md`).
  La puntuación (`l2.go`) no depende de ORT y está probada con una sesión falsa; solo `l2_ort.go` toca ONNX Runtime.
  Sin `-tags ort`, `l2_stub.go` devuelve `ErrSinORT` y L2 queda como stub (el servidor avisa en el log).

### T2.6b: L2c, «L2 conjunta» (sección `CONJ`)
Si el `.chispa` trae `CONJ`, `ArmarDesde` monta `L2c` (`decide/l2c.go`) en lugar de L2. Sigue llamándose `L2` en la cascada, la
config y `layer`: mismo contrato `/v1/decide` y misma τ (la de CALIB sin `--config`). La cascada le pasa lo que dijeron las capas
anteriores (`DecisorConPrevias`), y L2c usa las probabilidades de L0 con:
- `a = log P_L0`, `b = simproto` (media sobre las ranuras del mensaje de la similitud máxima con las ranuras del prototipo de la
  clase; prototipos int8 de `CONJ`), `c = log P_L2` con `P_L2 = softmax((MaxSim + β·simproto)/T)` (β y T del modelo, en `CONJ`);
  cada una centrada por fila y dividida por su desviación de train, más las marcas «es la primera de L0 / de L2 / de ambas».
- `softmax(w · [a, b, c, top0, top2, top0·top2])` con los 6 pesos de la cabeza `lr` de `model/l2/conjunta.py`.
- La clave de `CONJ` es `HashEsquema(pregunta, ids ordenados)`: la pregunta debe ser la misma que al entrenar.
- Cae a L2 de siempre (sin tocar la cabeza) si: la pregunta no es `choice`, `CONJ` no tiene ese esquema, L0 no dio
  probabilidades (L0 no tiene modelo para el esquema), o las ranuras no tienen la `d` de los prototipos. Una opción sin clase
  en `CONJ` vale simproto 0, como en Python.
- El codificador va detrás de `Similitudes` (el ONNX y las torres): `l2c_test.go` prueba con similitudes falsas sin ORT.
- **Paridad con Python**: `TestL2cParidadConPython` lee `model/l2/tests/fixtures_conjunta/paridad.json` (lo genera
  `sdk/python/tests/fixture_conjunta.py` con `conjunta.Cabeza`): |Δp| máx 8e-8 en 8 casos (tolerancia 1e-4).
- **L0TF (T4.5c)**: si el `.chispa` trae `L0TF`, `ArmarDesde` registra ese L0 TF-IDF (`l0.go`, `chispa3.L0TFModelo.Probs`) y no el de la sección
  `L0`; la capa L0 de la cascada y la entrada de L0 de L2c usan sus probabilidades. Sin `L0TF`, el L0 de Chispa como antes.
  Paridad con sklearn: `TestL0TFParidadConSklearn` (`testdata/l0tf`, 270 frases con tildes, emojis, mayúsculas y espacios raros; lo genera
  `sdk/python/tests/fixture_l0tf.py`): |Δp| máx 4e-8 en f32 (tolerancia 1e-5); con datos reales (`L0TF_REAL=dir`), 4e-8 en 1500 frases de
  massive y de clinc150. Latencia: `go test ./decide -bench L0TF` (80 000 n-gramas × 150 clases, f32, frase de 14 palabras): 0,10 ms por consulta.
- **Latencia** (medida antes de T4.5; después, ver «T4.5»): la cabeza no añade llamadas al ONNX (L2c usa las mismas ranuras S que L2); el coste extra es el simproto, que va
  lineal con las clases: C·K·K·d multiplicaciones (150 clases, K=16, d=256: ≈ 10 ms en esta microVM de 4 vCPU, Go escalar,
  `go test -bench L2c ./decide`; con 2–10 clases, < 1 ms). El resto de la cabeza (logits y softmax) son µs. Frente a los ~30 ms de
  L2 no son despreciables con muchas clases; si hace falta, el bucle por clases se puede paralelizar o vectorizar.
- Sin L0 en la cascada, L2c no puede usar la cabeza y se comporta como L2.

### Compilar y probar con ORT
`go.mod` trae `github.com/yalue/onnxruntime_go v1.38.0` (probado con `libonnxruntime.so.1.31.1`). Sin `-tags ort` no se usa
(`l2_stub.go`, `torre/ort_stub.go`). Receta sin red (nodo-b; la caché de módulos de `~/go/pkg/mod` tiene el módulo):
```
. ~/orquestador/herr/env.sh                      # Go, venv, GOPROXY=off
export CC=~/orquestador/herr/zigcc CGO_ENABLED=1 # para -race
export CHISPA_ORT_LIB=~/orquestador/herr/venv/lib/python3.14/site-packages/onnxruntime/capi/libonnxruntime.so.1.31.1
cd server && go test -tags ort -race -count=1 ./...
```
Ruta de la .so en `chispa-server`, de mayor a menor precedencia: `-ort-lib` > `CHISPA_ORT_LIB` > `-ldflags -X …/server/decide.RutaORT=` >
búsqueda por defecto del sistema. `main` la asigna a `decide.RutaORT` y `torre.RutaORT` (`torre` no puede importar `decide`), así que L2 y la
torre usan la misma. Al arrancar, si el `.chispa` trae L2 o TORR y ORT no carga, el log dice `AVISO: ONNX Runtime no carga (ruta …, origen)`
(y L2 queda en stub / `chispa_torres_calculadas_total` en 0). Test: `cmd/chispa-server/ort_si_test.go` (un proceso hijo por origen de la ruta).
Para (re)añadir el módulo sin red: `GOPROXY=file://$HOME/go/pkg/mod/cache/download GOSUMDB=off GOFLAGS=-mod=mod go get github.com/yalue/onnxruntime_go@v1.38.0`.
Tests ORT: `torre/ort_test.go` (`sintetico.onnx` y su referencia) y `decide/l2_ort_test.go` (`TestL2TorreORTEsquemaNuevo`: L2 con
`decide/testdata/l2_sintetico.onnx` + torre al vuelo + `/v1/decide` con un esquema nuevo, un solo entorno ORT; se regenera con
`python decide/testdata/l2_sintetico.py`). Los ONNX son sintéticos (pesos aleatorios): prueban la mecánica, no la calidad.
El tokenizador de e5 llegó en T4.5 (abajo): `chispa-server -tok e5.chispa-tok`; sin `-tok`, L2 queda en stub aun con `ort`.

### Medidas de L1 real (microVM kindling de 4 vCPU, Xeon 3,3 GHz; cota del i3)
Potion multilingüe (`runtime/l1/exportar.py`, 155 MB, en un v3 en memoria), `go test ./decide -bench L1Real -benchtime 3s -cpu 1,4`:
cascada completa (L0 sin modelo para el esquema → L1) en lotes de 16 preguntas de ~70 caracteres, 3 esquemas con caché
de esquemas caliente, **sin HTTP/JSON**, 4 hilos de goroutine solo en la fila `-4`:

| Núcleos | decisiones/s | p99 por lote de 16 |
|---|---|---|
| 1 | ≈ 24 000 | 1,2 ms |
| 4 | ≈ 49 000 | 5,4 ms |

Con HTTP y JSON el techo medido en T4.1 era ≈ 13 k/s con L0, así que el servidor completo con L1 queda entre eso y estas cifras;
no se midió por HTTP con el potion. El objetivo del plan (≥ 5 k/s en el i7) tiene margen en CPU, pero no se confirma aquí.
Máquina compartida: ±30 %. Sin caché fría de páginas del mmap (no se puede vaciar en la VM).

### T4.5: tokenizador de e5 en Go, simproto entero y e2e
- **Tokenizador** (`runtime/tok`, Go puro, `README.md` allí): `chispa-server -tok e5.chispa-tok` lo pasa a `ArmarDesde`, que monta L2 / L2c
  con el ONNX. El `.chispa-tok` se exporta con `runtime/tok/exportar.py <dir-e5> x.chispa-tok` (12 MB, no va a git).
- **simproto entero** (`decide/l2c.go`): cada ranura S se cuantiza a int8 (escala max|S|/127) y el producto con los prototipos int8 se
  hace en enteros, tres elementos por multiplicación de 64 bits y cuatro ranuras por pasada; los prototipos se empaquetan una vez por
  entrada de CONJ. `go test ./decide -bench 'Simproto150|L2cCabeza'` (150 clases, K=16, d=256, 16 ranuras; microVM Xeon 3,3 GHz, 4 vCPU):
  | | antes (float32 escalar) | después |
  |---|---|---|
  | `BenchmarkSimproto150` | 10,5 ms | 2,3 ms |
  | `BenchmarkL2cCabeza` (cabeza entera) | 10,1 ms | 2,4 ms |
  Coste: la cuantización de S mueve las probabilidades (|Δp| ≤ 3e-3 con el fixture de Python, que tiene d pequeña) frente a los 8e-8 del
  cálculo en float; ese cálculo sigue en `simprotoRef` y las pruebas de paridad estricta lo usan. El efecto en macro-F1 se mide en `e2e.sh`.
- **`MaxOpciones` 64 → 256**: clinc150 trae 150 clases (151 con `escalate`).
- **`deploy/aws/e2e.sh`**: prueba de punta a punta en una c6a.xlarge spot (`__CHISPA_S3__`, `empaquetar_e2e.sh > codigo.tgz`). Pasos en la
  cabecera del script. En seco: `CHISPA_LOCAL=1 bash server/deploy/aws/e2e.sh` (fixtures, sin ORT).
