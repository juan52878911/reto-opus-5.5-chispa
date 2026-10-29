# demo/wasm — L1 de Chispa en el navegador

`runtime/l1` (Go puro) compilado a `GOOS=js GOARCH=wasm`, **sin cambios** en el runtime: `mmap_otros.go` ya cubre
`js` (no es `unix`) y `Desde([]byte)` carga el modelo desde memoria. Una página estática con un L1 **recortado**
(el completo pesa 155 MB).

## Construir y servir
```
source ~/.profile
M=$(ls -d ~/hf/hub/models--minishlab--potion-multilingual-128M/snapshots/*)
cd runtime/l1
python vocab_recortado.py $M /tmp/vocab-es.json            # ~30 s: elige 50 000 piezas del español (corpus sin el test del sondeo)
python exportar.py $M ../../demo/wasm/potion-es.chispa-l1 --vocab /tmp/vocab-es.json    # 15,8 MB, ~20 s
cd ../../demo/wasm && ./construir.sh                         # chispa.wasm (5 MB)
python -m http.server 8000                                   # y abrir http://localhost:8000/
```
`chispa.wasm` y `potion-es.chispa-l1` no van a git (se regeneran con lo anterior). `wasm_exec.js` y
`wasm_exec_node.js` son los de `$(go env GOROOT)/lib/wasm/` (Go 1.27.1). Sin CDN ni red: todo se carga de la misma carpeta.

## API que expone el wasm (`syscall/js`)
- `cargar(Uint8Array)` → `{ok, vocab, dim, bytes}` (verifica el sha256 del modelo).
- `decidir(texto, preguntaJSON)` → `{ok, answer, conf, probs}`. La pregunta es la del servidor
  (`ejemplo_pregunta.json`: intención de WhatsApp compra/soporte/queja/saludo, `kind: "choice"`); misma cuenta que
  `server/decide/l1.go`: coseno del mensaje con «pregunta · opción · descripción», softmax con T = 0,05. Zero-shot,
  sin cabeza entrenada: sobre las 213 frases de `whatsapp_comercio` acierta ≈ 50 % (la demo enseña la latencia y el
  mecanismo, no la calidad; para eso están L0 y `chispa train`).
- `huella(frasesJSON)` → sha256 de los embeddings float32; `medir(tokens, reps, preguntaJSON)` → p50/p99 en µs de
  `decidir` (embedding + coseno con las opciones ya en caché) sobre un texto de exactamente ese número de tokens.
- `decidirLote(textosJSON, preguntaJSON)` → `{ok, n, answers, total_us}`: decide un lote en una sola llamada y mide el total dentro del wasm.
- `memoriaGo()` → `{heap_alloc, sys, num_gc}` (runtime de Go dentro del wasm).
- El botón «Medir latencia» de la página llama a `medir` con 16, 64 y 256 tokens × 200 repeticiones.

La lógica está en `nucleo/` (sin `syscall/js`), así que se prueba igual en nativo y en wasm.

## Pruebas sin navegador
```
GOOS=js GOARCH=wasm go build -o chispa.wasm . && go vet ./...
node prueba_node.js potion-es.chispa-l1 --latencia
```
`prueba_node.js` elige 50 frases del sondeo y exige **la misma huella de embeddings y las mismas respuestas** en
(1) `chispa.wasm` ejecutado con `wasm_exec_node.js`, (2) el API de JS (`cargar`/`decidir`/`huella`, como la página) y
(3) la versión nativa (`go run ./nativo`). Huella de las 50 frases:
`4ce4952c206b9b0fd561825894cec879905443f9f0f36d29fe2006dbe4f8166c`.

