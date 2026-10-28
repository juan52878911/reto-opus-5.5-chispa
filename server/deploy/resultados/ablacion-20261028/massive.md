### massive

| corrida | macro-F1 | Δ vs 1 (puntos) |
|---|---|---|
| 1 todo servidor | 0.7657 |  |
| 2 todo referencia | 0.8165 | +5.09 |
| 3A servidor con A de referencia (codificador) | 0.7655 | -0.02 |
| 3B servidor con B de referencia (torres (ESQUEMAS)) | 0.7662 | +0.05 |
| 3C servidor con C de referencia (prototipos (CONJ)) | 0.7663 | +0.06 |
| 3D servidor con D de referencia (simproto int8) | 0.7657 | +0.00 |
| 3E servidor con E de referencia (L0 (Chispa/sklearn)) | 0.8127 | +4.70 |
| 3F servidor con F de referencia (atajo de la cascada) | 0.7657 | +0.00 |
| 4A referencia con A de servidor (codificador) | 0.8127 | +4.70 |
| 4B referencia con B de servidor (torres (ESQUEMAS)) | 0.8165 | +5.08 |
| 4C referencia con C de servidor (prototipos (CONJ)) | 0.8167 | +5.10 |
| 4D referencia con D de servidor (simproto int8) | 0.8165 | +5.09 |
| 4E referencia con E de servidor (L0 (Chispa/sklearn)) | 0.7663 | +0.06 |
| 4F referencia con F de servidor (atajo de la cascada) | 0.8165 | +5.09 |

- Reproducción: corrida 1 = 0.7657 (objetivo 0.771 ±0.005) NO; corrida 2 = 0.8165 (objetivo 0.817 ±0.005) ok.
- Hueco 2 − 1 = +5.09 puntos; suma de las sustituciones (solo las positivas) = +4.81.
- **EL ARNÉS ESTÁ MAL (o falta una pieza): una de las corridas 1/2 no reproduce su objetivo. No hay conclusiones.**
- F, pred.jsonl del servidor: macro-F1 0.7705; acuerdo top-1 con la corrida 1 0.9983, |Δp| máx 0.115, capas del servidor {'L2': 2974}.
- **E+** (cabeza reentrenada con L0 de Chispa): macro-F1 0.7742 (+0.85 puntos vs 1).
- conjunta.py pura (ids originales del train, cabeza reentrenada): macro-F1 0.8165.
