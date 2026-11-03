# Chispa: Serpiente — evaluación (20 partidas por agente, tope 500 pasos)

- Modo de decisión de Chispa: `argmax`
- Servidor: `http://127.0.0.1:8090`

| agente | pasos (media) | pasos (mediana) | comida (media) | comida (mediana) | coincide prof. % | bajo τ % | escudo % | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| aleatorio | 38.95 | 35.0 | 0.15 | 0.0 | 34.7 | — | — | 0.001 | 0.003 |
| profesor | 500.0 | 500.0 | 38.25 | 39.0 | 100.0 | — | — | 0.849 | 1.736 |
| chispa_zero_shot | 500.0 | 500.0 | 0.0 | 0.0 | 31.9 | 100.0 | 0.0 | 26.624 | 144.61 |

Pasos y comida: por partida (se acaba al chocar o a los 500 pasos). Coincidencia: entre las decisiones donde Chispa decidió (sin escudo), % de jugadas iguales a la del profesor; en aleatorio, de todas. Bajo τ y escudo: % de las decisiones (sin contar las forzadas, con una sola opción que no choca). Latencia: por decisión, medida en el cliente (en aleatorio y profesor es el cálculo local).
