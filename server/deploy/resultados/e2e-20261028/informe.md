# T4.5: /v1/decide de punta a punta

| tarea | modo | n | macro-F1 /v1/decide | macro-F1 conjunta.py (T2.2c) | Δ | H2 (Δ ≥ −0,01) |
|---|---|---|---|---|---|---|
| massive | cascada | 2974 | 0.7630 | 0.8165 | -0.0535 | – |
| massive | forzado | 2974 | 0.7620 | 0.8165 | -0.0545 | NO |
| clinc150 | cascada | – | sin resultados | | | |
| clinc150 | forzado | – | sin resultados | | | |

| tarea | modo | capa | fracción | p50 ms | p99 ms | p50 ms (cliente) | p99 ms (cliente) |
|---|---|---|---|---|---|---|---|
| massive | cascada | (total) | 1.000 | 0.0 | 8.1 | 0.7 | 8.7 |
| massive | cascada | L0 | 0.612 | 0.0 | 0.1 | 0.6 | 0.8 |
| massive | cascada | L3 | 0.388 | 4.7 | 8.8 | 5.3 | 9.4 |
| massive | forzado | (total) | 1.000 | 4.5 | 8.6 | 5.2 | 9.3 |
| massive | forzado | L2 | 1.000 | 4.5 | 8.6 | 5.2 | 9.3 |
