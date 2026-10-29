# Contrato de la torre de esquemas de L2 (para calcular torres al vuelo en `chispa-server`)

Fuente de verdad: `model/l2/modelo.py` (`texto_opcion`, `texto_consulta`, `Codificador.pasaje`, `Torre`, `maxsim`) y
`model/l2/exportar.py` (torres de ESQUEMAS). Este contrato describe lo que existe. El ONNX de la torre lo exporta
`model/l2/exportar.py --torre-onnx SALIDA`. Si algo de aquí no cuadra con el código, manda el código: avísame.

## Texto de entrada (por vector de torre)
- **choice**: un vector **por opción**. Texto: `"passage: " + pregunta + " · " + opción + " · " + descripción(opción)`.
  Si no hay descripción, la cadena vacía, así que el texto termina en `" · "`. El separador es `" · "`: espacio, punto
  medio U+00B7 y espacio.
- **noul** y **score**: **un** vector por pregunta, el «vector de consulta», con el mismo formato y la **última** opción
  (`"true"` en noul y el nivel máximo en score).
- La clave en ESQUEMAS es `HashEsquema(pregunta, [opción])` en choice y `HashEsquema(pregunta, opciones)` en noul y score,
  como hoy.

## Tokenización
- e5 (XLM-R unigram), igual que la consulta (`runtime/tok`), **pero con el prefijo `"passage: "`** en lugar de
  `"query: "`. El prefijo forma parte del texto que se tokeniza.
- Truncado a `max_len` tokens, con los especiales `<s>` y `</s>` incluidos, y relleno con máscara de atención. `max_len` es el
  `max_tok` con que se entrenó el checkpoint (G.8: 256; antes 128) y viaja en las `metadata_props` (abajo); el runtime lo lee de ahí.

## Red
1. e5-small: el mismo codificador que la consulta, congelado en T2.1b.
2. Media de los estados ocultos de la última capa, ponderada por la máscara.
3. Normalización L2: `v` (384).
4. `Torre`: `Linear(384→512)` → GELU (exacta, erf) → `Linear(512→256)`.
5. Normalización L2: **`h` (256)**.

## ONNX de la torre (lo que se exporta)
- **Entradas:**
  - `input_ids` int64 (B, T);
  - `attention_mask` int64 (B, T).
  - Son ids del tokenizador **original** de e5. Si el vocabulario está podado, el grafo trae la tabla id→id podado, como el
    de la consulta.
- **Salida:** `h` float32 (B, 256), ya normalizada.
- **Variantes** (`exportar.py --torre-onnx SALIDA --cuant-torre ninguna|dinamico|estatico`; por defecto `dinamico`). Las tres
  tienen las mismas entradas, salida y `metadata_props`, así que el runtime no distingue una de otra:
  - `ninguna`: fp32, sin cuantizar (~175 MB con el vocabulario podado compartido).
  - `dinamico`: int8 dinámico **por canal** en los MatMul y la tabla de embeddings de e5; escalas de activación calculadas en
    cada llamada. Las capas de `Torre` quedan en fp32, igual que las ranuras en la consulta (~47 MB).
  - `estatico`: int8 **estático** con QDQ (`onnxruntime.quantization.quantize_static`): pesos por canal y escalas de activación
    por tensor fijadas con `--calib-torre <jsonl> --n-calib 500` (hasta 500 textos de torre distintos, `texto_opcion` de filas
    de train, elegidos al azar con semilla fija). `Torre` queda en fp32. `--metodo-calib minmax|percentil` elige el rango.
  - `--sin-poda` (con cualquiera de las tres) exporta la tabla de embeddings completa en vez de la podada.
  La paridad y la elección entre variantes salen de `model/bench/torre/e2e.sh` (`informe.md`, una tabla por variante).
- **Opset:** 17.
- **`metadata_props`** (las escribe `exportar.py` y las lee `chispa train --torre`; valores en texto):
  - `chispa.torre.dim` = `256` (dimensión de `h`);
  - `chispa.torre.max_len` = el `max_tok` del checkpoint (truncado en tokens; `--max-tok`, por defecto 128, si el checkpoint no lo guarda);
  - `chispa.torre.prefijo` = `passage: ` (con el espacio final; forma parte del texto que se tokeniza).

- **Consulta:** el ONNX de consulta lleva `chispa.consulta.max_len` con el mismo valor. Sin esa propiedad el runtime trunca a 128.

## Cómo se combinan torre y consulta
- La consulta (el ONNX que ya existe) da las ranuras `S` (K = 16, d = 256), normalizadas.
- **Similitud**: `s(opción) = max_k softplus(h_opción · S_k)` (`maxsim`).
- **Cabezas**, con los parámetros de CALIB y sin cambios respecto a hoy:
  - **choice**: `softmax(s / T)`;
  - **noul**: `p(true) = σ(a·s + b)` con el vector de consulta, más el umbral θ;
  - **scoreK**: CORAL. `P(y > j) = σ(a·s − b_j)`; las claves `scoreK#j` llevan los incrementos de `b_j`.
- **Con soporte (prototipos):** se suma `β_tipo · simproto` (`modelo.simproto`). Va aparte de la torre.
- **L2c (CONJ):** usa estas mismas similitudes como entrada, más las log-probs de L0.
- **Caché:** `h` depende solo del texto de la torre, así que se cachea por la clave de ESQUEMAS y se calcula una vez por
  esquema nuevo.

## Paridad medida
Con e5 de `~/hf` y pesos de L2 aleatorios (semilla fija); tabla completa en `model/l2/resultados/torre-onnx/LEEME.md`.
- **Cuantización sola** (sin `<unk>`): coseno medio de `h` 0,9998 (mínimo 0,9995), ≥ 0,999 como se esperaba.
- **Vocabulario podado**: los tokens que no están en la tabla podada pasan a `<unk>` dentro del grafo (7,5 % de los tokens en los
  textos de massive-es) y el coseno medio baja a 0,9987 (mínimo 0,9978). Es la poda y no el int8: vale lo mismo que en la consulta;
  si el vocabulario no cubre el idioma del esquema, las torres al vuelo se alejan de las de ESQUEMAS.
- **Top-1 de choice** con torres al vuelo frente a PyTorch: 0,66 con la poda y 0,75 sin `<unk>` en 300 filas; con pesos aleatorios
  el margen entre opciones es ~0,001, así que mide ruido sobre empates (0,93 en la mitad de filas con más margen). **No confirma ni
  refuta el 0,98** hasta repetirlo con el checkpoint real.
- **Tamaño**: 46,7 MB con el vocabulario podado compartido (fp32: 174 MB).
- **Lote** (solo `dinamico`; `ninguna` y `estatico` no dependen del lote): la escala int8 de las activaciones es dinámica y por tensor, así que `h` varía ~1e-4 según qué otros textos vayan en el
  lote (y su relleno). Para reproducir un valor exacto, un texto por llamada. La caché por clave de ESQUEMAS no se ve afectada.
- **Fixture para Go**: `model/l2/tests/fixtures_torre/torre.json` (20 textos, `input_ids` sin relleno con `<s>`=0, `</s>`=2 y
  `<pad>`=1, `h_fp32` y `h_onnx`). Un texto llega a los 128 tokens del truncado (el fixture es de `dinamico` con `max_len` 128).
