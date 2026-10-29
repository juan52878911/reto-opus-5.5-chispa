# G.2 Generalización a tareas no vistas: L2 entrenado sin tareas enteras

## Antecedentes
Juan quiere un clasificador multipropósito, como Laya o Jev. Hoy L2 (T2.1b, `model/l2/`) se entrena con dos fuentes:
- el metaentrenamiento: `meta-20261027` con pawsx, sib200, synzs y tasksource-jev;
- el train de los conversores: massive, clinc150, hatecheck, inyecciones y herramientas.

Después se evalúa en el test de esas mismas tareas. Eso mide aprender una tarea, no generalizar a una nueva.

## Hipótesis
- H1: con L2 reentrenado **sin** un grupo de tareas enteras (filas de train y esquemas), sobre esas tareas:
  - L2 zero-shot queda ≥ 0,9 × L2 entrenado con ellas;
  - L2 con soporte k = 32 queda a ≤ 3 puntos.
- Se refuta si cae más.

## Terminado cuando
- `model/l2/entrenar.py`: `--excluir-tareas a,b,…` quita del entrenamiento (meta y local) todas las filas de esas tareas.
  Usa la agrupación por conjunto de `datos.conjunto`, no por el campo `tarea`. Su test con fixtures comprueba que no queda
  ninguna fila excluida.
- `model/l2/aws/no_vistas.sh`: user-data de la g5.xlarge con el patrón de `model/l2/aws/arranque.sh`:
  - marcador `__CHISPA_S3__`, `shutdown -h +150`, descargas por fichero y ≤ 16 KB.
  - Pasos:
    1. entrena L2 desde cero con los mismos hiperparámetros de T2.1b (`--episodios …`), con
       `--excluir-tareas massive,hatecheck,inyecciones` (un caso de cada tipo: muchas clases, noul y seguridad);
    2. evalúa esas 3 tareas con y sin soporte (k = 8 y k = 32);
    3. compara con las cifras de T2.1b en `model/l2/resultados/` sobre las mismas tareas;
    4. compara también la cascada de `chispa train` sin `--conjunta` con k = 8 y k = 32, si cabe en el tope de tiempo.
- Prueba en seco aquí: tests y `CHISPA_LOCAL=1 bash model/l2/aws/no_vistas.sh` con fixtures.
- `python -m unittest discover -s model -t .`, `make test` y `make smoke` en verde.
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- `model/l2/entrenar.py`, `model/l2/datos.py` (solo si hace falta para el filtro), `model/l2/tests/test_excluir*.py` y
  `model/l2/aws/no_vistas.sh`.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Python en `~/venv`. Sin GPU y sin red salvo la API de Claude.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.

## Tope
- ≤ 90 min de reloj · ≤ 5 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 10 líneas:
- rama y sha;
- la prueba en seco;
- qué sustituyo para lanzar;
- el coste estimado en g5.
