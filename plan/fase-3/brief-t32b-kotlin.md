# T3.2b Arreglar la compilación de Kotlin del SDK de Android

Sigue a T3.2 (`sdk/android/`). En AWS, el AAR de gomobile se construyó, pero Kotlin falla. El log entero está en
`sdk/android/aws/resultados/c6a-intento1.log`:

```
Chispa.kt:42:31 No value passed for parameter 'onnx'.
Chispa.kt:42:46 Argument type mismatch: actual type is 'kotlin.String', but 'com.chispa.sdk.SesionRanuras' was expected.
```

Gradle tampoco ejecutó ningún test JVM.

## Terminado cuando
- `Chispa.kt:42` construye el objeto de L2 con los tipos correctos: abre la `SesionRanuras` (ORT) a partir de los bytes de
  la sección L2 y pasa el parámetro `onnx` que falta.
- Revisa **a mano todos los ficheros Kotlin** buscando el mismo tipo de error de firmas: aquí no hay `kotlinc`, así que no
  hay compilador que lo detecte. Cruza cada llamada con la declaración.
- Que los tests JVM se ejecuten de verdad. Si `./gradlew test` no encuentra tests, revisa `src/test/kotlin`, el
  `testImplementation` y que el plugin `com.android.library` tenga `unitTests` activado. Con un test basta para comprobarlo.
- `cd sdk/movil/chispamovil && go test ./...` sigue en verde, igual que `bash -n sdk/android/aws/arranque.sh`.
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- Solo `sdk/android/`. Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Sin red salvo la API de Claude.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.

## Tope
- ≤ 45 min de reloj · ≤ 2 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 8 líneas: qué cambiaste, la rama y el sha, y qué otras llamadas revisaste.
