# runtime/l1 — Model2Vec en Go puro, int8 y determinista

Runtime del L1 de Chispa (T3.1, adelantado). Un Model2Vec es un embedding estático: tokenizar, buscar
vectores, media, normalizar. Aquí: Go, solo biblioteca estándar (`go 1.27`), pesos int8 con una escala por
fila, acumulación entera y resultado idéntico bit a bit en amd64 y arm64.

## Modelo de referencia y licencia
`minishlab/potion-multilingual-128M` (tokenizador de `BAAI/bge-m3`: Unigram + Metaspace + normalizador
Precompiled de sentencepiece; 500 353 piezas × 256 dim). **Licencia: la copia en `~/hf` no incluye la tarjeta
(`README.md`) ni un fichero de licencia**, solo `config.json`, `tokenizer.json`, `vocab.txt` y
`model.safetensors`, así que no he podido leerla en el entorno. Según mi conocimiento la tarjeta del modelo
declara MIT (abierta), pero **no está verificado aquí: confírmalo contra la tarjeta en Hugging Face antes de
redistribuir el `.chispa-l1`**. No he usado otro potion.

## Uso
```
python3 exportar.py <dir-del-modelo> /tmp/potion.chispa-l1      # ~30 s, determinista
cd runtime/l1 && go vet ./... && go test -race ./...            # los tests que necesitan el modelo se saltan si falta
```
```go
m, _ := l1.Abrir("potion.chispa-l1")      // mmap, sin copiar ni indexar nada
out := make([]float32, m.Dim())
m.Embed("hola, ¿qué tal?", out)           // vector unitario float32; false y ceros si no hay tokens
```
Variables de los tests: `CHISPA_L1` (ruta del modelo, por defecto `/tmp/potion.chispa-l1`),
`CHISPA_L1_FUZZ` (jsonl de `referencia.py ids ... --fuzz N`), `CHISPA_L1_REF` (jsonl de `referencia.py emb`).
El `.chispa-l1` (155 MB) no va a git.

## Formato `.chispa-l1` (versión 1, little endian)
Cabecera de 256 bytes: magia `CHL1\0\0\0\0` · `u32` versión · dim · vocabulario · flags (0) · max. caracteres
por pieza · bits de la tabla hash (20) · bits del filtro de prefijos (26) · 9 pares `u64` (offset, longitud) de
sección · `sha256` del cuerpo (todo lo que sigue a la cabecera) · relleno. Secciones, alineadas a 16 bytes:

| # | sección | contenido |
|---|---|---|
| 0 | params | JSON: parámetros del tokenizador (max 512 tokens, recorte de texto = 512·mediana de pieza, `unk_id`, penalización unk 10, `min_score`, metaspace `▁`, prepend `always`, tokens añadidos `[PAD]`/`[UNK]`, lista de puntuación espaciada, bits de escala) |
| 1 | charsmap | `precompiled_charsmap` de sentencepiece tal cual (u32 tamaño del trie · array doble darts-clone · pool de cadenas) |
| 2 | piezas | bytes UTF-8 de las 500 353 piezas concatenadas |
| 3 | offsets | `u32 × (vocab+1)` |
| 4 | scores | `f64 × vocab` (log-prob del unigram) |
| 5 | hash | tabla abierta de 2^20 `u32` (id+1; 0 = vacío), FNV-1a 64, sondeo lineal |
| 6 | pesos | `int8 × vocab × dim`, fila a fila |
| 7 | escalas | `f32 × vocab`; escala = max\|fila\|/127, `q = rint(x/escala)` |
| 8 | prefijos | filtro de 2^26 bits con cada prefijo (en caracteres) de cada pieza; corta la búsqueda en Viterbi |

Los ids de pieza son los índices de fila de `pesos`. Hash del cuerpo del modelo exportado:
`01fe1e57dc1bb1917757723e35264b146c25c4d81a3950a8ec7bb0f6a4ba8808`.

**Como sección del `.chispa` v3:** el cuerpo (secciones 0–8, con offsets relativos al inicio de la sección) cabe
tal cual como una sección «l1» del contenedor; la cabecera propia se sustituiría por la entrada de la tabla de
secciones del `.chispa` (tipo, offset, longitud, sha256), y `Desde([]byte)` ya acepta un trozo de memoria, así que
bastaría pasarle el subslice mapeado. Para eso habría que convertir los offsets absolutos de la cabecera en
relativos al inicio de la sección (cambio mecánico, versión 2 del formato).

