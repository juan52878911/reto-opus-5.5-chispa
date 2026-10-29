# JevBench público (231 decisiones): L2 y la cascada de un cliente nuevo

Casos: 231 ({'choice': 139, 'noul': 74, 'score': 18}), esquemas distintos: 117, con algún otro caso de su esquema fuera de sus paráfrasis: 135, medibles por la cascada: 59.

## Exactitud y macro-F1 por variante y subconjunto

| variante | subconjunto | n | exactitud | IC95 | macro-F1 (agrupado) | macro-F1 (media por familia) | ECE |
|---|---|---|---|---|---|---|---|
| l2_k0 | todos | 231 | 0.407 | 0.346–0.471 | 0.242 | 0.291 | 0.176 |
| l2_k0 | con soporte | 135 | 0.489 | 0.406–0.572 | 0.447 | 0.403 | 0.131 |
| l2_k0 | cascada | 59 | 0.390 | 0.276–0.517 | 0.346 | 0.348 | 0.220 |
| l2_k8 | todos | 231 | 0.255 | 0.203–0.315 | 0.125 | 0.161 | 0.418 |
| l2_k8 | con soporte | 135 | 0.230 | 0.167–0.307 | 0.084 | 0.134 | 0.542 |
| l2_k8 | cascada | 59 | 0.458 | 0.337–0.583 | 0.457 | 0.442 | 0.256 |
| l2_k32 | todos | 231 | 0.255 | 0.203–0.315 | 0.125 | 0.161 | 0.418 |
| l2_k32 | con soporte | 135 | 0.230 | 0.167–0.307 | 0.084 | 0.134 | 0.542 |
| l2_k32 | cascada | 59 | 0.458 | 0.337–0.583 | 0.457 | 0.442 | 0.256 |
| cascada_k8 | todos | 59 | 0.339 | 0.231–0.466 | 0.288 | 0.324 | 0.518 |
| cascada_k8 | con soporte | 59 | 0.339 | 0.231–0.466 | 0.288 | 0.324 | 0.518 |
| cascada_k8 | cascada | 59 | 0.339 | 0.231–0.466 | 0.288 | 0.324 | 0.518 |
| cascada_k32 | todos | 59 | 0.339 | 0.231–0.466 | 0.288 | 0.324 | 0.518 |
| cascada_k32 | con soporte | 59 | 0.339 | 0.231–0.466 | 0.288 | 0.324 | 0.518 |
| cascada_k32 | cascada | 59 | 0.339 | 0.231–0.466 | 0.288 | 0.324 | 0.518 |

## Cobertura y escalado de la cascada (sobre los casos que midió)

| variante | n | cobertura (no escala) | escalados | exactitud respondidos | exactitud total (sin respuesta = fallo) | errores | capas |
|---|---|---|---|---|---|---|---|
| cascada_k8 | 59 | 0.339 | 39 | 0.200 | 0.339 | 0 | {'escalar': 39, 'L0': 20} |
| cascada_k32 | 59 | 0.339 | 39 | 0.200 | 0.339 | 0 | {'escalar': 39, 'L0': 20} |

Omitidos en cascada_k8: 172 casos: 96 sin otros casos de su esquema, 66 el soporte no cubre todas las opciones, 10 falló dos veces

Omitidos en cascada_k32: 172 casos: 96 sin otros casos de su esquema, 66 el soporte no cubre todas las opciones, 10 falló dos veces

## Hipótesis

- **H1** (L2 zero-shot ≥ 0.55): exactitud 0.407 (IC95 0.346–0.471, n=231) → refutada en estimación puntual.
- **H2** l2_k8 frente a L2 zero-shot en los mismos 135 casos (con soporte): 0.230 vs 0.489 (Δ -0.259); acierta donde el zero-shot falla en 6, y al revés en 41.
- **H2** l2_k32 frente a L2 zero-shot en los mismos 135 casos (con soporte): 0.230 vs 0.489 (Δ -0.259); acierta donde el zero-shot falla en 6, y al revés en 41.
- **H2** cascada_k8 frente a L2 zero-shot en los mismos 59 casos (cascada): 0.339 vs 0.390 (Δ -0.051); acierta donde el zero-shot falla en 6, y al revés en 9.
- **H2** cascada_k32 frente a L2 zero-shot en los mismos 59 casos (cascada): 0.339 vs 0.390 (Δ -0.051); acierta donde el zero-shot falla en 6, y al revés en 9.
- k = 8 y k = 32 son idénticos en la cascada: ningún esquema de JevBench público tiene más de 8 ejemplos por opción, así que el tope k no actúa y el soporte es el mismo.

## Límites

- 108 de 231 casos tienen estados de más de 400 caracteres (≈ 128 tokens): L2 trunca el estado (MAX_TOK) y no ve el final.
- Los esquemas son casi todos de un solo caso: el soporte sale de otros casos del mismo esquema (misma pregunta, opciones y criterios), sin el caso ni sus paráfrasis (`grupo`); donde no hay, el caso queda sin soporte y no cuenta como «con soporte».
- La cascada solo se mide donde `chispa train` puede entrenar sin forzar: el soporte debe cubrir todas las opciones. No se recorta el esquema.
- Es el split público de JevBench (231 casos): no es la puntuación oficial de la tabla (sellada, otra escala).
