# Compilar y probar sdk/ios en una mac2 de AWS

Receta de una sola pasada para quien no ha leído nada más. **El código Swift nunca se ha compilado** (el nodo de
desarrollo no tiene Swift ni Xcode): espera errores, sobre todo en `MotorNativo.swift` y `SesionOrt.swift`
(ver «Sitios que probablemente fallen»). Si el mismo paso falla dos veces por la misma causa, para y cuéntalo.

Resultado esperado: `** TEST SUCCEEDED **` con **53 tests** XCTest (CacheYErroresTests 11, CascadaTests 11, ConjTests 6, L2Tests 5, ModelosTests 4,
ZeroShotTests 11, TorreDefectoTests 5) contra un motor falso. Ninguno necesita un `.chispa` real ni ONNX.

## 0. La máquina
- Instancia `mac2.metal` (Apple Silicon, macOS 13+), con Xcode ≥ 15. Si no está: bajar el `.xip` de Apple (cuenta de
  desarrollador) y luego:
  ```
  sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
  sudo xcodebuild -license accept
  sudo xcodebuild -runFirstLaunch
  xcodebuild -downloadPlatform iOS          # el runtime del simulador, ~8 GB; tarda
  ```
  Comprobar: `xcodebuild -version` (→ `Xcode 15.x` o 16.x) y `xcrun simctl list devices available | grep -i iphone`
  (debe salir al menos un iPhone; anota su nombre exacto para el paso 6).
- Go 1.27.1 para darwin-arm64 (el `go.mod` de `chispamovil` pide `go 1.27`):
  ```
  curl -fsSLO https://go.dev/dl/go1.27.1.darwin-arm64.tar.gz
  sudo tar -C /usr/local -xzf go1.27.1.darwin-arm64.tar.gz     # si ya había un /usr/local/go antiguo, muévelo antes
  export PATH=/usr/local/go/bin:$PATH ; go version             # → go version go1.27.1 darwin/arm64
  ```

## 1. El código
Desde una máquina con el repo y la caché de Go (en la de desarrollo): `bash sdk/android/aws/empaquetar.sh > codigo.tgz`
(lleva `sdk/ios`, `sdk/movil`, `runtime/*`, `format/chispa3`, `server/` y `gomod-proxy/` con la caché de módulos de
kindling, que no se baja de un proxy público). Cópialo a la mac2 y:
```
export T=$HOME/chispa && mkdir -p $T && tar -xzf codigo.tgz -C $T && ls $T      # → sdk runtime format server gomod-proxy …
```

## 2. Go: entorno y pruebas del motor
```
export GOFLAGS=-mod=mod GONOSUMDB='github.com/juan52878911/*' GOTOOLCHAIN=local
export GOPROXY=file://$T/gomod-proxy,https://proxy.golang.org
export GOPATH=$HOME/gopath ; export PATH=$GOPATH/bin:$PATH
cd $T/sdk/movil/chispamovil && go test ./... 2>&1 | tail -5       # → ok  chispa/sdk/movil/chispamovil …
```
Si `go test` falla aquí, no sigas: es el motor, no Swift.

## 3. gomobile bind → xcframework
```
cd $T/sdk/movil/chispamovil
go get golang.org/x/mobile@latest
go install golang.org/x/mobile/cmd/gomobile@latest golang.org/x/mobile/cmd/gobind@latest
gomobile init
mkdir -p $T/sdk/ios/Frameworks
gomobile bind -v -target=ios,iossimulator -iosversion 15 -o $T/sdk/ios/Frameworks/Chispamovil.xcframework .
```
Esperado: termina sin error y crea `Frameworks/Chispamovil.xcframework/` con `Info.plist` y carpetas
`ios-arm64/` e `ios-arm64_x86_64-simulator/` (los nombres exactos varían). `Frameworks/*.xcframework` está en el
`.gitignore`: no se versiona.

**Antes de compilar Swift, comprueba los nombres que gomobile ha generado** (Swift los usa de memoria):
```
H=$(find $T/sdk/ios/Frameworks/Chispamovil.xcframework -name Chispamovil.h | head -1); echo $H
grep -n "ChispamovilAbrir\|@interface ChispamovilChispa\|preguntaJSON\|puntuarL2\|tokenizarE5\|cargarTokenizadorE5\|extraerL2\|cabezaConjunta\|tauEscalate\|tieneCalib\|cerrar" $H
```
Compáralos con `Sources/Chispa/MotorNativo.swift` (ver la lista de abajo).

## 4. Swift: compilar el paquete
```
cd $T/sdk/ios
xcodebuild build -scheme Chispa -destination 'generic/platform=iOS Simulator' -skipPackagePluginValidation 2>&1 | tail -40
```
Esperado: `** BUILD SUCCEEDED **`. La primera vez resuelve `onnxruntime-swift-package-manager` desde GitHub (necesita red).

