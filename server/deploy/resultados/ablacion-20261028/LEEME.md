# T4.5b, ablación de H2 (c6a, 2026-10-28): el culpable es L0

- **Arnés.** En clinc150 reproduce las dos corridas de control: 0,8462 y 0,8894, frente a 0,846 y 0,890. En massive la
  corrida «todo servidor» da 0,7657 frente a 0,771, 0,53 puntos fuera de ±0,5. Aun así coincide en top-1 con el
  `pred.jsonl` del servidor en el 99,8 % de las filas; la diferencia sale del tokenizador de HF frente al de Go.
- **Culpable: E, el L0.**

| | hueco | E (L0 de sklearn con su cabeza) | E+ (cabeza reentrenada con el L0 de Chispa) | resto |
|---|---|---|---|---|
| massive | 5,1 | +4,7 | +0,9 | A–D y F ≤ 0,1 |
| clinc150 | 4,3 | +4,1 | +1,2 | A +0,4; B–D y F ≤ 0,05 |

- **Qué significa.** No es solo un desajuste de entrenamiento: reentrenar la cabeza sobre el L0 de Chispa recupera ~1
  punto. Las probabilidades del L0 de Chispa (`pkg/chispa`, hashing y temperatura calibrada) son peores como
  característica de la cabeza que las del TF-IDF de caracteres con regresión logística de sklearn, aunque como
  clasificador solo validen igual (0,790 frente a 0,794).
- **Descartados.** El ONNX int8, las torres, los prototipos, simproto int8 y el atajo de la cascada: ≤ 0,4 puntos cada uno.
- **Arreglo.** Llevar al servidor el L0 TF-IDF con el que se entrena y mide la conjunta (T4.5c).
- **Coste.** Dos c6a. La primera paró al exportar porque faltaba `--min-top1 0`, fallo de configuración del
  orquestador. La segunda tardó unos 60 min. Menos de 0,2 USD.
