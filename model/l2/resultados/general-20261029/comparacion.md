# G.8 L2 de propósito general: comparación

## Tareas no vistas y control (macro-F1 global; κ = 1; «ref» = T2.1b, que sí vio las tareas)

| tarea | no vista | zero-shot | ref zero-shot | razón | k=8 | k=8 κ | k=32 | k=32 κ | ref k=32 |
|---|---|---|---|---|---|---|---|---|---|
| massive | sí | 0.243 | 0.487 | 0.50 | 0.480 | 0.481 | 0.512 | 0.514 | 0.632 |
| hatecheck | sí | 0.463 | 0.610 | 0.76 | 0.498 | 0.486 | 0.494 | 0.493 | 0.630 |
| inyecciones | sí | 0.326 | 0.862 | 0.38 | 0.459 | 0.444 | 0.444 | 0.444 | 0.922 |
| tasksource_fuera | sí | 0.201 | 0.221 | 0.91 | 0.201 | 0.201 | 0.201 | 0.201 | 0.221 |
| clinc150 | no (control) | 0.607 | 0.544 | 1.12 | 0.770 | 0.769 | 0.793 | 0.792 | 0.775 |
| herramientas | no (control) | 0.498 | 0.328 | 1.52 | 0.593 | 0.575 | 0.595 | 0.597 | 0.504 |

**H1 (no vistas)** zero-shot ≥ 0,9 × T2.1b en todas las no vistas: SE REFUTA

## JevBench público (231 casos; exactitud / macro-F1)

| variante | exactitud | macro-F1 |
|---|---|---|
| zero-shot | 0.472 | 0.300 |
| k=8 | 0.286 | 0.146 |
| k=8 κ=1 | 0.281 | 0.141 |
| k=32 | 0.286 | 0.146 |
| k=32 κ=1 | 0.281 | 0.141 |

T2.1b (G.1): zero-shot 0.407, con soporte 0.230 (exactitud).
**H1 (JevBench)** exactitud sin soporte ≥ 0,55: SE REFUTA (0.472)

## H2: el soporte con shrinkage no empeora el zero-shot en más de 1 punto y mejora con k ≥ 4

| conjunto | zero-shot | k=8 κ | Δ k=8 | k=32 κ | Δ k=32 |
|---|---|---|---|---|---|
| massive | 0.243 | 0.481 | +0.238 | 0.514 | +0.271 |
| hatecheck | 0.463 | 0.486 | +0.023 | 0.493 | +0.030 |
| inyecciones | 0.326 | 0.444 | +0.118 | 0.444 | +0.118 |
| clinc150 | 0.607 | 0.769 | +0.161 | 0.792 | +0.185 |
| herramientas | 0.498 | 0.575 | +0.077 | 0.597 | +0.099 |
| JevBench k=8 κ=1 | 0.472 | 0.281 | -0.190 | | |
| JevBench k=32 κ=1 | 0.472 | 0.281 | -0.190 | | |

**H2** nunca peor que el zero-shot en más de 1 punto: SE REFUTA
**H2** mejora con k ≥ 4 (en todas): NO EN TODAS
