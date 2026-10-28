# T2.2d Cabeza conjunta: calibración, ajuste fuera de pliegue en test y comparación justa con la cascada

## Antecedentes
- T2.2c (`model/l2/resultados/t22c-conjunta/LEEME.md`): la cabeza conjunta L0 + L2 (`model/l2/conjunta.py`, cabeza `lr`)
  pasa T2.2 en 5/5 y supera a la mejor capa en ≥ 1 punto en 3/5. Hay tres huecos:
  1. **hatecheck** pierde 5,9 puntos frente a L2 solo. La cabeza se entrena en train y hatecheck es de plantillas: lo
     aprendido en train no se traslada bien a test.
  2. **Sin calibrar.** Falta el criterio de T2.4 para la conjunta: ECE ≤ 0,05 y cobertura a precisión 0,95 ≥ 70 % por tarea.
  3. **Comparación desigual.** La cascada de T2.7 (`model/cascada/`) usó L0 con la línea base de 32 por clase, pero L0
     entrenado con todo el train es mucho mejor (massive 0,794 frente a 0,678). (b) y (c) hay que compararlas con el mismo L0.
- Las características ya calculadas por tarea (L0 fuera de pliegue en train, L2 con soporte, test) están en
  `s3://chispa-pruebas-879381269751/conjunta-20261028/caracteristicas/<tarea>.npz`, junto a `pred_l0/`, `pred_l2/` y `pred/`
  de `resultados.tgz`. Esta fase **no necesita GPU**.

## Hipótesis
- H1: entrenar la cabeza con validación cruzada a 2 pliegues sobre test (partición por hash del `id`, semilla 0, la misma
  de `model/cascada`), en lugar de en train, recupera hatecheck (≥ L2 − 1 punto) sin perder más de 1 punto en las demás.
  Se refuta si no.
- H2: con calibración de temperatura (o Platt en noul) ajustada fuera de pliegue, la conjunta cumple ECE ≤ 0,05 en las 5
  tareas, y cobertura a precisión 0,95 ≥ 70 % en ≥ 3.
- H3: con L0 completo, la cascada L0 → L2 (τ elegido fuera de pliegue) queda por debajo de la conjunta en ≥ 3 tareas.

## Terminado cuando
- `model/l2/conjunta.py`:
  - `--modo-cabeza train|cvtest`: `cvtest` entrena y evalúa por pliegues de test, con la misma partición que
    `model/cascada/cascada.py`, importada y no copiada. Por defecto `train`, que no cambia nada.
  - `--calibrar`: T por tarea (choice) o Platt (noul) fuera de pliegue, más ECE, cobertura a precisión 0,95 y AUROC de
    `escalate` en clinc150 (`oos`), con las mismas funciones de `model/l2/calibrar.py`, importadas.
  - `--desde-cache DIR`: carga las `.npz` y las `pred_*` sin codificador ni GPU.
- `model/cascada/`: opción para usar como L0 las predicciones de `pred_l0/` (L0 completo) y como capa la conjunta
  (`pred/`). El informe añade las cascadas L0completo → L2b-sop, L0completo → conjunta y conjunta sola.
- `model/l2/aws/conjunta_cpu.sh`: user-data para una m6a.xlarge spot con el patrón de siempre:
  - marcador `__CHISPA_S3__` y `shutdown -h +45`;
  - trap que sube `log.txt` y `resultados.tgz`;
  - descargas por fichero;
  - baja las `.npz` y `resultados.tgz` de `conjunta-20261028`;
  - corre las dos modalidades con `--calibrar` y la cascada nueva.
  - Si hace falta otro empaquetado, va en `aws/empaquetar_conjunta.sh`.
- Prueba en seco aquí, con fixtures (sin S3):
  - tests nuevos en `model/l2/tests/test_conjunta*.py`: la partición `cvtest` es la de la cascada, ninguna fila se
    predice con una cabeza que la vio, y la calibración no empeora el log-loss en los fixtures;
  - `CHISPA_LOCAL=1 bash model/l2/aws/conjunta_cpu.sh`.
- `python -m unittest discover -s model -t .`, `make test` y `make smoke` en verde. Parada: si algo falla 2 veces, márcalo y para.

## Zona
- `model/l2/conjunta.py`, `model/l2/conjunta.md`, `model/l2/tests/test_conjunta*.py`, `model/l2/aws/conjunta*.sh`,
  `model/l2/aws/empaquetar_conjunta.sh` y `model/cascada/**`.
- No toques el resto de `model/l2/`.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Python en `~/venv`. Sin GPU, sin S3 y sin red salvo la API de Claude.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.
- No vuelques datos en el contexto. Las PQRS no entran.

## Tope
- ≤ 90 min de reloj · ≤ 5 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 12 líneas:
- rama y sha;
- la prueba en seco;
- qué sustituyo para lanzar `conjunta_cpu.sh`;
- qué quedó sin verificar.
