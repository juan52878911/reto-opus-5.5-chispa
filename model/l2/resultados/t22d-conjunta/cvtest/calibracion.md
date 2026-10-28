# Calibración de la conjunta (cabeza cvtest, T o Platt fuera de pliegue sobre test)

| tarea | ECE antes | ECE después | NLL antes | NLL después | cobertura p≥0,95 antes | después | AUROC acierto | AUROC escalate |
|---|---|---|---|---|---|---|---|---|
| clinc150 | 0.022 | 0.022 | 0.534 | 0.535 | 0.801 | 0.799 | 0.891 | 0.893 |
| hatecheck | 0.058 | 0.060 | 0.506 | 0.508 | 0.230 | 0.066 | 0.693 | - |
| herramientas | 0.040 | 0.037 | 0.862 | 0.877 | 0.448 | 0.489 | 0.848 | 0.535 |
| inyecciones | 0.053 | 0.143 | 0.245 | 0.609 | 0.836 | 0.431 | 0.843 | - |
| massive | 0.014 | 0.012 | 0.584 | 0.584 | 0.721 | 0.720 | 0.869 | - |

H2 (ECE ≤ 0,05 en las 5 tareas y cobertura ≥ 70 % en ≥ 3): ECE ok en 3/5 (clinc150, herramientas, massive); cobertura ok en 2/5 (clinc150, massive) → REFUTADA.
Los parámetros de cada fila salen del otro pliegue de test; la cobertura usa el τ que da precisión ≥ 0,95 sobre el mismo test (como en T2.4), no uno ajustado fuera de pliegue. En `cvtest` las probabilidades del pliegue de ajuste salen de una cabeza que vio el pliegue evaluado: dependencia débil (1 parámetro), no eliminada.
