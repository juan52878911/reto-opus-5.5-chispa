# L1 propio (T3.1c): informe

Host: linux/amd64 go1.27.1  abrir=457.448µs  abrir+primer_embed=678.226µs
Maestro de la cabeza: `l0` (fuera de pliegue, k = 5).

## Macro-F1 por tarea (test de T2.2; soporte = 32 por clase del train)

| tarea | potion-zs | potion-proto | propio-256-zs | propio-256-proto | propio-256-cabeza | propio-128-zs | propio-128-proto | propio-128-cabeza |
|---|---|---|---|---|---|---|---|---|
| massive | 0.406 | 0.597 | 0.354 | 0.567 | 0.581 | 0.295 | 0.512 | 0.558 |
| hatecheck | 0.491 | 0.540 | 0.363 | 0.562 | 0.501 | 0.390 | 0.545 | 0.507 |
| clinc150 | 0.445 | 0.745 | 0.277 | 0.738 | 0.758 | 0.178 | 0.706 | 0.733 |
| inyecciones | 0.538 | 0.793 | 0.370 | 0.775 | 0.675 | 0.391 | 0.758 | 0.647 |
| herramientas | 0.397 | 0.597 | 0.400 | 0.510 | 0.455 | 0.343 | 0.419 | 0.405 |
| **media** | **0.455** | **0.654** | **0.353** | **0.630** | **0.594** | **0.319** | **0.588** | **0.570** |

Cabeza > proto en 2 de 5 tareas con propio-256 (H2 pide ≥ 3).

## Tamaño en disco y coseno frente a e5-small (2 274 frases del sondeo)

| modelo | tamaño (MB) | coseno tras ridge (2 mitades) | Spearman de cosenos de pares | frases sin vector |
|---|---|---|---|---|
| potion | 154.8 | 0.9194 | 0.3548 | 6 |
| propio-256 | 17.2 | 0.9308 | 0.2057 | 4 |
| propio-128 | 10.1 | 0.9248 | 0.2075 | 4 |

## Latencia de Embed (runtime/l1, 2 000 repeticiones por tamaño)

| modelo | 16 tok p50 / p99 | 64 tok p50 / p99 | 256 tok p50 / p99 |
|---|---|---|---|
| potion | 25.127µs / 74.347µs | 109.787µs / 267.821µs | 402.529µs / 864.798µs |
| propio-256 | 24.909µs / 62.488µs | 80.262µs / 192.098µs | 294.545µs / 754.964µs |
| propio-128 | 21.541µs / 61.223µs | 72.606µs / 165.81µs | 265.903µs / 786.883µs |

## Lectura

- **H1 (macro-F1 igual o mayor que potion): refutada.** Con 256 dimensiones, propio queda por debajo de potion en
  la media de las cinco tareas: zs 0,353 frente a 0,455 y proto 0,630 frente a 0,654 (proto empata en clinc150, 0,738
  frente a 0,745, y gana en hatecheck, 0,562 frente a 0,540; pierde en las otras tres, sobre todo en herramientas: 0,510 frente a 0,597).
  Lo que sí se cumple es el tamaño: 17,2 MB (256) y 10,1 MB (128) frente a 154,8 MB (9× y 15× menos, ≤ 30 MB).
- El zero-shot es el punto débil (−0,10 de media): un embedding estático sin contexto de e5 no reproduce la
  proximidad texto-descripción de e5; con 128 dimensiones cae más (media 0,319 / 0,588).
- Ablación de SIF (`ablacion-sif.json`, 256 dim, medias zs / proto): sin ponderar 0,250 / 0,567; 1e-3 0,310 / 0,602;
  1e-4 (por defecto) 0,353 / 0,630; 1e-5 0,362 / 0,611. La ponderación importa, pero el óptimo está en el valor usado y
  no cierra la distancia con potion en zs. No se probaron otros ajustes (pooling sin tokens especiales, destilar con
  contexto de frases del corpus).
- **H2 (cabeza > proto en ≥ 3 tareas): refutada con L0 como maestro.** Mejora en 2 de 5 (massive +0,014, clinc150 +0,020)
  y empeora en hatecheck (−0,061), inyecciones (−0,100) y herramientas (−0,055). Las tres que empeoran son las que
  tienen soporte pequeño (64, 64 y 1 024 filas con 32 clases) o un maestro L0 flojo; hiperparámetros fijos (300 pasos,
  lr 0,02), sin ajuste por tarea. En hatecheck e inyecciones el mejor maestro según `delta.md` es L2 con soporte, y ese
  no se pudo calcular aquí: el resultado de esas dos columnas no es concluyente sobre H2.
- Latencia: 17 MB frente a 155 MB no cambia el p99 de forma relevante (62 µs frente a 74 µs a ~16 tokens, 755 µs frente a
  865 µs a 256): domina el tokenizador. Los tamaños pedidos (16, 64, 256) dan 19, 66 y 256 tokens con el tokenizador de e5.
- Coseno frente a e5: el ridge de 384 dimensiones da 0,931 (propio-256) y 0,919 (potion), pero la correlación de Spearman entre
  cosenos de pares sin ajustar es 0,21 frente a 0,35: el espacio de potion se parece más al de e5 en geometría; el de
  propio se parece menos aunque se puede reconstruir linealmente mejor. No es una métrica de calidad de tarea.
- Caveats: soporte de 32 por clase (el de las líneas base), una sola semilla, test sin intervalos de confianza; en las
  tareas pequeñas (hatecheck n = 361, inyecciones n = 116) una diferencia de ±0,03 es ruido.
