
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
