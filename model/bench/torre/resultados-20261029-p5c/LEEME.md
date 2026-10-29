# P5 tras R9 (c6a.2xlarge, `248e763`, 2026-10-29): las torres al vuelo funcionan, pero el servidor no reproduce a Python

- Se calcularon 368 torres, 0 errores. L2 contesta 15 de 231 con τ de CALIB y 185 de 231 con `tau_l2_esquema_nuevo` = 0,276.
- **Exactitud servidor frente a Python k = 0:** 0,437 frente a 0,485. Igual que antes de R9: con torres al vuelo no se usa
  ESQUEMAS, así que R9 no influye aquí.
  - **Por tipo:** choice 0,439 / 0,468; noul 0,473 / 0,554; score 0,278 / 0,333.
  - **El top-1 discrepa caso a caso:**
    - choice: 34 de 139;
    - noul: 44 de 74 (todas las filas `[false, true]`);
    - score: 18 de 18.
- **Pistas** (`capas_por_caso.jsonl` lleva las probabilidades del servidor):
  - En noul el servidor se va hacia `true` (por ejemplo 0,77 frente a 0,42 de Python). Parece CALIB: el `.chispa` sale
    de `chispa train --torre` sobre un esquema mínimo de 16 ejemplos, y sus `a`, `b` y `T` no son los de la evaluación
    en Python.
  - En choice discrepa el 32 % de los textos largos (> 400 caracteres) y el 17 % de los cortos. Hay que revisar el
    truncado de la consulta y el texto de pregunta y torre que arma `servidor.py` frente a `jevbench_l2`.
- **Pendiente:** un diagnóstico caso a caso que compare `s`, el texto de la torre, la pregunta y CALIB entre el servidor
  y Python.
- **Coste:** ≈ 0,02 USD.
