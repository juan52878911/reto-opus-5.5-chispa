# SDK de Python de Chispa

Paquete `chispa` (`pyproject.toml`, sin dependencias obligatorias), con la CLI `chispa`.

## Instalación
```
pip wheel . --no-deps --no-build-isolation -w dist/     # o: python -m build --wheel
pip install dist/chispa-0.1.0-py3-none-any.whl          # sin el repositorio al lado
```
- **Dentro del wheel**: cliente de `/v1/decide`, `chispa train` (zero-shot y few-shot), la CLI, y el entrenador de Go
  (`entrenador_go/`) con las fuentes de `format/chispa3` y `runtime/l1` copiadas por `setup.py` al construir desde el repositorio
  (`entrenador_go/vendor/`, no versionado). Con Go ≥ 1.27 en el PATH, `chispa train` entrena L0 sin el repositorio; hace falta además
  `github.com/juan52878911/kindling v0.17.0` en la caché de módulos de Go o acceso por red (`GOPROXY`; por defecto está en `off`).
  Sin Go, el fichero sale sin L0 y lo avisa.
- **Extras**: `chispa[yaml]` (esquemas `.yaml`), `chispa[torre]` (`--torre`: numpy, onnx, onnxruntime),
  `chispa[l2]` (torch, transformers, scikit-learn: `--ckpt` y `--conjunta`).
- **Fuera del wheel**: `model/l2` (checkpoint, calibrar, exportar). `--ckpt` y `--conjunta` necesitan el repositorio (`--repo` o
  `CHISPA_REPO`) y fallan con ese mensaje si no está. Licencia: Apache-2.0 (ver `LICENSE` y `NOTICE`).

## Tests
Desde `sdk/python`, cualquiera de los dos comandos carga y corre todo (los tests se importan como `tests.<módulo>`):
`python -m unittest` · `python -m unittest discover -s tests`

## Modos de `chispa train` y ejemplos
Ver `chispa train --help`. Con el esquema de ferretería de `docs/02-inicio-rapido.md`, en `ejemplos/`:
- `ejemplos/zero_shot.py --l1 potion.chispa-l1`: sin ejemplos.
- `ejemplos/few_shot.py --l1 potion.chispa-l1`: 5 ejemplos por opción (`ejemplos.csv`).
- `ejemplos/cliente.py [--url …]`: pregunta a un `chispa-server`.
`tests/test_ejemplos.py` los ejecuta (L1 falso y servidor falso).

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

## `chispa evaluar`
Mide un servidor con una muestra etiquetada del cliente (choice, noul o score); métrica y plantilla en `pilotos/metrica.md`.
```
python -m chispa evaluar --url http://127.0.0.1:8090 --esquema esquema.json --datos muestra.csv [--precision-objetivo 0.95] [--concurrencia 4] [--salida informe] [--filas]
```
`--datos`: CSV (con cabecera) o JSONL con `texto|text` y `etiqueta|label` (noul: `true`/`false`; score: `1`…`K`). Con `--salida informe` escribe `informe.md` e `informe.json`; sin ella imprime el markdown.
Da exactitud, F1 macro (escala = fallo y mejor respuesta), matriz de confusión, tasa de escalado, cobertura y precisión de lo aceptado, capas, p50/p99, MAE (score) y la cobertura al umbral de confianza que alcanza la precisión objetivo.
Cada fila es una petición, porque `/v1/decide` lleva un solo `state` por petición. Probado con un servidor falso (`tests/test_evaluar.py`).

### Batería de regresión (la puerta de un cambio de modelo)
```
python -m chispa evaluar --bateria ejemplos/bateria.json --modelo m.chispa --linea-base base.json [--robustez] [--salida informe]
python -m chispa evaluar --bateria ejemplos/bateria.json --url http://127.0.0.1:8090 --guardar-linea-base base.json
```
Mide varios conjuntos (filas de `model/esquema.md` o JevBench crudo) y da exactitud, F1 macro, ECE (10 cubos), cobertura a precisión 0,95, % escalado y p50/p99 por conjunto, tipo, grupo y en global. Con `--linea-base` sale con **1** si una métrica empeora más que su umbral (`--umbrales` o `umbrales` del manifiesto), con **2** si el manifiesto, los datos o el servidor están mal. `--modelo` arranca `chispa-server` (`--servidor`, `CHISPA_SERVER` o el PATH) en un puerto libre. `--robustez` añade la estabilidad con `chispa.variantes` si existe. Manifiesto de ejemplo con rutas por variable de entorno en `ejemplos/bateria.json`; detalle en `docs/10-bateria.md`. Probado con un servidor falso (`tests/test_bateria.py`).

