# G.9 Techo del profesor zero-shot: bge-m3-zeroshot-v2.0 (con y sin «-c») en JevBench y en las tareas no vistas

## Antecedentes
G.8 (`model/l2/resultados/general-20261029b/LEEME.md`) muestra que L2 sobre e5-small no generaliza a esquemas ni tareas
nuevas. JevBench se queda en 0,463 y las tareas no vistas (massive, hatecheck, inyecciones y el 10 % de tasksource
apartado, `fuera.json`) quedan muy por debajo de T2.1b. Antes de decidir si destilar de un profesor zero-shot, se mide su
techo con el mismo arnés.

**Licencias, comprobadas en el model card el 2026-10-29:**
- `MoritzLaurer/bge-m3-zeroshot-v2.0-c`: MIT, entrenado solo con datos comerciales (síntesis propia, MNLI y FEVER-NLI).
  **Destilable.**
- `MoritzLaurer/bge-m3-zeroshot-v2.0`: MIT, pero entrenado también con ANLI, WANLI, LingNLI y otros de licencia mixta.
  **Solo de referencia.**

## Hipótesis
Si el profesor «-c» saca ≥ 0,55 en JevBench sin soporte y mejora claramente las tareas no vistas frente a G.8 (≥ +10
puntos de macro-F1 en ≥ 2 de 4), destilar es el camino. Si no, el límite está en los datos y no en el modelo.

## Terminado cuando
- **`model/evaluacion/profesor.py`**: clasificador zero-shot por NLI.
  - Para cada opción, la hipótesis es una plantilla con la pregunta, la opción y su descripción. Usa la plantilla del model
    card y una variante en español; elige en dev y no en test.
  - La probabilidad de entailment se normaliza entre opciones en choice.
  - noul: entailment frente a contradicción de la opción «true».
  - score: niveles como opciones y la mediana o el argmax según el `tipo`; dilo.
  - Truncado a 512 tokens.
  - Escribe `{id, probs, ms}` y pasa por `chispa_eval` con el formato de siempre.
  - Tests con un modelo falso.
- **`model/evaluacion/aws/profesor.sh`**: user-data de una c6a.2xlarge spot, en CPU, con el patrón de siempre.
  - Marcador `__CHISPA_S3__`, `shutdown -h +150`, descargas por fichero y ≤ 16 KB.
  - Pasos:
    1. Baja los dos modelos de HF y JevBench (como `model/evaluacion/aws/jevbench.sh`).
    2. Prepara las tareas no vistas como `model/l2/aws/barrido.sh`, con la lista de `s3://chispa-pruebas-879381269751/general-20261029b/fuera.json`.
    3. Recorta a ≤ 300 filas por tarea, salvo JevBench, que va entero.
  - Mide los dos modelos.
  - `informe.md`: tabla de profesor frente a G.8 corrida 2 frente a T2.1b, con la licencia de cada fila, el tiempo por
    caso en CPU y el veredicto de la hipótesis.
  - **Coste:** ≤ 0,5 USD; dilo en el informe.
- **Prueba en seco:** `CHISPA_LOCAL=1` con fixtures y un modelo NLI diminuto o falso, y `bash -n`.
- Tests y `make test`/`make smoke` en verde **después** del último cambio.
- **Parada:** si algo falla 2 veces, márcalo y para.

## Zona
- `model/evaluacion/**`.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Python en `~/venv` y modelos en `~/hf`. Sin GPU y sin red salvo la API de Claude.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.

## Tope
- ≤ 60 min de reloj · ≤ 4 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 8 líneas:
- rama y sha;
- la prueba en seco;
- qué sustituyo para lanzar;
- el coste estimado.
