# T1.7a Líneas base provisionales (test reales)

Rama `delega/20261027-144248-11528`. Reproducir: `python -m model.lineas_base.correr` y `python -m model.lineas_base.informe`.
Predicciones por fila en `pred/` (`{id, probs, ms}`; las de más de 5 MB, en `.gz`); métricas crudas en `resultados.json`,
calculadas con `chispa eval`.

## Cómo se midió
- **Datos**: test de `model.datos.convertir` (MASSIVE es, HateCheck-ES, CLINC150 con `oos`→`escalate`, deepset) y
  `model/herramientas/test.jsonl`. Banking77 no se convierte (sin ficheros de train en ~/hf) y no se pedía aquí.
- **Entrenamiento/soporte**: 32 ejemplos por clase del train, semilla 0; kNN-8 usa 8 de esos 32.
- **L0**: **no** es el Chispa lineal de la Arena (su entrenador depende de `kindling/pkg/chispa` y no se invoca desde Python
  sin tocar `arena/`). Es el equivalente: TF-IDF de caracteres (`char_wb`, 2-5) + regresión logística (C=10, sin ajustar).
- **e5-small kNN**: prefijo `query: `, coseno, softmax(sim/T) sobre los 10 vecinos. T (columna T) se fija en dev por
  log-verosimilitud negativa sobre una rejilla de 8 valores; en herramientas, sin dev, con «dejar uno fuera» sobre el soporte.
- **p99 ms**: consulta a consulta en una microVM de 4 hilos compartida; en e5 incluye codificar la consulta (~150 ms, con
  cola larga). No es la latencia en el i7. El p99 de deepset (1757 ms) es una pausa de la máquina sobre 116 filas.
- **THX-01**: solo herramientas y con **40 filas** (no 300): ~13 s por fila en esta CPU. MASSIVE y CLINC150 con THX-01
  **no medidos**. Con n=40 la cifra es orientativa.

## Resultados

### MASSIVE es (intención, 60 clases)

| sistema | n | macro-F1 | ECE | cob@0,95 | AUROC escalate | p99 ms | T |
|---|---|---|---|---|---|---|---|
| l0_tfidf_lr | 2974 | 0,678 | 0,223 | 0,266 | - | 7,6 | - |
| e5_knn8 | 2974 | 0,518 | 0,055 | 0,045 | - | 259,9 | 0,020 |
| e5_knn32 | 2974 | 0,635 | 0,057 | 0,192 | - | 265,7 | 0,020 |

### HateCheck-ES (toxicidad, 2 clases)

| sistema | n | macro-F1 | ECE | cob@0,95 | AUROC escalate | p99 ms | T |
|---|---|---|---|---|---|---|---|
| l0_tfidf_lr | 361 | 0,530 | 0,085 | 0,006 | - | 9,3 | - |
| e5_knn8 | 361 | 0,594 | 0,104 | 0,033 | - | 239,8 | 0,050 |
| e5_knn32 | 361 | 0,579 | 0,037 | 0,028 | - | 239,8 | 0,100 |

### CLINC150 con oos→escalate (151 clases)

| sistema | n | macro-F1 | ECE | cob@0,95 | AUROC escalate | p99 ms | T |
|---|---|---|---|---|---|---|---|
| l0_tfidf_lr | 5500 | 0,811 | 0,203 | 0,608 | 0,912 | 10,8 | - |
| e5_knn8 | 5500 | 0,711 | 0,106 | 0,408 | 0,544 | 275,4 | 0,010 |
| e5_knn32 | 5500 | 0,794 | 0,053 | 0,580 | 0,563 | 282,3 | 0,020 |

### deepset (inyección, 2 clases)

| sistema | n | macro-F1 | ECE | cob@0,95 | AUROC escalate | p99 ms | T |
|---|---|---|---|---|---|---|---|
| l0_tfidf_lr | 116 | 0,835 | 0,172 | 0,276 | - | 4,3 | - |
| e5_knn8 | 116 | 0,640 | 0,119 | 0,431 | - | 1757,4 | 0,030 |
| e5_knn32 | 116 | 0,800 | 0,073 | 0,543 | - | 1757,4 | 0,030 |

### Herramientas (32 clases, con escalate)

| sistema | n | macro-F1 | ECE | cob@0,95 | AUROC escalate | p99 ms | T |
|---|---|---|---|---|---|---|---|
| l0_tfidf_lr | 368 | 0,696 | 0,351 | 0,245 | 0,922 | 3,8 | - |
| e5_knn8 | 368 | 0,543 | 0,070 | 0,152 | 0,789 | 299,1 | 0,010 |
| e5_knn32 | 368 | 0,632 | 0,066 | 0,245 | 0,838 | 299,1 | 0,010 |
| thx01 | 40 | 0,696 | 0,140 | 0,275 | 0,854 | 28775,1 | - |


### THX-01, solo herramientas (n=40, subconjunto fijo, sin comparabilidad directa con n=368)
macro-F1 0.696, ECE 0.140, cob@0,95 0.275, AUROC escalate 0.854, p99 28775 ms. Con 32 clases y 40 filas, el macro-F1 está muy
sesgado por clases con 0-2 filas.

## Criterio (a) de G1
La hipótesis no se sostiene tal como estaba escrita: e5 kNN-32 queda lejos del umbral de refutación (macro-F1 ≥ 0,9 y
cobertura ≥ 50 % en todas; se queda en 0,58-0,79 de macro-F1) y el L0 de reemplazo le gana en macro-F1 en MASSIVE, CLINC150,
deepset y herramientas (no en HateCheck, donde ambos rondan el azar). El hueco medible para L2 está en tres sitios: calidad
absoluta (ninguna tarea llega a 0,9 con 32 por clase), toxicidad (macro-F1 0,53-0,59) y escalate en CLINC150 y
herramientas, donde e5 kNN da AUROC 0,56 y 0,84 frente a 0,91 y 0,92 del L0; la calibración (ECE) es lo único en que kNN-32
supera al L0 (0,05-0,07 frente a 0,2-0,35). Es provisional: L0 es un sustituto y falta Jev.
