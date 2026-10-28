# T4.5: /v1/decide de punta a punta

| tarea | modo | n | macro-F1 /v1/decide | macro-F1 conjunta.py (T2.2c) | Δ | H2 (Δ ≥ −0,01) |
|---|---|---|---|---|---|---|
| massive | cascada | 2974 | 0.8144 | 0.8165 | -0.0021 | – |
| massive | forzado | 2974 | 0.8144 | 0.8165 | -0.0021 | sí |
| clinc150 | cascada | 5500 | 0.8862 | 0.8898 | -0.0036 | – |
| clinc150 | forzado | 5500 | 0.8868 | 0.8898 | -0.0030 | sí |

| tarea | modo | capa | fracción | p50 ms | p99 ms | p50 ms (cliente) | p99 ms (cliente) |
|---|---|---|---|---|---|---|---|
| massive | cascada | (total) | 1.000 | 0.1 | 8.9 | 0.7 | 9.6 |
| massive | cascada | L0 | 0.572 | 0.1 | 0.2 | 0.7 | 0.9 |
| massive | cascada | L3 | 0.428 | 4.9 | 9.8 | 5.5 | 10.5 |
| massive | forzado | (total) | 1.000 | 4.9 | 9.2 | 5.6 | 9.9 |
| massive | forzado | L2 | 1.000 | 4.9 | 9.2 | 5.6 | 9.9 |
| clinc150 | cascada | (total) | 1.000 | 0.2 | 10.3 | 1.1 | 11.3 |
| clinc150 | cascada | L0 | 0.537 | 0.1 | 0.2 | 0.9 | 1.2 |
| clinc150 | cascada | L3 | 0.463 | 6.7 | 11.0 | 7.6 | 11.9 |
| clinc150 | forzado | (total) | 1.000 | 6.4 | 10.7 | 7.4 | 11.7 |
| clinc150 | forzado | L2 | 1.000 | 6.4 | 10.7 | 7.4 | 11.7 |
