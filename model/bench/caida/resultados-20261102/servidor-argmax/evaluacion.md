# Chispa: Caída — evaluación (20 partidas por agente, tope 150 piezas)

- Modo de decisión de Chispa: `argmax`
- Chispa zero-shot: `http://127.0.0.1:8090`
- Chispa few-shot: `http://127.0.0.1:8090`

| agente | piezas | filas | puntos | game over | coincide prof. | chispa_tau | coin. tau | bajo_tau | coin. bajo_tau | escudo | coin. escudo | coin. jugada | escudo % | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| aleatorio | 21.55 | 0.05 | 236.5 | 20 | 0.111 | 0 | — | 0 | — | 0 | — | — | — | 0.081 | 0.222 |
| profesor | 117.3 | 23.4 | 4702.5 | 13 | 1.0 | 0 | — | 0 | — | 0 | — | — | — | 0.486 | 0.981 |
| chispa_zero_shot | 40.85 | 3.0 | 881.5 | 20 | — | 0 | — | 805 | 0.282 | 0 | — | 0.282 | 0.0 | 184.747 | 347.379 |
| chispa_few_shot | 40.85 | 3.0 | 881.5 | 20 | — | 0 | — | 805 | 0.282 | 0 | — | 0.282 | 0.0 | 110.115 | 139.029 |

Piezas/filas/puntos: media por partida. Coincidencia: entre las decisiones donde Chispa opinó (sin escalar), fracción que eligió la mejor del profesor; en aleatorio, fracción de jugadas iguales a la del profesor. chispa_tau: Chispa no escaló; bajo_tau: escaló pero se jugó su argmax (solo con `--decidir argmax`); escudo: jugó el profesor (su coincidencia es 1 por construcción); coin. jugada: la jugada final contra la del profesor, las tres juntas. Las opciones se ofrecen barajadas con la semilla de la partida: un azar entre 6 coincide ≈ 0,167. Latencia: por decisión (dos peticiones HTTP en Chispa: choice, y score + noul; cálculo local en el resto).
