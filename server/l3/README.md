# Medir L3 contra un LLM real

`medir.sh` arranca un `chispa-server` con L3 apuntando a un endpoint OpenAI-compatible (`POST {url}/chat/completions`) que ya
exista, le manda ~50 preguntas por `/v1/decide` y resume latencia, respuestas válidas y exactitud. No instala ni descarga nada
y no llama a ningún LLM por su cuenta: solo al endpoint que le des.

## Requisitos
- `go` (compila `server/cmd/chispa-server`; o pasa `CHISPA_L3_SERVER` con el binario ya compilado), `python3` (solo stdlib), `curl`, `bash`.
- Un endpoint OpenAI-compatible accesible desde esta máquina.
- Opcional: un clon de JevBench (`datasets/public/{easy,hard,original}.jsonl`, 231 casos). No se copia al repo.

## Variables
| Variable | Qué es |
|---|---|
| `CHISPA_L3_URL` | base del endpoint sin `/chat/completions` (obligatoria), p. ej. `http://127.0.0.1:11434/v1` |
| `CHISPA_L3_MODELO` | nombre del modelo en el endpoint (obligatoria) |
| `CHISPA_L3_API_KEY` | clave del endpoint (opcional; se pasa a L3 por `api_key_env`, no se escribe a disco) |
| `CHISPA_JEVBENCH` | clon de JevBench, su `datasets/public` o un `.jsonl`; sin ella se usa solo `casos-respaldo.jsonl` (28 casos) |
| `CHISPA_L3_N` / `CHISPA_L3_SEMILLA` | casos (50) y semilla del muestreo (0) |
| `CHISPA_L3_TIMEOUT` | plazo por llamada al LLM (60s) |
| `CHISPA_L3_SALIDA` | JSONL con una línea por caso (capa, respuesta, oro, ms) |
| `CHISPA_L3_SERVER` | `chispa-server` ya compilado |

## Receta con Ollama (solo documentada, no ejecutada aquí)
```sh
# en la máquina que servirá el modelo
ollama serve &                       # escucha en 127.0.0.1:11434
ollama pull qwen3:4b-instruct        # o qwen3:1.7b, más pequeño y rápido
# desde el repo
CHISPA_L3_URL=http://127.0.0.1:11434/v1 CHISPA_L3_MODELO=qwen3:4b-instruct \
CHISPA_JEVBENCH=/ruta/al/jevbench CHISPA_L3_SALIDA=/tmp/l3-detalle.jsonl \
  server/l3/medir.sh
```
Ollama no pide clave. La primera llamada incluye la carga del modelo en memoria: lanza `medir.sh` una vez de calentamiento
(o con `CHISPA_L3_N=3`) antes de la medida buena. Si L3 corre en otra máquina, usa su IP en `CHISPA_L3_URL`.

## Qué mide y cómo se lee
- Casos: JevBench (muestreo con semilla de choice, noul y score, convertidos como `model/evaluacion/jevbench.py`: noul → `false`/`true`, score → `1..K`) o, sin él, `casos-respaldo.jsonl` (esquemas de `pilotos/esquemas/`, textos de `ejemplos/`).
  Formato del respaldo: una fila por línea con `id, tipo, pregunta, texto, opciones, descripciones, etiqueta`.
- Cada caso va como una pregunta por petición. El servidor se configura con los `.chispa` de `server/testdata` y `capas` con L3 a τ=0; así lo que no conocen L0–L2 escala a L3 y "poco segura" no se confunde con "inválida".
- **Latencia**: p50/p95 por pregunta con el campo `ms` de la respuesta y con el reloj del cliente. Incluye el paso por L0–L2, despreciable frente a un LLM.
- **Respuestas válidas**: `chispa_l3_llamadas_total{resultado}` de `/metrics` antes y después (`ok`, `invalida`, `error`, `timeout`). Válida = el JSON del LLM pasó la validación de `interpretarL3`.
- **Exactitud**: `layer=="L3"` y `answer == oro`; sobre las contestadas y sobre todas (no contestada cuenta como fallo). En score la respuesta es la mediana, no el argmax.
- Si un caso lo resuelve L0–L2 antes de L3 (p. ej. un esquema que coincide con un `.chispa` de testdata), se cuenta aparte y no mide L3.

## Límites del contrato de L3 para medir
- `/v1/decide` no devuelve la latencia de L3 sola ni la respuesta cruda del LLM; la latencia de L3 por llamada solo está agregada en un histograma de `/metrics`. Por eso se usa `ms` por pregunta.
- No hay forma de distinguir en la respuesta una L3 inválida de una L3 válida por debajo de τ (ambas son `layer:"escalar"`); se resuelve con τ=0 y los contadores de `/metrics`.
- La exactitud con `max_por_peticion=1` y una pregunta por petición no prueba el reparto de presupuesto entre varias preguntas.

## Probar el script sin LLM
`falso.py` es un servidor OpenAI-compatible falso (elige por palabras en común; sin valor de exactitud):
```sh
FALSO_PUERTO_ARCHIVO=/tmp/p python3 -I server/l3/falso.py & sleep 1
CHISPA_L3_URL=http://127.0.0.1:$(cat /tmp/p)/v1 CHISPA_L3_MODELO=falso server/l3/medir.sh
```
`FALSO_LATENCIA`, `FALSO_INVALIDAS` (fracción de respuestas rotas) y `FALSO_CLAVE` (exige Bearer) lo ajustan.

Test de Go opcional: `CHISPA_L3_URL=… CHISPA_L3_MODELO=… go test ./decide -run TestL3Real -v` (sin la variable, se salta).
