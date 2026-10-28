# Servidor de Chispa (T4.1)

`POST /v1/decide` decide preguntas con una cascada de capas: L0 (Chispa lineal real, `pkg/chispa`
de kindling v0.17.0) y L1, L2, L3 (stubs «sin opinión», confianza 0, hasta que lleguen los modelos).
Esquema de preguntas: `model/esquema.md` (choice, score, noul).

```
make -C server test     # go vet + go test -race
make -C server bench    # benchmarks (1 y 4 núcleos)
make -C server serve    # arranca con testdata/config.json (3 modelos de prueba)
make -C server carga    # generador de carga contra :8090
```

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
  `kind` ∈ `choice|score|noul`, `options` y `nonce` (opcional).
  - `choice`: ≥ 2 opciones (≤ 64) con `id` único y `description` opcional.
  - `score`: ≥ 2 opciones ordinales, ids `"1"…"K"`.
  - `noul`: opciones opcionales; si van, solo `"false"` y `"true"`. Por defecto las dos.
- Cuerpo ≤ 1 MiB; campos desconocidos → 400.

### Salida (200)
```json
{"results": [
  {"id": "u1", "kind": "choice", "answer": "alta", "probs": {"alta": 0.9, "baja": 0.1},
   "layer": "L0", "escalate": false, "ms": 0.012, "nonce": "abc-1"}
]}
```
- `answer`: id de la opción elegida (en `noul`, `"true"`/`"false"`; en `score`, `"1"…"K"`).
- `probs`: id de opción → probabilidad calibrada (la de la capa que respondió).
- `layer`: la capa que contestó; si `escalate` es true, la última capa de la cascada.
- `escalate`: ninguna capa llegó a su τ. `answer`/`probs` son entonces la mejor pista vista
  (la capa con más confianza) y quedan vacíos (`""`, `{}`) si ninguna opinó.
- `ms`: tiempo de la cascada para esa pregunta. `nonce` se devuelve tal cual.
- Los resultados van en el orden de `questions`.

### Errores
`400 {"error": "..."}` con la ruta del campo: `questions[2].kind: "raro" no válido (choice, score o noul)`.
También 405 (método ≠ POST) y 413 (cuerpo > 1 MiB). No hay errores por pregunta: la validación es
todo o nada, y un fallo interno de una capa solo la salta (se cuenta en `chispa_capa_errores_total`).

### Nonce
Clave de idempotencia: la misma petición con el mismo `nonce` devuelve el resultado guardado sin
volver a decidir (`ms` incluido). La clave es `nonce + estado + esquema + id`: el mismo nonce con
otro estado o pregunta se recalcula. Sin `nonce` no se cachea. LRU de `cache_respuestas` entradas.

### Cascada
L0 → L1 → L2 → L3: se pasa a la siguiente mientras la confianza top-1 sea < τ de la capa (una capa
sin opinión o con error vale 0). Con confianza ≥ τ responde esa capa. Si la última no llega,
`escalate: true`. Capas y τ se leen del JSON de configuración (`-config`):

```json
{"capas": [{"nombre":"L0","tau":0.8},{"nombre":"L1","tau":0.8},{"nombre":"L2","tau":0.7},{"nombre":"L3","tau":0.6}],
 "modelos": ["testdata/intencion.chispa"], "cache_esquemas": 1024, "cache_respuestas": 4096}
```
Interfaz por capa: `type Decisor interface { Decidir(ctx, Pregunta) (Respuesta, error); Nombre() string }`
(`decide/types.go`). Para sustituir un stub basta pasar otro `Decisor` con el mismo nombre en `main.go`.

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
`chispa_cache_esquemas_total{resultado}`, `chispa_cache_nonce_aciertos_total`.

## Relación con `/v1/systemone` de Jev — SUPOSICIÓN, sin verificar
No tengo la especificación de `/v1/systemone`. Lo que supuse, por el encargo:
- Se parece: petición con `state` + lista `questions` de `{id, question, kind, options[{id, description}], nonce?}`,
  y `nonce` devuelto tal cual. Se parecen los tres `kind`.
- **Suposición**: la respuesta es una lista por pregunta con el mismo `id`. Aquí va envuelta en `{"results": [...]}`;
  si systemone devuelve un array desnudo o usa otra clave, hay que cambiar `respuestaHTTP` (`decide/http.go`).
- No se parece / es nuestro: `probs`, `layer`, `escalate`, `ms`, y el 400 todo-o-nada con `{"error"}`.
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
