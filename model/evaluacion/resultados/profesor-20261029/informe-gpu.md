# G.9 Techo del profesor zero-shot (CPU, c6a.2xlarge spot)

JevBench en exactitud (231 casos, sin soporte); tareas no vistas en macro-F1 (≤ 300 filas por tarea, `profesor preparar`).

| fila | licencia | JevBench (exact.) | massive | hatecheck | inyecciones | tasksource apartado | ms/caso CPU (medio) |
|---|---|---|---|---|---|---|---|
| profesor bge-m3-zeroshot-c (plantilla es) | MIT, solo datos comerciales: destilable | 0,528 | 0,134 | 0,568 | 0,388 | 0,225 | 22 |
| profesor bge-m3-zeroshot (plantilla card) | MIT, pero con ANLI/WANLI/LingNLI (licencia mixta): solo de referencia | 0,541 | 0,274 | 0,420 | 0,351 | 0,225 | 22 |
| G.8 corrida 2 (L2 sobre e5-small, 12.000 pasos) | propia | 0,463 | 0,309 | 0,531 | 0,326 | 0,192 | - |
| T2.1b (L2; vio las tareas) | propia | 0,407 | 0,487 | 0,610 | 0,862 | 0,221 | - |

Muestras: los conjuntos del profesor son ≤ 300 filas con hash estable y no son los mismos casos que G.8 (tasksource_fuera, allí 40 por tarea): la comparación es de orden de magnitud, no de décimas.

**Hipótesis (profesor «-c»):** JevBench sin soporte 0,528 (umbral 0,550) y mejora de ≥ +10 puntos de macro-F1 sobre G.8 en 0 de 4 tareas no vistas (ninguna; hacen falta 2).

**NO SE CUMPLE: el límite parece estar en los datos y no en el modelo.**

Etiqueta: choice y noul por argmax; score, la mediana CORAL de la distribución sobre los niveles (`metricas.top1`). Plantilla elegida en dev por modelo: bge-m3-zeroshot-c: es {'card': 0.2275755820147188, 'es': 0.2842722143337738}; bge-m3-zeroshot: card {'card': 0.39534959509540013, 'es': 0.3759415093812688}.

**Coste:** 8 min de instancia × 0.20 USD/h ≈ 0.03 USD (tope 0,5 USD; spot, estimado, más unos céntimos de disco y tráfico).
