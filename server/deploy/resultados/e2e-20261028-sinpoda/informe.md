# T4.5: /v1/decide de punta a punta

| tarea | modo | n | macro-F1 /v1/decide | macro-F1 conjunta.py (T2.2c) | Δ | H2 (Δ ≥ −0,01) |
|---|---|---|---|---|---|---|
| massive | cascada | 2974 | 0.7636 | 0.8165 | -0.0530 | – |
| massive | forzado | 2974 | 0.7705 | 0.8165 | -0.0461 | NO |
| clinc150 | cascada | 5500 | 0.8430 | 0.8898 | -0.0467 | – |
| clinc150 | forzado | 5500 | 0.8488 | 0.8898 | -0.0410 | NO |

| tarea | modo | capa | fracción | p50 ms | p99 ms | p50 ms (cliente) | p99 ms (cliente) |
|---|---|---|---|---|---|---|---|
| massive | cascada | (total) | 1.000 | 0.0 | 8.5 | 0.7 | 9.2 |
| massive | cascada | L0 | 0.612 | 0.0 | 0.1 | 0.6 | 0.8 |
| massive | cascada | L3 | 0.388 | 5.2 | 10.0 | 5.8 | 10.7 |
| massive | forzado | (total) | 1.000 | 5.4 | 9.6 | 6.1 | 10.2 |
| massive | forzado | L2 | 1.000 | 5.4 | 9.6 | 6.1 | 10.2 |
| clinc150 | cascada | (total) | 1.000 | 0.1 | 9.9 | 1.0 | 10.8 |
| clinc150 | cascada | L0 | 0.672 | 0.1 | 0.1 | 0.9 | 1.1 |
| clinc150 | cascada | L3 | 0.328 | 6.5 | 10.6 | 7.4 | 11.6 |
| clinc150 | forzado | (total) | 1.000 | 6.7 | 10.9 | 7.7 | 11.9 |
| clinc150 | forzado | L2 | 1.000 | 6.7 | 10.9 | 7.7 | 11.9 |
