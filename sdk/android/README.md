# sdk/android — Chispa para Android (Kotlin)

Biblioteca `:chispa` (Gradle, Kotlin DSL) más una app de demo `:demo` («WhatsApp sin conexión»: un cuadro de texto y la
intención con su confianza). Sobre `sdk/movil/chispamovil` (L0 y L1, vía `gomobile bind`) y ONNX Runtime Mobile
(`onnxruntime-android`, L2).

```kotlin
val chispa = Chispa.abrir(contexto, "modelo.chispa")             // ruta absoluta o asset (se copia a filesDir)
val r = chispa.decidir("quiero comprar dos camisetas", listOf(pregunta)).first()
r.respuesta; r.confianza; r.capa; r.escalar; r.ms
```

- **Tipo `multi`** (`Pregunta(texto, opciones, tipo = "multi")`): cada opción es un sí/no con su p en `probs` (no suman 1).
  `r.respuestas` son las activas en el orden de la pregunta (vacía si ninguna: es una respuesta válida y no escala);
  `r.respuesta` es la activa más probable o `""`. La confianza que se compara con τ es la de la opción más dudosa: la calcula
  el motor (`multi` de `chispamovil`), así que la cascada no cambia; una capa solo acepta si todas sus decisiones pasan τ. L0 no
  opina en `multi`. Al escalar, `respuestas` es la de la capa con más confianza. En choice, noul y score `respuestas` va vacía.

- **Cascada** (`Cascada.kt`): igual que `server/decide/cascada.go`. L0 → L1 → L2, pasa a la siguiente mientras la
  confianza top-1 sea < τ; una capa que falla o no opina se salta; si ninguna llega, `escalar = true` con la pista de
  mayor confianza y la última capa. τ: L0 = 0,80; L1 y L2 = `tau_escalate` de CALIB (0,80 y 0,70 si el fichero no trae
  CALIB).
- **τ de L2 para esquemas nuevos**: si CALIB trae `tau_l2_esquema_nuevo` (`Motor.tauL2EsquemaNuevo()`, −1 si falta), L2 lo usa
  en lugar de su τ cuando las torres de la pregunta salieron al vuelo (`SalidaCapa.esquemaNuevo`); con esquemas de ESQUEMAS o sin
  ese campo, el τ de siempre.
- **Soporte few-shot**: `Chispa.abrir(contexto, ruta, lambdaSoporteL1 = 3.0, lambdaSoporteL2 = 3.0)` llama a `AbrirConSoporte` (o a `Abrir` si ambos son los de por defecto)
  (sección SOPL1; `lambdaSoporteL1` = `Chispa.SOPORTE_POR_DEFECTO` (`Double.NaN`) por defecto: lo decide el motor (`Abrir` del puente: λ = 4 si el fichero trae `l1_lambda_calib`; un `.chispa` viejo con SOPL1 sin él queda con L1 apagado), `null` = apagado explícito de L1, un número = explícito; `lambdaSoporteL2` nulo = apagado; con `lambdaSoporteL2` y L1 por defecto, L1 va con 4 explícito (el puente no ofrece «L1 por defecto» con L2: para respetar un fichero viejo, pasar `lambdaSoporteL1 = null` o un λ propio): para apagar L1, pasar `lambdaSoporteL1 = null`; 0 = solo ejemplos; `Double.POSITIVE_INFINITY` = solo descripción).
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

## Revisión estática de los tests frente a las firmas (sin kotlinc/JDK en el nodo)
Se leyeron a mano los 10 ficheros de `chispa/src/test` y los 3 de `demo/src/test` contra `Motor`, `Capa`, `CapaL2`, `Cascada`,
`Chispa.montar/soporteDe`, `CacheFicheros`, `abrirConRespaldo`, `Medidor.medir` y `ConfigMedida` (nombres de parámetros,
número y orden, tipos, valores por defecto, `internal`, miembros de `Motor` en `MotorFalso`). Arreglado: `Medidor.FallosCapa`
está declarada dentro del `companion`, y los tests la citaban como `Medidor.FallosCapa()` (se usa `Medidor.Companion.FallosCapa()`);
`MotorFalso.textosTorreL2` lleva ahora el tipo de retorno explícito. No se cambió ninguna API.
Sigue sin asegurarse (nadie lo compiló):
- Conversión SAM de lambdas a parámetros `fun interface` anulables (`Tokenizador?`, `CodificadorTorre?`) en `Chispa.montar` y `CapaL2(...)`: válida en Kotlin ≥ 1.4, pero no comprobada con la versión del proyecto.
- `Medidor.Companion.FallosCapa` desde el test del demo y `Medidor.medir` (`internal`): mismo módulo de test, pero sin compilar.
- Que `android.util.Log` lance `RuntimeException` en la JVM de test (el código lo captura); `unitTests.isReturnDefaultValues` no está activado.
- El resultado numérico de los tests (se razonó a mano la traza de cada uno, no se ejecutó).
- `androidTest/MedirP99Test.kt` queda fuera de este repaso.
Verificar con: `cd sdk/android && ./gradlew :chispa:testDebugUnitTest :demo:testDebugUnitTest`.

## Tipo `multi` (revisión estática, sin JDK)
Cambios: `Pregunta.tipo` admite `"multi"`; `SalidaCapa.respuestas: List<String>?` (null salvo que el JSON del motor traiga `answers`;
al final de los parámetros, con valor por defecto); `SalidaCapa.opina` acepta `respuesta == ""` si `respuestas != null`
(«ninguna activa»); `Respuesta.respuestas: List<String> = emptyList()` (último parámetro, con valor por defecto: las llamadas
posicionales de antes compilan igual); `Cascada.decidir` la rellena con la de la capa que acepta o la de la mejor pista.
Tests: `MultiTest.kt` (9) con `jsonMulti` y `PREGUNTA_MULTI` de `Falsos.kt`. Revisadas a mano las firmas: `SalidaCapa.copy` conserva
`respuestas` (lo usa `CapaL2`), `List(n) { aj.getString(it) }` sobre `JSONArray`, `orEmpty()` sobre `List<String>?`.
Sin compilar ni ejecutar. Verificar con: `cd sdk/android && ./gradlew :chispa:testDebugUnitTest --tests '*MultiTest'`.

**score y `escalateReason`.** Un `score` solo vale con ids exactamente `1..K` (en cualquier orden); con otros ids ninguna capa opina. `Respuesta.escalateReason` (nulo/`nil` si no escaló o escaló por el fallo de una capa) trae, igual que `escalate_reason` del servidor: `sin_opinion`, `baja_confianza` o `score_ids_no_validos`.

## Licencia

Apache-2.0 (ver `LICENSE` de la raíz del repositorio). Las atribuciones de terceros están en `NOTICE`. Los datasets con SA, NC o con términos pendientes
(XNLI, clima, datos.gov.co, SIB-200, etiquetas de ALIA, salidas de Haiku) no se redistribuyen y solo se usan como test.
