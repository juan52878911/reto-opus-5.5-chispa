# T4.5: /v1/decide de punta a punta

| tarea | modo | n | macro-F1 /v1/decide | macro-F1 conjunta.py (T2.2c) | Δ | H2 (Δ ≥ −0,01) |
|---|---|---|---|---|---|---|
| massive | cascada | 2974 | 0.7645 | 0.8165 | -0.0521 | – |
| massive | forzado | 2974 | 0.7705 | 0.8165 | -0.0460 | NO |
| clinc150 | cascada | 5500 | 0.8404 | 0.8898 | -0.0494 | – |
| clinc150 | forzado | 5500 | 0.8459 | 0.8898 | -0.0439 | NO |

| tarea | modo | capa | fracción | p50 ms | p99 ms | p50 ms (cliente) | p99 ms (cliente) |
|---|---|---|---|---|---|---|---|
| massive | cascada | (total) | 1.000 | 0.0 | 8.7 | 0.7 | 9.5 |
| massive | cascada | L0 | 0.612 | 0.0 | 0.1 | 0.6 | 0.9 |
| massive | cascada | L3 | 0.388 | 5.4 | 9.4 | 6.1 | 10.2 |
| massive | forzado | (total) | 1.000 | 5.0 | 9.4 | 5.7 | 10.2 |
| massive | forzado | L2 | 1.000 | 5.0 | 9.4 | 5.7 | 10.2 |
| clinc150 | cascada | (total) | 1.000 | 0.1 | 9.3 | 1.0 | 10.3 |
| clinc150 | cascada | L0 | 0.672 | 0.1 | 0.1 | 0.9 | 1.2 |
| clinc150 | cascada | L3 | 0.328 | 6.5 | 10.1 | 7.6 | 11.2 |
| clinc150 | forzado | (total) | 1.000 | 6.7 | 11.1 | 7.9 | 12.3 |
| clinc150 | forzado | L2 | 1.000 | 6.7 | 11.1 | 7.9 | 12.3 |
