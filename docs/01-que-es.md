# Qué es Chispa

Chispa responde preguntas sobre un texto. Tú mandas el texto y una lista de preguntas. Chispa devuelve, por pregunta,
una respuesta, sus probabilidades y la capa que contestó.

Corre en CPU. No necesita GPU para servir.

## Preguntas tipadas
Cada pregunta tiene un `kind`. Esquema de filas de datos: [`model/esquema.md`](../model/esquema.md).

| `kind` | Qué pregunta es | Opciones | Respuesta |
|---|---|---|---|
| `choice` | Elegir una opción | de 2 a 256, con `id` único | el `id` elegido |
| `noul` | Sí o no | opcionales; si van, solo `"false"` y `"true"` | `"true"` o `"false"` |
| `score` | Nivel ordinal | de 2 en adelante, ids `"1"` … `"K"` | `"1"` … `"K"` |

Contrato completo: [03-api.md](03-api.md). Fuente: [`server/README.md`](../server/README.md#contrato).

## La cascada
Las capas se prueban en orden. Cada una tiene un umbral τ.

```
L0 → L1 → L2c → escalar
```

| Capa | Qué es | Cuándo contesta |
|---|---|---|
| L0 | Clasificador lineal sobre el texto. Si el `.chispa` trae `L0TF`, es TF-IDF de caracteres con regresión logística. Si no, el Chispa lineal de kindling | confianza top-1 ≥ τ |
| L1 | Embedding estático (potion) y coseno con «pregunta · opción · descripción». Sin entrenar con tus datos | confianza top-1 ≥ τ |
| L2c | Codificador e5-small (ONNX int8) con ranuras y prototipos de tus ejemplos, más una cabeza que combina L0 y L2 | confianza top-1 ≥ τ |
| escalar | Ninguna capa llegó a su τ | siempre |

- L1 no opina en `score`.
- Una capa sin modelo, sin sección en el `.chispa` o con error cuenta como confianza 0. La cascada pasa a la siguiente.
- L2c se llama `L2` en `layer` y en la config. Sin la sección `CONJ`, esa capa es L2 sin cabeza conjunta.
- L3 existe como capa de la cascada, pero es un stub sin opinión.

Detalle: [`server/README.md`](../server/README.md#cascada).

## Cuándo escala
La respuesta trae `escalate: true` cuando ninguna capa llegó a su τ.

- `answer` y `probs` son entonces la mejor pista vista. Quedan vacíos (`""`, `{}`) si ninguna capa opinó.
- `layer` es la última capa de la cascada.
- Qué hacer con un escalado lo decides tú: una persona, un modelo mayor o una regla.

El τ sale de `CALIB` (`tau_escalate`, y `tau_l2c` para L2c) o de la config del servidor (`-config`). Con `-config`, manda la config.
`chispa train --conjunta` fija `tau_l2c` con probabilidades fuera de pliegue al 0,95 de precisión
([`sdk/python/README.md`](../sdk/python/README.md#chispa-train)).

El porcentaje que escala con tráfico normal está en [07-rendimiento-y-limites.md](07-rendimiento-y-limites.md#abstención).
