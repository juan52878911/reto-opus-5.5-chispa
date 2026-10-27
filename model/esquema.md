# Esquema de filas de Chispa (v1, congelado)

Lo cambia solo la sesión principal, como `arena/contracts/`. Lo consumen el conversor (T1.1), el arnés
`chispa eval` (T1.2), la tarea de herramientas (T1.4) y el corpus sintético (T1.3).

## Fila de datos (`*.jsonl`, una por línea, UTF-8)

| Campo | Tipo | Obligatorio | Qué es |
|---|---|---|---|
| `id` | str | sí | Único dentro del conjunto: `<fuente-corta>:<split>:<n>` |
| `tarea` | str | sí | `intencion`, `toxicidad`, `herramientas`, `whatsapp_comercio`, `pqrs`, `banca`, `fuera_de_ambito`, `inyeccion`, `nli`… |
| `tipo` | str | sí | `choice` (una de `opciones`), `noul` (`false`/`true`) o `score` (entero 1..K ordinal) |
| `pregunta` | str | sí | La pregunta en español, p. ej. «¿Qué quiere hacer el cliente?» |
| `texto` | str | sí | El mensaje que se clasifica |
| `opciones` | list[str] | sí | Ids de las opciones; en `noul`, `["false","true"]`; en `score`, `["1",…,"K"]` |
| `descripciones` | dict[str,str] | sí | Id → definición en español (zero-shot y torres de opción) |
| `etiqueta` | str | sí | Uno de `opciones`; `escalate` solo si está en `opciones` |
| `idioma` | str | sí | `es`, `es-CO`, `en`… del `texto` |
| `split` | str | sí | `train`, `dev` o `test` |
| `fuente` | str | sí | Dataset de origen y su split original |
| `licencia` | str | sí | SPDX o texto corto de la licencia de la fila |
| `uso_comercial` | bool | sí | `false` si la licencia es NC, ND o no está clara |
| `plantilla` | str | no | Id de plantilla o semilla, para repartir sin fugas |
| `blanda` | dict[str,float] | no | Distribución del maestro (T1.6) o de los anotadores humanos (listón, T1.5c) |
| `anotadores` | int | no | Cuántas personas etiquetaron la fila (listón humano); con él, `blanda` es la proporción de votos |
| `variedad` | str | no | Variedad del español del **texto** (co, mx, ar, es…), si la fuente la da |
| `paises_anotadores` | list[str] | no | País de residencia de cada anotador, si la fuente lo da |

Reglas:
- Una fila con `uso_comercial: false` **nunca** entra en `split: train` ni `dev`. Va solo a `test`,
  y solo si la licencia permite evaluar.
- Las filas de una misma `plantilla` caen todas en el mismo split.

## Predicciones (entrada de `chispa eval`)

`*.jsonl` con `{"id": str, "probs": {opcion: float}, "ms": float?}`. `probs` suma 1 (±1e-6) e
incluye `escalate` si el sistema puede escalar. Se puntúa contra las filas por `id`.
