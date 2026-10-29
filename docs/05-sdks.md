# SDK

| SDK | Qué hace | Estado | README |
|---|---|---|---|
| Python | cliente de `/v1/decide` y `chispa train` | probado con tests y a mano contra `chispa-server` | [`sdk/python`](../sdk/python/README.md) |
| Android | cascada en el dispositivo (Kotlin) | se compila en AWS; sin tokenizador, solo L0 y L1 | [`sdk/android`](../sdk/android/README.md) |
| iOS | cascada en el dispositivo (Swift) | **escrito sin compilar** | [`sdk/ios`](../sdk/ios/README.md) |
| WASM | L1 en el navegador | demo con L1 recortado | [`demo/wasm`](../demo/wasm/README.md) |

Los móviles y WASM no hablan con el servidor. Abren el `.chispa` y deciden en el dispositivo.

## Python
Sin dependencias. Python ≥ 3.9. PyYAML es opcional, para esquemas `.yaml`.

```python
from chispa import Chispa, Choice, Noul, Score
c = Chispa("http://127.0.0.1:8090")
rs = c.decidir("necesito ayuda ya", [
    Choice("u1", "¿Qué tan urgente es?", [("alta", "Requiere atención inmediata"), "baja"]),
    Noul("s1", "¿Es spam?"), Score("p1", "¿Qué tan molesto está?", 5)])
rs[0].answer, rs[0].probs, rs[0].layer, rs[0].escalate
```

- Reintentos: 3 por defecto, con espera exponencial. El nonce se fija antes del primer intento, así que reintentar es idempotente.
- `ErrorSolicitud`: 400, 405 o 413. No se reintenta.
- `ErrorTransporte`: red, 5xx o 429 tras los reintentos.
- Una pregunta suelta desde la consola: `python -m chispa decide --url … --estado … --pregunta … --opciones a b`
  ([`cli.py`](../sdk/python/chispa/cli.py)).
- Entrenar: [02-inicio-rapido.md](02-inicio-rapido.md).

Los nombres de campo son los del contrato de [03-api.md](03-api.md). `/v1/systemone` de Jev no se ha visto
([`server/README.md`](../server/README.md#relación-con-v1systemone-de-jev--suposición-sin-verificar)).

## Android
Biblioteca `:chispa` y demo `:demo`. L0 y L1 vienen de `chispamovil` (gomobile). L2 usa `onnxruntime-android`.

```kotlin
val chispa = Chispa.abrir(contexto, "modelo.chispa")
val r = chispa.decidir("quiero comprar dos camisetas", listOf(pregunta)).first()
r.respuesta; r.confianza; r.capa; r.escalar; r.ms
```

- Cascada L0 → L1 → L2 con el mismo criterio que el servidor.
- L2 pide un `Tokenizador` de e5 (`Chispa.abrir(contexto, ruta, tokenizador)`). La app debe aportarlo. Sin él, solo L0 y L1.
- El SDK no tiene código para `CONJ` ni `L0TF` (L2c y el L0 TF-IDF son del servidor).
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
Como en Android, L2 necesita un `Tokenizador` de e5 que aporte la app.

## WASM
`runtime/l1` en Go puro, compilado a `GOOS=js GOARCH=wasm`. Una página estática con L1 recortado: 50 000 piezas, 15,8 MB, frente a los 155 MB del completo.

- API en JS: `cargar(Uint8Array)`, `decidir(texto, preguntaJSON)`, `huella` y `medir`.
- Solo L1, zero-shot. La demo enseña el mecanismo y la latencia, no la calidad
  ([`demo/wasm/README.md`](../demo/wasm/README.md)).
- Construir: `./construir.sh` en `demo/wasm`, y servir con `python -m http.server`. Necesita `chispa.wasm` y `potion-es.chispa-l1`, que no van a git.

## Núcleo móvil
`sdk/movil/chispamovil` es el paquete Go que usan Android e iOS: `Abrir`, `Decidir` (L1), `DecidirL0`, `PuntuarL2` y `ExtraerL2`
([`sdk/movil/README.md`](../sdk/movil/README.md)).
