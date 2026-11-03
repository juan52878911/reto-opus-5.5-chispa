# SDK

| SDK | Qué hace | Estado | README |
|---|---|---|---|
| Python | cliente de `/v1/decide` y `chispa train`; empaquetable como wheel, con extras | probado con tests y a mano contra `chispa-server` | [`sdk/python`](../sdk/python/README.md) |
| JavaScript | cliente de `/v1/decide` y `/healthz` para Node ≥ 20 y navegador: sin dependencias, ESM, tipos a mano, validación en bytes, reintento con el mismo nonce | probado con `node --test` contra un servidor falso; sin probar contra `chispa-server` real | [`sdk/js`](../sdk/js/README.md) |
| Go | cliente de `/v1/decide` y `/healthz` (`github.com/juan52878911/chispa/sdk/go`): solo biblioteca estándar, validación en bytes, nonce estable, reintentos como Python y JS, `api_key` opcional | `go test -race` con `httptest`; sin probar contra `chispa-server` real | [`sdk/go`](../sdk/go/README.md) |
| Android | cascada en el dispositivo (Kotlin), con proveedores de ORT, torre al vuelo y demo «Medir» | se compila en AWS; sin tokenizador, solo L0 y L1 | [`sdk/android`](../sdk/android/README.md) |
| iOS | cascada en el dispositivo (Swift), con proveedores de ORT y torre al vuelo | **escrito sin compilar**: no se compila en la VM ni en el Mac de Juan, solo en una mac2 o un runner macOS | [`sdk/ios`](../sdk/ios/README.md) |
| WASM | L1 en el navegador; demo con formulario de esquema nuevo y arnés de latencia | demo con L1 recortado | [`demo/wasm`](../demo/wasm/README.md) |

Los móviles y WASM no hablan con el servidor. Abren el `.chispa` y deciden en el dispositivo.

## Python
Sin dependencias obligatorias. Python ≥ 3.9. Se empaqueta como wheel (versión 0.1.0, licencia Apache-2.0 de Juan Bedoya, ver `LICENSE` y `NOTICE`):

```
pip wheel ./sdk/python --no-deps --no-build-isolation -w dist/
pip install dist/chispa-0.1.0-py3-none-any.whl          # sin el repositorio al lado
pip install "dist/chispa-0.1.0-py3-none-any.whl[yaml]"  # o [torre] o [l2]
```

| Extra | Instala | Para qué |
|---|---|---|
| `yaml` | pyyaml | esquemas `.yaml` (los `.json` no lo piden) |
| `torre` | numpy, onnx, onnxruntime | `chispa train --torre`: valida el ONNX y añade `TORR` |
| `l2` | numpy, torch, transformers, scikit-learn, pyyaml | `--ckpt` y `--conjunta`; además necesitan el repositorio (`--repo` o `CHISPA_REPO`): `model/l2` no va en el wheel |

El wheel lleva el cliente, `chispa train` (zero-shot, few-shot, `--torre`, `--shrinkage-lambda`), la CLI y el entrenador de Go con las fuentes de
`format/chispa3` y `runtime/l1` copiadas al construir desde el repositorio. Con Go ≥ 1.27 en el PATH entrena L0 sin el repositorio; sin Go, el
`.chispa` sale sin L0 y lo avisa. Hace falta `kindling v0.17.0` en la caché de Go o red (`GOPROXY` está en `off` por defecto). El wheel se construyó en este nodo (copiando `sdk/python`, `format` y `runtime` a un directorio temporal) y trae las fuentes de Go en `entrenador_go/vendor/`; no se instaló en
un entorno limpio ni se entrenó con él (no hay Go aquí): sin verificar. Ejemplos ejecutables en [`sdk/python/ejemplos/`](../sdk/python/ejemplos) (`zero_shot.py`, `few_shot.py`, `cliente.py`).

```python
from chispa import Chispa, Choice, Noul, Score
c = Chispa("http://127.0.0.1:8090")
rs = c.decidir("necesito ayuda ya", [
    Choice("u1", "¿Qué tan urgente es?", [("alta", "Requiere atención inmediata"), "baja"]),
    Noul("s1", "¿Es spam?"), Score("p1", "¿Qué tan molesto está?", 5)])
rs[0].answer, rs[0].probs, rs[0].layer, rs[0].escalate
```

