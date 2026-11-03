# Tetris ALE en el CT 109 (i7), 2026-11-02

`ALE/Tetris-v5`, frameskip=1, repeat_action_probability=0, ale-py 0.12.1. 20 partidas por agente, tope 500 piezas.
El cartucho repite la secuencia de piezas sea cual sea la semilla o los NOOP iniciales (medido), así que las 3 primeras piezas
de cada semilla se colocan al azar, las mismas para todos los agentes.

| agente | líneas/partida | piezas | game over | coincide maestro | p50 / p99 ms |
|---|---|---|---|---|---|
| aleatorio | 0,0 | 17,6 | 20 | 3 % | 2,8 / 4,0 |
| maestro (Dellacherie) | **153,9** (28–198) | 410,6 | 10 | 100 % | 2,3 / 4,4 |
| Chispa zero-shot (servidor fp32, `--decidir argmax`) | 0,0 | 23,9 | 20 | 17 % (3/18, partida del vídeo) | 164 / 206 |

- **Controlador:** 8181 de 8212 piezas del maestro (99,6 %) quedan asentadas como predijo el simulador.
- **Chispa zero-shot** escala el 100 % de las veces y su confianza es casi plana (probabilidad máxima media de 0,18 entre 7
  opciones). Juega como el aleatorio. Es lo que dice lo publicado: hace falta ajuste por imitación.
- **Vídeo:** `~/Documents/chispa-caida/tetris-zeroshot-argmax-i7.mp4`, 19 s, 1080p, semilla 1.
  - Grabado tras las 20 partidas, con la caché de torres caliente, por eso la latencia baja a 8 ms.
- **Ficheros:** `ale-local.*` (aleatorio y maestro), `ale-chispa-zeroshot.*`, `traza-video-chispa-zeroshot.jsonl`.
