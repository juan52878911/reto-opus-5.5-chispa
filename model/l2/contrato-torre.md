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
- La clave en ESQUEMAS y CONJ depende de la versión del formato de claves (siguiente sección). Desde la v2 incluye la descripción.

## Claves de ESQUEMAS y CONJ: versión 2 (con descripción)
**Dónde viaja la versión:** `META.version` del `.chispa` (entero; ya existía y el lector solo exige ≥ 1). `1` = claves antiguas, `2` = claves
con descripción. No cambia el binario de ninguna sección, así que `format/chispa3` lee un fichero v2 sin tocarse; solo el runtime que
busca las torres tiene que elegir la clave según `META.version`. `exportar.py` **siempre escribe 2**; los `.chispa` existentes dicen 1.

`HashEsquema(pregunta, lista)` es el de siempre (`chispa3.HashEsquema`: sha256 con prefijos de longitud u64). Lo que cambia es la `lista`:

| sección / tipo | v1 (`META.version` 1) | v2 (`META.version` 2) |
|---|---|---|
| ESQUEMAS, choice (una entrada por opción) | `[opción]` | `[opción, descripción]` |
| ESQUEMAS, noul y score (una por pregunta) | `[o1, o2, …]` (en el orden de la pregunta) | `[o1, d1, o2, d2, …]` (ídem) |
| CONJ y SOPL1 (solo choice) | `[id1, id2, …]` ordenados | `[id1, d1, id2, d2, …]` con los ids ordenados |

`descripción` = la de la opción tal cual, y la cadena vacía si no hay (el mismo valor que entra en el texto de la torre). Es la clave de
la torre al vuelo: dos esquemas con las mismas opciones y distinta descripción ya no comparten torre precalculada.

Ejemplo (choice, pregunta `¿Qué quiere la persona?`, opción `alarma`, descripción `Poner una alarma.`):
- v1: `HashEsquema("¿Qué quiere la persona?", ["alarma"])` = `5fc4d79dee73d7018f230686f9e139193461929ea3d3d8a0a0031f7ed5d459db`
- v2: `HashEsquema("¿Qué quiere la persona?", ["alarma", "Poner una alarma."])` =
  `6143d44c05f4222dee1832556566605bb109f52893a315334728e742121880d4`

**Compatibilidad hacia atrás (qué hace el runtime):**
- `META.version` 1 (o ausente): buscar con la clave v1, como hoy. Los fixtures v1 (`fixtures/calib-score.chispa`, `format/chispa3/testdata`) se
  quedan tal cual para probarlo.
- `META.version` ≥ 2: buscar con la v2. No hace falta reintentar con la otra.
- Reintentar con la v1 si la v2 no aparece (y a la inversa) sería opcional y daría falsos aciertos en descripciones que cambian; no se recomienda.
- **CONJ y SOPL1 no los escribe `exportar.py`** sino `chispa train --conjunta` (SDK): ese escritor debe pasar a la clave v2 y poner
  `META.version` 2 cuando todas sus claves lo sean. Un fichero con ESQUEMAS v2 y CONJ v1 no es válido: la versión es única por fichero.

**Fixture de paridad para el runtime:** `model/l2/tests/fixtures/esquemas-v2.chispa` (2,3 KB: ONNX de L2 de relleno, torres de un modelo diminuto) y
`esquemas-v2.json` con, por entrada, `tipo`, `pregunta`, `opciones` (la lista v2), `hash` y `hash_v1` en hex, el `texto_torre`, y las claves de
`conj`. Se regeneran con `python -m model.l2.tests.gen_esquemas_v2`; `test_esquemas_v2.py` comprueba que coinciden con un hashlib
independiente y con la sección ESQUEMAS del fichero. Incluye dos filas con las mismas opciones y distinta descripción de «alarma».

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
  - `--perfil servidor|movil` fija la combinación elegida (ver «Perfiles»).
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

## Perfiles (`exportar.py --perfil`)
- **`servidor`** = `--cuant ninguna --cuant-torre ninguna --sin-poda`: consulta y torre en fp32 con el vocabulario completo (250 037 ids). Sin `<unk>`
  nuevos: la paridad con PyTorch es exacta. ~473 MB la consulta y ~472 MB la torre.
- **`movil`**: int8 dinámico por canal en consulta (ranuras en fp32) y en torre, con el vocabulario podado **ampliado**.
  `--vocab-ampliar F…` (repetible, `.jsonl` o `.txt`) une al podado los ids de los tokens de esos textos (con los prefijos `query: ` y
  `passage: `); el informe da el % de `<unk>` antes y después. Ampliar es tolerable porque cada id nuevo cuesta una fila de 384 floats en int8.
- Medidas (e5 real, pesos aleatorios) en `model/l2/resultados/perfiles/LEEME.md`.
