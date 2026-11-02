# Chispa: Caída — evaluación (20 partidas por agente, tope 150 piezas)

- Chispa zero-shot: `http://127.0.0.1:8090`
- Chispa few-shot: `http://127.0.0.1:8090`

| agente | piezas | filas | puntos | game over | coincide prof. | escudo | escudo % | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| aleatorio | 21.55 | 0.05 | 236.5 | 20 | 0.111 | 0 | — | 0.082 | 0.25 |
| profesor | 117.3 | 23.4 | 4702.5 | 13 | 1.0 | 0 | — | 0.497 | 1.097 |
| chispa_zero_shot | 117.3 | 23.4 | 4702.5 | 13 | — | 2329 | 1.0 | 68.753 | 269.422 |
| chispa_few_shot | 117.3 | 23.4 | 4702.5 | 13 | — | 2329 | 1.0 | 68.547 | 85.286 |

Piezas/filas/puntos: media por partida. Coincidencia: entre las decisiones donde Chispa opinó (sin escalar), fracción que eligió la mejor del profesor; en aleatorio, fracción de jugadas iguales a la del profesor. Latencia: por decisión (una petición HTTP de tres preguntas en Chispa; cálculo local en el resto).
