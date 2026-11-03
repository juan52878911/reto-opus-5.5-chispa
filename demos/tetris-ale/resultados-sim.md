Generado con: `python -m tetris_ale evaluar --salida /tmp/ev --agentes aleatorio maestro el-tetris` (20 semillas, 1…20, tope 500 piezas, sin servidor).

# Tetris ALE (simulador) — evaluación (20 partidas por agente, tope 500 piezas)

- Semillas: 1…20

| agente | líneas/partida | mín | máx | piezas | game over | coincide maestro | % bajo τ | escudo | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|---|
| aleatorio | 0.05 | 0 | 1 | 23.5 | 20 | 0.062 | — | 0 | 2.313 | 5.245 |
| maestro | 194.0 | 140 | 199 | 494.5 | 1 | 1.0 | — | 0 | 1.941 | 4.521 |
| el-tetris | 148.4 | 87 | 197 | 403.0 | 13 | 1.0 | — | 0 | 2.207 | 4.797 |

Líneas, piezas: media por partida (la principal es líneas). Coincidencia: en Chispa, entre las decisiones donde opinó (sin escalar), fracción que eligió la mejor del maestro; en los demás, fracción de jugadas iguales a la del maestro. % bajo τ: decisiones donde Chispa escaló (juega el maestro, o su argmax con `--decidir argmax`). Latencia: por decisión (una petición HTTP en Chispa; cálculo local en el resto). Todos los agentes pasan por el veto de seguridad.

Criterio: maestro ≥ 50 líneas de media (194,0) y aleatorio < 2 (0,05). Con 500 piezas el máximo teórico es 200 líneas. Las columnas de Chispa (coincidencia, % bajo τ) quedan en «—» hasta evaluar contra un servidor real con `--url`.
