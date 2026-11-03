# Plantilla de informe del piloto few-shot

Se rellena con la salida de [`medir.py`](medir.py) (JSON y tabla Markdown) y lo que dice [`metrica.md`](metrica.md). **Una celda sin medida dice «sin medir»**; no se inventan cifras ni se comparan con benchmarks como si fueran la misma tarea.
Este fichero es una plantilla: no trae cifras de ningún cliente. Las celdas `<…>` se rellenan; los ejemplos del repo son sintéticos.

```
python3 pilotos/medir.py --url $URL --casos evaluacion.jsonl --precio-hora <USD/h> --salida informe-AAAAMMDD   # CHISPA_CLAVE en el entorno si hay claves
```
Formato de `evaluacion.jsonl` (una línea por caso, **filas aparte de las de entrenamiento y de las que fijan τ**):
`{"id": "c1", "state": "<texto anonimizado>", "question": "<pregunta del entrenamiento>", "options": ["id1", "id2"], "gold": "id1"}`
(`kind` opcional, `choice` por defecto; `options` pueden ser `{"id","description"}`; `noul`: `gold` `true`/`false`).

---

# Informe del piloto Chispa few-shot: <tarea>
Fecha: <aaaa-mm-dd> · Periodo: <desde – hasta> · Autores: <nombres> · Versión (sha del repo): <sha> · Modelo: `<fichero.chispa>` `sha256:<…>`

## 1. Tarea
- Pregunta(s) y tipo (`choice`/`noul`/`score`): <…> · opciones: <ids>
- Capas del `.chispa` (`/healthz`): L0 <sí/no> · L1 <sí/no, potion> · L2/TORR <sí/no> · L0TF + L2c <sí/no>
- Servidor: <CPU, RAM, ORT sí/no, on-prem/nube> · τ: <de CALIB / de `-config`: valores>

## 2. Datos
| | n | por opción (mín – máx) | Fuente y periodo |
|---|---|---|---|
| Ejemplos de entrenamiento | <n> | <mín – máx> | <…> |
| Validación (τ) | <n> | <…> | <…> |
| Evaluación (`evaluacion.jsonl`) | <n> | <tabla de `por_opcion`> | <…> |
- Anonimización aplicada y revisada: <sí/no, cómo> · acuerdo entre etiquetadores (n = 50): <…>

## 3. Línea base
Se mide **la misma muestra de evaluación** con cada una; sin ella, «sin medir».
| Sistema | Exactitud | F1 macro | Latencia p99 | Coste / 1 000 | Fuente de la cifra |
|---|---|---|---|---|---|
| Lo que hace hoy el cliente (reglas, personas, otro modelo): <qué> | <…> | <…> | <…> | <…> | <…> |
| Codificador abierto ajustado con los **mismos** ejemplos: <modelo, hiperparámetros, versión> | <…> | <…> | <…> | <…> | <…> |
| Chispa (esta corrida) | <…> | <…> | <…> | <…> | `medir.py` |
Condiciones comparables: mismos ejemplos de entrenamiento, misma muestra de evaluación, mismo hardware; si cambia alguna, dígalo aquí: <…>

## 4. Métricas de Chispa (pegue la tabla de `medir.py`)
<tabla Markdown de `informe-AAAAMMDD.md`>
| Métrica de `metrica.md` | Valor | Umbral acordado | ¿Cumple? |
|---|---|---|---|
| Exactitud | <…> | <…> | <…> |
| F1 macro (escala = fallo) / (mejor respuesta) | <…> / <…> | <…> | <…> |
| Tasa de escalado | <…> | ≤ <…> | <…> |
| Cobertura a precisión <0,95> (umbral de confianza <…>, fijado en una parte y medido en otra) | <…> | <…> | <…> |

## 5. Latencia y coste
| | p50 | p95 | p99 | Notas |
|---|---|---|---|---|
| Cliente (extremo a extremo, ms) | <…> | <…> | <…> | <red, concurrencia, ¿cliente en otra máquina?> |
| Servidor (cascada, ms) | <…> | <…> | <…> | |
- Decisiones/s sostenidas (de [`server/cmd/carga`](../server/cmd/carga), cliente en otra máquina; el valor de `medir.py` es solo de esa corrida): <…>
- Coste por 1 000 decisiones = precio/h ÷ (decisiones/s × 3 600) × 1 000 = <…> USD; más revisión humana de lo escalado: <coste persona × tasa de escalado = …>

## 6. Por capa y escalados
| Capa | % de decisiones | Exactitud de la capa |
|---|---|---|
| L0 / L1 / L2 / L3 / escalar | <…> | <…> |
- **% escalado:** <…> · motivos (`escalados_por_motivo`): <baja_confianza / sin_opinion / …> · ¿escala lo difícil o lo fácil?: <…>

## 7. Errores típicos
- Las 3 confusiones más frecuentes (`confusiones`: real → predicho) y 5 ejemplos de cada una (anonimizados): <…>
- Opciones con < 30 casos en la evaluación (su F1 no es confiable): <…>
- Causa probable y qué se cambió (descripciones, ejemplos, τ) entre corridas, y su efecto: <…>

## 8. Decisión
- <**seguir** / **seguir con cambios** / **no seguir**> — razón en una frase, con la cifra que la sostiene: <…>
- Si sigue: qué datos más, qué capa (L1/L2c/torre) y qué τ; si no: qué línea base ganó y por cuánto: <…>
- Pendientes de producto que afectaron el piloto ([`README.md`](README.md#pendiente-de-producto)): <…>
- Datos: checklist de [`datos-y-consentimiento.md`](datos-y-consentimiento.md) <cerrado/abierto>; borrado de la muestra y de los `.chispa` entrenados: <fecha y constancia>
