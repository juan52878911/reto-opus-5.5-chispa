# Abstención de la cascada con tráfico no adversarial (T4.6)

| tarea | n | escala | precisión contestada | macro-F1 contestada | macro-F1 escala=fallo | macro-F1 mejor respuesta | H1 | τ (abst. ≤ 20 %) | abstención | precisión |
|---|---|---|---|---|---|---|---|---|---|---|
| clinc150 | 5500 | 0.1 % | 0.859 | 0.887 | 0.887 | 0.887 | se refuta (precisión < 0,95) | 0.791 | 20.0 % | 0.949 |
| injection | 108 | 18.5 % | 1.000 | 1.000 | 0.886 | 0.897 | se cumple | 0.902 | 19.4 % | 1.000 |
| massive | 2974 | 27.8 % | 0.949 | 0.903 | 0.736 | 0.814 | no aplica (F1 < 0,85) | 0.687 | 20.0 % | 0.928 |
| spam | 108 | 32.4 % | 1.000 | 1.000 | 0.760 | 0.829 | no aplica (F1 < 0,85) | 0.812 | 19.4 % | 1.000 |
