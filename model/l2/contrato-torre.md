# Contrato de la torre de esquemas de L2 (para calcular torres al vuelo en `chispa-server`)

Fuente de verdad: `model/l2/modelo.py` (`texto_opcion`, `texto_consulta`, `Codificador.pasaje`, `Torre`, `maxsim`) y
`model/l2/exportar.py` (torres de ESQUEMAS). Este contrato describe lo que existe. El ONNX de la torre lo exporta
`model/l2/exportar.py` (en preparación: `--torre-onnx`). Si algo de aquí no cuadra con el código, manda el código: avísame.

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
- Truncado a **128** tokens (`MAX_TOK`), con los especiales `<s>` y `</s>` incluidos, y relleno con máscara de atención.

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
- **Cuantización:** int8 dinámico **por canal**, solo en los MatMul de e5. Las capas de `Torre` quedan en fp32, igual que
  las ranuras en la consulta.
- **Opset:** 17.

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

## Paridad esperada
- Para medirla (pendiente), se compara `h` ONNX int8 con `h` PyTorch fp32, por coseno, y el top-1 de choice con torres al
  vuelo frente a las de ESQUEMAS.
- El objetivo es un coseno medio ≥ 0,999 y un top-1 ≥ 0,98, al nivel del de la consulta.
- Las cifras se publicarán en `model/l2/resultados/torre-onnx/`.
