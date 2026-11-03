# Tetris ALE (emulador, ALE/Tetris-v5) — evaluación (20 partidas por agente, tope 500 piezas)

- Modo de decisión de Chispa: `argmax`
- Servidor: `http://127.0.0.1:8090`
- Semillas: 1…20

| agente | líneas/partida | mín | máx | piezas | game over | coincide maestro | % bajo τ | escudo | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|---|
| chispa | 0.0 | 0 | 0 | 23.85 | 20 | — | 100.0 | 0 | 163.829 | 206.023 |

Líneas, piezas: media por partida (la principal es líneas). Coincidencia: en Chispa, entre las decisiones donde opinó (sin escalar), fracción que eligió la mejor del maestro; en los demás, fracción de jugadas iguales a la del maestro. % bajo τ: decisiones donde Chispa escaló (juega el maestro, o su argmax con `--decidir argmax`). Latencia: por decisión (una petición HTTP en Chispa; cálculo local en el resto). Todos los agentes pasan por el veto de seguridad.

Controlador: chispa: 439/477 piezas asentadas como predijo el simulador, 36 fallos. Las 3 primeras piezas de cada semilla son al azar (las mismas para todos): el cartucho repite la secuencia.
