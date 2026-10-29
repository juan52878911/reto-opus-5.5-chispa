# G.1, JevBench público con L2 (c6a, 2026-10-29): L2 zero-shot saca 0,407 frente al suelo de 0,55

231 casos: 139 choice, 74 noul y 18 score, en 117 esquemas.

| variante | n | exactitud (IC95) |
|---|---|---|
| **L2 zero-shot, en Python** | 231 | **0,407 (0,346–0,471)** |
| L2 zero-shot, casos con soporte | 135 | 0,489 |
| L2 con soporte k = 8 (= k = 32) | 135 | 0,230 |
| cascada de `chispa train` sin `--conjunta` | 59 | 0,339 (escala 39 de 59) |

- **H1 (≥ 0,55) se refuta.** L2 no llega al suelo de JevBench. Además, 108 casos pasan de unos 128 tokens y L2 los trunca.
- **El soporte empeora el resultado.** Los esquemas de JevBench tienen 1 o 2 ejemplos por opción, y los prototipos con tan
  pocos ejemplos meten ruido. k = 8 y k = 32 dan lo mismo, porque ninguna opción tiene más de 8.
- **La cascada solo se puede medir en 59 casos.** En el resto no hay soporte que cubra todas las opciones, y en lo que mide
  queda por debajo de L2 zero-shot.
- **Servidor hoy.** Con un esquema nuevo solo decide L1, porque las torres al vuelo aún no están integradas. No se midió
  aquí: lo cubre G.6.
- **Coste:** una c6a spot de 37 min, ≈ 0,05 USD.
