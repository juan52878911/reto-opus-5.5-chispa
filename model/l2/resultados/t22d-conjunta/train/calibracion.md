# Calibración de la conjunta (cabeza train, T o Platt fuera de pliegue sobre test)

| tarea | ECE antes | ECE después | NLL antes | NLL después | cobertura p≥0,95 antes | después | AUROC acierto | AUROC escalate |
|---|---|---|---|---|---|---|---|---|
| clinc150 | 0.033 | 0.025 | 0.561 | 0.553 | 0.803 | 0.801 | 0.896 | 0.908 |
| hatecheck | 0.321 | 0.109 | 1.919 | 0.602 | 0.000 | 0.000 | 0.548 | - |
| herramientas | 0.187 | 0.056 | 1.245 | 0.937 | 0.478 | 0.435 | 0.851 | 0.494 |
| inyecciones | 0.035 | 0.064 | 0.183 | 0.467 | 0.940 | 0.621 | 0.749 | - |
| massive | 0.020 | 0.017 | 0.585 | 0.585 | 0.715 | 0.717 | 0.867 | - |

H2 (ECE ≤ 0,05 en las 5 tareas y cobertura ≥ 70 % en ≥ 3): ECE ok en 2/5 (clinc150, massive); cobertura ok en 2/5 (clinc150, massive) → REFUTADA.
Los parámetros de cada fila salen del otro pliegue de test; la cobertura usa el τ que da precisión ≥ 0,95 sobre el mismo test (como en T2.4), no uno ajustado fuera de pliegue. En `cvtest` las probabilidades del pliegue de ajuste salen de una cabeza que vio el pliegue evaluado: dependencia débil (1 parámetro), no eliminada.
