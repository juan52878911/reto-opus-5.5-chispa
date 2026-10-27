# chispa eval (T1.2)

```
python -m model.evaluacion.chispa_eval --datos <jsonl> --pred <jsonl> [--pred-b <jsonl>] [--salida x.json]
python -m model.evaluacion.chispa_eval --jevbench <volcado.jsonl> --pred <jsonl>
python -m model.evaluacion.chispa_eval --arena arena/data/ledger.jsonl     # ASR por detector y por dimensión
```

Filas y predicciones: `model/esquema.md`. numpy puro; sklearn solo en los tests como contraste. Salida 2 y mensaje
en stderr ante id sin predicción, probs que no suman 1 (±1e-6), opción desconocida (`escalate` siempre vale) o id repetido.

## Convenciones de las métricas
- Top-1 = mayor prob; el empate cae en la primera clave de `probs`. Macro-F1 sobre las clases de etiqueta ∪ predicción.
- ECE: 15 cubos de igual ancho, cubo k = (k/15, (k+1)/15] sobre la confianza top-1.
- Brier: por fila, Σ(p−y)² sobre opciones ∪ claves de `probs`, media de filas.
- Cobertura a precisión P: umbral sobre confianza (se acepta conf ≥ umbral; los empates entran juntos); mayor cobertura con precisión ≥ P, 0 si ninguna.
- AUROC del escalate: positivo = etiqueta `escalate`, puntuación `probs["escalate"]` o 1 − confianza top-1; vacío (`-`) si no hay positivos o negativos.
- Latencia: p50/p99 lineales de `ms`. Deriva: tasa de cambio del top-1 y variación total media ½Σ|p−q| entre `--pred` y `--pred-b`.
- ASR (Arena): `fooled` / rondas contestadas (sin `error`), por detector; el del enjambre por dimensión.
- El sondeo congelado (T0.2) no trae `id`: el arnés le asigna `<fichero>:<split>:<n línea>` si ninguna fila lo trae.
- JevBench: `cargar_jevbench(ruta) -> filas`; forma del volcado documentada (e inventada) en `jevbench.py`; la API no se llama.

## Demostración: predicciones uniformes sobre `model/sondeo/`
En `model/eval0/out/` solo hay agregados de e5 kNN-32, no predicciones por fila, así que se usan uniformes
(`python -m model.evaluacion.demo_uniforme <dir>`). Sirven de suelo: ECE ≈ 0, Brier = 1 − 1/K, cobertura 0.

| tarea | n | exact | macroF1 | ECE | Brier | cob@.95 | cob@.99 | AUROC-esc |
|---|---|---|---|---|---|---|---|---|
| intencion | 390 | 0.0769 | 0.0110 | 0.0000 | 0.9231 | 0.0000 | 0.0000 | - |
| toxicidad | 300 | 0.5000 | 0.3333 | 0.0000 | 0.5000 | 0.0000 | 0.0000 | - |
| herramientas | 212 | 0.0566 | 0.0067 | 0.0059 | 0.9375 | 0.0000 | 0.0000 | 0.5000 |
| whatsapp_comercio | 213 | 0.2535 | 0.1011 | 0.0035 | 0.7500 | 0.0000 | 0.0000 | - |

Herramientas: AUROC 0,5 (puntuación constante). Pendiente: repetir con las predicciones por fila de e5 kNN cuando se guarden.
