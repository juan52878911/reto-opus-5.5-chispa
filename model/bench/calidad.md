# Calidad de e5-small y mmBERT-small (codificador + kNN)

Macro-F1 (×100) y ECE de `model.evaluacion.chispa_eval` sobre las 4 tareas de `model/sondeo/` (train_*.jsonl como memoria, *.jsonl como test). e5-small: prefijo `query: `, media de tokens normalizada. mmBERT-small (pesos reales de `pytorch_model.bin`): media de la última capa normalizada, sin entrenar para embeddings. kNN-k = k ejemplos por clase, 10 vecinos, softmax(sim/0,05) (igual que `model/eval0/e5_knn.py`). Generado por `model/bench/calidad_codificadores.py`.

## Test completo (n por tarea: intencion 390, toxicidad 300, whatsapp_comercio 213, herramientas 212)

| codificador | kNN | intencion | toxicidad | whatsapp_comercio | herramientas | media macro-F1 | ECE medio |
|---|---|---|---|---|---|---|---|
| e5-small | 8 | 72.6 | 48.2 | 66.8 | 72.9 | **65.1** | 0.166 |
| e5-small | 32 | 87.2 | 55.5 | 77.1 | 80.5 | **75.0** | 0.106 |
| mmBERT-small | 8 | 62.5 | 55.3 | 45.1 | 58.0 | **55.2** | 0.146 |
| mmBERT-small | 32 | 78.4 | 54.8 | 53.7 | 69.1 | **64.0** | 0.139 |

mmBERT − e5 con kNN-32: -11.1 puntos de macro-F1 media (umbral de la hipótesis: +3).

## Subconjunto fijo de 120 (semilla 0, el de la fase 0) (n por tarea: intencion 120, toxicidad 120, whatsapp_comercio 120, herramientas 120)

| codificador | kNN | intencion | toxicidad | whatsapp_comercio | herramientas | media macro-F1 | ECE medio |
|---|---|---|---|---|---|---|---|
| e5-small | 8 | 74.2 | 47.9 | 67.6 | 72.9 | **65.6** | 0.172 |
| e5-small | 32 | 87.2 | 57.9 | 78.1 | 80.5 | **75.9** | 0.127 |
| mmBERT-small | 8 | 66.6 | 57.1 | 38.8 | 59.6 | **55.5** | 0.171 |
| mmBERT-small | 32 | 82.8 | 60.6 | 47.4 | 67.9 | **64.6** | 0.154 |

mmBERT − e5 con kNN-32: -11.3 puntos de macro-F1 media (umbral de la hipótesis: +3).
