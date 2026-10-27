# T1.7a Líneas base provisionales sobre los test reales

Encargo: `plan/fase-1/encargo.md`. Arnés: `model.evaluacion.chispa_eval`, que ya está integrado.
Esto es la parte de T1.7 que no necesita ni las etiquetas humanas (T1.5) ni la API de Jev. El
informe definitivo, con conjuntos congelados y adjudicados y con Jev, llega después.

## Hipótesis
- e5-small con kNN-32 queda cerca de L0 lineal en las tareas fáciles (intención) y lejos en las de
  muchas clases o con fuera de ámbito (CLINC con `oos`, herramientas). Esas son el hueco medible que
  la puerta G1 pide para L2. Se refuta si e5 kNN-32 ya da ≥ 0,9 de macro-F1 y ≥ 50 % de cobertura a
  precisión 0,95 en todas.

## Terminado cuando
- `model/lineas_base/correr.py` produce predicciones (`{id, probs, ms}`) y las pasa por `chispa eval`.
- Conjuntos de test:
  - las salidas de `python -m model.datos.convertir` (MASSIVE es, HateCheck-ES, CLINC150 con
    `escalate`, deepset) más `model/herramientas/test.jsonl`;
  - entrenamiento o soporte kNN: los train correspondientes (32 por clase), con semilla fija.
- Sistemas:
  1. L0 lineal: el Chispa lineal de la Arena (`arena/internal/detectors/`, mira `train.go` y
     `bank.go`), o, si no se puede invocar desde Python sin tocar `arena/`, una regresión logística
     sobre TF-IDF de caracteres como equivalente. Di cuál usaste.
  2. e5-small con kNN-8 y con kNN-32: prefijo `query: `, probabilidades por softmax de similitudes
     con una temperatura fijada en dev.
  3. THX-01, como en `model/eval0/thx01.py`, solo en intención, herramientas y CLINC, con ≤ 300
     filas por tarea si es lento.
- `model/lineas_base/informe.md`, una tabla por tarea y sistema con: macro-F1, ECE, cobertura a 0,95,
  AUROC del escalate donde aplique y p99. Cierra con una frase sobre el criterio (a) de G1: dónde está
  el hueco medible.
- Guarda las predicciones por fila en `model/lineas_base/pred/`, comprimidas si pasan de 5 MB.
- `python -m unittest discover -s model -t .`, `make test` y `make smoke` en verde.
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- Solo `model/lineas_base/`. **No tocar**: `arena/` (solo leer), `model/esquema.md`, el resto de `model/` (solo usar).
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Python en `~/venv`, modelos y datos en `~/hf`. No hay red salvo la API de Claude.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.

## Tope
- ≤ 120 min de reloj · ≤ 6 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 15 líneas: qué cambiaste, rama y sha, la tabla resumida, qué quedó sin
verificar y qué recomiendas.
