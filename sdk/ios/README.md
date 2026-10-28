# sdk/ios — Chispa para iOS (Swift)

Paquete Swift (`Package.swift`): `Chispa.abrir(ruta:)` y `decidir(_:_:)`, con la misma cascada que Android
(`server/decide/cascada.go`: L0 → L1 → L2, τ de CALIB para L1 y L2). L0 y L1 vienen del xcframework de gomobile
(`binaryTarget` `Chispamovil`); L2 usa ONNX Runtime (`onnxruntime-swift-package-manager`, módulo `OnnxRuntimeBindings`)
con el **EP de CoreML**. Como en Android, L2 necesita un `Tokenizador` de e5 que todavía no existe.

```swift
let chispa = try Chispa.abrir(ruta: Bundle.main.path(forResource: "modelo", ofType: "chispa")!)
let p = Pregunta("¿Qué quiere el cliente?", opciones: [Opcion("compra", descripcion: "quiere comprar"), Opcion("soporte")])
let r = chispa.decidir("quiero comprar dos camisetas", [p])[0]   // r.respuesta, r.confianza, r.capa, r.escalar
```

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