`swift build` a secas apunta a macOS (`platforms: .macOS(.v12)`) y el xcframework del paso 3 **no trae slice macOS**, así que
falla al enlazar `Chispamovil`; no es un error del código. Para usarlo, añade `macos` al `-target` del paso 3
(`-target=ios,iossimulator,macos`; depende de la versión de gomobile) y entonces:
```
swift build 2>&1 | tail -20 ; swift test 2>&1 | tail -20      # → Executed 37 tests, with 0 failures
```
La vía soportada es `xcodebuild` con el simulador (paso 6).

## 5. Solo la parte pura (sin xcframework ni ORT) si el 4 no compila
Para aislar si el fallo es de gomobile/ORT o de la lógica: copia `Capas.swift`, `Cascada.swift`, `Modelos.swift` y
`Chispa.swift` (todo menos `MotorNativo.swift` y `SesionOrt.swift`, y quitando la llamada a `MotorNativo.abrir`/`SesionOrt(...)`
de `Chispa.abrir`) a un paquete nuevo con los tests de `Tests/ChispaTests`, y `swift test`. La lógica de cascada, L2c,
zero-shot y modelos solo usa Foundation.

## 6. Tests en el simulador
```
cd $T/sdk/ios
xcrun simctl list devices available | grep -i iphone          # elige un nombre
xcodebuild test -scheme Chispa -destination 'platform=iOS Simulator,name=iPhone 15' -skipPackagePluginValidation 2>&1 | tee /tmp/xcb.log | tail -40
grep -n "error:" /tmp/xcb.log | head
```
Esperado: `Test Suite 'All tests' passed`, `Executed 37 tests, with 0 failures` y `** TEST SUCCEEDED **`. Si el nombre del
simulador no existe, usa uno de la lista (`name=iPhone 16`, etc.) o `id=<UDID>`.

## Sitios que probablemente fallen
Todo esto está escrito de memoria. En este orden de probabilidad:

1. **Nombres de gomobile (`MotorNativo.swift`).** Se esperan: `ChispamovilAbrir(ruta, &error)` → `ChispamovilChispa?`;
   métodos `capas()`, `tieneCalib()`, `tauEscalate()`, `decidirL0(_:preguntaJSON:)`, `decidir(_:preguntaJSON:)`,
   `torresL2(_:)`, `puntuarL2(_:ranuras:k:)`, `extraerL2(_:)` (throws), `tieneConj()`, `cabezaConjunta(_:)`, `tieneTokenizadorE5()`,
   `cargarTokenizadorE5(_:)` (throws), `tokenizarE5(_:)` → `Data?`, `cerrar()`; y los de W7: `textosTorreL2(_:)` → `String`,
   `instalarTorresL2(_:torres:n:)` (`n` es `Int` en Swift; si el header dice `long`, `n: Int64(n)`), `tieneTorre()`, `onnxTorre()` → `Data?`,
   `idsPasaje(_:)` → `Data?`; y los de FG: `tauL2c()` → `Double` (−1 si falta) y `hashSeccion(_:)` → `String` (el `tipo` Go `int` llega como `Int`;
   si el header dice `long`, `Int64(tipo)`; sha256 hex de la sección, "" si no hay). `CacheFicheros.swift` usa `CryptoKit` (iOS 13+). Cosas típicas: gomobile escribe `JSON` en
   mayúsculas (`preguntaJSON`); el primer argumento va sin etiqueta; los métodos Go que devuelven solo `error` llegan como
   `throws`, y los que devuelven `(T, error)` como `func m(...) throws -> T` (o `m(_:error:)` según la versión); `int` de
   Go es `Int`, `int64` es `Int64`, `float64` es `Double`; `[]byte` es `Data?`. Arreglo: editar solo `MotorNativo.swift`
   según el `.h` del paso 3.
