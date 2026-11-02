# M1 con el ajuste v2 (texto de torre sin id) por servidor: peor que el ajuste 1. **No es la línea base oficial.**

- `/healthz`: `texto_torre: "v2_sin_id"` y `torre_al_vuelo: true`. Código: `sdk` `5d285f1` (VF20). c6a.2xlarge, 18 min.
- **Exactitud 0,5836 y F1 0,5296**, determinista. Con el ajuste 1 era 0,6436 y 0,5769.

| conjunto | v2 | ajuste 1 |
|---|---|---|
| JevBench | 0,472 | 0,489 |
| massive | 0,353 | 0,413 |
| clinc150 | 0,631 | 0,715 |
| hatecheck | 0,488 | 0,476 |
| spam | 0,923 | 0,926 |
| inyecciones | 0,483 | 0,491 |
| herramientas | 0,595 | 0,633 |

**Sospecha de un fallo de paridad en el camino v2.** En Python, el mismo checkpoint da 0,5022 en JevBench (`ajuste.sh`, con
`jevbench_l2` k = 0). Por servidor da 0,472. Con v1 la paridad era de 0 discrepancias. Diagnóstico en curso con `e2e.sh`
(`paridad_servidor diagnosticar`) sobre v2.

La línea base oficial sigue siendo `linea-base-oficial-20261102` (ajuste 1).
