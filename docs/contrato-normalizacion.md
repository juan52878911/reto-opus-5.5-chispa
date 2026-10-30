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
- En el móvil, `chispamovil.TokenizarE5`/`TrozosE5` son tokenizadores puros (idénticos a `runtime/tok`) y no normalizan: lo hace quien llama a L2, una sola vez, con `NormalizarMayusculas` (Go), `normalizarMayusculas` (Kotlin, `CapaL2.decidir`) o `normalizarMayusculas` (Swift, `CapaL2.decidir`).

## Diferencias conocidas con Python

No se intenta cubrirlas todas; cada runtime usa las clases de caracteres de su plataforma.

- «İ» (U+0130): Python y Kotlin (`lowercase(Locale.ROOT)`) la pasan a «i» + punto combinante (dos code points); `strings.ToLower` de Go usa el mapeo simple y da «i». El texto resultante puede tokenizar distinto.
- Letras titlecase («ǅ») y letras de categorías raras: cada plataforma decide si son mayúscula; las cuatro cuentan como letra, pero pueden diferir en `isUpper`.
- «ª» y «º» (U+00AA, U+00BA) cuentan como letras pero no como mayúsculas en todos los runtimes («LA CITA Nº 2ª vez» no se normaliza, 13.º caso). Swift cuenta por escalares Unicode (`properties.isAlphabetic` / `properties.isUppercase`); `Character.isUppercase` las daría por mayúsculas y rompería la paridad.
- Swift cuenta por escalar Unicode, igual que Python, Go y Kotlin por code point. `isAlphabetic` incluye números romanos («Ⅻ») y letras en círculo («Ⓐ»), que `isalpha`/`IsLetter` no cuentan; raro en español.
- Versiones de Unicode distintas entre Python, Go, la JVM y Swift pueden clasificar distinto las letras añadidas recientemente.