## L1 recortado
50 000 de 500 353 piezas (las del español en MASSIVE es train/validación, XNLI es, PAWS-X es, SIB-200 es,
GoEmotions es y los `train_*.jsonl` del sondeo; completa el cupo con las de mayor log-prob), 256 dim int8.
Tabla hash y filtro de prefijos dimensionados al vocabulario (2^17 y 2^23). **15 804 144 B (15,8 MB).**
Frente al completo en las 2 268 frases del sondeo con vector (`CHISPA_L1_RECORTADO=… go test -run TestRecortado -v`):
**coseno medio 0,9954**, p1 0,881, mínimo 0,0009; 96,3 % de las frases ≥ 0,99. Lo que baja la cola: escrituras
fuera del vocabulario (hangul, emoji), nombres propios y erratas (p. ej. «mroir», «alamar»), cuyo tokenizado sin las
piezas largas cambia.

## Latencia (cota en node v22, wasm, microVM de 4 vCPU compartidas)
`decidir` con 4 opciones, 200 repeticiones:

| tokens | p50 | p99 | nativo amd64 p50 / p99 |
|---|---|---|---|
| 16 | 238 µs | 3,1 ms | 36 / 72 µs |
| 64 | 397 µs | 2,7 ms | 111 / 172 µs |
| 256 | 1,42 ms | 3,5 ms | 401 / 887 µs |

Es una cota de node en una máquina compartida (los p99 incluyen el GC de Go-wasm y ruido de la VM); la del navegador
(Chrome) queda por medir con el botón de la página.

## Esquema nuevo (zero-shot) en la UI
`index.html` trae un formulario: pregunta, opciones (una por línea, `id: descripción`) y un mensaje. Al pulsar «Decidir» muestra
la opción, la capa (siempre L1: es lo que lleva este wasm), la confianza, las probabilidades y el tiempo (incluye el cruce
JS→wasm). Precargado: la ferretería colombiana de `docs/02-inicio-rapido.md` (no es una tarea de benchmark); el botón
«WhatsApp de comercio» carga `ejemplo_pregunta.json`. Solo `kind: choice`.

## Arnés de latencia (`latencia.html`, `arnes.js`)
Receta completa, desde la raíz del repo:
```
. ~/orquestador/herr/env.sh                       # Go 1.27 (o el Go que tengas)
cd demo/wasm && ./construir.sh                    # chispa.wasm; imprime el tamaño
# potion-es.chispa-l1 en esta carpeta: ver «Construir y servir» arriba (no va a git)
python3 -m http.server 8000                       # y abrir http://localhost:8000/latencia.html
```
En la página: N (2 000 por defecto), calentamiento (200) y tamaño de lote (50) → **Medir** → **Descargar JSON**
(`latencia-chispa-<fecha>.json`). Deja el fichero en `demo/wasm/resultados/<navegador>-<máquina>.json`
(esa carpeta no existe aún; créala) y no lo mezcles con otras medidas. Todo es local, sin red.

Qué mide, con textos deterministas (semilla fija) y variados (de ~10 a ~70 palabras) sobre el esquema de la ferretería (5 opciones):
- **Por decisión**: N llamadas a `decidir`, cada una con `performance.now()` (incluye el cruce JS→wasm y la conversión del
  resultado): p50, p95, p99, mín/máx/media, y decisiones/s sobre el total.
- **Por lote**: `decidirLote` con lotes de 50, tiempo medido dentro del wasm; p50/p95/p99 del lote y por texto.
- **Memoria**: tamaño del buffer del wasm, heap de Go (`memoriaGo`) y, solo en Chrome, `performance.memory`.
- **Entorno**: user agent, plataforma, núcleos, fecha y configuración. La torre de opciones ya está en caché (se calcula en el calentamiento).
Nota: los navegadores redondean `performance.now()` (Firefox 1 ms por defecto con `privacy.resistFingerprinting`; Chrome 100 µs
sin aislamiento de origen): por eso las cifras por lote son más fiables que las de una sola decisión.

### Con node (sin navegador)
```
node demo/wasm/prueba_latencia_node.js demo/wasm/potion-es.chispa-l1 [--n 2000] [--calentamiento 200] [--lote 50] [--salida f.json]
node demo/wasm/prueba_latencia_node.js --stub     # solo comprueba la lógica del arnés (decisor falso; no mide Chispa)
```
Usa el mismo `arnes.js` y escribe `latencia-node.json` (por defecto, junto al script). Necesita `chispa.wasm` y el modelo.
