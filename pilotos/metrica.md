# Métrica del piloto

Se mide con una **muestra etiquetada por el cliente**. Las cifras de `docs/` son de benchmarks (inglés y español, no son del cliente): sirven de referencia, no de meta
([`docs/07-rendimiento-y-limites.md`](../docs/07-rendimiento-y-limites.md)). Lo que no está medido, dice «sin medir».

## Qué se mide
| Métrica | Definición | Referencia del repo (benchmarks) | En el cliente |
|---|---|---|---|
| Exactitud | respuestas correctas / mensajes de la muestra | sin medir (el repo mide macro-F1 y precisión de lo contestado) | por medir |
| F1 macro | media del F1 de cada opción: no se deja ganar por la clase más grande | zero-shot 0,455; few-shot (32 por clase) 0,654; con datos del cliente 0,814 (massive) y 0,887 (clinc150) — [`docs/07`](../docs/07-rendimiento-y-limites.md#por-modo) | por medir |
| Tasa de escalado | preguntas con `escalate: true` / total | objetivo ≤ 20 %; medido antes de T4.6b: 43–46 % en massive y clinc150 — [`abstencion-20261028/LEEME.md`](../server/deploy/resultados/abstencion-20261028/LEEME.md) | por medir |
| Cobertura a precisión objetivo | fracción que Chispa contesta (sin escalar) con una precisión ≥ objetivo (0,95) | 72–80 % en massive y clinc150 (cabeza conjunta) — [`docs/07`](../docs/07-rendimiento-y-limites.md#calibración-t24-y-excepciones-de-g2) | por medir |
| Latencia p99 | percentil 99 del tiempo por decisión | p99 de 9,6 ms (massive) y 11,3 ms (clinc150) en una c6a.xlarge con la cascada completa — [`docs/07`](../docs/07-rendimiento-y-limites.md#latencia); L1 por HTTP con el potion real: sin medir | por medir |
| Coste por 1.000 decisiones | (coste de infraestructura por hora) / (decisiones por hora) × 1.000 | sin medir (el repo no trae costes por decisión) | por medir |

## Tamaño de la muestra
- Mínimo sugerido: **300 mensajes**, y al menos 30 por opción cuando se pueda (sin medir si ese tamaño basta para su caso; con 108 filas el repo ya vio mucha varianza —
  [`docs/07`](../docs/07-rendimiento-y-limites.md#excepción-2-la-abstención)). Con menos de 30 en una opción, su F1 no es confiable.
- Las opciones raras (p. ej. `felicitacion`) pueden necesitar muestreo dirigido: dígalo en el informe.
- Doble etiquetado de 50 mensajes por dos personas para saber qué tan de acuerdo están; si ellas no coinciden, el esquema es ambiguo y ningún modelo lo arregla.

## Cómo se mide
Hay herramientas en el repo, escritas para benchmarks. Lo que se puede usar y sus límites:

**0. Atajo: `chispa evaluar`** (SDK de Python, sin dependencias nuevas). Para `choice`, `noul` y `score` hace los pasos 1 a 4 de una vez, desde un CSV/JSONL con `texto` y `etiqueta` (noul: `true`/`false`; score: `1`…`K`) y el mismo esquema de `chispa train`:
```
python -m chispa evaluar --url http://127.0.0.1:8090 --esquema pqrs.json --datos muestra.csv --precision-objetivo 0.95 --salida informe
```
Escribe `informe.md` (con la tabla de resultados de la plantilla) e `informe.json` (`--filas` añade cada predicción): exactitud, F1 macro (escala = fallo y mejor respuesta), matriz de confusión, escalado, cobertura y precisión de lo aceptado, distribución por capa, p50/p99 del cliente (y del servidor), MAE en score y, con `--precision-objetivo`, el umbral de confianza único que da esa precisión y su cobertura. Cada fila es una petición (`/v1/decide` lleva un solo `state` por petición); `--concurrencia` las reparte. Un error tipado del esquema (p. ej. `invalid_options`) en la primera petición detiene la medición; los de fila (`state_too_long`) y los de red se cuentan como errores. No mide el coste por 1.000 (paso 5). El umbral sale de la misma muestra que se mide: para fijarlo y medirlo en partes distintas, corra dos veces con dos ficheros. Probado solo con un servidor falso (`sdk/python/tests/test_evaluar.py`): sin correr contra `chispa-server` ni datos del cliente.

**1. Preparar la muestra** en el formato de [`server/deploy/aws/e2e_util.py`](../server/deploy/aws/e2e_util.py): un JSONL por fila, con
`id`, `texto`, `etiqueta`, `pregunta`, `opciones` (lista de ids) y `descripciones` (mapa id → descripción). Las filas de la muestra deben salir de la anonimización
([`datos-y-consentimiento.md`](datos-y-consentimiento.md)). Lo prepara el responsable técnico a mano o con un script propio: **no hay un conversor listo** (pendiente de producto).

**2. Correr las decisiones por el servidor** (una pregunta por petición, en serie; guarda `probs`, `layer`, `escalate`, `ms` y `cliente_ms` por fila):
```
python3 -I server/deploy/aws/e2e_util.py cliente --url http://127.0.0.1:8090 --test muestra.jsonl --salida pred.jsonl
```
Limitación (se salva con `chispa evaluar`): este cliente manda siempre `kind: "choice"`, así que mide solo preguntas `choice`. Para `noul` y `score` no hay medición lista (pendiente de producto);
una persona del equipo puede repetir con el cliente de Python ([`sdk/python/README.md`](../sdk/python/README.md)) y el mismo formato de salida.

**3. Calcular la métrica** con [`server/deploy/abstencion/medir.py`](../server/deploy/abstencion/medir.py) (solo biblioteca estándar):
```
python3 -I server/deploy/abstencion/medir.py --pred pqrs=pred.jsonl --verdad pqrs=muestra.jsonl --salida informe-pilotos
```
Entrega por tarea (`informe-pilotos/<tarea>.md` y `abstencion.json`): fracción que escala, precisión y macro-F1 sobre lo contestado, macro-F1 contando lo escalado como fallo,
macro-F1 de la mejor respuesta de todas, y una tabla τ → (abstención, precisión) cada 5 % de abstención. De ahí salen:
- **F1 macro:** «macro-F1 con lo escalado como fallo» (la cifra que ve la operación) y «con la mejor respuesta de todas» (la calidad del modelo sin escalar).
- **Tasa de escalado:** «escala».
- **Cobertura a una precisión objetivo:** en la tabla τ → (abstención, precisión), 1 − la abstención de la fila cuya precisión llega al objetivo (p. ej. 0,95).

`medir.py` lee `id` y `etiqueta` de la muestra y `probs`, `layer`, `escalate` de `pred.jsonl`. La **exactitud** no la imprime como tal (da precisión de lo contestado y
macro-F1): se calcula con la mejor respuesta de `pred.jsonl` frente a `etiqueta`. `medir.py` se corrió aquí solo con 2 filas sintéticas (corre y da la tabla); sobre datos del cliente: sin verificar. `e2e_util.py cliente` no se corrió: no hay servidor en este nodo.
La muestra de la que sale el τ no debe ser la que se usa para evaluar: fije τ en una parte y mida en la otra.

**4. Latencia p99.** `pred.jsonl` trae `ms` (cascada, dentro del servidor) y `cliente_ms` (extremo a extremo). Percentil 99 sin dependencias:
```
python3 -I -c "import json,sys;v=sorted(json.loads(l)['cliente_ms'] for l in open('pred.jsonl'));print(v[int(0.99*(len(v)-1))])"
```
Y la carga del servidor con [`server/cmd/carga`](../server/cmd/carga) (`-url`, `-c`, `-d`, `-lote`, `-textos`, `-csv`, `-capas`), que da decisiones/s, p50 y p99.
Cuidado: `carga` manda un esquema fijo de 4 opciones sin descripciones, no el del cliente, así que sirve para el rendimiento del servidor, no para la calidad. El cliente de carga debe correr en otra máquina:
el repo anota ±30 % de ruido cuando comparten máquina ([`docs/07`](../docs/07-rendimiento-y-limites.md#rendimiento-del-servidor)). Compile `carga` con Go desde `server/` (`go build ./cmd/carga`).

**5. Coste por 1.000 decisiones.** Con las decisiones/s de `carga` (sostenidas, con el hardware del cliente):
`coste_1000 = (precio de la máquina por hora) / (decisiones/s × 3600) × 1000`. El precio lo da el cliente (nube o costo interno de la máquina); Chispa no tiene licencia por decisión en el repo: **el precio comercial del producto no está en el repo (sin medir)**.
Si hay revisión humana de lo escalado, súmela aparte: coste de una persona × tasa de escalado.

## Reglas para leer los resultados
- Lo escalado va a una persona: la tasa de escalado y la precisión de lo contestado se leen **juntas**. Una tasa de escalado baja con precisión baja es peor que una alta con precisión alta.
- Reporte siempre cuántos mensajes hay por opción y los intervalos o la variación si se repite la muestra.
- El τ de zero-shot (0,6) no está calibrado; el ECE en zero-shot: sin medir. No hable de «probabilidad» como si fuera real, hable de «puntaje».
- No compare con los benchmarks como si fueran la misma tarea.

## Plantilla de informe final
```
# Informe final del piloto Chispa: <cliente>
Fecha: <aaaa-mm-dd> · Periodo: <semana 1 – semana 4> · Autores: <nombres>

## 1. Alcance
- Esquema(s) probados: <pqrs_tipo / soporte_categoria / …> · tipo: <choice/noul/score>
- Modos probados: <zero-shot / few-shot k=? / con datos del cliente>
- Versión de Chispa (sha del repo): <sha> · potion: <fichero> · checkpoint de L2: <sí/no>
- Servidor: <on-prem/nube, CPU, RAM, versión de ORT o «sin ORT»>

## 2. Muestra
- Fuente y periodo: ... · n total: ... · por opción: <tabla> · acuerdo entre etiquetadores (n = 50): ...
- Anonimización aplicada y revisada: <sí/no, cómo>

## 3. Resultados (muestra de evaluación, aparte de los ejemplos)
| Modo | Exactitud | F1 macro (escala = fallo) | F1 macro (mejor respuesta) | Escalado | Cobertura a 0,95 | p99 ms | Coste / 1.000 |
|---|---|---|---|---|---|---|---|
| zero-shot | | | | | | | |
| few-shot (k=?) | | | | | | | |
| con datos del cliente | | | | | | | |
Las celdas sin medida dicen «sin medir».

## 4. Errores
- Las 3 confusiones más frecuentes (opción real → opción predicha) y 5 ejemplos de cada una (anonimizados).
- Descripciones que se cambiaron entre semanas y su efecto.

## 5. Criterios acordados en la semana 0
| Criterio | Umbral | Resultado | ¿Cumple? |
|---|---|---|---|

## 6. Pendientes de producto que afectaron el piloto
<lista del README del kit, con los que se tocaron>

## 7. Recomendación
<seguir / seguir con cambios / no seguir>, el modo recomendado y los siguientes pasos (qué datos más, qué cambios en el esquema).

## 8. Datos y consentimiento
- Checklist de datos y consentimiento: <cerrado / abierto>; borrado de datos al terminar: <fecha y constancia>
```
