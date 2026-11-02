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
- La clave en ESQUEMAS y CONJ es `HashEsquema2` (siguiente sección) e incluye la descripción.

## Texto de torre versión 2: sin id cuando hay descripción (`texto_torre: "v2_sin_id"`)
Aprobado el 2026-11-02, porque el id de la opción en el texto hacía que renombrar ids cambiara el 35 % de las decisiones de L2.
- **Flag:** el campo `texto_torre` de la sección **META** del `.chispa` (JSON).
  - Valores: `"v1"` o `"v2_sin_id"`.
  - **Si falta, es `"v1"`**, así que los `.chispa` existentes no cambian.
  - Lo escribe `model.l2.exportar` según el checkpoint: el checkpoint guarda `texto_torre` en su configuración y se entrena
    con él. `chispa train` lo copia del `l2.chispa` al `.chispa` final.
- **Texto v2 de una opción**, por vector de torre, en choice, en multi por opción, y en la opción de noul (`true`) y de score
  (nivel máximo):
  - si `descripción(opción).strip()` no está vacía: `"passage: " + pregunta + " · " + descripción(opción)`;
  - si está vacía, el texto v1 exacto: `"passage: " + pregunta + " · " + opción + " · "`. Sin descripción, el id es lo único
    que distingue las opciones.
  - **La descripción no se recorta ni se normaliza en el texto:** el `strip()` solo sirve para decidir si está vacía.
- **Lo que no cambia:**
  - las claves de ESQUEMAS y CONJ (`HashEsquema2` sigue incluyendo el id, que es lo que identifica la entrada);
  - el prefijo `passage: `, la tokenización, la red y el ONNX de la torre;
  - la consulta (`query: `) y la normalización de mayúsculas.
- **Las torres precalculadas en ESQUEMAS** se calculan con el texto de la versión que diga META. **El runtime calcula las
  torres al vuelo con esa misma versión.** Un `.chispa` v2 servido como v1 daría torres distintas de las de entrenamiento.
- **Paridad:** `model/l2/tests/fixtures/texto_torre_v2.json` trae casos `{pregunta, opcion, descripcion, v1, v2}` (con
  descripción, sin descripción, solo espacios y acentos) para los tests de Go, Kotlin y Swift.

## Claves de ESQUEMAS y CONJ: versión 2 (`HashEsquema2`)
**Dónde viaja la versión:** en la propia sección, no en `META.version` (que sigue siendo la del META y vale 1). ESQUEMAS v2 empieza con
la palabra `(2<<16 | dim)`; CONJ v2 con `versión = 2`. Las dos llevan claves de 16 bytes. `exportar.py` **siempre escribe ESQUEMAS v2**.

Clave (`format/chispa3/clave2.go`, explicada en `docs/04-formato-chispa.md`):
`sha256(pregunta · 0x1f · kind · 0x1f · por cada opción ordenada por id: id · 0x1e · descripción · 0x1d)[:16]`.

| sección | `kind` | opciones de la clave |
|---|---|---|
| ESQUEMAS, choice (una entrada por opción) | `choice` | solo `(opción, descripción)` |
| ESQUEMAS, noul y score (una por pregunta) | `noul` / `score` | todas las `(id, descripción)` |
| CONJ (solo choice) | `choice` | todas las `(id, descripción)` |
| SOPL1 | — | **sigue con la clave v1** (`clave_conj`) |

`descripción` = la de la opción tal cual, y la cadena vacía si no hay. Es la clave de la torre al vuelo: dos esquemas con las mismas
opciones y distinta descripción no comparten torre precalculada.

`exportar.py` pasa a `empaquetar_go` entradas `{pregunta, kind, opciones: [{id, description}], escala, vec}` y el empaquetador calcula
la clave con `chispa3.HashEsquema2`. En Python: `exportar.clave_torre` y `exportar.hash_clave` (`formato.hash_esquema2`);
`test_esquemas_v2.py` reproduce los 5 vectores de `format/chispa3/vectores-clave-v2.json`.

**Compatibilidad:** el runtime elige la clave según la versión de la sección (`Esquemas.Version()`), no según `META`. Los fixtures v1
(`fixtures/calib-score.chispa`) siguen con ESQUEMAS v1. **CONJ no lo escribe `exportar.py`** sino `chispa train --conjunta` (SDK):
fuera de esta zona.

**Fixture de paridad para el runtime:** `model/l2/tests/fixtures/esquemas-v2.chispa` (2,3 KB: ONNX de L2 de relleno, torres de un modelo diminuto) y
`esquemas-v2.json` con, por entrada, `tipo`, `pregunta`, `kind`, `opciones` (`{id, description}`) y `hash` en hex, el `texto_torre`, y las claves de
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
