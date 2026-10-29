# G.8 L2 de propósito general: metaentrenamiento con muchas tareas, max_len 256 y soporte con shrinkage

## Antecedentes
- **L2 no generaliza.** G.1 y G.2 (`model/evaluacion/resultados/jevbench-20261029/` y
  `model/l2/resultados/no-vistas-20261029/`) lo muestran: JevBench sin soporte saca 0,407 y con soporte 0,230. Al excluir
  massive, hatecheck e inyecciones, el zero-shot cae al 51–78 % del de T2.1b.
- **El metaentrenamiento actual está sesgado.** En `model/meta`, el cupo se lo lleva casi entero tasksource-jev (521 k
  filas, ver `entrenamiento.json` de G.2), sin equilibrio por tarea. Además pawsx, sib200 y synzs quedan con cupo 0.
- **Más datos de licencia comercial.** El catálogo de la bóveda propone:
  - `tasksource/tasksource-jev-typed-decisions` filtrado a `license_use == "commercial"`: choice, score y noul, con cientos
    de tareas; ya se convierte en `model/meta/tasksource_jev.py`;
  - `tasksource/tasksource-instruct-v0` filtrado a sus 232 tareas comerciales: clasificación, opción múltiple y NLI;
  - los de `model/datos` con `uso_comercial: true`.
- **L2 trunca a 128 tokens** (`model/l2/modelo.py`, `MAX_TOK`). En JevBench, 108 de 231 casos pasan de eso.
- **Con 1 o 2 ejemplos por opción, el soporte estropea.** Los prototipos sustituyen a la torre de la descripción en lugar
  de completarla.

## Hipótesis
- H1: un L2 metaentrenado con muestreo equilibrado por **tarea** (p ∝ n_t^0,3, con tope por tarea) sobre cientos de tareas
  comerciales, con max_len 256 y sin las tareas que se dejan fuera, consigue:
  - JevBench sin soporte ≥ 0,55;
  - en las tareas no vistas, zero-shot ≥ 0,9 × T2.1b (el que sí las vio).
- H2: con shrinkage, el soporte nunca empeora el zero-shot en más de 1 punto y mejora con k ≥ 4. El prototipo de la clase
  c es `P_c = normaliza(λ_c · torre(desc_c) + (1 − λ_c) · media(soporte_c))`, con `λ_c = κ / (κ + n_c)` y κ elegido en dev
  (por ejemplo 4).
- Se refuta midiendo en la g5.

## Terminado cuando
- **Datos (`model/meta/`).**
  - Conversor o ampliación para tasksource-instruct-v0 (solo filas comerciales) al esquema de `model/esquema.md`.
  - Muestreo equilibrado por tarea con tope; el `datos.conjunto` o el nombre de tarea de tasksource identifica la tarea.
  - Una lista **fija y con semilla** de tareas que se dejan fuera para medir: ~10 % de las tareas de tasksource, más massive,
    hatecheck e inyecciones.
  - Tests con fixtures.
  - Aquí no hay red: lo que haya que bajar de HF lo baja el script de la g5. Deja los conversores probados con fixtures.
- **`model/l2/`.**
  - `MAX_TOK` configurable con `--max-tok`, 256 en esta corrida.
  - Shrinkage en `prototipos`/`simproto`, o en una función nueva, con `--kappa`. Con κ = 0 se comporta como hoy.
  - Tests: con n_c = 1 el prototipo queda cerca de la torre de la descripción; con n_c grande, cerca de la media.
- **`model/l2/formula-shrinkage.md`.** La fórmula exacta para el runtime en Go y en el móvil: entradas, normalización,
  orden de operaciones, κ por defecto y dónde va en el `.chispa`. Si basta con un campo nuevo en CALIB, `kappa`, dilo. Ese
  fichero lo usará otra sesión.
- **`model/l2/aws/general.sh`.** User-data de la g5.xlarge con el patrón de siempre: marcador `__CHISPA_S3__`, descargas
  por fichero, ≤ 16 KB y `shutdown -h +N` con N según tu estimación, **≤ 270 min**.
  - Pasos:
    1. baja y convierte los datos;
    2. entrena;
    3. evalúa JevBench (sin soporte y con soporte con shrinkage, reutilizando `model/evaluacion/jevbench.py`) y las tareas no
       vistas sin y con soporte (k = 8, 32) frente a T2.1b (`l2-20261028b/ckpt/mejor.pt`);
    4. escribe `comparacion.md`.
  - **Estima el coste** (g5 on-demand ≈ 1,0 USD/h) y escríbelo en el informe. **Tope: 5 USD.** Si no cabe, recorta pasos
    o datos y dilo.
- **Prueba en seco:** `CHISPA_LOCAL=1` con fixtures y pocos pasos, y `bash -n`.
- `python -m unittest discover -s model -t .`, `make test` y `make smoke` en verde **después** del último cambio.
- **Parada:** si algo falla 2 veces, márcalo y para.

## Zona
- `model/meta/**`, `model/l2/modelo.py`, `model/l2/datos.py`, `model/l2/entrenar.py`, `model/l2/evaluar.py`,
  `model/l2/formula-shrinkage.md`, `model/l2/aws/general.sh`, `model/l2/aws/empaquetar*.sh`, `model/l2/tests/test_g8*.py`,
  `model/evaluacion/jevbench.py` y `model/evaluacion/aws/**`.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Python en `~/venv` y modelos en `~/hf`. Sin GPU y sin red salvo la API de Claude.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.

## Tope
- ≤ 120 min de reloj · ≤ 7 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 12 líneas:
- rama y sha;
- cuántas tareas y filas;
- las tareas que se dejan fuera;
- la fórmula;
- el coste estimado en la g5;
- qué sustituyo para lanzar.
