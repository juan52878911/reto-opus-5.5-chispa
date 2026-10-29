# sdk/android — Chispa para Android (Kotlin)

Biblioteca `:chispa` (Gradle, Kotlin DSL) más una app de demo `:demo` («WhatsApp sin conexión»: un cuadro de texto y la
intención con su confianza). Sobre `sdk/movil/chispamovil` (L0 y L1, vía `gomobile bind`) y ONNX Runtime Mobile
(`onnxruntime-android`, L2).

```kotlin
val chispa = Chispa.abrir(contexto, "modelo.chispa")             // ruta absoluta o asset (se copia a filesDir)
val r = chispa.decidir("quiero comprar dos camisetas", listOf(pregunta)).first()
r.respuesta; r.confianza; r.capa; r.escalar; r.ms
```

- **Cascada** (`Cascada.kt`): igual que `server/decide/cascada.go`. L0 → L1 → L2, pasa a la siguiente mientras la
  confianza top-1 sea < τ; una capa que falla o no opina se salta; si ninguna llega, `escalar = true` con la pista de
  mayor confianza y la última capa. τ: L0 = 0,80; L1 y L2 = `tau_escalate` de CALIB (0,80 y 0,70 si el fichero no trae
  CALIB).
- **L0TF y L2c**: `DecidirL0` usa la sección L0TF si está. Con CONJ en el fichero, `CapaL2` hace L2c: las ranuras de ORT van a
  `Motor.cabezaConjunta` junto con las probabilidades de L0 (la cascada pasa a cada capa lo que dijeron las anteriores); si la
  cabeza no opina, cae a `puntuarL2`.
- **L2 necesita el tokenizador de e5**: el del motor (`Chispa.abrir(contexto, ruta, rutaTokenizador = "e5.chispa-tok")`, el
  `.chispa-tok` de `runtime/tok/exportar.py`, ~12 MB, como asset o ruta) o uno de la app (`Tokenizador`, `fun interface`).
  Sin ninguno, `Chispa.abrir` monta solo L0 y L1. La demo va así.
- **Proveedor de ORT** (`ProveedorOrt.kt`): `Chispa.abrir(contexto, ruta, proveedorOrt = ProveedorOrt.NNAPI)` con `CPU`, `XNNPACK`
  (por defecto) o `NNAPI`; se aplica a L2 y a la torre. Si `addXnnpack`/`addNnapi` o la creación de la sesión lanzan, se
  reabre en CPU y se registra con `Log.w` (etiqueta `Chispa`); `chispa.proveedorOrt` dice cuál quedó. XNNPACK recibe
  `intra_op_num_threads` = núcleos (máx. 4). La API anterior no cambia (parámetro opcional al final).
- Los tests JVM (`chispa/src/test`) usan un `Motor` falso: la cascada y el parsing no dependen del AAR.

## Construir (en AWS, nunca en el Mac)
```
bash sdk/android/aws/empaquetar.sh > codigo.tgz        # sube codigo.tgz al prefijo S3
# user-data de la instancia: sdk/android/aws/arranque.sh con __CHISPA_S3__ sustituido por s3://bucket/ruta
```
Amazon Linux 2023 **x86_64**, ≥ 4 vCPU / 8 GB y **≥ 30 GB de disco** (SDK + NDK + cachés de Gradle). El script instala
JDK 17, cmdline-tools, SDK 34, NDK 26.1, Go 1.27.1, Gradle 8.9 (y genera el wrapper con `gradle wrapper`: el
`gradle-wrapper.jar` no va a git), corre `go test` y `go vet` de `chispamovil`, `gomobile bind -target=android/arm64,android/amd64`,
`./gradlew test assembleDebug`, y sube a S3 `log.txt`, `resultados.tgz`, `chispamovil.aar` y `chispa-demo-debug.apk`.
Se apaga solo (`shutdown -h +120`). La demo espera `demo/src/main/assets/modelo.chispa` (un `.chispa` v3 con L0/L1/CALIB);
sin él, arranca y lo dice en pantalla.

Prueba en seco en kindling (solo la parte de Go): `CHISPA_LOCAL=1 bash arranque.sh` con el tgz en `/tmp/chispa/s3/<prefijo>/`.

## Sitios que probablemente fallen (sin compilar: no hay JDK aquí)
API de `onnxruntime-android` 1.19.2 (`build.gradle.kts`) escrita de memoria, sin AAR delante:
1. `OrtSession.SessionOptions.addXnnpack(Map<String, String>)`: los valores son **cadenas** (`"4"`, no `4`). Si el AAR no lo
   trae (paquete «mobile» sin XNNPACK) falla en ejecución con `OrtException`, no al compilar: el respaldo lo cubre, pero
   la medida saldría como CPU. Comprobarlo con `OrtEnvironment.getAvailableProviders()` (el JSON de Medir lo lista).
2. `addNnapi()` (sin argumentos) y `addNnapi(EnumSet<NNAPIFlags>)`: existen en 1.19; `OrtException` si no hay NNAPI. NNAPI está
   en desuso desde Android 15; algunos SoC lo aceptan y luego van más lento que la CPU: por eso Medir lo mide aparte.
3. `SessionOptions` es `AutoCloseable`: `opcionesOrt(...).use { createSession(...) }` cierra las opciones tras crear la
   sesión (vale en ORT Java; si diera un fallo nativo, quitar el `use` y cerrar en `close()`).
4. `abrirConRespaldo` captura `Exception`; `OrtException` hereda de `Exception`, pero `UnsatisfiedLinkError` (Error) no se
   captura y subiría.
5. `Pair<T, ProveedorOrt>` desestructurado en `init` de `SesionOrt`/`SesionTorreOrt` con `val` asignados después: Kotlin lo admite.
6. Test: `abrirConRespaldo<String>(…)` con lambda final de `crear`; si Kotlin no infiere `T`, ya va explícito donde el cierre solo lanza.
7. Demo: `Medidor.conProveedor` y los parámetros nuevos de `ResultadoEscenario` (con valor por defecto) no rompen `EstadisticasTest`.
