# M6 L1 frente a L2

L1 = potion con prototipos (32 por clase). L2 = checkpoint con k = 32 y sin soporte. Mismo test por tarea.

| tarea | n test | L1 | L2 k=32 | L1/L2 | L2 k=0 | L1/L2(k=0) |
|---|---|---|---|---|---|---|
| massive | 2974 | 0.597 | 0.431 | 1.387 | 0.308 | 1.938 |
| hatecheck | 361 | 0.540 | 0.515 | 1.049 | 0.531 | 1.017 |
| clinc150 | 5500 | 0.745 | 0.823 | 0.905 | 0.784 | 0.951 |
| inyecciones | 116 | 0.793 | 0.379 | 2.091 | 0.326 | 2.434 |
| herramientas | 368 | 0.597 | 0.639 | 0.934 | 0.603 | 0.991 |

Media L1/L2 con L2 k = 32 (criterio de la fase 3): **1.273** (5 tareas) → cumple el criterio ≥ 0.90

Media L1/L2 con L2 k = 0: **1.466** (5 tareas) → cumple el criterio ≥ 0.90
