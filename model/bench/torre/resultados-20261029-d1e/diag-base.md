# Paridad servidor ↔ Python (JevBench, 78 casos)

- Consulta del `.chispa`: max_len 256 (declarado en el ONNX; el checkpoint usa 256), 384 filas de embeddings (completo = 250037), int8: False.
- TORR: max_len 256.

CALIB (servidor frente a checkpoint):

| cabeza | parámetros del `.chispa` | parámetros del checkpoint |
|---|---|---|
| choice | — | T=0.02211, a=0, b=0, theta=0.5 |
| noul | — | T=1, a=4.25, b=-3.804, theta=0.5 |
| score4 | — | T=1, a=3.945, b=2.046, theta=0.5 |
| score4#1 | — | T=1, a=0.7147, b=0, theta=0.5 |
| score4#2 | — | T=1, a=0.709, b=0, theta=0.5 |
| score5 | — | T=1, a=3.95, b=2.032, theta=0.5 |
| score5#1 | — | T=1, a=0.7182, b=0, theta=0.5 |
| score5#2 | — | T=1, a=0.7253, b=0, theta=0.5 |
| score5#3 | — | T=1, a=0.7216, b=0, theta=0.5 |

| tipo | casos | discrepan | truncados Python / servidor | textos de torre distintos | ‖Δp‖ medio | replay fiel (máx |Δp|) | causas |
|---|---|---|---|---|---|---|---|
| choice | 30 | 0 | 0 / 0 | 0 | 0.002 | 0.339 | — |
| noul | 30 | 13 | 16 / 16 | 0 | 0.325 | 0.000 | calib: 13 |
| score | 18 | 0 | 5 / 5 | 0 | — | — | — |
| todos | 78 | 13 | 21 / 21 | 0 | 0.163 | 0.339 | calib: 13 |

«replay fiel» mide si el recálculo en Python reproduce lo que devolvió el servidor (debe ser ≈ 0: si no, la atribución no vale).
