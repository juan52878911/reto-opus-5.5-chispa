# W17 Hito 4, alternativa (b): codificador abierto ajustado con cabeza cross-encoder por opción (solo código y pruebas en seco)

## Pregunta que responde el hito
¿Gana Chispa a un codificador abierto ajustado al estilo de Laya?
- **Rival:** e5-small o mmBERT-small, descongelado, con una cabeza que puntúa cada opción por concatenación (cross-encoder), sin ranuras ni torre MLP.
- **Criterio del hito:** el rival gana si supera a Chispa por ≥ +5 puntos en JevBench y en el banco colombiano, con p50 ≤ 60 ms en el i7.
- **Esta pieza solo prepara el código y lo prueba en seco.** El entrenamiento real (g5 spot) lo lanza el orquestador cuando Juan dé el OK al gasto.

## Qué construir, en `model/alt/` (carpeta nueva; no toques `model/l2/` ni `sdk/`)
1. **Modelo** (`modelo.py`):
   - codificador de HF: `intfloat/multilingual-e5-small` por defecto y `--codificador mmbert-small` (`jhu-clsp/mmBERT-small`; confirma el id real en HF y si no existe, dilo);
   - para cada opción, la entrada es `query: <pregunta> [SEP] <texto> [SEP] <descripción de la opción>`, con el prefijo que corresponda al codificador;
   - cabeza lineal sobre el [CLS] o el pooling medio, que da una puntuación; softmax sobre las opciones de la pregunta;
   - noul como choice de 2 opciones («no» o «sí» con sus descripciones), y score como choice ordenado por id;
   - pérdida: entropía cruzada con etiqueta dura y, si la fila trae `blanda`, mezcla con la blanda.
2. **Manifiesto de entrenamiento** (`manifiesto.py` + `manifiesto-entrenamiento.json`):
   - lista de conjuntos de train, cada uno con fuente, licencia, `uso_comercial`, filas y sha256 de su fichero;
   - **rechaza al construirse** cualquier conjunto con licencia SA (`-sa`, «share alike»), NC (`-nc`, «non-commercial»), ND, `sin verificar` o vacía, y cualquier fila de train con `uso_comercial: false`;
   - **lista de exclusión explícita mientras Juan no decida:** SIB-200, Clandestino, PQRS (datos.gov.co), las blandas de Qwen3.5 (`model/maestro`) y XNLI, clima y ALIA;
   - el manifiesto se escribe junto al checkpoint para que el peso sea publicable bajo Apache desde el principio;
   - tests: un SA, un NC y uno sin verificar se rechazan; uno CC-BY o Apache se acepta; SIB-200 se rechaza aunque venga marcado como comercial.
3. **tsjev por tarea:**
   - lee el `sources.yaml` de `tasksource/tasksource-jev-typed-decisions`; ya hay un lector en `model/meta/tasksource_jev.py` (`censo_yaml`, línea ~31). Si el fichero está en `~/hf` del nodo, úsalo; si no, intenta bajarlo de HF (solo ese fichero);
   - saca la tabla tarea → `license_use` / licencia y deja en el manifiesto **solo las tareas `commercial` cuya licencia no sea SA, NC ni ND**;
   - el informe dice cuántas tareas y filas quedan, y cuáles se excluyen y por qué. Si no puedes obtener el `sources.yaml`, para y avisa con un `blocker`, sin inventar licencias.
4. **Entrenamiento** (`entrenar.py`):
   - CPU y GPU, AdamW, `--epocas`, `--lote`, `--max-tok`, `--lr`, checkpoint por época y elección del mejor en dev por exactitud;
   - semilla fija;
   - lee el manifiesto y se niega a arrancar si el manifiesto no valida.
5. **Evaluación con el mismo arnés:**
   - JevBench: reutiliza `model/evaluacion/jevbench.py` (`cargar_jevbench`, pliegues y métricas de `model/evaluacion/metricas.py`) y escribe las mismas columnas que Chispa: exactitud, F1 macro, ECE y cobertura a precisión 0,95;
   - batería oficial: las filas de `model/esquema.md` (`split: test`) de massive, clinc150, hatecheck, spam, inyecciones y herramientas;
   - mide la latencia p50/p99 por decisión en CPU con 4 hilos, como referencia del i7.
6. **Lanzador AWS preparado pero NO ejecutado** (`aws/entrenar.sh`):
   - g5 spot, user-data con `__CHISPA_S3__`, `shutdown -h +N`, watcher de tope y `--instance-initiated-shutdown-behavior terminate`, como en `model/l2/aws/ajuste.sh`;
   - escribe en un comentario el coste estimado.
   - **No lances ninguna instancia.**

## Pruebas en seco (obligatorias)
- con un codificador diminuto aleatorio (config pequeña de BERT construida en el test, sin bajar pesos) y 20 filas de fixture: entrenar 2 pasos, guardar, cargar, evaluar;
- el manifiesto rechaza SA, NC y lo no verificado;
- el arnés de JevBench corre sobre un fixture pequeño;
- `python -m unittest discover -s model/alt -t .` pasa, y también `make test`.

## Límites
- tope de 90 min y 10 USD;
- sin AWS y sin cómputo de pago; solo escribes en `model/alt/` (y su `README.md`);
- la rama es `delega/<id>`, commits sin firmas ni trailers;
- si algo falla dos veces, `blocker`.

## Informe de cierre
- rama y commits;
- tabla de tsjev: tareas y filas totales frente a admitidas, con los motivos de exclusión;
- tests;
- cómo se lanza el entrenamiento real y qué cuesta;
- si el id de mmBERT-small existe;
- qué queda.
