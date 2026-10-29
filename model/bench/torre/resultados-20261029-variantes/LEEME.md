# G.7, variantes de la torre de L2 con el checkpoint real (c6a, rama del SDK `530c7c9`, 2026-10-29)

| variante | coseno sin `<unk>` | top-1 sin `<unk>` | coseno con poda (7,5 % `<unk>`) | top-1 con poda | MB | p50 / p99 por texto |
|---|---|---|---|---|---|---|
| **fp32 (ninguna)** | **1,0000** | **1,000** | 0,967 | 0,917 | 174 | 16,1 / 21,8 ms |
| int8 dinámico por canal | 0,986 | 0,937 | 0,954 | 0,887 | 46,7 | 9,5 / 13,3 ms |
| int8 estático (500 frases) | 0,907 | 0,810 | 0,898 | 0,840 | 46,8 | 10,4 / 14,8 ms |

- **Solo fp32 sin `<unk>` cumple la paridad** (coseno ≥ 0,999 y top-1 ≥ 0,98).
  - El int8 dinámico pierde fidelidad con la torre entrenada.
  - El estático calibrado sale peor: la calibración con massive-es no representa bien los textos de la torre.
- **La poda del vocabulario** (55 k tokens) cuesta 3–8 puntos de top-1 con cualquier variante, porque el 7,5 % de los tokens
  de massive-es caen en `<unk>`. Para cumplir la paridad hace falta fp32 **sin poda** (unos 470 MB) o una poda ampliada con
  el idioma de los esquemas.
- **Tests de la rama del SDK con `CHISPA_TOK`:** `go test -tags ort ./server/torre/...` da 7 PASS y
  `TestIgualdadTransformersPasaje` pasa. `chispa train --torre` y el servidor funcionan en las tres variantes.
- **JevBench por el servidor** con la variante estática: 0,429, frente a 0,416 en Python con los mismos casos. Los 231
  escalan, por el τ de CALIB.
- **El `.chispa` con score K ≥ 3 falló** (`exportar-score.log`, que no se subió). Queda pendiente.
- **Coste:** una c6a de 7 min, ≈ 0,02 USD.
