# Paridad Android ↔ iOS

Comparado a mano, fichero a fichero (`sdk/android/chispa/src/main/kotlin/com/chispa/sdk/*.kt` ↔ `sdk/ios/Sources/Chispa/*.swift`)
y sus tests. Ni Kotlin ni Swift se han podido compilar en el nodo de desarrollo (sin JDK, Android SDK, `swiftc` ni Xcode):
esta tabla sale de leer el código, no de ejecutarlo. Líneas de después de W3.

`K:` = Kotlin (`Capas.kt`, `Cascada.kt`, `Chispa.kt`, `Modelos.kt`), `S:` = Swift (mismos nombres, `.swift`).

| # | Comportamiento | Android | iOS | Estado |
|---|---|---|---|---|
| 1 | L0 (y L0TF: el motor elige TF-IDF si el fichero trae L0TF, el SDK solo pasa la pregunta) | K:Capas 60 | S:Capas 63 | igual |
| 2 | L1 (L1-zs con descripciones: las torres de texto «pregunta · opción · descripción» las calcula y cachea el motor Go) | K:Capas 66 | S:Capas 71 | igual |
| 3 | L2: sin torres no tokeniza ni llama a ONNX; sin tokens no opina | K:Capas 130-134 | S:Capas 140-146 | igual |
| 4 | L2c/CONJ: con `tieneConj` y probs de L0, la cabeza decide; si no opina, cae a `puntuarL2` | K:Capas 136-141, 156 | S:Capas 148-152, 169 | igual |
| 5 | Ranuras a float32 little endian; validación K×d | K:Capas 99 | S:Capas 108 | igual (Kotlin lanza `IllegalArgumentException`, Swift `precondition`; la entrada ya la validan `SesionOrt` en ambos) |
| 6 | Tokenizador del motor (int32 LE → ids) | K:Capas 78 | S:Capas 91 | arreglado (si el motor no tiene tokenizador Kotlin lanzaba `ErrorChispa`; Swift devolvía `[]` y L2 callaba. `Tokenizador.ids` ahora `throws`) |
| 7 | `Motor.tieneTokenizadorE5` | K:Capas 43 | S:Capas 23, MotorNativo 39 | arreglado (faltaba en el protocolo y en `MotorNativo`) |
| 8 | Cascada: orden, «la mejor pista», `escalar`, capa de escalada = la última | K:Cascada 30-48 | S:Cascada 30-47 | igual |
| 9 | Capa que lanza → sin opinión y sigue (Kotlin `catch Exception`, Swift `try?`) | K:Cascada 38 | S:Cascada 36 | igual |
| 10 | τ por defecto (L0 0,80, L1 0,80, L2 0,70) | K:Cascada 7 | S:Cascada 10 | igual (`TauPorDefecto.de(nombre)` solo existe en Kotlin y no lo usa nadie) |
| 11 | τ de CALIB para L1 y L2, nunca para L0 | K:Cascada 55-61 | S:Cascada 50-56 | igual |
| 12 | Sin ninguna capa utilizable → `ErrorChispa` | K:Cascada 62 | S:Cascada 57 | igual |
| 13 | `capas` (L2 solo si hay sesión) | K:Chispa 27 | S:Chispa 29 | igual |
| 14 | Abrir: tokenizador de la app o del motor (`rutaTokenizador`); extracción del ONNX con caché por nombre/tamaño | K:Chispa 43-62, 112 | S:Chispa 32-55 | igual (Android resuelve además assets; en iOS la ruta es un fichero del bundle) |
| 15 | Cierre: Kotlin cierra sesión y motor, y la sesión si falla `montar`; Swift cierra el motor en `deinit` y ORT libera su sesión por ARC | K:Chispa 33, 81 | S:Chispa 26 | igual (por plataforma) |
| 16 | Errores: `desdeJson` (JSON ilegible, `ok:false` → `ErrorChispa(error)`, sin opinión) | K:Modelos 34 | S:Modelos 59 | igual |
| 17 | JSON de la pregunta (`question`, `kind`, `options[id,description]`; la descripción vacía se omite) | K:Modelos 15 | S:Modelos 24 | igual |
| 18 | Zero-shot L1: pregunta con esquema nuevo y descripciones → L0 sin modelo (sin opinión), L1-zs decide | K:Capas 66 | S:Capas 71 | igual (no hay código nuevo: el esquema viaja en `Pregunta`; test `CascadaZeroShot…`) |
| 19 | Zero-shot L2: torres al vuelo con `CodificadorTorre` la primera vez, el motor las cachea; la segunda no codifica | K:Capas 119-156 | S:Capas 129-167 | arreglado (faltaba en los dos; añadido con tests; necesita soporte de `chispamovil`, ver abajo) |
| 20 | Few-shot: esquema entrenado dentro del `.chispa` (L0/L0TF + ESQUEMAS); no calcula torres | K:Capas 132 | S:Capas 142-144 | igual (test `fewShot…`) |
| 21 | `Chispa.abrir/montar` aceptan `codificadorTorres` (opcional, por defecto nil: la API existente no cambia) | K:Chispa 43, 66 | S:Chispa 32, 58 | arreglado |

Resumen: 21 filas → 17 igual, 4 arregladas (6, 7, 19, 21), **0 faltan** en los SDK. Lo abierto está en el motor Go
(sección siguiente), no en la paridad.

## Contrato nuevo con el motor (zero-shot L2)

`Motor` gana dos métodos con implementación por defecto (vacío / `false`): no rompen a `MotorNativo` actual ni a motores
de prueba.

- `textosTorreL2(preguntaJson) -> [String]`: textos «passage: pregunta · opción · descripción» cuyas torres faltan (con las
  reglas de `server/decide/l2.go:torresNuevas`: una por opción en choice, una en noul/score). Vacío si ya las tiene
  o no sabe pedirlas.
- `instalarTorresL2(preguntaJson, torres: bytes, n) -> Bool`: `n` vectores float32 LE; el motor los cuantiza
  (`cuantizarTorre`) y los cachea por `ClaveEsquema`. A partir de ahí `torresL2` da true.

Flujo en `CapaL2.decidir`: `torresL2` false → con codificador, `textosTorreL2` → `codificador.torre(texto)` por texto →
`instalarTorresL2` → sigue como siempre (tokeniza, ranuras, CONJ o `puntuarL2`). Un fallo del codificador no cachea nada
(se reintenta en la siguiente pregunta); L1 se evalúa antes y, si llega a su τ, no se calcula ninguna torre.

### Qué necesita `chispamovil` (no tocado aquí: está fuera de mi zona)
1. `TextosTorreL2(preguntaJSON string) string` (JSON de `[]string`) y `InstalarTorresL2(preguntaJSON string, torres []byte, n int) bool`;
   `TorresL2` debe pasar a true con las instaladas. Si prefiere calcular las torres dentro de Go, basta con que
   `TorresL2` dé true y el SDK no llama a nada.
2. El codificador de torres no existe en el móvil: `server/decide/l2.go` dice que el ONNX del `.chispa` solo exporta las
   ranuras S; hace falta un segundo ONNX (e5 de pasaje + cabeza de torre) y `tokenizarE5` con prefijo «passage: ».
   Cuando exista, se implementa `CodificadorTorre` con ORT (una sesión nueva como `SesionOrt`).
3. Mientras no exista (1), `MotorNativo` usa los valores por defecto y L2 sigue sin opinar con esquemas nuevos; L1-zs ya
   funciona con el motor actual (`chispamovil.go` `torres()` cachea por esquema).
