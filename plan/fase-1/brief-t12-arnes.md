# T1.2 Arnés `chispa eval` con todas las métricas del plan de pruebas

Encargo: `plan/fase-1/encargo.md` (criterio de aceptación congelado; no lo cambies tú).
Esquema de filas y predicciones: `model/esquema.md` (congelado).

## Hipótesis
- Todas las métricas salen de un par (filas, predicciones) unido por `id`, con numpy y sin
  dependencias nuevas. Se refuta con tests de cifras calculadas a mano: si una no cuadra, está mal.

## Terminado cuando
- Paquete `model/evaluacion/` con `chispa_eval.py`:
  `python -m model.evaluacion.chispa_eval --datos <jsonl> --pred <jsonl> [--pred-b <jsonl>] [--salida x.json]`.
- Métricas, por tarea y global: exactitud, macro-F1, ECE con 15 cubos de igual ancho sobre la
  confianza top-1, Brier multiclase, cobertura a precisión 0,95 y 0,99 (umbral sobre la confianza
  top-1, la mayor cobertura cuya precisión ≥ objetivo), AUROC del escalate (positivo = etiqueta
  `escalate`, puntuación = `probs["escalate"]`, o 1 − confianza top-1 si no existe), latencia p50/p99
  si hay `ms`, y deriva entre `--pred` y `--pred-b` (tasa de cambio del top-1 y variación total media).
- Adaptador de la Arena: lee los resultados que escribe `arena/` (mira `arena/contracts/contracts.go`,
  `SwarmResult`/`DetectorResult`, y un resultado real de `make smoke`) y calcula el ASR por detector.
- Adaptador de JevBench detrás de una interfaz (`cargar_jevbench(ruta) -> filas`), probado con un
  fixture que inventes con la forma que documentes. La API de Jev no es alcanzable desde la VM: no la llames.
- Errores claros: id sin predicción, probs que no suman 1, opción desconocida.
- Tests con `unittest` en `model/evaluacion/tests/`: cada métrica con un caso de cifras calculadas a
  mano (incluye ECE y cobertura con ejemplos de 4-10 filas), más uno de punta a punta sobre
  `model/sondeo/intencion.jsonl` con predicciones uniformes (macro-F1 y ECE conocidos).
- Demostración: corre el arnés sobre `model/sondeo/*.jsonl` con las predicciones de e5 kNN-32 si
  están en `model/eval0/out/`; si no, con predicciones uniformes, y pon la tabla en `model/evaluacion/README.md`.
- `python -m unittest discover -s model -t .`, `make test` y `make smoke` en verde.
- Parada: si una métrica no cuadra tras 2 intentos, márcala «sin verificar» y sigue.

## Zona
- Solo `model/evaluacion/`. **No tocar**: `model/esquema.md`, `arena/` (solo leer), otras carpetas de `model/`.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Python en `~/venv` (numpy, scikit-learn; sklearn solo como contraste en los
  tests, no en el código del arnés). Sin red salvo la API de Claude.
- `data/` y `models/` no viajan con el repo; si `make smoke` los necesita, `make dataset` primero.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.

## Tope
- ≤ 150 min de reloj · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤15 líneas: qué cambiaste, rama y sha, qué verificaste ejecutando (con
números), qué quedó sin verificar y qué recomiendas a continuación.
