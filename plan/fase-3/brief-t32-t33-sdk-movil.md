# T3.2 + T3.3 SDKs móviles: Android (Kotlin, L1 con gomobile y L2 con ORT) e iOS (Swift, sin compilar)

Plan aprobado, fase 3. Directiva de Juan del 2026-10-28:
- compilar y probar en AWS o en CI, **nunca en el Mac**;
- iOS se escribe sin compilar, porque la mac2 la decide Juan.

Antecedentes:
- `runtime/l1/`: Go puro, determinista en arm64;
- `format/chispa3/`;
- `server/decide/l1.go`, que tiene la lógica de puntuación de L1;
- `demo/wasm/`, que es la misma API mínima en otro destino.

## Hipótesis
- `gomobile bind` de un paquete Go pequeño (`sdk/movil/chispamovil`: `Abrir(ruta)`,
  `Decidir(texto, preguntaJSON) string`) sobre `runtime/l1` y `format/chispa3` produce un AAR para Android y un
  xcframework para iOS con la misma API.
- L2 en el móvil va con ONNX Runtime Mobile (Android: `onnxruntime-android`; iOS: `onnxruntime-objc` con
  CoreML EP), usando la sección L2 y las torres de ESQUEMAS.
- Se refuta si el AAR no se construye en AWS.

## Terminado cuando
- `sdk/movil/chispamovil/`: un paquete Go con tests nativos. Su `decidir` debe coincidir con el de
  `demo/wasm` (misma huella en 50 frases del sondeo).
- `sdk/android/`: una biblioteca Kotlin, Gradle con Kotlin DSL.
  - `Chispa.abrir(contexto, rutaModelo)` y `decidir(texto, preguntas): List<Respuesta>`;
  - cascada L0 → L1 (gomobile) → L2 (ORT), con τ desde CALIB, igual que `server/`;
  - una app de demo mínima («WhatsApp sin conexión»: un cuadro de texto y la intención con su confianza);
  - tests JVM de la lógica de cascada y de parsing, con L1 falso.
- `sdk/android/aws/arranque.sh`, user-data para Amazon Linux 2023 x86_64 con el patrón de siempre:
  - marcador `CHISPA_S3`, `shutdown -h +120` y un trap que sube `log.txt` y `resultados.tgz`;
  - descargas de S3 por fichero;
  - pasos:
    1. instala JDK 17, Android cmdline-tools, SDK 34, NDK, Go 1.27 y `gomobile`;
    2. `gomobile bind -target=android`;
    3. `./gradlew test assembleDebug`;
    4. sube el AAR, el APK y los informes de test.
  - `sdk/android/aws/empaquetar.sh`: empaqueta lo necesario usando `find` y `tar` portables, sin `-C` combinado con `-T`,
    porque se ejecuta también con bsdtar.
- `sdk/ios/`: un paquete Swift (`Package.swift`) con `Chispa.abrir/decidir`, el xcframework de gomobile
  referenciado como `binaryTarget` y ORT con CoreML EP, más tests XCTest de la cascada con L1 falso.
  **No se compila aquí**. En el README va el comando exacto para una mac2 o un runner macOS de CI.
- Prueba en seco aquí:
  - `cd sdk/movil/chispamovil && go test ./...`;
  - `GOOS=android GOARCH=arm64 go vet ./...` si el SDK de Go lo permite sin NDK;
  - `bash -n` del script de AWS;
  - `kotlinc` o Gradle no están en la VM: dilo.
- `make test` y `make smoke` en verde.
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- `sdk/movil/**`, `sdk/android/**` y `sdk/ios/**`.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Go en `~/go-sdk/bin`. Sin red salvo la API de Claude.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.

## Tope
- ≤ 150 min de reloj · ≤ 8 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 15 líneas: qué cambiaste, rama y sha, la prueba en seco, lo que tengo que
sustituir para la compilación en AWS, qué quedó sin verificar y qué recomiendas.
