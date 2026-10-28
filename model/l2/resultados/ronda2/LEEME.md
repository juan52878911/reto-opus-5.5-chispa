# T2.1b, ronda 2 (g5.xlarge, 2026-10-28): mejora mucho, pero no cumple. Queda como limitación conocida

- Con soporte (32 por clase, los mismos ejemplos que kNN-32): +0,050 en HateCheck y +0,122 en inyecciones. MASSIVE empata
  (+0,001), CLINC queda a −0,019 y herramientas a −0,128. Son 2 tareas con Δ ≥ 0,05, y el criterio pide 3.
- Frente a la ronda 1, el soporte sube la macro-F1 entre 0,10 y 0,37 según la tarea. La ECE con soporte en MASSIVE es 0,040.
- Por qué no pasó la ronda 1:
  1. Datos: 84 % de metaentrenamiento, casi todo en inglés.
  2. Sin soporte: kNN-32 ve 32 ejemplos por clase y L2 no.
  3. Una sola época con e5 congelado.
  La cabeza y la pérdida no parecen la causa: con soporte, la misma cabeza ya iguala o supera a kNN.
- Por qué T2.1b tampoco pasa: con e5 congelado, la representación limita en las tareas de muchas clases
  parecidas (CLINC 150, herramientas 32 con pares leer/escribir).
- Es la segunda y última iteración de esta hipótesis, así que queda como limitación conocida. Lo siguiente es T2.2,
  otra hipótesis: descongelar las 4 últimas capas de e5 con renombrado, partiendo de este checkpoint.
- Coste: g5.xlarge on-demand, unas 2 h (≈ 2 USD).
