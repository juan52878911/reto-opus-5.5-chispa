# G.9, techo del profesor bge-m3-zeroshot-v2.0-c (c6a.2xlarge en CPU, 2026-10-29): incompleto por tiempo

Con NLI en CPU, el profesor tarda **0,6–1,8 s por caso** (una pasada por opción, con bge-m3 de 568 M parámetros). En 149
minutos solo se midieron dos tareas no vistas con la variante «-c», que es la destilable. JevBench, massive, el 10 % de
tasksource y la variante sin «-c» quedaron sin medir.

| tarea no vista | profesor «-c» | G.8 corrida 2 (L2 zero-shot) | T2.1b (sí la vio) |
|---|---|---|---|
| hatecheck (n = 300) | **0,568** (exactitud 0,707) | 0,531 | 0,610 |
| inyecciones (n = 116) | **0,388** (exactitud 0,457) | 0,326 | 0,862 |

- **El profesor mejora a L2 en esas dos tareas, pero poco:** +3,7 y +6,2 puntos. No llega a lo que da haber visto la tarea.
  Con dos tareas no se puede dar veredicto. La señal apunta a que **parte del límite está en los datos**.
- **Para cerrarlo** hace falta GPU: una g5 de ≈ 30–40 min, ≈ 0,6 USD, mide JevBench y todas las tareas con las dos
  variantes. No la lanzo sin OK.
- **Coste:** c6a.2xlarge spot de 2 h 20 min, ≈ 0,3 USD.
