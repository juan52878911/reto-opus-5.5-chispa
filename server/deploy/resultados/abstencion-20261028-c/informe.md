# Abstención de la cascada con tráfico no adversarial (T4.6)

| tarea | n | escala | precisión contestada | macro-F1 contestada | macro-F1 escala=fallo | macro-F1 mejor respuesta | H1 | τ (abst. ≤ 20 %) | abstención | precisión | precisión estimada (train) | real − estimada |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| clinc150 | 5500 | 11.7 % | 0.918 | 0.933 | 0.908 | 0.886 | se refuta (precisión < 0,95) | 0.791 | 20.0 % | 0.949 | 0.950 | -0.032 |
| injection | 108 | 24.1 % | 1.000 | 1.000 | 0.841 | 0.897 | se cumple | 0.893 | 18.5 % | 1.000 | 1.000 | +0.000 |
| massive | 2974 | 22.2 % | 0.933 | 0.875 | 0.761 | 0.815 | no aplica (F1 < 0,85) | 0.687 | 20.0 % | 0.929 | 0.950 | -0.017 |
| spam | 108 | 84.3 % | 1.000 | 1.000 | 0.239 | 0.839 | no aplica (F1 < 0,85) | 0.813 | 19.4 % | 1.000 | 1.000 | +0.000 |
