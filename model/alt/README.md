# model/alt: alternativa (b) del hito 4

Rival de Chispa: `intfloat/multilingual-e5-small` (o `jhu-clsp/mmBERT-small`, que existe en HF: ModernBERT, 22 capas, hidden 384) descongelado,
con una cabeza lineal que puntúa cada opción por concatenación `<prefijo><pregunta> [SEP] <texto> [SEP] <descripción>` y softmax por pregunta.
Sin ranuras ni torre MLP. El rival gana si supera a Chispa por ≥ 5 puntos en JevBench y en el banco colombiano con p50 ≤ 60 ms en el i7.

| Fichero | Qué es |
|---|---|
| `modelo.py` | `CrossEncoder`: entrada, cabeza, pérdida (dura + mezcla con `blanda`), guardar/cargar sin red |
| `manifiesto.py`, `manifiesto-entrenamiento.json` | conjuntos de train con licencia y sha256; rechaza SA/NC/ND/sin verificar y la lista de exclusión; tsjev por tarea |
| `entrenar.py` | AdamW, checkpoint por época, mejor en dev; se niega si el manifiesto no valida; copia el manifiesto junto al checkpoint |
| `evaluar.py` | JevBench y batería con `chispa_eval` (exactitud, F1 macro, ECE, cobertura@0,95) y latencia p50/p99 en CPU con 4 hilos |
| `aws/entrenar.sh`, `aws/empaquetar.sh` | lanzador g5 spot **preparado, no ejecutado**, y su paquete de código |

    python -m unittest discover -s model/alt -t .           # pruebas en seco, sin red ni pesos
    python -m model.alt.manifiesto tsjev                     # tabla de tareas admitidas/excluidas de tsjev
    python -m model.alt.entrenar --datos DIR --salida CK --codificador e5-small --sellar
    python -m model.alt.evaluar --ckpt CK/mejor --jevbench RUTA --bateria DIR --salida RES

Excluido mientras Juan no decida: SIB-200, Clandestino, PQRS de datos.gov.co, las blandas de Qwen3.5, XNLI, clima y ALIA.