## `chispa train`
```
python -m chispa train --ejemplos ej.csv --esquema esquema.yaml --salida m.chispa [--l1 potion.chispa-l1] [--ckpt DIR | --l2 l2.chispa] [--conjunta]
```
- Ejemplos: CSV (con cabecera) o JSONL, columnas `texto|text` y `etiqueta|label`.
- Esquema (YAML/JSON): `id`, `pregunta`, `tipo` (`choice|noul|score|multi`), `opciones` (mapa id → descripción, lista de ids o de `{id, descripcion}`),
  y opcionalmente `licencias` y `dorado` (van a META). Un `.chispa` por pregunta (el servidor elige L0 por el conjunto de etiquetas).
- Salida (`chispa.entrenar(...)` hace lo mismo y devuelve el informe):
  - **META**, **L0**: lineal de kindling sobre los ejemplos; 80 % entrena y 20 % valida (partición por hash; fija el τ del propio L0).
  - **L1** (con `--l1`): el potion de `runtime/l1/exportar.py` tal cual (155 MB por fichero); en `CALIB` van T (choice) o a, b, θ (noul)
    ajustados en la validación con exactamente el texto «pregunta · opción · descripción» que usa el servidor, y `tau_escalate`
    = el τ más bajo que da 0,95 de precisión en la validación (mínimo 10 ejemplos; si no se alcanza, 1,0 = L1 siempre escala).
  - **L2 y ESQUEMAS**: solo con `--ckpt` (corre `model.l2.calibrar` y `model.l2.exportar` sobre los ejemplos) o `--l2` (un `.chispa`
    ya exportado, de donde se copian L2 y ESQUEMAS). **No probado con un checkpoint real: no hay ninguno en la microVM**; sin ellos se avisa
    por stderr y el informe lo lista en `omitidas`. Los prototipos de T2.1b son parte de L2 y no están en el formato: no se usan.
  - **Perfiles de L2** (`--perfil`, solo con `--ckpt`): `servidor` (defecto) exporta con `model.l2.exportar --perfil servidor`: consulta fp32,
    sin cuantizar y **sin poda de vocabulario** (los 250.037 tokens), para que un esquema nuevo no caiga en `<unk>`. `movil` usa `--perfil movil`:
    fp16, vocabulario podado **ampliado** (`--vocab-ampliar`) con los textos del esquema (≈ 89 MB); `movil-int8` es el int8 dinámico de antes
    (más pequeño, top-1 ≈ 0,87). En móvil, los esquemas que no estaban en el entrenamiento rinden menos (≈ 0,90 relativo, por `<unk>`) y escalan
    más. El esquema nunca poda por sí solo. Con `--l2` el perfil ya lo fijó quien exportó. Con `--ckpt`, de `l2.chispa` se copian L2 y ESQUEMAS
    y su CALIB entera (todos los tipos, `scoreK#j`, `multi_l2@…`, `tau_escalate`→`tau_escalate_l2`, `tau_l2c`) a `tipos_l2`/`tau_escalate_l2`/`tau_l2c`,
    igual que con `--l2`; se avisa solo si ese `l2.chispa` no trae CALIB. La CALIB de L1 del `.chispa` final no se toca.
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

### Multietiqueta (`tipo: multi`)
Cada opción es un sí/no independiente; un ejemplo puede llevar varias etiquetas separadas por `|` en el CSV (`texto,etiqueta` → `Me cobraron dos veces y nadie contesta,cobro|atencion`), una lista en el JSONL, o ninguna (celda vacía). Los ids de opción no pueden llevar `|`.
`chispa train` con ejemplos escribe SOPL1 (k y media de los ejemplos activos de cada opción) y ajusta en `CALIB` la sigmoide `multi@<hash>` (a, b) y un θ por opción (`multi@<hash>#<id>`; el que maximiza F1, si hay ≥ 3 positivos y ≥ 3 negativos; las claves sin `@` son del formato antiguo); necesita `--l1` y Go para embeber. **No entrena L0** (el lineal es multiclase: en `multi` no opina) ni admite `--conjunta`. La calibración usa los prototipos de la descripción, sin encogimiento. SOPL1 se escribe, pero en multi el servidor la ignora por defecto (train quita `l1_lambda_calib` de CALIB, porque se calibró sin encogimiento): solo actúa si el operador fija `l1_shrinkage_lambda`, y con λ finito las probabilidades cambian. Con `multi_l2` (hace falta el tokenizador y la sesión de L2) se calibra también L2 (`multi_l2@<hash>`); sin él L2 no opina en multi. `chispa evaluar` mide `multi`.
`Multi("t", "¿Qué temas toca?", [("cobro", "habla de un cobro"), "atencion"])` crea la pregunta; `Resultado.answers` trae las activas.

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

## Licencia

Apache-2.0 (ver `LICENSE`). Las atribuciones de terceros están en `NOTICE`. Los datasets con SA, NC o con términos pendientes
(XNLI, clima, datos.gov.co, SIB-200, etiquetas de ALIA, salidas de Haiku) no se redistribuyen y solo se usan como test.
