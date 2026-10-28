### clinc150

| corrida | macro-F1 | Δ vs 1 (puntos) |
|---|---|---|
| 1 todo servidor | 0.8462 |  |
| 2 todo referencia | 0.8894 | +4.32 |
| 3A servidor con A de referencia (codificador) | 0.8505 | +0.43 |
| 3B servidor con B de referencia (torres (ESQUEMAS)) | 0.8461 | -0.01 |
| 3C servidor con C de referencia (prototipos (CONJ)) | 0.8463 | +0.02 |
| 3D servidor con D de referencia (simproto int8) | 0.8460 | -0.02 |
| 3E servidor con E de referencia (L0 (Chispa/sklearn)) | 0.8869 | +4.08 |
| 3F servidor con F de referencia (atajo de la cascada) | 0.8462 | +0.00 |
| 4A referencia con A de servidor (codificador) | 0.8870 | +4.08 |
| 4B referencia con B de servidor (torres (ESQUEMAS)) | 0.8895 | +4.33 |
| 4C referencia con C de servidor (prototipos (CONJ)) | 0.8889 | +4.27 |
| 4D referencia con D de servidor (simproto int8) | 0.8894 | +4.32 |
| 4E referencia con E de servidor (L0 (Chispa/sklearn)) | 0.8505 | +0.43 |
| 4F referencia con F de servidor (atajo de la cascada) | 0.8894 | +4.32 |

- Reproducción: corrida 1 = 0.8462 (objetivo 0.846 ±0.005) ok; corrida 2 = 0.8894 (objetivo 0.890 ±0.005) ok.
- Hueco 2 − 1 = +4.32 puntos; suma de las sustituciones (solo las positivas) = +4.53.
- Culpable(s) (Δ ≥ 3 puntos): E.
- F, pred.jsonl del servidor: macro-F1 0.8459; acuerdo top-1 con la corrida 1 0.9955, |Δp| máx 0.192, capas del servidor {'L2': 5500}.
- **E+** (cabeza reentrenada con L0 de Chispa): macro-F1 0.8580 (+1.19 puntos vs 1).
- conjunta.py pura (ids originales del train, cabeza reentrenada): macro-F1 0.8894.
