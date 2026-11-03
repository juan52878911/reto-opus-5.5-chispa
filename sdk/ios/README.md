# sdk/ios — Chispa para iOS (Swift)

Paquete Swift (`Package.swift`): `Chispa.abrir(ruta:)` y `decidir(_:_:)`, con la misma cascada que Android
(`server/decide/cascada.go`: L0 → L1 → L2, τ de CALIB para L1 y L2). L0 y L1 vienen del xcframework de gomobile
(`binaryTarget` `Chispamovil`); L2 usa ONNX Runtime (`onnxruntime-swift-package-manager`, módulo `OnnxRuntimeBindings`)
con el **EP de CoreML**. Como en Android, L0 usa L0TF si el fichero la trae y, con CONJ, L2 es L2c (`Motor.cabezaConjunta`). L2 necesita el tokenizador de e5:
el del motor (`Chispa.abrir(ruta:, rutaTokenizador:)` con el `.chispa-tok` de `runtime/tok/exportar.py`) o uno de la app (`Tokenizador`).
Todo esto, sin compilar.

```swift
let chispa = try Chispa.abrir(ruta: Bundle.main.path(forResource: "modelo", ofType: "chispa")!)
let p = Pregunta("¿Qué quiere el cliente?", opciones: [Opcion("compra", descripcion: "quiere comprar"), Opcion("soporte")])
let r = chispa.decidir("quiero comprar dos camisetas", [p])[0]   // r.respuesta, r.confianza, r.capa, r.escalar
```

Tipo `multi` (`Pregunta(..., tipo: "multi")`): cada opción es un sí/no con su p en `probs` (no suman 1); `r.respuestas` son las activas en
el orden de la pregunta (vacía si ninguna: es una respuesta válida y no escala) y `r.respuesta` la activa más probable o `""`. La confianza
que se compara con τ es la de la opción más dudosa (la calcula el motor: la cascada no cambia) y L0 no opina en `multi`. Al escalar,
`respuestas` es la de la capa con más confianza; en choice, noul y score va vacía.

Paridad con Android fila a fila: [PARIDAD.md](PARIDAD.md). Receta exacta de compilación en una mac2: [COMPILAR.md](COMPILAR.md).
Esquemas nuevos (zero-shot): la pregunta trae las opciones con `descripcion`; L1 las usa tal cual y, si pasas un
`CodificadorTorre` a `Chispa.abrir(..., codificadorTorres:)`, L2 recibe las torres al vuelo (el motor las cachea).

## ⚠️ Escrito sin compilar
Este paquete **no se ha compilado ni probado**: no hay Swift ni Xcode en la VM de desarrollo y la compilación se hace
en una mac2 o en un runner macOS de CI, nunca en el Mac de Juan. Los nombres que genera gomobile
(`ChispamovilAbrir`, `ChispamovilChispa`, `decidir(_:preguntaJSON:)`, …) y la API de ORT están escritos de memoria; los
primeros que fallen estarán en `Sources/Chispa/MotorNativo.swift` y `SesionOrt.swift`, y son los únicos ficheros que
tocan esas APIs. La cascada, los modelos y los tests XCTest (con un motor falso) no dependen de ellas.

## Compilar y probar (mac2 o runner macOS)
Desde la raíz del repo, con Xcode ≥ 15, Go 1.27.1 y el `codigo.tgz` de `bash sdk/android/aws/empaquetar.sh` (lleva la
caché de módulos de kindling) extraído en `$T`:
```
cd $T/sdk/movil/chispamovil
export GOFLAGS=-mod=mod GONOSUMDB='github.com/juan52878911/*' GOTOOLCHAIN=local \
       GOPROXY=file://$T/gomod-proxy,https://proxy.golang.org
go get golang.org/x/mobile@latest
go install golang.org/x/mobile/cmd/gomobile@latest golang.org/x/mobile/cmd/gobind@latest
export PATH=$(go env GOPATH)/bin:$PATH
gomobile init
gomobile bind -target=ios,iossimulator -iosversion 15 -o ../../ios/Chispamovil.xcframework .   # → sdk/ios/Chispamovil.xcframework
mkdir -p ../../ios/Frameworks && mv ../../ios/Chispamovil.xcframework ../../ios/Frameworks/
cd ../../ios
xcodebuild test -scheme Chispa -destination 'platform=iOS Simulator,name=iPhone 15' -skipPackagePluginValidation
```
(`xcodebuild -scheme Chispa` descubre el esquema del paquete; usa el simulador que haya en el runner.) Si
`onnxruntime-swift-package-manager` no resuelve `from: "1.19.2"`, ajustar la versión en `Package.swift`.

**score y `escalateReason`.** Un `score` solo vale con ids exactamente `1..K` (en cualquier orden); con otros ids ninguna capa opina. `Respuesta.escalateReason` (nulo/`nil` si no escaló o escaló por el fallo de una capa) trae, igual que `escalate_reason` del servidor: `sin_opinion`, `baja_confianza` o `score_ids_no_validos`.

## Licencia

Apache-2.0 (ver `LICENSE` de la raíz del repositorio). Las atribuciones de terceros están en `NOTICE`. Los datasets con SA, NC o con términos pendientes
(XNLI, clima, datos.gov.co, SIB-200, etiquetas de ALIA, salidas de Haiku) no se redistribuyen y solo se usan como test.
