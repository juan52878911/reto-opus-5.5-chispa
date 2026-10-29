# Qué es Chispa

Chispa es un clasificador tipado, de bajo coste y de propósito general. Tú mandas un texto y una pregunta con sus opciones.
Chispa devuelve una respuesta, sus probabilidades y la capa que contestó. Decide sobre esquemas que no ha visto, sin datos
o con pocos ejemplos.

Corre en CPU, sin GPU: en x86, en ARM y en el móvil. massive, clinc150, hatecheck, spam e injection son **benchmarks**
para medirlo. No son el objetivo del producto.

## Preguntas tipadas
Cada pregunta tiene un `kind`. Esquema de filas de datos: [`model/esquema.md`](../model/esquema.md).

| `kind` | Qué pregunta es | Opciones | Respuesta |
|---|---|---|---|
| `choice` | Elegir una opción | de 2 a 256, con `id` único | el `id` elegido |
| `noul` | Sí o no | opcionales; si van, solo `"false"` y `"true"` | `"true"` o `"false"` |
| `score` | Nivel ordinal | de 2 en adelante, ids `"1"` … `"K"` | `"1"` … `"K"` |

Las descripciones de las opciones importan: en zero-shot son lo único que Chispa sabe de tu tarea.
Contrato completo: [03-api.md](03-api.md). Fuente: [`server/README.md`](../server/README.md#contrato).

## Tres modos
Cada modo añade datos y calidad. Empieza por el primero.

| Modo | Qué necesitas | Cuándo usarlo | Comando |
|---|---|---|---|
| Zero-shot | El esquema, con descripciones | Probar una idea, o una tarea sin datos | `chispa train` sin `--ejemplos` |
| Few-shot | Pocos ejemplos por opción (k ≥ 1) | Ya tienes unos casos; sin `--conjunta` | `chispa train --ejemplos` |
| Con datos del cliente | ≥ 20 ejemplos por opción, un checkpoint de L2 | Quieres la mayor calidad y tienes datos etiquetados | `chispa train --conjunta` |

- Con menos de 10 ejemplos en alguna opción no se entrena L0 y L1 se calibra con todos.
- Con `--conjunta` y menos de 20 por opción, `chispa train` avisa por stderr y cae a few-shot.
- Cifras y límites de cada modo: [07-rendimiento-y-limites.md](07-rendimiento-y-limites.md). Paso a paso:
  [02-inicio-rapido.md](02-inicio-rapido.md).

## La cascada
Las capas se prueban en orden y cada una tiene un umbral τ: L0 (lineal sobre el texto, solo si hay ejemplos), L1 (embedding
estático contra «pregunta · opción · descripción»), L2 (e5 contra una torre por opción) y, si ninguna llega a su τ, escalar.
Una capa sin modelo o con error cuenta como confianza 0 y la cascada pasa a la siguiente.

```
L0 → L1 → L2 → escalar
```

| Capa | Qué es | Cuándo contesta |
|---|---|---|
| L0 | Clasificador lineal sobre el texto; con `L0TF`, TF-IDF de caracteres. Pide ejemplos | confianza top-1 ≥ τ |
| L1 | Embedding estático (potion) y coseno con «pregunta · opción · descripción». Sirve esquemas nuevos | confianza top-1 ≥ τ |
| L2 | e5-small (ONNX int8) con ranuras y una torre por opción. Con `CONJ` es L2c, con cabeza conjunta | confianza top-1 ≥ τ |
| escalar | Ninguna capa llegó a su τ | siempre |

- L1 no opina en `score`.
- Para un esquema que solo llega en la petición decide L1; si el `.chispa` trae `TORR` (y el servidor usa `-tags ort` y `-tok`), también L2 con torre al vuelo:
  [08-esquemas-nuevos.md](08-esquemas-nuevos.md).
- L2c y L0TF pertenecen al modo con datos del cliente y a la tarea con la que se entrenó el `.chispa`.
- L3 existe como capa de la cascada, pero es un stub sin opinión.

Detalle: [`server/README.md`](../server/README.md#cascada).

## Cuándo escala
La respuesta trae `escalate: true` cuando ninguna capa llegó a su τ.

- `answer` y `probs` son entonces la mejor pista vista. Quedan vacíos (`""`, `{}`) si ninguna capa opinó.
- `layer` es la última capa de la cascada.
- Qué hacer con un escalado lo decides tú: una persona, un modelo mayor o una regla.

El τ sale de `CALIB` (`tau_escalate`, y `tau_l2c` para L2c) o de la config del servidor (`-config`). Con `-config`, manda la config.
En zero-shot, `CALIB` queda sin calibrar con τ = 0,6. `chispa train --conjunta` fija `tau_l2c` con probabilidades fuera de
pliegue al 0,95 de precisión ([`sdk/python/README.md`](../sdk/python/README.md#chispa-train)).

El porcentaje que escala con tráfico normal está en [07-rendimiento-y-limites.md](07-rendimiento-y-limites.md#abstención).
