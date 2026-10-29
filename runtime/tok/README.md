# runtime/tok — tokenizador de multilingual-e5-small en Go

`tok.Abrir("e5.chispa-tok").Tokenizar(texto) []int32` devuelve los ids de `AutoTokenizer(...)("query: " + texto,
truncation=True, max_length=128)` de `transformers` (con `<s>` y `</s>`), que es lo que hace `model/l2/modelo.py` y lo que espera el ONNX de L2.

- **Motor**: el de `runtime/l1` (Viterbi sobre unigram, charsmap de sentencepiece, tabla hash FNV). `l1.DesdeTokenizador` lee un
  `.chispa-tok` (misma cabecera y secciones que el `.chispa-l1` con magia `CHTK` y sin pesos) y activa el modo `xlmr`: Precompiled →
  WhitespaceSplit → Metaspace(`always`, partiendo antes de cada `▁`) → Unigram palabra a palabra. No toca el modo de potion (su test dorado
  sigue igual).
- **Referencia**: el pipeline de `transformers` 5.x, que NO es el de `tokenizer.json` tal cual (el JSON normaliza `" {2,}"` y hace
  Metaspace sobre toda la frase; transformers usa WhitespaceSplit). Difieren en 38 de 2.315 frases de borde (un `▁` final suelto);
  `referencia.py --tokenizers` genera la referencia del otro pipeline. Si AWS instala otra versión de transformers y esto cambia, el test lo dice.
- **Exportar**: `python runtime/tok/exportar.py <dir-e5> /tmp/e5.chispa-tok` (3 s, determinista).
- **Pruebas** (`CHISPA_TOK`, por defecto `/tmp/e5.chispa-tok`; se saltan si falta): `go test ./...` compara con `testdata/ids_e5.jsonl`
  (2.274 frases del sondeo + 41 de borde, ids de transformers; 390 KB); `CHISPA_TOK_FUZZ=f.jsonl` con `referencia.py <dir> f.jsonl --fuzz N`;
  `go test -fuzz FuzzTokenizar -fuzztime 2m` comprueba forma, rango de ids y determinismo.

## Modo «passage: » (torre de esquemas de L2)
`TokenizarPasaje(texto)` = `TokenizarCon("passage: ", texto)`: mismo pipeline, prefijo de pasaje, truncado a 128. `referencia.py <dir> <salida> --pasaje`
genera los ids de transformers con ese prefijo (más 9 textos con el formato `pregunta · opción · descripción`, U+00B7 y descripción vacía);
`testdata/ids_e5_passage.jsonl` (2.324 frases) lo comprueba `TestIgualdadTransformersPasaje`.
