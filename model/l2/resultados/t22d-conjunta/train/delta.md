| tarea | n | L0 (línea base) | L0 (train completo) | L2+soporte | conjunta | cabeza | lr | puerta | Δ vs mejor capa | listón (0,95×mejor ref.) | cumple |
|---|---|---|---|---|---|---|---|---|---|---|---|
| clinc150 | 5500 | 0.811 | 0.877 | 0.775 | 0.890 | lr | 0.890 | 0.862 | +0.012 | 0.771 | sí |
| hatecheck | 361 | 0.530 | 0.592 | 0.630 | 0.571 | lr | 0.571 | 0.592 | -0.059 | 0.550 | sí |
| herramientas | 368 | 0.696 | 0.696 | 0.504 | 0.729 | lr | 0.729 | 0.704 | +0.033 | 0.661 | sí |
| inyecciones | 116 | 0.835 | 0.843 | 0.922 | 0.931 | lr | 0.931 | 0.931 | +0.009 | 0.793 | sí |
| massive | 2974 | 0.678 | 0.794 | 0.632 | 0.817 | lr | 0.817 | 0.798 | +0.023 | 0.644 | sí |

H1 (conjunta ≥ mejor capa + 0,01 en ≥ 3 de 5 y listón en ≥ 4 de 5): 3/5 tareas con Δ ≥ +0,01; 5/5 con el listón.
Refutación (no supera a la mejor capa en ≥ 3 tareas): 4/5 tareas con Δ > 0 → no refutada.
Mejor capa = máximo de L0 (línea base), L0 (train completo) y L2 con soporte; «cabeza» es la elegida por CV en train.
