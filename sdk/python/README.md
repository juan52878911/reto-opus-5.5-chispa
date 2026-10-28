# SDK de Python de Chispa (T4.3)

Paquete `chispa` (`pyproject.toml`, sin dependencias; PyYAML opcional para esquemas `.yaml`).

## Cliente de `/v1/decide`
```python
from chispa import Chispa, Choice, Noul, Score
c = Chispa("http://127.0.0.1:8090")          # reintentos=3, espera exponencial, nonce automático
rs = c.decidir("necesito ayuda ya", [
    Choice("u1", "¿Qué tan urgente es?", [("alta", "Requiere atención inmediata"), "baja"]),
    Noul("s1", "¿Es spam?"), Score("p1", "¿Qué tan molesto está?", 5)])
rs[0].answer, rs[0].probs, rs[0].layer, rs[0].escalate   # Resultado; rs[1].verdadero; rs[2].nivel
```
Errores: `ErrorSolicitud` (400/405/413, con `status` y el `{"error"}` del contrato; no se reintenta), `ErrorTransporte`
(red, 5xx o 429 tras los reintentos). El nonce se fija antes del primer intento, así que un reintento es idempotente.
Probado contra el JSON de `server/README.md` con un servidor falso (`tests/test_cliente.py`) y a mano contra `chispa-server`.

## `chispa train`
```
python -m chispa train --ejemplos ej.csv --esquema esquema.yaml --salida m.chispa [--l1 potion.chispa-l1] [--ckpt DIR | --l2 l2.chispa] [--conjunta]
```
- Ejemplos: CSV (con cabecera) o JSONL, columnas `texto|text` y `etiqueta|label`.
- Esquema (YAML/JSON): `id`, `pregunta`, `tipo` (`choice|noul|score`), `opciones` (mapa id → descripción, lista de ids o de `{id, descripcion}`),
  y opcionalmente `licencias` y `dorado` (van a META). Un `.chispa` por pregunta (el servidor elige L0 por el conjunto de etiquetas).
- Salida (`chispa.entrenar(...)` hace lo mismo y devuelve el informe):
  - **META**, **L0**: lineal de kindling sobre los ejemplos; 80 % entrena y 20 % valida (partición por hash; fija el τ del propio L0).
  - **L1** (con `--l1`): el potion de `runtime/l1/exportar.py` tal cual (155 MB por fichero); en `CALIB` van T (choice) o a, b, θ (noul)
    ajustados en la validación con exactamente el texto «pregunta · opción · descripción» que usa el servidor, y `tau_escalate`
    = el τ más bajo que da 0,95 de precisión en la validación (mínimo 10 ejemplos; si no se alcanza, 1,0 = L1 siempre escala).
  - **L2 y ESQUEMAS**: solo con `--ckpt` (corre `model.l2.calibrar` y `model.l2.exportar` sobre los ejemplos) o `--l2` (un `.chispa`
    ya exportado, de donde se copian L2 y ESQUEMAS). **No probado con un checkpoint real: no hay ninguno en la microVM**; sin ellos se avisa
    por stderr y el informe lo lista en `omitidas`. Los prototipos de T2.1b son parte de L2 y no están en el formato: no se usan.
