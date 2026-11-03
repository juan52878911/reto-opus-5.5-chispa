# Chispa: Caída — evaluación (20 partidas por agente, tope 150 piezas)

- Modo de decisión de Chispa: `argmax`
- Chispa zero-shot: `http://127.0.0.1:8090`
- Chispa few-shot: `http://127.0.0.1:8090`

| agente | piezas | filas | puntos | game over | coincide prof. | chispa_tau | coin. tau | bajo_tau | coin. bajo_tau | escudo | coin. escudo | coin. jugada | escudo % | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| aleatorio | 21.55 | 0.05 | 236.5 | 20 | 0.111 | 0 | — | 0 | — | 0 | — | — | — | 0.082 | 0.348 |
| profesor | 117.3 | 23.4 | 4702.5 | 13 | 1.0 | 0 | — | 0 | — | 0 | — | — | — | 0.495 | 1.181 |
| chispa_zero_shot | 42.65 | 3.35 | 963.5 | 20 | 0.077 | 13 | 0.077 | 820 | 0.27 | 0 | — | 0.267 | 0.0 | 149.077 | 335.081 |
| chispa_few_shot | 42.65 | 3.35 | 963.5 | 20 | 0.077 | 13 | 0.077 | 820 | 0.27 | 0 | — | 0.267 | 0.0 | 78.68 | 137.232 |

Piezas/filas/puntos: media por partida. Coincidencia: entre las decisiones donde Chispa opinó (sin escalar), fracción que eligió la mejor del profesor; en aleatorio, fracción de jugadas iguales a la del profesor. chispa_tau: Chispa no escaló; bajo_tau: escaló pero se jugó su argmax (solo con `--decidir argmax`); escudo: jugó el profesor (su coincidencia es 1 por construcción); coin. jugada: la jugada final contra la del profesor, las tres juntas. Las opciones se ofrecen barajadas con la semilla de la partida: un azar entre 6 coincide ≈ 0,167. Latencia: por decisión (dos peticiones HTTP en Chispa: choice, y score + noul; cálculo local en el resto).
