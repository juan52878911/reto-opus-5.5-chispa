# G.8, primera corrida (g5, 2026-10-29): entrenó 14 min, no 140

- **El entrenamiento fue corto.** `entrenar.py` cuenta las épocas sobre las filas **locales** (78.726) y no sobre el meta,
  así que hizo 1 época = 1.640 pasos en 836 s. El meta (521 k filas de tsjev más tsinst) apenas se tocó. Lo que sigue
  mide eso, no la hipótesis.
- **JevBench sin soporte:** 0,472 frente a 0,407 de T2.1b. Mejora, pero sigue por debajo de 0,55.
- **Tareas no vistas:** no mejoran. massive 0,243, hatecheck 0,463, inyecciones 0,326 y el 10 % de tasksource que quedó
  fuera 0,201. H1 se refuta.
- **Shrinkage (κ elegido en dev = 1).**
  - Con soporte, sube en las tareas con datos de train (massive +24 puntos con k = 8).
  - En JevBench baja 19 puntos, porque allí hay 1–2 ejemplos por opción.
  - En dev el mejor κ fue 0, es decir, solo ejemplos.
  - H2 se refuta en JevBench.
- **Segunda corrida** (`general-20261029b`): el mismo script con `--pasos 12000 --minutos 115`, para que el meta sí entre.
  Coste ≈ 2,7 USD; la suma de G.8 en GPU queda en ≈ 3,3 de los 5 aprobados.
- **Coste de esta corrida:** g5 de 36 min, ≈ 0,6 USD.
