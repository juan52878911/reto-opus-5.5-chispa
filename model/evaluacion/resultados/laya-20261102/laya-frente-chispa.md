# Laya frente a Chispa (zero-shot, CPU, 4 hilos)

Cada celda: exactitud (argmax) · F1 macro · ECE sin calibrar. Mismas filas de la batería (split test); Chispa de los linea-base*.json del repo.

**Recorte:** Laya midió como mucho 750 filas por conjunto (submuestra regular y determinista, por la prueba de velocidad); con `n` Laya/total. Chispa midió todas, así que las cifras no son del mismo subconjunto.

| conjunto | n | Laya multilingual | Laya typed-decisions | Chispa ajuste 1 | Chispa v2 | latencia ms p50/p99 (Laya multilingual / typed-decisions · Chispa ajuste 1 / v2) |
|---|---|---|---|---|---|---|
| jevbench | 231/231 | 0.489 · F1 0.473 · ECE 0.299 | 0.506 · F1 0.475 · ECE 0.084 | 0.489 · F1 0.484 · ECE 0.086 | 0.472 · F1 0.469 · ECE 0.063 | 124/1257 · 352/3370 vs 100/319 · 108/319 |
| massive | 750/2974 | 0.357 · F1 0.291 · ECE 0.183 | 0.272 · F1 0.190 · ECE 0.054 | 0.413 · F1 0.344 · ECE 0.025 | 0.353 · F1 0.309 · ECE 0.032 | 284/301 · 802/865 vs 21/29 · 23/31 |
| clinc150 | 750/5500 | 0.529 · F1 0.565 · ECE 0.250 | 0.440 · F1 0.474 · ECE 0.064 | 0.715 · F1 0.763 · ECE 0.162 | 0.631 · F1 0.671 · ECE 0.186 | 707/727 · 1874/1945 vs 21/30 · 24/34 |
| hatecheck | 361/361 | 0.598 · F1 0.586 · ECE 0.264 | 0.416 · F1 0.415 · ECE 0.249 | 0.476 · F1 0.465 · ECE 0.105 | 0.488 · F1 0.478 · ECE 0.092 | 76/88 · 236/288 vs 23/35 · 26/40 |
| spam | 750/1450 | 0.788 · F1 0.767 · ECE 0.172 | 0.889 · F1 0.888 · ECE 0.125 | 0.926 · F1 0.926 · ECE 0.222 | 0.923 · F1 0.923 · ECE 0.216 | 88/105 · 280/338 vs 30/42 · 32/42 |
| inyecciones | 116/116 | 0.621 · F1 0.570 · ECE 0.320 | 0.603 · F1 0.544 · ECE 0.172 | 0.491 · F1 0.344 · ECE 0.201 | 0.483 · F1 0.326 · ECE 0.230 | 79/174 · 246/556 vs 31/64 · 37/70 |
| herramientas | 368/368 | 0.283 · F1 0.259 · ECE 0.330 | 0.321 · F1 0.306 · ECE 0.055 | 0.633 · F1 0.609 · ECE 0.099 | 0.595 · F1 0.575 · ECE 0.076 | 274/284 · 798/823 vs 24/31 · 27/34 |
| global | 3326 | 0.529 · F1 0.467 · ECE 0.228 | 0.498 · F1 0.423 · ECE 0.034 | 0.644 · F1 0.577 · ECE 0.113 | 0.584 · F1 0.530 · ECE 0.110 | 277/1242 · 793/3192 vs 22/171 · 24/176 |

## M4: español frente a inglés (exactitud)

| par | n | Laya multilingual es · en · Δ | Laya typed-decisions es · en · Δ |
|---|---|---|---|
| massive | 200 | 0.395 · 0.455 · -0.060 | 0.265 · 0.450 · -0.185 |
| mmmlu | 200 | 0.295 · 0.315 · -0.020 | 0.295 · 0.355 · -0.060 |

Velocidad (50 preguntas de massive, multilingual): 0.28 s/pregunta; recortada a 750 filas por conjunto (submuestra regular y determinista).
