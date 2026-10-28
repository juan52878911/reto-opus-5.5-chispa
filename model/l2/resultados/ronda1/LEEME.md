# T2.1, ronda 1 (g5.xlarge, 2026-10-28): no cumple

- Ninguna tarea saca +0,05 de macro-F1 sobre e5 kNN-32: Δ entre −0,29 y −0,01. El detalle está en `delta.md`.
- Causas (análisis del orquestador):
  1. Mezcla desequilibrada: 506 k de las 600 k filas son de tasksource-jev (sobre todo en inglés y generalista), y solo
     94 k (16 %) son de las tareas que se evalúan. Una sola época, con e5 congelado.
  2. kNN-32 usa 32 ejemplos por clase al predecir; L2 predice sin soporte, solo con la descripción de la opción.
- Coste: g5.xlarge on-demand unos 95 min (≈ 1,6 USD). Checkpoints en `s3://chispa-pruebas-879381269751/l2-20261028a/ckpt/`.
- Segunda iteración (T2.1b): ≥ 50 % de datos de las tareas evaluadas, varias épocas de esos datos y una vía few-shot
  con un prototipo por clase a partir de k ejemplos de soporte, entrenada por episodios.
