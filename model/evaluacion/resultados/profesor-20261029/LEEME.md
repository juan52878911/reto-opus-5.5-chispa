# G.9, techo del profesor bge-m3-zeroshot-v2.0 (g5, 2026-10-29): la destilación no es el camino

En GPU todo se midió en 5 minutos. La corrida en CPU, incompleta, está en `log.txt`.

| conjunto (zero-shot) | profesor «-c» (destilable) | profesor sin «-c» (referencia) | L2 G.8 corrida 2 | T2.1b (vio la tarea) |
|---|---|---|---|---|
| JevBench, exactitud | **0,528** | 0,541 | 0,463 | 0,407 |
| massive, macro-F1 | 0,134 | 0,274 | 0,309 | 0,487 |
| hatecheck, macro-F1 | 0,568 | 0,420 | 0,531 | 0,610 |
| inyecciones, macro-F1 | 0,388 | 0,351 | 0,326 | 0,862 |
| 10 % de tasksource apartado | 0,225 | 0,225 | 0,192 | 0,221 |

- **La hipótesis se refuta.** Pedía que «-c» llegara a ≥ 0,55 en JevBench y ganara ≥ 10 puntos en ≥ 2 de 4 tareas no
  vistas:
  - JevBench queda en 0,528;
  - en las no vistas gana +3,7 (hatecheck), +6,2 (inyecciones) y +3,3 (tasksource);
  - en massive pierde 17,5 puntos.
- **Lectura.** Un profesor zero-shot de 568 M parámetros, entrenado para esto, saca casi lo mismo que L2 sobre e5-small.
  Destilar de él daría como mucho unos pocos puntos. **El límite está sobre todo en los datos y en la naturaleza de las
  tareas** (intenciones de 60 clases en español, inyecciones con jerga propia), no en el tamaño del modelo. Lo que mueve la
  aguja es ver ejemplos de la tarea: T2.1b, CONJ, o L0 con datos del cliente.
- **Licencias:**
  - «-c» es MIT con solo datos comerciales;
  - sin «-c» es MIT con datos de licencia mixta, solo como referencia.
- **Coste:** g5 de unos 8 min, ≈ 0,15 USD, más la c6a.2xlarge en CPU de antes, ≈ 0,3 USD.
