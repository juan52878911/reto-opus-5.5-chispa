# T2.1b Segunda iteración de L2: mezcla de datos de las tareas evaluadas y vía few-shot con prototipos

Encargo: `plan/fase-2/encargo.md`, con el criterio de T2.1 congelado: ≥ +0,05 de macro-F1 sobre e5
kNN-32 en ≥ 3 tareas. Antecedente: `model/l2/resultados/ronda1/LEEME.md`, donde la ronda 1 queda por
debajo de kNN-32 en todas las tareas. Es la **segunda y última** iteración de esta hipótesis: si no
llega, se documenta como limitación conocida.

## Hipótesis (del orquestador)
- kNN-32 gana porque ve 32 ejemplos de cada clase de la propia tarea, y L2 no.
- Si L2 recibe esos mismos ejemplos como **soporte** y se entrena por episodios con tareas reales,
  debe igualar a kNN-32 en el peor caso y superarlo donde las descripciones de las opciones aportan.
- Se refuta midiendo con el mismo soporte (32 por clase, semilla 0, igual que T1.7a).

## Diseño
- **Prototipos:**
  - para cada clase c de la pregunta, los k ejemplos de soporte (k = 32 en la evaluación; en el
    entrenamiento, k aleatorio entre 4 y 32) pasan por el codificador y las ranuras;
  - el prototipo es la media normalizada de sus vectores de ranura, P_c ∈ R^{K×d}.
- **Puntuación:** `logit_c = sim_opción(c) + β · simproto(c)`.
  - `simproto(c) = mean_k max_k' (s_k · P_c,k')`, un MaxSim entre las ranuras del mensaje y las del prototipo;
  - β se aprende por tipo de pregunta, con β = 1 al inicio;
  - sin soporte, β·simproto = 0 y se cae al modo zero-shot de la ronda 1.
- **Episodios:**
  - en cada paso se elige una tarea con soporte (las tareas evaluadas y los conversores locales);
  - se toman k por clase de su train como soporte y un lote de consultas disjunto;
  - en el 25 % de los pasos se entrena sin soporte (zero-shot) con metaentrenamiento.
- **Mezcla:** ≥ 50 % de los pasos con tareas evaluadas o locales (`model/datos`, T1.4, sondeo);
  el metaentrenamiento queda limitado al resto. Varias épocas de los datos locales.
- **Evaluación:** con soporte = los mismos 32 por clase de T1.7a (semilla 0), y también sin soporte.
  Dos columnas en `delta.md`.

## Terminado cuando
- `model/l2/` tiene los prototipos (`modelo.py`), el muestreador por episodios (`datos.py`), las
  opciones `--episodios`, `--k-min/--k-max`, `--frac-meta 0.5` y `--frac-zeroshot 0.25`
  (`entrenar.py`), y `--soporte k` en `evaluar.py`.
- Las opciones de T2.2 (`--descongelar`, `--renombrar`) siguen funcionando: construye encima de lo
  que ya esté integrado y no lo reviertas.
- La caché de prototipos va por tarea y por hash del soporte; en la evaluación se calcula una sola vez.
- `model/l2/aws/arranque.sh` admite estas opciones mediante `L2_ARGS`, con descargas de S3 **por fichero**:
  el rol no puede listar el bucket.
- Prueba en seco en CPU, con `CHISPA_LOCAL=1`:
  - un episodio de intención y uno de herramientas, 100 pasos;
  - la macro-F1 en dev con soporte debe superar a la que da sin soporte.
- Tests con `unittest`:
  - forma y normalización del prototipo;
  - β = 0 reproduce la ronda 1;
  - episodios sin fuga entre soporte y consulta;
  - caché de prototipos.
- `python -m unittest discover -s model -t .`, `make test` y `make smoke` en verde.
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- Solo `model/l2/` (sin `calibrar.py`, `exportar.py` ni `empaquetar_go/`, que son de otro worker).
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.
- Ni datos ni pesos a git.

## Entorno
- `source ~/.profile`. Python en `~/venv` y modelos en `~/hf`. No hay red salvo la API de Claude.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.

## Tope
- ≤ 120 min de reloj · ≤ 6 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 15 líneas: qué cambiaste, rama y sha, la prueba en seco (con y sin
soporte), la estimación de horas de g5, qué quedó sin verificar y qué recomiendas.
