# Listón humano (T1.5c)

Test con etiquetas de varios anotadores humanos, de datasets públicos. Sustituye al etiquetado a mano:
da el `etiqueta` (mayoría), la `blanda` (reparto de los anotadores) y el acuerdo entre humanos, que es el
techo contra el que se mide a Chispa. Esquema: `model/esquema.md` (sin tocar).

    python -m model.liston.acuerdo_humano --salida /tmp/liston [--readme]

Convierte las cinco fuentes a `/tmp/liston/<fuente>.jsonl` (nunca a git), escribe `acuerdo.json` (con el
desglose por variedad de MultiPICo) y, con `--readme`, rehace la tabla de abajo. Valida con
`python -m model.datos.validar /tmp/liston/*.jsonl`. Tests: `python -m unittest discover -s model -t .`.

## Reglas de conversión
- `split: test` siempre. `etiqueta` = mayoría de los anotadores; **empate → la clase de menor índice** en
  `opciones` (en las binarias, `false`). `blanda` = proporción de anotadores por clase (suma 1, con ceros).
- Una unidad por texto; se descartan las que no tienen todos los votos válidos.
- **Campos extra opcionales, pendientes de aprobación del orquestador** (`esquema.md` no se ha tocado):
  `anotadores: int` (pedido), y dos más solo en MultiPICo, `variedad: str` y `paises_anotadores: list[str]`.

## Fuentes
| Fuente | Tarea | Qué se hace |
|---|---|---|
| MultiPICo | `ironia` (noul) | Solo `language == es`. `texto` = «Mensaje: … / Respuesta: …». 3 a 14 anotadores por texto. |
| ALIA `human_sample` | `odio` (noul) | Solo filas con `annotator_1..3` válidos (las 3000). No se usan las etiquetas de LLM. |
| toxicity-protests-ES, toxicity-Constitution-ES | `toxicidad` (noul) | `coder_1`, `coder_2`. Con desacuerdo, `false`; no se usa la columna `consensus` (adjudicada). |
| GoEmotions `raw` | `emocion` (choice, 28) | Ver abajo. |

**MultiPICo y la variedad.** `language_variety` (co, mx, ar, es, us) es la variedad **del texto**, no la del
anotador: es constante por `reply_id` y los anotadores residen en cualquier país (el del anotador solo viene
como país de residencia). Por eso `variedad` guarda la del texto y `paises_anotadores` el país de cada
anotador; el desglose de `acuerdo.json` es por variedad del texto. `us` también se incluye (español de EE. UU.).

**GoEmotions.** `raw` está en inglés y trae varias emociones posibles por anotador. La unión con
`mrm8488/go_emotions-es-mt` por `id` funciona (se pierden pocos ids, ver `info` en `acuerdo.json`), así que
`texto` es la traducción automática al español y `idioma: en` indica que los anotadores vieron el inglés.
Cada anotador aporta **una** etiqueta: su emoción de menor índice (orden de GoEmotions, `neutral` la última);
los anotadores sin emoción se descartan y las unidades con menos de 3 anotadores no se usan. Esa regla
infravalora el acuerdo real de la tarea multietiqueta: úsese como cota baja, no como techo comparable.

## Acuerdo humano
α de Krippendorff nominal (admite nº variable de anotadores), κ de Fleiss (unidades con el nº de anotadores
más frecuente; con 2 anotadores equivale a π de Scott), κ de Cohen donde hay dos codificadores fijos
(`model.etiquetado.acuerdo.kappa`) y **techo humano** = exactitud media de un anotador contra la mayoría de
los demás (si los demás empatan, el acierto se reparte entre las clases empatadas).

<!-- tabla -->
| Fuente | Tarea | Filas | Anotadores/fila | α Krippendorff | κ Fleiss | κ Cohen | Techo humano |
|---|---|---|---|---|---|---|---|
| multipico | ironia | 4683 | 5.13 | 0.238 | 0.238 (n=5) | n/d | 0.705 |
| alia | odio | 3000 | 3.00 | 0.255 | 0.255 (n=3) | n/d | 0.853 |
| toxprotestas | toxicidad | 1000 | 2.00 | 0.944 | 0.944 (n=2) | 0.944 | 0.972 |
| toxconstitucion | toxicidad | 1000 | 2.00 | 0.652 | 0.652 (n=2) | 0.654 | 0.835 |
| goemotions | emocion | 52944 | 3.58 | 0.287 | 0.401 (n=3) | n/d | 0.376 |
<!-- /tabla -->

Lectura: el criterio original (κ ≥ 0,7) solo lo cumple toxicity-protests-ES; ironía, odio y emoción tienen
acuerdo bajo entre humanos, y es lo esperable en tareas subjetivas. Para esas, conviene medir a Chispa con
la `blanda` (log-loss / Brier contra la distribución) además de la exactitud contra la mayoría.