## Aritmética determinista
Por fila, multiplicador entero `M = round(escala·2^32)` (exacto en float64, redondeo a par). Se acumula
`acc_j = Σ q_ij·M_i` en int64 (la media se cancela al normalizar). Norma = `sqrt(Σ acc_j²)` en float64 con orden
fijo y conversiones explícitas `float64(f*f)` para impedir que arm64 funda multiplicación y suma (FMA);
`out_j = float32(acc_j / norma)`. Solo hay `+`, `*`, `/` y `sqrt` de IEEE-754 (correctamente redondeados) y enteros.

## Tokenizador
Reproduce `tokenizers`: split literal de `[PAD]`/`[UNK]` → normalizador (charsmap darts-clone sobre grafemas
<6 bytes, o por carácter; `" {2,}"`; espaciado de puntuación ASCII; `\s+`→`" "`; strip) → Metaspace
(`▁`, prepend siempre) → Viterbi sobre el unigram (desempate: pieza más larga; carácter sin pieza → `[UNK]` con
`min_score−10`; `[UNK]` consecutivos fundidos) → truncado a 512 tokens, tras recortar el texto a
512·mediana caracteres como hace `model2vec`; `[UNK]` (id 1) se descarta al promediar.

## Resultados (microVM de kindling, 4 vCPU compartidas, Go 1.27.1 linux/amd64)
**Tokenizador:** 2 274 frases (`model/sondeo/*.jsonl` + 39 casos borde) idénticas a `tokenizers`
(`testdata/ids_sondeo.jsonl`, test `TestTokenizadorSondeo`). Además, fuzz: 1 157 032 + 18 380 cadenas (todos los
puntos de código, marcas combinantes, hangul, mezclas con `[UNK]`/`[PAD]`/`▁`/emoji) con **0 diferencias**.

**Paridad** (2 268 frases con norma no nula; 6 dan vector cero en ambos lados):
- Coseno int8 (Go) frente a fp32 (model2vec): **media 0,999967, mínimo 0,999895** («Oido a los discapacitados.»).
- Go int8 frente a Python con la misma cuantización (`referencia.py`, enteros de Python + float64 secuencial):
  **bit a bit idéntico** en las 2 274 frases (`CHISPA_L1_REF`).

**Determinismo:** golden `hash200` = `f70784322c226eb1ae28718134a16e4b19573be88743ed1a4e7ad11542ed7ac8`
(sha256 de los float32 LE de las 200 primeras frases de `testdata/ids_sondeo.jsonl`); en amd64 coincide con la
referencia de Python (`TestEmbeddingDorado`). `GOARCH=arm64` cross-compila (`go vet`, `go build`, `go test -c`).
**No se ha ejecutado en arm64**: la VM no tiene `qemu-aarch64`. Para correrlo en ARM:
```
GOARCH=arm64 go test -c -o l1.arm64.test .     # y en la máquina ARM, con el .chispa-l1 exportado:
CHISPA_L1=/ruta/potion.chispa-l1 ./l1.arm64.test -test.run 'Hash|Dorado|Sondeo' -test.v
```
Deben pasar `TestHashCuerpo`, `TestEmbeddingDorado` y `TestTokenizadorSondeo`.

**Rendimiento** (`go run ./cmd/l1medir /tmp/potion.chispa-l1`, caché de página caliente; máquina compartida, el
p99 es ruidoso — entre tandas varió de 0,3 a 10 ms):
| tokens | p50 | p99 |
|---|---|---|
| 16 | 41–52 µs | 0,3–1,2 ms |
| 66 | 122–208 µs | 0,5–5,6 ms |
| 256 | 0,71–0,77 ms | 3,7–10 ms |

- Tamaño del `.chispa-l1`: 154 772 608 B (147,6 MiB): 128 MB de pesos, 8 MB de filtro de prefijos, 4 MB de tabla hash, etc.
- Arranque: `Abrir` (mmap + parseo de cabecera/params/charsmap) 0,4 ms; hasta el primer embed ≈ 0,8 ms con caché
  caliente. **Con caché fría no se midió** (no se puede vaciar la caché en la VM); el coste es la lectura de las
  páginas tocadas.
- RSS: 4–7 MB tras el primer embed, ~30 MB tras 20 000 embeds (la mayor parte `RssFile`, páginas del mapeo
  compartidas con la caché; `RssAnon` ≈ 6 MB).

## Tests y referencia
`referencia.py ids|emb` genera las referencias en Python (usa `model2vec`/`tokenizers` del venv). `go test` lee
`testdata/ids_sondeo.jsonl` (texto + ids) y necesita el `.chispa-l1`; sin él esos tests se saltan con un aviso explícito.
