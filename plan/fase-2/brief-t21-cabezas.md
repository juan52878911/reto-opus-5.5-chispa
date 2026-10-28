# T2.1 Ranuras de lectura, torres de opción y cabezas noul y score (CORAL) sobre e5 congelado

Encargo: `plan/fase-2/encargo.md` (criterio de T2.1 congelado). Esquema: `model/esquema.md`.
Arnés: `model.evaluacion.chispa_eval`. Tú escribes y pruebas el código en CPU. El entrenamiento real
lo lanza el orquestador en una g5.xlarge con tu script de arranque.

## Diseño (del orquestador; no lo cambies sin avisar con `question`)
- **Codificador:** `intfloat/multilingual-e5-small`, **congelado** (`no_grad`). Entrada: `query: ` +
  `texto`, con máximo 128 tokens. Salida: los estados de token de la última capa, H ∈ R^{T×384}, con su máscara.
- **Ranuras de lectura:** K = 16 consultas aprendidas Q ∈ R^{K×384}. Una capa de atención cruzada
  (4 cabezas, más residual y LayerNorm) con Q como consultas y H como claves y valores. Da
  S ∈ R^{K×d}, proyectadas a d = 256 y normalizadas. Un solo pase por mensaje, sirva para todas las preguntas.
- **Torre de opción:** e5 congelado sobre `passage: {pregunta} · {opción} · {descripción}`, con media
  normalizada, más un MLP de 2 capas → d = 256, normalizado. Es **cacheable**: el mismo texto da el
  mismo vector. Haz la caché por hash del texto dentro del entrenamiento.
- **Puntuación de una opción h:** `sim(h) = max_k softplus(h · s_k)` (MaxSim).
- **Cabezas:**
  - `choice`: softmax(sim / T_choice);
  - `noul`: P(true) = σ(a · sim(h_q) + b), donde h_q es la torre sobre `pregunta · true · descripción`;
    a y b se aprenden;
  - `score` (K niveles): CORAL. P(y > j) = σ(w · sim(h_q) − θ_j), con θ_j ordenados (θ_j = θ_1 +
    Σ softplus(δ)) para la monotonía. Devuelve la distribución y el valor esperado.
  - T_choice, a, b, w y θ, uno por tipo de pregunta.
- **Pérdida:**
  - CE sobre la etiqueta dura;
  - más λ_kl · KL(blanda ‖ p) donde haya `blanda` (λ_kl = 1);
  - más λ_nce · InfoNCE con negativos dentro del lote en `choice`, con las opciones de otras filas
    del lote como negativos (λ_nce = 0,5);
  - más λ_b · Brier (λ_b = 0,5).
- **Muestreo:** por tarea con temperatura (p ∝ n^0,5) para que las tareas grandes no dominen. Lotes
  de 64 mensajes.
- **Optimizador:** AdamW, lr 3e-4 en ranuras y cabezas y 1e-4 en el MLP de la torre, con warmup del
  5 % y coseno. Entre 1 y 3 épocas de ~600 k filas según el tiempo; selección por macro-F1 en dev.

## Terminado cuando
- `model/l2/` contiene:
  - `modelo.py`: las ranuras, las torres, las cabezas y la caché de opciones;
  - `datos.py`: carga los JSONL del esquema (incluidos `.jsonl.gz`), submuestrea y muestrea por tarea;
  - `entrenar.py`: entrenamiento con checkpoint cada 10 min a un directorio. En AWS se sube a S3
    con `--s3`, y debe poder reanudar;
  - `evaluar.py`: predice al formato `{id, probs, ms}` y llama a `chispa_eval` en los test de T1.7a,
    el listón y T1.4.
- `model/l2/aws/arranque.sh` y `empaquetar.sh` para la g5.xlarge (AMI Deep Learning PyTorch 2.10
  AL2023). Mismo patrón que `model/maestro/aws/`:
  - marcadores `CHISPA_S3` y `HORAS`, y `shutdown -h +` HORAS×60 + 20;
  - un trap que sube los checkpoints, `resultados.json` y `log.txt`.
  En la instancia:
  1. baja de S3 el metaentrenamiento y las blandas del maestro;
  2. baja los datasets y corre los conversores, como hace `model/maestro/aws/arranque.sh`;
  3. entrena;
  4. evalúa en test frente a las cifras de `model/lineas_base/informe.md`;
  5. escribe una tabla con el Δ por tarea.
- Prueba en seco aquí en CPU:
  - `CHISPA_LOCAL=1` y un subconjunto de 2 k filas de los datos que haya en `~/hf` o en los fixtures;
  - 50 pasos con e5 real de `~/hf`;
  - comprueba que la pérdida baja, que las probabilidades suman 1, que CORAL es monótono y que la
    caché de opciones acierta.
- Tests con `unittest` en `model/l2/tests/`:
  - formas de los tensores;
  - MaxSim;
  - monotonía de CORAL;
  - la caché;
  - la KL con `blanda` parcial;
  - reanudar desde un checkpoint.
- `python -m unittest discover -s model -t .`, `make test` y `make smoke` en verde.
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- Solo `model/l2/`. **No tocar**: `model/esquema.md` ni el resto de `model/`, que solo se usa.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.
- Ni datos ni pesos a git.

## Entorno
- `source ~/.profile`. Python en `~/venv` (torch CPU) y modelos en `~/hf`. No hay red salvo la API de Claude.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.

## Tope
- ≤ 150 min de reloj · ≤ 8 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 15 líneas que incluya:
- qué cambiaste, rama y sha;
- la cola del log de la prueba en seco, con la pérdida al principio y al final;
- tu estimación de horas de g5 para 1 época de 600 k filas;
- qué quedó sin verificar y qué recomiendas.
