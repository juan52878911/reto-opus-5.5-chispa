# Contrato de normalización de mayúsculas de L2 (W3b)

Para la sesión del runtime (paridad en Go). Referencia ejecutable: `modelo.normalizar_mayusculas`; tests en
`model/l2/tests/test_normalizacion.py`; casos en `model/l2/tests/fixtures/normalizacion.json` (12 pares entrada → salida).

## Regla exacta
Sea `L` la lista de caracteres del texto con `str.isalpha()` verdadero (Unicode, incluye acentos y ñ; no cuentan dígitos, signos ni emojis).
Si `len(L) ≥ 8` **y** `10·(nº de L con str.isupper()) > 7·len(L)` (más del 70 %, estricto), el resultado es `texto.lower()`.
Si no, el texto sin tocar. Es idempotente. En Go: `unicode.IsLetter`, `unicode.IsUpper`, `strings.ToLower` (cuidado con `lower()` de Python
en casos especiales como «İ»; los 12 casos no los incluyen).

## Qué campo y cuándo
- Solo el **texto del mensaje** (`fila["texto"]`), nunca la pregunta, las opciones ni las descripciones. La torre de pasaje
  (`texto_opcion`/`texto_consulta`) no lleva mensaje y no cambia.
- **Antes** de anteponer `"query: "`, de tokenizar y de truncar o ventanear (`contrato-largos.md`).
- Entrenamiento y evaluación (`Codificador.tokens`, `largos.tokenizar`, `calibrar.py`, `exportar.py`): se aplica al codificar. El
  aumento genera la variante de mayúsculas antes, así que el modelo ve lo mismo que verá en producción.
- No se aplica a L1.
