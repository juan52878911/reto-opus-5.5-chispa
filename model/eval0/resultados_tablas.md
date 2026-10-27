
### A. 1 hilo, subconjunto fijo de 120 ejemplos por tarea (base de la comparación D2)

| modelo | tarea | n | macro-F1 | ECE | p50 ms | p99 ms | RSS pico MB |
|---|---|---|---|---|---|---|---|
| e5_knn8 | intencion | 120 | 74.2 | 0.162 | 136 | 284 | 989 |
| e5_knn8 | toxicidad | 120 | 47.9 | 0.116 | 140 | 370 | 978 |
| e5_knn8 | whatsapp_comercio | 120 | 67.6 | 0.176 | 156 | 293 | 982 |
| e5_knn8 | herramientas | 120 | 72.9 | 0.234 | 133 | 245 | 997 |
| e5_knn32 | intencion | 120 | 87.2 | 0.117 | 111 | 219 | 1010 |
| e5_knn32 | toxicidad | 120 | 57.9 | 0.157 | 125 | 217 | 983 |
| e5_knn32 | whatsapp_comercio | 120 | 78.1 | 0.074 | 140 | 282 | 988 |
| e5_knn32 | herramientas | 120 | 80.5 | 0.160 | 129 | 290 | 1012 |
| gliclass | intencion | 120 | 39.3 | 0.092 | 1826 | 3148 | 1558 |
| gliclass | toxicidad | 120 | 53.7 | 0.208 | 675 | 968 | 1554 |
| gliclass | whatsapp_comercio | 120 | 17.4 | 0.336 | 1372 | 1720 | 1554 |
| gliclass | herramientas | 120 | 12.2 | 0.154 | 5202 | 5722 | 1557 |
| julia1 | intencion | 120 | 54.1 | 0.314 | 1072 | 2067 | 870 |
| julia1 | toxicidad | 120 | 48.6 | 0.356 | 587 | 857 | 858 |
| julia1 | whatsapp_comercio | 120 | 31.2 | 0.495 | 491 | 1491 | 852 |
| julia1 | herramientas | 120 | 37.9 | 0.273 | 1985 | 2838 | 876 |
| thx01 | intencion | 120 | 93.3 | 0.067 | 2174 | 2607 | 2323 |
| thx01 | toxicidad | 120 | 53.0 | 0.303 | 1268 | 1650 | 2320 |
| thx01 | whatsapp_comercio | 120 | 64.6 | 0.329 | 1760 | 2167 | 2322 |
| thx01 | herramientas | 120 | 82.2 | 0.092 | 5059 | 5652 | 2321 |
| laya | intencion | 120 | 73.9 | 0.153 | 2206 | 4214 | 2236 |
| laya | toxicidad | 120 | 63.3 | 0.219 | 818 | 1123 | 2323 |
| laya | whatsapp_comercio | 120 | 50.9 | 0.198 | 1098 | 1446 | 2320 |
| laya | herramientas | 120 | 60.5 | 0.191 | 3561 | 8775 | 2321 |

### B. 1 hilo, test completo (solo e5; referencia del tamaño de muestra)

| modelo | tarea | n | macro-F1 | ECE | p50 ms | p99 ms | RSS pico MB |
|---|---|---|---|---|---|---|---|
| e5_knn32 | intencion | 390 | 87.2 | 0.105 | 60 | 90 | 1023 |
| e5_knn32 | toxicidad | 300 | 55.5 | 0.099 | 72 | 121 | 993 |
| e5_knn32 | whatsapp_comercio | 213 | 77.1 | 0.074 | 103 | 160 | 990 |
| e5_knn32 | herramientas | 212 | 80.5 | 0.148 | 71 | 115 | 1020 |

### C. 4 hilos, 30 ejemplos por tarea (p99 sobre 30 = prácticamente el máximo; la macro-F1 no es comparable)

| modelo | tarea | n | macro-F1 | ECE | p50 ms | p99 ms | RSS pico MB |
|---|---|---|---|---|---|---|---|
| gliclass | intencion | 30 | 37.7 | 0.165 | 1331 | 1668 | 1550 |
| gliclass | toxicidad | 30 | 60.0 | 0.281 | 636 | 802 | 1549 |
| gliclass | whatsapp_comercio | 30 | 18.4 | 0.425 | 1522 | 1736 | 1549 |
| gliclass | herramientas | 30 | 6.3 | 0.176 | 2454 | 2821 | 1550 |
| julia1 | intencion | 30 | 49.5 | 0.334 | 1314 | 2624 | 851 |
| julia1 | toxicidad | 30 | 37.5 | 0.410 | 584 | 847 | 854 |
| julia1 | whatsapp_comercio | 30 | 33.3 | 0.445 | 515 | 879 | 844 |
| julia1 | herramientas | 30 | 37.7 | 0.255 | 1993 | 2761 | 859 |
| thx01 | intencion | 30 | 89.4 | 0.106 | 1841 | 2133 | 2326 |
| thx01 | toxicidad | 30 | 47.1 | 0.483 | 1446 | 1895 | 2319 |
| thx01 | whatsapp_comercio | 30 | 69.4 | 0.307 | 963 | 1361 | 2317 |
| thx01 | herramientas | 30 | 64.3 | 0.121 | 5045 | 5643 | 2324 |
| laya | intencion | 30 | 66.4 | 0.281 | 1798 | 2089 | 2322 |
| laya | toxicidad | 30 | 59.8 | 0.281 | 778 | 908 | 2317 |
| laya | whatsapp_comercio | 30 | 56.4 | 0.251 | 994 | 1240 | 2322 |
| laya | herramientas | 30 | 41.8 | 0.316 | 6188 | 7092 | 2320 |

### C'. 4 hilos, 60 ejemplos por tarea (solo e5, primera pasada)

| modelo | tarea | n | macro-F1 | ECE | p50 ms | p99 ms | RSS pico MB |
|---|---|---|---|---|---|---|---|
| e5_knn32 | intencion | 60 | 14.0 | 0.167 | 58 | 86 | 1006 |
| e5_knn32 | toxicidad | 60 | 42.3 | 0.133 | 118 | 173 | 974 |
| e5_knn32 | whatsapp_comercio | 60 | 76.1 | 0.098 | 107 | 204 | 981 |
| e5_knn32 | herramientas | 60 | 76.8 | 0.202 | 77 | 128 | 999 |

### D. Regla de D2 (≥ 5 puntos de macro-F1 de media sobre e5 kNN-32 y p99 ≤ 50 ms), tabla A

| modelo | macro-F1 media (4 tareas) | Δ vs e5_knn32 | p99 máx entre tareas (ms) | cumple |
|---|---|---|---|---|
| e5_knn8 | 65.6 | -10.3 | 370 | no |
| e5_knn32 | 75.9 | +0.0 | 290 | no |
| gliclass | 30.7 | -45.3 | 5722 | no |
| julia1 | 43.0 | -32.9 | 2838 | no |
| thx01 | 73.3 | -2.6 | 5652 | no |
| laya | 62.1 | -13.8 | 8775 | no |
