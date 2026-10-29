# G.2, L2 sin tareas enteras (g5, 2026-10-29): L2 no generaliza a tareas no vistas

L2 se reentrenó con los hiperparámetros de T2.1b **sin** massive, hatecheck e inyecciones. Fue 1 época, 1.640 pasos en
11 min, con 78.726 filas locales y 521.416 de meta. Se evalúa con el mismo soporte frente a T2.1b, que sí vio esas tareas.

| tarea | ¿excluida? | zero-shot (T2.1b) | k = 32 (T2.1b) |
|---|---|---|---|
| massive | sí | 0,266 (0,487) | 0,515 (0,632) |
| hatecheck | sí | 0,475 (0,610) | 0,494 (0,630) |
| inyecciones | sí | 0,444 (0,862) | 0,530 (0,922) |
| clinc150 | no, control | 0,604 (0,544) | 0,783 (0,775) |
| herramientas | no, control | 0,510 (0,328) | 0,623 (0,504) |

- **H1 se refuta.** En las tareas excluidas, zero-shot cae al 51–78 % de T2.1b y k = 32 pierde entre 12 y 39 puntos.
- **Los controles** igualan o superan a T2.1b, así que la caída no viene de entrenar menos.
- **Lectura:** buena parte de lo que L2 sabe en esas tareas viene de haberlas visto. Con JevBench (0,407) apunta a lo mismo:
  **L2, tal como está, no es todavía un clasificador zero-shot de propósito general.**
- **Avisos.**
  - Hubo un 403 al bajar un fichero opcional de S3: el entrenamiento siguió y salió `fallo=no`.
  - `banking77` no se convirtió (etiqueta sin tabla de nombres).
  - Un dataset de HF (`somosnlp/suicide-comments-es`) ya no existe.
- **Coste:** una g5 on-demand de unos 25 min, ≈ 0,45 USD.
