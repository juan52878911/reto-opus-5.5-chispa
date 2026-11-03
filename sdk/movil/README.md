# sdk/movil — `chispamovil`, el núcleo Go de los SDK móviles

Un paquete Go (`chispamovil/`) pensado para `gomobile bind`: solo `string`, `[]byte`, `int`, `float64`, `error` y
punteros a structs. Abre un `.chispa` v3 y expone cada capa por separado; **la cascada y ONNX Runtime viven en Kotlin
(`sdk/android/`) y Swift (`sdk/ios/`)**.

| Go | Qué hace |
|----|----------|
| `Abrir(ruta) (*Chispa, error)` | abre el fichero (CRC y sha256 de cada sección que use) y monta L0, L1 y L2 si las trae |
| `Decidir(texto, preguntaJSON) string` | **L1**: coseno con «pregunta · opción · descripción» y softmax con la T de CALIB (0,05 por defecto); `choice` y `noul` (`score` no opina) |
| `DecidirL0(texto, preguntaJSON) string` | **L0**: el TF-IDF de la sección L0TF si el fichero la trae (manda, como en el servidor), si no el Chispa lineal de la sección L0; el modelo es el cuyo conjunto de etiquetas coincide con los ids de las opciones |
| `CargarTokenizadorE5(ruta) error` · `TokenizarE5(texto) []byte` · `TieneTokenizadorE5()` | el tokenizador de e5 de `runtime/tok` (un `.chispa-tok`); devuelve los ids como int32 little endian |
| `CabezaConjunta(simsJSON) string` · `TieneConj()` | **L2c**: la cabeza de la sección CONJ. `simsJSON` = la pregunta + `"l0"` (probabilidades de `DecidirL0` por id) + `"ranuras"` (las K×d salidas de ORT aplanadas, números JSON) + `"k"`. Las similitudes MaxSim se calculan contra ESQUEMAS. Sin CONJ, sin L0 o con otra pregunta devuelve `opina:false` y la cascada cae a `PuntuarL2` |
| `TorresL2(preguntaJSON) bool` · `PuntuarL2(preguntaJSON, ranuras, k) string` | **L2** sin ONNX: MaxSim de las ranuras `S` (K×d float32 LE, las que da ONNX Runtime) contra las torres de ESQUEMAS y las cabezas de CALIB, como `server/decide/l2.go` (choice, noul, score/CORAL) |
| `ExtraerL2(destino) error` | escribe el ONNX int8 de la sección L2 en un fichero para que ORT lo abra desde ruta |
| `Capas()`, `TauEscalate()`, `TieneCalib()`, `Huella(frasesJSON)`, `Cerrar()` | metadatos y utilidades |

Toda decisión devuelve JSON: `{"ok":true,"opina":bool,"answer":…,"conf":…,"probs":{…}}` o `{"ok":false,"error":…}`.
La pregunta es la del servidor (`{"question":…,"kind":"choice","options":[{"id":…,"description":…}]}`).

## Pruebas
```
source ~/.profile
cd sdk/movil/chispamovil
go test ./...                          # nativas, con un embebedor falso; la paridad usa los fixtures del repo
CHISPA_TOK=/tmp/e5.chispa-tok go test -run TokenizarE5 -v ./...   # paridad del tokenizador (se salta sin el fichero)
GOOS=android GOARCH=arm64 go vet ./...  # compila para Android sin NDK (CGO desactivado)
CHISPA_L1_RECORTADO=ruta/potion-es.chispa-l1 go test -run Huella -v ./...
```
La última exige **la misma huella** de embeddings (`4ce4952c…8166c`) y las mismas 50 respuestas que `demo/wasm` sobre
las 50 frases del sondeo; sin el modelo recortado (no va a git, ver `demo/wasm/README.md`) se salta.

## Licencia

Apache-2.0 (ver `LICENSE` de la raíz del repositorio). Las atribuciones de terceros están en `NOTICE`. Los datasets con SA, NC o con términos pendientes
(XNLI, clima, datos.gov.co, SIB-200, etiquetas de ALIA, salidas de Haiku) no se redistribuyen y solo se usan como test.
