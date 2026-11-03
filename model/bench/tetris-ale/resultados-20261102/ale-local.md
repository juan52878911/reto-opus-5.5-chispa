# Tetris ALE (emulador, ALE/Tetris-v5) — evaluación (20 partidas por agente, tope 500 piezas)

- Semillas: 1…20

| agente | líneas/partida | mín | máx | piezas | game over | coincide maestro | % bajo τ | escudo | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|---|
| aleatorio | 0.0 | 0 | 0 | 17.55 | 20 | 0.031 | — | 0 | 2.829 | 3.964 |
| maestro | 153.9 | 28 | 198 | 410.6 | 10 | 1.0 | — | 0 | 2.308 | 4.359 |

Líneas, piezas: media por partida (la principal es líneas). Coincidencia: en Chispa, entre las decisiones donde opinó (sin escalar), fracción que eligió la mejor del maestro; en los demás, fracción de jugadas iguales a la del maestro. % bajo τ: decisiones donde Chispa escaló (juega el maestro, o su argmax con `--decidir argmax`). Latencia: por decisión (una petición HTTP en Chispa; cálculo local en el resto). Todos los agentes pasan por el veto de seguridad.

Controlador: aleatorio: 314/351 piezas asentadas como predijo el simulador, 29 fallos; maestro: 8181/8212 piezas asentadas como predijo el simulador, 31 fallos. Las 3 primeras piezas de cada semilla son al azar (las mismas para todos): el cartucho repite la secuencia.
