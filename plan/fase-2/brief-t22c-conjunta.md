# T2.2c Cabeza conjunta L0 + L2: preparar el arnés offline (opción (b))

Decisión de Juan del 2026-10-28: «C y después b». En tres rondas, L0 (TF-IDF de caracteres con regresión logística) gana a
todo lo basado en e5-small en las tareas de muchas clases (`model/l2/resultados/ronda3-t22/LEEME.md`). (b) da a L2 las
características de L0 en una cabeza conjunta. Este encargo prepara el arnés y lo prueba en seco. El entrenamiento en GPU lo
lanza el orquestador después, con tu script.

## Hipótesis
- H1, fusión tardía por tarea: una cabeza pequeña sobre [log-probs de L0, similitudes de L2 con soporte, sus diferencias]
  saca ≥ max(L0, L2) + 1 punto de macro-F1 en ≥ 3 de las 5 tareas de T2.2, y cumple el listón de T2.2
  (≥ 0,95 × la mejor referencia) en ≥ 4. Las cabezas candidatas son una regresión logística multinomial con las
  características por clase compartidas, y un apilado con una puerta σ(w·[conf_L0, conf_L2, margen…]).
- La caída al renombrar las opciones baja porque L0 no depende del nombre de la opción. Hay que medirla.
- Se refuta si la cabeza conjunta no supera a la mejor capa sola en ≥ 3 tareas.
- H2, fusión temprana en la red (las características de L0 entran en las ranuras o en la torre): solo se diseña, en
  `model/l2/conjunta.md`, por si H1 falla. No se implementa.

## Terminado cuando
- `model/l2/conjunta.py`, que importa `modelo.py`, `datos.py` y `evaluar.py` sin cambiarlos:
  - **Características sin fuga**:
    - L0 fuera de pliegue en train: k = 5 pliegues, con el mismo código que `model/lineas_base/correr.py`;
    - L2 en train con soporte **dejando fuera la propia fila**: el prototipo de su clase se calcula sin ella
      (`modelo.prototipos`);
    - en test, L0 entrenado en todo train y L2 con el soporte de `datos.soporte_t17a`, como en la evaluación de T2.1b.
  - Entrena la cabeza por tarea sobre train y elige sus hiperparámetros con validación cruzada en train, nunca en test.
  - Escribe predicciones `{id, probs, ms}` y pasa por `chispa_eval` como `evaluar.py`. `delta.md` lleva las columnas
    L0, L2 y conjunta, y el listón.
  - `--renombrar`: la misma evaluación con las opciones renombradas a A/B/C, y `caida.md`.
- Tests en `model/l2/tests/test_conjunta.py`:
  - sin fuga: una fila de train nunca está en su propio soporte ni en el pliegue que la predice;
  - determinismo con semilla;
  - en fixtures donde L0 acierta unas clases y L2 otras, la cabeza supera a las dos.
- `model/l2/aws/conjunta.sh`: user-data para la g5.xlarge con el patrón de `model/l2/aws/arranque.sh`:
  - marcador `__CHISPA_S3__`, `shutdown -h +120` y un trap que sube `log.txt` y `resultados.tgz`;
  - descargas por fichero;
  - checkpoint en `__CKPT__`, por defecto `s3://chispa-pruebas-879381269751/l2-20261028b/ckpt/mejor.pt`, el de T2.1b;
  - pasos: calcula las características de train y test y las guarda en S3 para reusarlas, entrena las cabezas, evalúa,
    hace la evaluación renombrada y sube los resultados.
  - El empaquetado sale de `model/l2/aws/empaquetar.sh`. Si no incluye tu fichero, añádelo **solo** si es una línea;
    si no, haz un `aws/empaquetar_conjunta.sh`.
- `model/l2/conjunta.md`: el diseño de H1, el boceto de H2 y cómo se lanza.
- Prueba en seco aquí:
  - `python -m unittest discover -s model -t .`;
  - `CHISPA_LOCAL=1 bash model/l2/aws/conjunta.sh` con fixtures y el codificador de `~/hf`, sobre una tarea pequeña
    recortada a ≤ 500 filas. Pega la cola del log;
  - `bash -n` de los scripts;
  - `make test` y `make smoke`.
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- `model/l2/conjunta.py`, `model/l2/conjunta.md`, `model/l2/tests/test_conjunta*.py`, `model/l2/aws/conjunta.sh` y
  `model/l2/aws/empaquetar*.sh`.
- No toques `modelo.py`, `datos.py`, `entrenar.py`, `evaluar.py`, `calibrar.py` ni `exportar.py`.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Python en `~/venv` y modelos en `~/hf`. No hay GPU. Sin red salvo la API de Claude.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.
- No vuelques datos en el contexto. Las PQRS no entran.

## Tope
- ≤ 120 min de reloj · ≤ 6 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 15 líneas:
- rama y sha;
- la cola de la prueba en seco;
- qué sustituyo para lanzar `conjunta.sh`;
- el coste estimado en g5;
- qué quedó sin verificar.
