| tarea | n | L0 (línea base) | L0 (train completo) | L2+soporte | conjunta | cabeza | lr | puerta | Δ vs mejor capa | listón (0,95×mejor ref.) | cumple |
|---|---|---|---|---|---|---|---|---|---|---|---|
| clinc150 | 5500 | 0.811 | 0.877 | 0.775 | 0.891 | lr | 0.891 | 0.875 | +0.014 | 0.771 | sí |
| hatecheck | 361 | 0.530 | 0.592 | 0.630 | 0.667 | puerta | 0.579 | 0.667 | +0.037 | 0.550 | sí |
| herramientas | 368 | 0.696 | 0.696 | 0.504 | 0.734 | lr | 0.734 | 0.665 | +0.038 | 0.661 | sí |
| inyecciones | 116 | 0.835 | 0.843 | 0.922 | 0.922 | lr | 0.922 | 0.914 | +0.000 | 0.793 | sí |
| massive | 2974 | 0.678 | 0.794 | 0.632 | 0.818 | lr | 0.818 | 0.796 | +0.024 | 0.644 | sí |

H1 (conjunta ≥ mejor capa + 0,01 en ≥ 3 de 5 y listón en ≥ 4 de 5): 4/5 tareas con Δ ≥ +0,01; 5/5 con el listón.
Refutación (no supera a la mejor capa en ≥ 3 tareas): 5/5 tareas con Δ > 0 → no refutada.
Mejor capa = máximo de L0 (línea base), L0 (train completo) y L2 con soporte; «cabeza» es la elegida por CV en train.
