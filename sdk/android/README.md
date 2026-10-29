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
