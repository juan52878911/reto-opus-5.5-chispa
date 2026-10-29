# Medir p99 en el móvil

La pantalla **Medir** de la demo corre N decisiones (por defecto 1.000, tras 100 de calentamiento) con 40 mensajes de
cliente en español sobre dos esquemas y por capa:

| Escenario | Qué es |
|---|---|
| `zero-shot · L1 solo` / `· cascada …` | esquema nuevo (`Medidor.ZERO_SHOT`, 5 áreas con descripciones); el motor calcula sus torres en la primera llamada (se anota aparte como `primera_llamada_ms` y no entra en los percentiles) |
| `few-shot · L1 solo` / `· cascada …` | el esquema del `.chispa` (`esquema.json`, o el de la demo por defecto) |

«L1 solo» es una cascada de una capa con τ = 0 (siempre responde L1). «Cascada» es `Chispa.abrir` completo: L0 → L1 y,
si hay tokenizador e5 y el `.chispa` trae L2/ESQUEMAS, → L2 (zero-shot en L2 necesita además TORR). El nombre del
escenario dice qué capas se montaron. Sale p50/p95/p99/máx, decisiones/s, qué capa respondió y el dispositivo (modelo,
Android, ABI, RAM, CPUs, proveedores de ORT: el SDK abre ORT con `SessionOptions()` por defecto, así que **no usa NNAPI ni
XNNPACK**; L0/L1 son Go puro).

**Importante:** el esquema few-shot solo cuenta como «del `.chispa`» si su `question` y los `id` de sus opciones son
exactamente los de ESQUEMAS (el motor busca la torre por hash de pregunta+opciones). Pon el verdadero en `esquema.json`
(`{"question": "...", "kind": "choice", "options": [{"id": "...", "description": "..."}]}`); si no, L2 no opinará
sobre él y la cascada medirá L0/L1 + escalada.

## 1. Compilar el APK
Necesitas el AAR de gomobile (`sdk/android/chispa/libs/chispamovil.aar`, no va a git) y el SDK de Android.

- **En AWS (entorno existente):** `bash sdk/android/aws/empaquetar.sh > codigo.tgz`, súbelo al prefijo S3 y lanza la
  instancia con `sdk/android/aws/arranque.sh` (ver `sdk/android/README.md`). Deja `chispa-demo-debug.apk` en el S3.
  Ya compila `:demo` (`assembleDebug`) y corre los tests JVM, incluido `EstadisticasTest`.
- **En un PC con Android SDK 34 + NDK 26.1, JDK 17, Go y gomobile:**
  ```
  cd sdk/movil/chispamovil && gomobile bind -target=android/arm64 -androidapi 24 -o ../../android/chispa/libs/chispamovil.aar .
  cd ../../android && echo "sdk.dir=$ANDROID_HOME" > local.properties
  gradle wrapper --gradle-version 8.9        # el gradle-wrapper.jar no va a git
  ./gradlew :demo:assembleDebug              # → demo/build/outputs/apk/debug/demo-debug.apk
  ```

## 2. Instalar y copiar el modelo
```
adb install -r demo/build/outputs/apk/debug/demo-debug.apk
D=/sdcard/Android/data/com.chispa.demo/files
adb shell mkdir -p $D     # si la app no se ha abierto aún
adb push modelo.chispa $D/
adb push e5.chispa-tok $D/        # tokenizador de e5 (runtime/tok/exportar.py), para L2
adb push esquema.json $D/         # el esquema few-shot del .chispa (ver arriba)
```
Alternativas: copiarlos a `demo/src/main/assets/` antes de compilar (están en `.gitignore`; el APK los trae), o en la
pantalla pulsar **Elegir .chispa** / **Elegir tokenizador** (el selector de ficheros del sistema). Orden de búsqueda:
fichero elegido → carpeta externa de la app → `filesDir` → `assets/`. (Android 11+ puede impedir a `adb push` escribir en
`Android/data`; en ese caso usa «Elegir» o los assets.)

## 3. Medir y recoger el resultado
- A mano: abre la app → **Medir** → N → **Medir**. Con el teléfono cargado, con la pantalla encendida y sin otras apps.
- Sin tocar: `adb shell am start -n com.chispa.demo/.MedirActivity --ei n 1000 --ez auto true`
- Logcat (etiqueta fija `ChispaMedir`: una línea por escenario y el JSON completo en trozos `RESULTADO_JSON i/n …`):
  `adb logcat -s ChispaMedir`
- Fichero: `adb pull /sdcard/Android/data/com.chispa.demo/files/chispa-medir-<fecha>.json` (también queda en
  Descargas en Android 10+, y el botón **Compartir JSON** lo envía como texto).
- Test instrumentado (falla si p99 > umbral; se salta si no hay `modelo.chispa`):
  ```
  ./gradlew :demo:connectedDebugAndroidTest \
    -Pandroid.testInstrumentationRunnerArguments.p99Max=150 \
    -Pandroid.testInstrumentationRunnerArguments.n=200
  ```

## ¿Qué cuenta como gama media?
Para la Fase 3 (p99 < 150 ms): un teléfono Android de unos 150–300 USD de 2021–2024, arm64-v8a, **SoC de gama media
(Snapdragon 6xx/7xx, Dimensity 700–900, Helio G85–G99, Exynos 1280)**, 4–6 GB de RAM y Android 11 o superior. Ejemplos:
Samsung Galaxy A34/A54, Xiaomi Redmi Note 12/13, Motorola Moto G (serie 73/84). Mídelo con carga normal (no en modo
ahorro, sin cargador rápido en caliente). Un gama alta o un emulador x86 no vale para la cifra de la Fase 3; los gama baja
(2–3 GB, Helio G35) conviene medirlos aparte. El JSON trae SoC, RAM y ABI para comprobarlo.
