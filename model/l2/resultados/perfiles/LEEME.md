# Perfiles del exportador: servidor y móvil

Generado con `python -m model.l2.exportar --torre-onnx SALIDA --ckpt-aleatorio --perfil P [--vocab-ampliar …] --medir-torre DIR/P` y
después `--tabla-perfiles DIR`. e5 de `~/hf` y **pesos de L2 aleatorios con semilla fija**: la fidelidad del codificador y el
% de `<unk>` no dependen del entrenamiento; el top-1 con pesos aleatorios mide en parte empates (margen ~0,001), así que no
extrapola a un checkpoint entrenado.

| perfil | consulta MB | torre MB | total MB | coseno medio de `h` | coseno mín. | top-1 choice (300 filas) | top-1, mitad con más margen | `<unk>` textos de torre massive-es (antes → después) | `<unk>` mensajes massive-es dev |
|---|---|---|---|---|---|---|---|---|---|
| movil | 49.3 | 47.8 | 97.1 | 0,9997 | 0,9992 | 0,8067 | 0,9800 | 7,55 % → 0,45 % | 0,00 % → 0,00 % |
| servidor | 473.0 | 471.6 | 944.6 | 1,0000 | 1,0000 | 1,0000 | 1,0000 | 0 (sin poda) | 0 (sin poda) |

- `servidor`: `--cuant ninguna --cuant-torre ninguna --sin-poda` (fp32, vocabulario completo).
- `movil`: int8 dinámico por canal en consulta (ranuras en fp32) y torre, con el vocabulario podado + `--vocab-ampliar`.
- Coseno y top-1: ONNX tal como se exporta frente a PyTorch fp32 (torres y consulta idénticas en los dos lados del top-1).
- `<unk>` de torre: parte de los tokens de 300 textos de torre de massive-es (pregunta · intención · descripción, con `passage: `) que cae
  en `<unk>`; «antes» = vocabulario podado actual, «después» = ampliado. `<unk>` de mensajes: ídem con 300 mensajes de validación (`query: `).

## Hipótesis frente a lo medido
- **`<unk>` < 0,5 %: se cumple** en los textos de torre de massive-es (7,55 % → 0,45 %; 55 000 → 57 893 ids). Toda la mejora sale del corpus de
  español de `~/datos` (datos.gov, 71 830 textos): solo con él da 0,45 %; solo con el train de massive-es (11 514 mensajes) se queda en 7,55 %,
  porque los mensajes ya están cubiertos (0,00 % antes y después) y lo que falta son las palabras de las descripciones y las preguntas. Con la
  ampliación el `.chispa` no crece en lo que importa: consulta 49,3 MB (≤ 60 MB) y torre 47,8 MB.
- **top-1 ≥ 0,93: no se puede decidir aquí.** Con pesos aleatorios el top-1 completo es 0,81 y solo 0,98 en la mitad de filas con más margen
  (G.7 midió 0,75 sin ningún `<unk>`, así que el 0,81 no viene de la poda). Hay que repetirlo con el checkpoint real.
- **Servidor: paridad exacta** (coseno ≥ 0,99999, top-1 1,0), pero ~945 MB entre consulta y torre (el vocabulario completo, 250 037 filas × 384 floats, está en las dos).
- Corpus usados (fuera del repo): textos de las columnas de los CSV de `~/datos/datosgov` (una línea por celda de más de 12 caracteres) y
  `train/es` de massive-es como sustituto del train del cliente.
