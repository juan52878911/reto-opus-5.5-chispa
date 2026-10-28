# Abstención de la cascada con tráfico no adversarial (T4.6)

| tarea | n | escala | precisión contestada | macro-F1 contestada | macro-F1 escala=fallo | macro-F1 mejor respuesta | H1 | τ (abst. ≤ 20 %) | abstención | precisión |
|---|---|---|---|---|---|---|---|---|---|---|
| clinc150 | 5500 | 46.3 % | 0.984 | 0.983 | 0.755 | 0.886 | se refuta (escala > 30 %) | 0.791 | 20.0 % | 0.949 |
| injection | 108 | 50.0 % | 1.000 | 1.000 | 0.500 | 0.897 | se refuta (escala > 30 %) | 0.902 | 19.4 % | 1.000 |
| massive | 2974 | 42.8 % | 0.969 | 0.937 | 0.628 | 0.814 | no aplica (F1 < 0,85) | 0.687 | 20.0 % | 0.928 |
| spam | 108 | 84.3 % | 1.000 | 1.000 | 0.239 | 0.829 | no aplica (F1 < 0,85) | 0.812 | 19.4 % | 1.000 |
