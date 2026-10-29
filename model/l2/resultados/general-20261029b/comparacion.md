# G.8 L2 de propósito general: comparación

## Tareas no vistas y control (macro-F1 global; κ = 1; «ref» = T2.1b, que sí vio las tareas)

| tarea | no vista | zero-shot | ref zero-shot | razón | k=8 | k=8 κ | k=32 | k=32 κ | ref k=32 |
|---|---|---|---|---|---|---|---|---|---|
| massive | sí | 0.309 | 0.487 | 0.63 | 0.421 | 0.420 | 0.431 | 0.433 | 0.632 |
| hatecheck | sí | 0.531 | 0.610 | 0.87 | 0.531 | 0.543 | 0.513 | 0.513 | 0.630 |
| inyecciones | sí | 0.326 | 0.862 | 0.38 | 0.362 | 0.362 | 0.379 | 0.379 | 0.922 |
| tasksource_fuera | sí | 0.192 | 0.221 | 0.87 | 0.192 | 0.192 | 0.192 | 0.192 | 0.221 |
| clinc150 | no (control) | 0.782 | 0.544 | 1.44 | 0.815 | 0.819 | 0.824 | 0.824 | 0.775 |
| herramientas | no (control) | 0.603 | 0.328 | 1.84 | 0.616 | 0.623 | 0.635 | 0.640 | 0.504 |

**H1 (no vistas)** zero-shot ≥ 0,9 × T2.1b en todas las no vistas: SE REFUTA

## JevBench público (231 casos; exactitud / macro-F1)

| variante | exactitud | macro-F1 |
|---|---|---|
| zero-shot | 0.463 | 0.297 |
| k=8 | 0.273 | 0.151 |
| k=8 κ=1 | 0.281 | 0.147 |
| k=32 | 0.273 | 0.151 |
| k=32 κ=1 | 0.281 | 0.147 |

T2.1b (G.1): zero-shot 0.407, con soporte 0.230 (exactitud).
**H1 (JevBench)** exactitud sin soporte ≥ 0,55: SE REFUTA (0.463)

## H2: el soporte con shrinkage no empeora el zero-shot en más de 1 punto y mejora con k ≥ 4

| conjunto | zero-shot | k=8 κ | Δ k=8 | k=32 κ | Δ k=32 |
|---|---|---|---|---|---|
| massive | 0.309 | 0.420 | +0.111 | 0.433 | +0.125 |
| hatecheck | 0.531 | 0.543 | +0.012 | 0.513 | -0.018 |
| inyecciones | 0.326 | 0.362 | +0.036 | 0.379 | +0.053 |
| clinc150 | 0.782 | 0.819 | +0.037 | 0.824 | +0.042 |
| herramientas | 0.603 | 0.623 | +0.020 | 0.640 | +0.037 |
| JevBench k=8 κ=1 | 0.463 | 0.281 | -0.182 | | |
| JevBench k=32 κ=1 | 0.463 | 0.281 | -0.182 | | |

**H2** nunca peor que el zero-shot en más de 1 punto: SE REFUTA
**H2** mejora con k ≥ 4 (en todas): NO EN TODAS
