# T1.4: orquestar herramientas (System One)

Catálogo de 32 entradas (31 herramientas, MCP y agentes + `escalate`), 368 casos de test y 1024 de train.

| Fichero | Qué es |
|---|---|
| `catalogo.json` | `{id, tipo, descripcion}`: 22 mcp, 7 herramienta (incl. `escalate`), 3 agente |
| `test.jsonl` | 368 filas a mano (10 por herramienta + 58 `escalate` = 15,8 %); 29 % `es-CO` |
| `train.jsonl` | 32 por clase: 4 plantillas × 8 rellenos revisados; `escalate` a mano |
| `datos.py`, `construir.py` | Fuente de los datos y generador determinista (`python model/herramientas/construir.py`) |
| `medir.py` | e5-small (`query: `) + kNN; escribe `pred_knn8.jsonl`, `pred_knn32.jsonl`, `medidas.json` |
| `tests/` | `unittest`: esquema, ≥ 15 % escalate, sin solape con `model/sondeo/` ni entre train y test |

Train y test no comparten texto ni `plantilla` (train: `<id>-pN`; test: `man-<id>-N`).
kNN-k = k ejemplos de train por clase; peso softmax(sim/0,05) sobre los 10 vecinos (igual que `model/eval0/e5_knn.py`).
Las métricas son de sklearn, provisionales hasta cambiar a `chispa eval`.

## Resultado (test, n = 368, CPU)

| | macro-F1 | exactitud | AUROC escalate (`p(escalate)`) | AUROC (1 − máx. herramienta) |
|---|---|---|---|---|
| kNN-8 | 0,490 | 0,454 | 0,766 | 0,724 |
| kNN-32 | 0,612 | 0,584 | 0,839 | 0,779 |

Hipótesis: «macro-F1 ≥ 0,8 pero AUROC < 0,8». **Refutada en las dos mitades con kNN-32**: la macro-F1 queda
muy por debajo de 0,8 (0,61) y el AUROC del escalate (0,84) supera 0,8 (con kNN-8 sí es < 0,8).
El fuera de ámbito sigue siendo lo peor: acierto de `escalate` 22 % en kNN-32 (9 caen en `editar_archivos`).
Confusiones principales: `obsidian_buscar`↔`obsidian_escribir`, `drive_leer`↔`drive_escribir`/`leer_documento`,
`slack_leer`↔`slack_enviar`. El español colombiano no cuesta más (0,59 frente a 0,58).

Salvedades: el train es de plantillas y el test escrito a mano, así que la distancia entre ambos es grande a propósito;
hay mucha pareja leer/escribir muy próxima por diseño. Una sola ejecución (determinista); sin intervalos de confianza.

## Reproducir
```
source ~/.profile
python model/herramientas/medir.py
python -m unittest discover -s model -t .   # necesita model/__init__.py (aún no existe en esta rama)
```
