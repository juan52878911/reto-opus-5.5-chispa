# «Chispa: Serpiente» en el servidor local (i7, CT 109), 2026-11-02

- **Juego original** del género serpiente (`demos/serpiente/`): rejilla de 16×16, tope de 500 pasos, una decisión `choice`
  por paso entre izquierda, recto y derecha, con el estado en palabras.
- **Servidor:** `chispa-server` (tar de ZJ2), modelo de servidor fp32 del ajuste 1, texto de torre v1. Zero-shot, `--decidir
  argmax`, 20 partidas por agente.

| agente | pasos (media) | comida (media) | coincide con el profesor | bajo τ | escudo | p50 / p99 por decisión |
|---|---|---|---|---|---|---|
| aleatorio | 39,0 | 0,15 | 34,7 % | — | — | ~0 ms |
| profesor (BFS con anti-encierro) | 500 | 38,3 | 100 % | — | — | 0,8 / 1,7 ms |
| **Chispa zero-shot** | **500** | **0,0** | 31,9 % | 100 % | 0 % | **27 / 145 ms** |

- **Lectura:** Chispa **sobrevive siempre los 500 pasos, pero no come nunca.** Evita chocar, porque las casillas libres por
  opción van en el texto, pero no persigue la comida: da vueltas. Sus probabilidades son casi uniformes (≈ 29/33/39 % en el
  paso 316) y todas sus decisiones quedan bajo τ.
- **Latencia aislada** (una pregunta):

  | caché de torres | p50 | p99 | decisiones/s |
  |---|---|---|---|
  | fría | 177 ms | 250 ms | 5,4 |
  | caliente | 29 ms | 56 ms | 33,4 |

- **Vídeo:** `~/Documents/chispa-caida/serpiente-zeroshot-argmax-i7.mp4`, 40 s, 1080p, renderizado en el Mac. Fotograma de
  muestra en `fotograma-paso316.png`. Hay dos detalles menores del render: el texto de estado se sale del panel y falta un
  glifo de flecha.