2. **`puntuarL2(_:ranuras:k:)`.** `k` en Go es `int` → `Int` en Swift; si el header dice `long`/`Int64`, convertir: `k: Int64(k)`.
3. **`go.cerrar()` con `try?`.** Si el método no lanza, `try?` da aviso y no error. Quitarlo o ponerlo según el header.
4. **ORT (`SesionOrt.swift`).** API de `onnxruntime-swift-package-manager` ≥ 1.19: `ORTEnv(loggingLevel:)`,
   `ORTSessionOptions()`, `appendCoreMLExecutionProvider(with: ORTCoreMLExecutionProviderOptions())`,
   `ORTSession(env:modelPath:sessionOptions:)`, `ORTValue(tensorData: NSMutableData, elementType: .int64, shape: [NSNumber])`,
   `session.run(withInputs:outputNames:runOptions:)` (`outputNames` es `Set<String>` en algunas versiones: cambiar
   `["S"]` por `Set(["S"])`), `tensorTypeAndShapeInfo().shape`, `tensorData()`. El módulo se importa como
   `OnnxRuntimeBindings`; el producto SPM se llama `onnxruntime` (`Package.swift`). Si SPM no resuelve `from: "1.19.2"`,
   listar las etiquetas (`git ls-remote --tags https://github.com/microsoft/onnxruntime-swift-package-manager`) y ajustar.
   El EP de CoreML en el simulador puede fallar en ejecución, pero ningún test lo ejecuta; para desactivarlo,
   `Chispa.abrir(..., proveedorOrt: .cpu)` (o `coreML: false`).
   **Proveedores (`ProveedorOrt.swift`, `OpcionesOrt.swift`):** `appendCoreMLExecutionProvider(with:)` lanza (`throws`) en la
   versión ObjC/Swift de ORT; si en la 1.2x pasa a devolver `Bool` o a llamarse distinto, solo hay que tocar `OpcionesOrt.swift`.
   `ORTCoreMLExecutionProviderOptions()` puede pedir `try`. `abrirConRespaldo` es genérica: si el compilador no infiere `T`
   en los tests, anotar el tipo de retorno del cierre (ya van anotados). La tupla `let (s, efectivo) = try …` dentro de `init`
   de una clase `final` con `let` se asigna después; si Swift se queja de uso antes de inicializar, mover `entorno` a una
   variable local. Dos `init` en `SesionOrt`/`SesionTorreOrt` (`proveedor:` y `coreML:`): ninguno tiene valor por defecto en
   el segundo, para que `SesionOrt(rutaOnnx:)` no sea ambiguo. `os_log` con `type: .default` (importa `os`).
5. **`SesionOrt` y `Chispa.abrir` no los ejercita ningún test** (necesitan un `.chispa` y ONNX reales): `BUILD SUCCEEDED` no
   garantiza que L2 funcione en un dispositivo.
6. **Conformidad de `Motor` en `MotorNativo`.** El protocolo ahora incluye `tieneTokenizadorE5`, `textosTorreL2` e
   `instalarTorresL2` (los dos últimos con implementación por defecto en la extensión). Si el compilador dice que
   `MotorNativo` no se ajusta a `Motor`, mira primero las firmas de `extraerL2(a:)` y `cargarTokenizadorE5(ruta:)`.
7. **Tests.** `Falsos.swift`: `instalarTorresL2(_:torres bytes:n:)` (etiqueta `torres`, nombre interno `bytes` para no tapar
   la propiedad `torres`). `ZeroShotTests.swift`: `Codificador` es una clase anidada que conforma un protocolo `public`
   (si molesta, sacarla del `XCTestCase`). `XCTAssertEqual` de `Data?` y de `[String: Double]?` deben compilar; si no, comparar `Array(...)`.
   `ConjTests` espera `ErrorChispa("el motor no tiene el tokenizador de e5")`: si cambias el texto en `TokenizadorMotor`, cámbialo también ahí.
   Nuevos en W7 que también pueden fallar: `SesionTorreOrt.swift` (mismo API de ORT que `SesionOrt`: `outputNames: ["h"]` →
   `Set(["h"])` si hace falta; `Data(contentsOf:options:.alwaysMapped)` y `write(to:options:.atomic)`), el cierre
   `crearSesionTorre` con valor por defecto en `Chispa.montar` y `TorreDefectoTests.swift` (clase `Fijo` declarada dentro de
   un método de test: si molesta, sacarla al nivel del fichero; `ids(_:)` asume little endian, como Apple).
   Ni `SesionTorreOrt` ni el camino real de TORR los ejercita ningún test.
8. **Swift 6 / concurrencia estricta.** El paquete usa `swift-tools-version:5.9`: Xcode 16 compila en modo Swift 5 y no
   debería quejarse. Si aparecen avisos de `Sendable` en `SesionOrt`, son avisos.
9. **`Package.swift` y la ruta del `binaryTarget`.** `path: "Frameworks/Chispamovil.xcframework"` es relativa a `sdk/ios`;
   «binary target … does not contain a binary artifact» = el paso 3 dejó el xcframework en otro sitio o con otro nombre.

## Al terminar
Anota en `sdk/ios/README.md` (quita el aviso «Escrito sin compilar» solo si el paso 6 pasó) qué cambiaste y con qué
versiones de Xcode, Go, gomobile y onnxruntime-swift-package-manager. Para el contrato de zero-shot de L2 y el
codificador de torres por defecto, ver `PARIDAD.md`.