- El esquema viaja en cada llamada a `decidir`: la pregunta, los ids y las descripciones de las opciones. Escribe las descripciones
  con cuidado, porque en zero-shot son lo único que Chispa ve de la tarea. Ejemplo: [02-inicio-rapido.md](02-inicio-rapido.md#desde-python).
- Reintentos (política vigente, definida en `cliente.py`; el cliente JS debe igualarla): 3 por defecto, con espera exponencial
  (`espera·2^(n-1)`, y al menos `Retry-After` si lo hay, tope 30 s). Se reintentan solo los errores de red y el 503 que no sea
  `timeout`. No se reintentan: el timeout propio del cliente, el 503 `timeout` del servidor, el 504, ni 429/500/502 ni ningún otro estado.
- Clave de API: `Chispa(url, api_key="…")` y `new ChispaCliente({ apiKey })` envían `Authorization: Bearer <clave>` solo a `/v1/decide` (si el servidor tiene
  `api_keys`, [06-despliegue.md](06-despliegue.md#claves-de-api)). **401** (`unauthorized`) y **429** (`rate_limited`) no se reintentan (arriba): lanzan
  `ErrorSolicitud` / `ErrorChispa` al instante. En un 429 el `Retry-After` del servidor (segundos, tope 30 s) queda en `ErrorSolicitud.retry_after` (Python, segundos)
  y `ErrorChispa.retryAfterMs` (JS, ms); `None`/`undefined` si no vino. Quien quiera esperar y repetir lo hace con el mismo `nonce`.
- Timeout: 35 s por defecto, mayor que el `-timeout` del servidor (30 s). Si lo baja, manténgalo por encima del `-timeout` del servidor;
  si no, el cliente corta antes, el servidor cancela sin guardar nada bajo el nonce y la petición nunca termina.
- El nonce se fija antes del primer intento (un nonce vacío cuenta como ausente y se genera uno), así que reintentar es idempotente.
- `ErrorSolicitud`: cualquier respuesta HTTP de error no reintentable (400, 405, 413, 429, 500, 502, 504, 503 `timeout`…).
- `ErrorTransporte`: red o 503 tras agotar los reintentos, timeout propio o cuerpo ilegible.
- Una pregunta suelta desde la consola: `python -m chispa decide --url … --estado … --pregunta … --opciones a b`
  ([`cli.py`](../sdk/python/chispa/cli.py)).
- Entrenar (zero-shot, few-shot, `--torre`, `--shrinkage-lambda` y `--conjunta`): [02-inicio-rapido.md](02-inicio-rapido.md).

Los nombres de campo son los del contrato de [03-api.md](03-api.md). `/v1/systemone` de Jev no se ha visto
([`server/README.md`](../server/README.md#relación-con-v1systemone-de-jev--suposición-sin-verificar)).

> **Modelos con `tipos_l2` y apps ya publicadas:** un `.chispa` con `tipos_l2` o `tau_escalate_l2` en `CALIB` **no carga** con un `chispamovil` (Android/iOS) o un servidor anterior al commit `2b7096a`: falla con `unknown field "tipos_l2"`. Actualiza la app (con el `chispamovil` nuevo) antes de distribuirle modelos entrenados con `--l2`/`--ckpt`. Ver [04](04-formato-chispa.md#espacio-de-nombres-de-l2-en-calib).

## Android
Biblioteca `:chispa` y demo `:demo`. L0 y L1 vienen de `chispamovil` (gomobile). L2 usa `onnxruntime-android`.

```kotlin
val chispa = Chispa.abrir(contexto, "modelo.chispa")
val r = chispa.decidir("quiero comprar dos camisetas", listOf(pregunta)).first()
r.respuesta; r.confianza; r.capa; r.escalar; r.ms
// r.escalateReason (si escaló): MotivoEscalada.SIN_OPINION, BAJA_CONFIANZA o SCORE_IDS_NO_VALIDOS. INCOMPLETA existe por paridad con el servidor, pero el móvil nunca lo devuelve (no tiene timeouts de L3 ni presupuesto compartido).
```

- Cascada L0 → L1 → L2 con el mismo criterio que el servidor.
- L0 usa la sección `L0TF` si el fichero la trae (si no, la sección `L0`). Si el fichero trae `CONJ`, L2 es L2c: ORT da las
  ranuras, `chispamovil` calcula las similitudes y la cabeza conjunta (el mismo código que `server/decide`, en `format/chispa3`), y la
  cascada le pasa las probabilidades de L0. Sin `CONJ`, o si la cabeza no opina, L2 es L2 a secas.
- L2 necesita el tokenizador de e5: el del motor (`runtime/tok` en Go), con `Chispa.abrir(contexto, ruta, rutaTokenizador = "e5.chispa-tok")`
  (el `.chispa-tok` es el del servidor, `runtime/tok/exportar.py`), o uno de la app (`tokenizador = …`). Sin ninguno, solo L0 y L1.
- Sin compilar todavía: el Kotlin nuevo (L2c, `TokenizadorMotor`) y los tests `ConjTest`; los compila `sdk/android/aws/arranque.sh`.
- **Proveedor de ORT**: `Chispa.abrir(contexto, ruta, proveedorOrt = ProveedorOrt.NNAPI)` con `CPU`, `XNNPACK` (por defecto) o `NNAPI`, para L2 y la torre.
  Si el proveedor falla al crear la sesión, se reabre en CPU y se registra con `Log.w`; `chispa.proveedorOrt` dice cuál quedó.
- **Torre al vuelo**: si el fichero trae `TORR` y hay tokenizador del motor, un esquema nuevo recibe sus torres de L2 calculadas con el ONNX de `TORR`
  (`SesionTorreOrt`); también se puede pasar un `CodificadorTorre` propio. L1 usa las descripciones tal cual.
- **Demo `:demo`, pantalla «Medir»** (`MedirActivity`): N decisiones por escenario con p50/p95/p99 y el proveedor de ORT medido por separado; se lanza con
  `adb shell am start -n com.chispa.demo/.MedirActivity --ei n 1000 --ez auto true`. Sin cifras en el repo: sin medir en dispositivo.
- `L0MULTI` (varios L0 en un `.chispa`): lo lee el motor Go (`chispamovil`) y Kotlin/Swift no cambian (llaman al motor); sin compilar aquí. Python lo lee y escribe a nivel de sección (`formato.l0multi`, `formato.leer_l0multi`); la validación de etiquetas es la del lado Go.
- λ de `SOPL1`: Kotlin no lo expone todavía (solo el núcleo Go, con `AbrirConSoporte`); en el móvil no hay mezcla de soporte.
- Se compila en AWS con `sdk/android/aws/`; no en un portátil. Pasos en el README.

## iOS
Paquete Swift con `Chispa.abrir(ruta:)` y `decidir(_:_:)`. L0 y L1 salen de un xcframework de gomobile. L2 usa ONNX Runtime con CoreML.

```swift
let chispa = try Chispa.abrir(ruta: Bundle.main.path(forResource: "modelo", ofType: "chispa")!)
let r = chispa.decidir("quiero comprar dos camisetas", [p])[0]   // r.respuesta, r.confianza, r.capa, r.escalar
```

**No se ha compilado ni probado.** Hace falta Xcode ≥ 15 en una mac2 o en un runner macOS. Los nombres que genera gomobile y la API de ORT
están escritos de memoria. Los primeros fallos estarán en `MotorNativo.swift` y `SesionOrt.swift`.
Pasos de compilación: [`sdk/ios/README.md`](../sdk/ios/README.md#compilar-y-probar-mac2-o-runner-macos).
Proveedor de ORT: `ProveedorOrt` es `cpu` o `coreML` (por defecto `coreML`; si falla al crear la sesión cae a CPU), con `Chispa.abrir(ruta:, proveedorOrt:)`.
Torre al vuelo: con `TORR` y tokenizador del motor, un esquema nuevo recibe sus torres de L2 (`SesionTorreOrt`), o pasas un `CodificadorTorre`.
No se compila en iOS aquí: sin Swift ni Xcode. Como en Android: L0TF, L2c (con `CONJ`) y el tokenizador del motor (`Chispa.abrir(ruta:, rutaTokenizador:)`) están escritos en Swift
(`CapaL2`, `TokenizadorMotor`, `ConjTests`) pero **sin compilar**, igual que el resto.

## WASM
`runtime/l1` en Go puro, compilado a `GOOS=js GOARCH=wasm`. Una página estática con L1 recortado: 50 000 piezas, 15,8 MB, frente a los 155 MB del completo.

- API en JS: `cargar(Uint8Array)`, `decidir(texto, preguntaJSON)`, `huella` y `medir`.
- `index.html` trae un formulario de esquema nuevo (pregunta, opciones `id: descripción`, mensaje; solo `choice`) y `latencia.html` un arnés de latencia (p50/p95/p99 por decisión y por lote; con node: `prueba_latencia_node.js`).
- Solo L1, zero-shot: decide sobre un esquema nuevo con la pregunta y las descripciones. La demo enseña el mecanismo y la latencia, no la calidad
  ([`demo/wasm/README.md`](../demo/wasm/README.md)).
- Construir: `./construir.sh` en `demo/wasm`, y servir con `python -m http.server`. Necesita `chispa.wasm` y `potion-es.chispa-l1`, que no van a git.

## Núcleo móvil
`sdk/movil/chispamovil` es el paquete Go que usan Android e iOS: `Abrir`, `Decidir` (L1), `DecidirL0` (L0TF o L0), `PuntuarL2`, `ExtraerL2`,
`CargarTokenizadorE5`/`TokenizarE5` (`runtime/tok`), `CabezaConjunta` (L2c), `AbrirConSoporte(ruta, λ1, λ2)` (mezcla de `SOPL1`) y la torre al vuelo (`TieneTorre`, `OnnxTorre`, `IdsPasaje`, `TextosTorreL2`, `InstalarTorresL2`) ([`sdk/movil/README.md`](../sdk/movil/README.md)).
La cabeza conjunta, `simproto` y MaxSim viven en `format/chispa3` (`conj_cabeza.go`) y las usan igual el servidor y el móvil. Tests de paridad
con el servidor (`decide.L0`, `decide.L2c`) y con `runtime/tok`: |Δp| ≤ 1e-6.
