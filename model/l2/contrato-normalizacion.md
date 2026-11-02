# Contrato de normalización de mayúsculas de L2 (W3b)

Para la sesión del runtime (paridad en Go). Referencia ejecutable: `modelo.normalizar_mayusculas`; tests en
`model/l2/tests/test_normalizacion.py`; casos en `model/l2/tests/fixtures/normalizacion.json` (16 pares entrada → salida; el 13.º, «LA CITA Nº 2ª vez», fija que «ª» y «º» son letras pero no mayúsculas: no cambia; el 14.º y el 15.º fijan «İ» → «i» y la sigma final → «σ»; el 16.º, «ⓉⓄⒹⓄ ⓂⒶⓁ ok», no cambia: las letras circuladas ⓐ–ⓩ no son letras para Python, que cuenta 2 letras y 0 mayúsculas entre ellas; `isupper()` sí marcaría las circuladas, por eso se cuentan solo sobre letras).

## Regla exacta
Sea `L` la lista de caracteres del texto con `str.isalpha()` verdadero (Unicode, incluye acentos y ñ; no cuentan dígitos, signos ni emojis).
Si `len(L) ≥ 8` **y** `10·(nº de L con str.isupper()) > 7·len(L)` (más del 70 %, estricto), el resultado es el texto en minúsculas **carácter a carácter**, con el primer punto de código de `c.lower()` de cada carácter (igual que `strings.ToLower` de Go: «İ» → «i», «Σ» final → «σ», sin la regla de sigma final de `str.lower`).
Si no, el texto sin tocar. Es idempotente. En Go: `unicode.IsLetter`, `unicode.IsUpper`, `strings.ToLower` (paridad exacta, incluidos «İ» y la sigma final).

## Qué campo y cuándo
- Solo el **texto del mensaje** (`fila["texto"]`), nunca la pregunta, las opciones ni las descripciones. La torre de pasaje
  (`texto_opcion`/`texto_consulta`) no lleva mensaje y no cambia.
- **Antes** de anteponer `"query: "`, de tokenizar y de truncar o ventanear (`contrato-largos.md`).
- Entrenamiento y evaluación (`Codificador.tokens`, `largos.tokenizar`, `calibrar.py`, `exportar.py`): se aplica al codificar. El
  aumento genera la variante de mayúsculas antes, así que el modelo ve lo mismo que verá en producción.
- No se aplica a L1.
