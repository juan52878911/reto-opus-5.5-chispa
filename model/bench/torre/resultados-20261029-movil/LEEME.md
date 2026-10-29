# P2b, variantes del perfil móvil con el checkpoint real (c6a.2xlarge, `248e763`, 2026-10-29): ninguna cumple

Objetivo: top-1 ≥ 0,93 con consulta y torre ≤ 60 MB cada una. Detalle en `informe.md`.

| variante | MB consulta / torre | top-1 vocabulario completo | top-1 poda ampliada | MB con poda |
|---|---|---|---|---|
| int8 dinámico | 121 / 120 | 0,86 | 0,87 | 50 / 49 |
| int8 estático solo en FFN | 143 / 141 | 0,67 | 0,68 | 72 / 71 |
| fp16 | 237 / 236 | **1,00** | 0,90 | 93 / 92 |
| fp32 | 473 / 472 | **1,00** | 0,90 | 184 / 182 |

- **El int8 no sirve con este checkpoint.**
  - El dinámico se queda en 0,86–0,87.
  - El estático en FFN sale peor, 0,67. Además cuantiza los embeddings y la calibración solo usa massive-es.
- **fp16 da paridad exacta**, pero pesa 236 MB por modelo con el vocabulario completo.
- **Posible bug de la poda.** Con la poda ampliada, fp32 y fp16 bajan a coseno 0,931 y top-1 0,90, aunque los `<unk>` en
  la comprobación son solo 0,08 % (de 1,60 %). Si la poda solo cambiara los `<unk>`, fp32 con poda tendría que dar casi
  1,00. Lo más probable es un fallo en la tabla id → id podado con la ampliación, o en los textos de la torre, que aquí
  tienen más `<unk>` que la comprobación. **Hay que investigarlo antes de elegir.** Si se arregla, fp16 con poda (~93 MB)
  o int8 con poda (~50 MB, pero top-1 0,87) son los candidatos.
- **Coste:** c6a.2xlarge de 8 min, ≈ 0,03 USD.