- **`--conjunta`** (T2.6b): añade `CONJ`, la cabeza lineal L0 + L2 por tarea. Necesita `--ckpt` (el modelo de L2 y e5 dan las
  características; el ONNX no basta) y L2, de `--l2` o de `--ckpt`; sólo `choice`. Importa `model/l2/conjunta.py` (no lo copia):
  L0 fuera de pliegue (5 pliegues; es el `correr_l0` de sklearn de las líneas base), L2 con el soporte de 32 por clase y los
  prototipos sin la propia fila; λ por validación cruzada en train; luego los prototipos con todo el soporte, en int8 con
  escala. El informe trae `conjunta` (λ, NLL de CV, bytes, T, β). Sin `--conjunta` el fichero sale igual que antes.
  Cuesta tiempo de entrenamiento (L0 ×5 + L2 sobre todos los ejemplos con e5; ver `informe["conjunta"]["s"]`) y, al servir,
  ≈ 0,07 ms por clase de simproto más µs de cabeza (`server/README.md`), frente a los ~30 ms de L2.
  **L0TF** (T4.5c): `--conjunta` también escribe `L0TF`, el L0 TF-IDF de caracteres de `model/lineas_base/correr.py` (`chispa/l0tf.py`
  ejecuta ese `correr_l0` y recoge el vectorizador y la regresión que ajusta: no hay copia de los hiperparámetros) entrenado con todo
  el train; la cabeza se ajusta con sus probabilidades fuera de pliegue. Coeficientes en f32 (`--l0tf-f16` los pasa a f16: |Δp| ~3e-4);
  si la tabla pasa de `--l0tf-max-mb` (48), se poda el vocabulario por frecuencia (`max_features`), también en los pliegues.
  clinc150: 34 976 n-gramas × 151 clases = 21 MB en f32, sin podar. El servidor usa L0TF en vez del L0 de Chispa si el fichero lo trae.
  **Ojo (anterior a T4.5c)**: la cabeza se ajusta con las probabilidades de L0 de sklearn, y el servidor le da las del L0 de kindling (otro modelo,
  mismas clases): están sin comparar. Tampoco se probó con un checkpoint real (en los tests, un `ModeloL2` aleatorio y e5 falso).
- L0 y la calibración los hace `entrenador_go/` (copiado a un directorio temporal con `replace` hacia el repo; hace falta Go y el repo, o
  `CHISPA_REPO`; offline: `GOFLAGS=-mod=mod GOPROXY=off`). **Sin Go** `chispa train` escribe META + L1 + CALIB por defecto, sin L0, y lo dice
  (`formato.py` es un escritor mínimo; el cargador de Go lo acepta, probado en `tests/test_train.py`).

## Punta a punta: intención del sondeo, 50 por clase
`python sdk/python/e2e/sondeo_intencion.py [--l1 /tmp/potion.chispa-l1]`. El sondeo solo trae 32 por clase: se completan hasta 50 con MASSIVE es
(train, de `~/hf`, sin texto del test). 13 clases × 50 = 650 ejemplos → `chispa train` → `.chispa` → `chispa3.Abrir` + `Verificar` →
test del sondeo (390 filas, 30 por clase). Medido el 2026-10-28 en la microVM (4 vCPU Xeon 3,3 GHz; un i3 será más lento; 1 hilo de entrenamiento):

| | reloj de `chispa train` | tamaño | L0 solo (argmax) | L0 confiado (p ≥ 0,8) | L1 solo | cascada L0→L1 |
|---|---|---|---|---|---|---|
| META+L0+CALIB | 1,0 s | 0,09 MB | **0,821** | cubre 66 %, acierta 97 % | – | – |
| META+L0+L1+CALIB | 3,5 s (3,5 / 3,5 / 3,6 en tres corridas) | 154,9 MB | 0,821 | cubre 66 %, acierta 97 % | 0,672 | resuelve 81 %, acierta 94 %; con lo escalado como fallo, 0,762 |

Criterio (≤ 5 min con 50 por clase): se cumple con holgura (≈ 3,5 s). Va con la caché de compilación de Go caliente (`go build` del entrenador
está incluido en `tiempos_s.go_build`; con la caché fría tardaría más, no medido). La cascada se evalúa como el servidor (τ de L0 = 0,8 de su
config; τ de L1 = `tau_escalate`), pero en Go aparte, no a través de HTTP; `chispa-server --modelo` cargó el fichero y respondió bien a mano
con el cliente de este SDK (4 frases).

## Sin verificar / límites
- L2, ESQUEMAS y los prototipos: nada medido (sin checkpoint). La hipótesis «el few-shot cabe en 5 min con prototipos de L2» **no** se ha probado;
  lo medido es la variante L0 + L1.
- Una corrida por configuración; una sola tarea (intención). El test tiene 390 filas: ±2 puntos de ruido.
- `score`: L0 entrena (etiquetas "1"…"K") pero L1 no calibra (el servidor no lo usa).
- Los nombres de campo del cliente son los del contrato propio de `server/README.md`; `/v1/systemone` de Jev no se ha visto.

## Pruebas
`python -m unittest discover -s sdk/python -t sdk/python` · `cd sdk/python/chispa/entrenador_go && GOFLAGS=-mod=mod GOPROXY=off go test ./...`
