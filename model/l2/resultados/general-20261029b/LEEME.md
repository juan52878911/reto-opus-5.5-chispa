# G.8, corrida 2 (g5, 2026-10-29): 12.000 pasos y L2 sigue sin generalizar a tareas no vistas

12.000 pasos en 44 minutos de entrenamiento, con el meta equilibrado por tarea, max_tok 256 y κ = 1 elegido en dev.

| | T2.1b (sí vio las tareas) | G.8 corrida 1 (1.640 pasos) | **G.8 corrida 2 (12.000 pasos)** |
|---|---|---|---|
| JevBench sin soporte (exactitud) | 0,407 | 0,472 | **0,463** |
| JevBench con soporte k = 8, κ = 1 | 0,230 | 0,281 | 0,281 |
| massive, no vista, zero-shot | 0,487 | 0,243 | 0,309 |
| hatecheck, no vista, zero-shot | 0,610 | 0,463 | 0,531 |
| inyecciones, no vista, zero-shot | 0,862 | 0,326 | 0,326 |
| 10 % de tasksource apartado, zero-shot | 0,221 | 0,201 | 0,192 |
| clinc150, control, zero-shot | 0,544 | 0,607 | **0,782** |
| herramientas, control, zero-shot | 0,328 | 0,498 | **0,603** |

- **Entrenar más mejora mucho lo visto** (clinc150 0,544 → 0,782) **y casi nada lo no visto.** JevBench se queda en
  0,46–0,47, por debajo de 0,55. Las tareas excluidas siguen lejos de T2.1b. **H1 se refuta otra vez.**
- **Shrinkage.** En dev, κ = 1 (0,779) le gana a κ = 0, solo ejemplos (0,697). En las tareas con train ayuda (massive
  +11 puntos con k = 8). En JevBench sigue costando 18 puntos con 1 o 2 ejemplos por opción. **H2 se refuta en JevBench.**
- **Lectura.** Con e5-small y este metaentrenamiento, el cuello de botella no es la cantidad de pasos. O bien la
  representación no transfiere a esquemas y dominios nuevos, o bien el metaentrenamiento (tsjev, sobre todo inglés y
  tareas de tasksource) no cubre lo que se mide. Lo que sigue es decisión de Juan:
  - un codificador mayor;
  - un profesor zero-shot (bge-m3-zeroshot, MIT) para destilar;
  - o aceptar L2 zero-shot como respaldo y que el producto viva del few-shot con datos del cliente.
- **Coste:** g5 de 66 min, ≈ 1,1 USD. G.8 suma ≈ 1,7 USD de GPU de los 5 aprobados.
