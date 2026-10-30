# Rendimiento y límites

Todo lo de aquí es medido y lleva su fuente. Lo que no se midió, se dice: «sin medir».

Chispa es un clasificador de propósito general. massive, clinc150, hatecheck, inyecciones, herramientas, spam e injection
son **benchmarks**: pruebas de que cada modo funciona, no el objetivo del producto. Ninguna cifra de abajo es de tu tarea.

## Por modo
| Modo | Qué se midió | Cifra | Fuente |
|---|---|---|---|
| Zero-shot (L1) | macro-F1 medio en 5 tareas, con potion | 0,455 | [`informe.md`](../model/l1/resultados/2026-10-28/informe.md) |
| Zero-shot (L1) | macro-F1 en massive y clinc150, con potion | 0,406 y 0,445 | [`informe.md`](../model/l1/resultados/2026-10-28/informe.md) |
| Zero-shot (L1) | macro-F1 medio con el L1 propio de 256 dim | 0,353 | [`informe.md`](../model/l1/resultados/2026-10-28/informe.md) |
| Zero-shot (L2, torre al vuelo) | cableado (`TORR` + `-tags ort` + `-tok`); sin paridad del ONNX real | sin medir | [08](08-esquemas-nuevos.md) |
| Few-shot | prototipos de L1 con 32 ejemplos por clase, macro-F1 medio en 5 tareas | 0,654 con potion | [`informe.md`](../model/l1/resultados/2026-10-28/informe.md) |
| Few-shot | L0 con 50 ejemplos por clase en un sondeo de 13 clases | 0,821 (L0), 0,762 (cascada L0 → L1, lo escalado cuenta como fallo) | [`sdk/python/README.md`](../sdk/python/README.md#punta-a-punta-intención-del-sondeo-50-por-clase) |
| Few-shot con k = 5 por opción | `chispa train` sin `--conjunta` | sin medir | — |
| Few-shot con soporte `SOPL1` | mezcla del prototipo con la media de los ejemplos (`--shrinkage-lambda`); efecto de λ en la calidad | sin medir | — |
| Zero-shot en `score` | L1 con la mediana de la distribución sobre niveles | sin medir | — |
| Con datos del cliente | macro-F1 por `/v1/decide` en massive y clinc150 | 0,814 y 0,887 | [`e2e-20261028/LEEME.md`](../server/deploy/resultados/e2e-20261028/LEEME.md) |

## Zero-shot
Lo que hay que saber antes de usarlo:
- **Es flojo.** Con potion, el macro-F1 medio es 0,455 en cinco tareas. En clinc150 (150 clases) es 0,445 y en massive 0,406
  ([`informe.md`](../model/l1/resultados/2026-10-28/informe.md)). Pasa de 0,45 a 0,65 al dar 32 ejemplos por clase.
- **Decide L1; L2 solo con `TORR`.** Un esquema que llega en la petición, sin `.chispa` propio, lo decide L1. Si el `.chispa` trae `TORR`, L2 calcula la torre al vuelo
  (requiere `-tags ort` y `-tok`); no hay cifra de L2 en tareas no vistas: sin medir ([08](08-esquemas-nuevos.md)).
- **Las descripciones son la señal.** Opciones parecidas o descripciones vagas bajan la calidad. No hay una medida del efecto: sin medir.
- **τ sin calibrar.** El `CALIB` del zero-shot usa τ = 0,6; sus probabilidades no están calibradas.
  El ECE en zero-shot: sin medir.
- **`score` en L1 es ordinal por descripciones.** L1 compara el mensaje con «pregunta · nivel · descripción» de cada nivel (en el orden de la pregunta), hace el softmax de cosenos / T
  y responde con la mediana de esa distribución; `probs` trae un valor por nivel, como L2. Un nivel sin descripción no tiene señal y confunde a L1.
  Si la masa se reparte entre niveles lejanos, la confianza de la mediana baja de τ y escala. La T es la de `score` en `CALIB` o, si falta, la de `choice`. No es una cabeza CORAL: sin medir la calidad en score zero-shot.
- **Latencia de L1 por HTTP con el potion real: sin medir.** La de `Embed` sí: 25 µs p50 y 74 µs p99 a 16 tokens, 110 µs y 268 µs a 64
  ([`informe.md`](../model/l1/resultados/2026-10-28/informe.md)).
- Las cifras de arriba son de tareas en inglés y español con una sola semilla. Colombia, ferretería, PQRS: sin medir.
- Si el costo de un error es alto, usa zero-shot con revisión humana de lo que escala, y pasa a few-shot cuanto antes.

## Con datos del cliente: calidad de punta a punta
Macro-F1 por `/v1/decide`, modo forzado, con la cascada de producción (`chispa train --conjunta`: L0TF + L2c).
Referencia: la cabeza conjunta en Python (`conjunta.py`).

| tarea | `/v1/decide` | cascada | `conjunta.py` | Δ |
|---|---|---|---|---|
| massive | 0,814 | 0,814 | 0,817 | −0,2 |
| clinc150 | 0,887 | 0,886 | 0,890 | −0,3 |

Fuente: [`e2e-20261028/LEEME.md`](../server/deploy/resultados/e2e-20261028/LEEME.md#intento-5-tras-la-ablación-t45b-y-el-l0-tf-idf-en-el-servidor-t45c-h2-se-cumple).

Líneas base con 32 ejemplos por clase, para ponerlas en contexto ([fase 1](../model/informes/fase-1.md#líneas-base-t17a)): MASSIVE es 0,678 con L0 solo,
CLINC150 0,811. Ninguna tarea llega a 0,9.

## Latencia
En una c6a.xlarge, 1 cliente, cascada ([misma fuente](../server/deploy/resultados/e2e-20261028/LEEME.md)):

| | cifra |
|---|---|
| L0 (TF-IDF) responde | 54–57 % de las consultas, p99 de 0,2 ms |
| L2c responde el resto | p99 de 9,8–11 ms |
| p99 total en el cliente | 9,6 ms en massive y 11,3 ms en clinc150 |

L2: 48 MB y 20 ms de p99 a 64 tokens en AVX2 ([fase 2](../model/informes/fase-2.md#criterios), criterio T2.6).

## Rendimiento del servidor
Medido en una microVM de 4 vCPU (Xeon 3,3 GHz), con stubs en L1–L3 y un modelo de 4 clases. Es una cota, no un objetivo:
el cliente de carga comparte la máquina y el ruido es de ±30 %
([`server/README.md`](../server/README.md#medidas-microvm-kindling-de-4-vcpu-xeon-33-ghz-cota-del-i3-no-el-objetivo)).

| Prueba | decisiones/s | p50 | p99 |
|---|---|---|---|
| HTTP, 1 pregunta por petición, 8 conexiones, 1 núcleo | 2 176 | 2,6 ms | 17,0 ms |
| HTTP, 16 preguntas por petición, 8 conexiones, 1 núcleo | 11 323 | 9,6 ms | 38,1 ms |

El lote amortiza el coste de HTTP y JSON. El objetivo del plan (≥ 5 k/s con L1 en un i7) no se confirmó.

## Carga del arnés
El arnés [`server/carga/`](../server/carga/README.md) corrió una vez, 10 s por punto y una tanda, en un i7-1255U (12 hilos lógicos) con **L2 en stub**
(sin ORT, modelo ni tokenizador), L0 con los `.chispa` de `testdata` y `textos.txt` (260 frases). Con el máximo de loadavg en 12,07 durante la corrida: es una cota ruidosa.
Fuente: [`resultados-…-20261028-210630.md`](../server/carga/resultados/resultados-MPC-NVKLGOK5UGQ-20261028-210630.md).

| modo | conexiones | decisiones/s | p50 | p99 | objetivo del arnés |
|---|---|---|---|---|---|
| `l1` (L1 es stub aquí) | 1 | 1 531 | 0,64 ms | 1,10 ms | no cumple |
| `l1` | 4 | 4 709 | 0,82 ms | 1,48 ms | no cumple |
| `l1` | 16 | 10 432 | 1,40 ms | 3,85 ms | cumple |
| `l1` | 64 | 19 797 | 2,67 ms | 9,87 ms | cumple |

- Esa corrida **no mide L1 real ni L2 real**: sin modelo, la capa «L1» es un stub y el modo `l2` acaba en «escalar» (sus filas están en el CSV y no valen como cifra de L2).
- Con `textos-es-co.txt` (2 400 mensajes en español de Colombia), con ORT y con modelos: sin medir. Tampoco se midió si la latencia de L1 depende de la longitud del texto.
- Microbenchmarks sin HTTP ([`server/BENCH.md`](../server/BENCH.md), i7-1255U, `-benchtime 2s`): L0 TF-IDF con 150 clases 35,2 µs; L1 en lote de 16 (modelo de prueba)
  70 µs; cabeza L2c 1,13 ms; cascada y handler `/v1/decide` 9,2 µs con 1 hilo. L2 con e5 y ONNX: no se mide ahí.
- WASM (node v22, microVM compartida, L1 recortado): p50 de 238 µs a 16 tokens, 397 µs a 64 y 1,42 ms a 256, con p99 de 2,7 a 3,5 ms; en Chrome, sin medir
  ([`demo/wasm/README.md`](../demo/wasm/README.md#latencia-cota-en-node-v22-wasm-microvm-de-4-vcpu-compartidas)).
- Android «Medir» e iOS: sin medir en dispositivo. Imagen de kindling (tamaño, memoria): sin medir. Audio: diseño sin modelos ni medidas ([`audio/DISENO.md`](../audio/DISENO.md)).
- Piloto en Colombia (PQRS, EPS, ferretería): sin medir; el kit pide medirlo en la semana 4 ([`pilotos/metrica.md`](../pilotos/metrica.md)).

## Few-shot: tiempos de entrenamiento
`chispa train` con 13 clases × 50 ejemplos: 1,0 s para META + L0 + CALIB y 3,5 s con L1 (154,9 MB de fichero). En esa corrida, L0 solo
tiene un macro-F1 de 0,821 y la cascada L0 → L1 resuelve el 81 % con un 94 % de acierto. Una corrida, 390 filas de test: ±2 puntos
([`sdk/python/README.md`](../sdk/python/README.md#punta-a-punta-intención-del-sondeo-50-por-clase)).
El tiempo de `--conjunta` con un checkpoint real no está medido en este README; lo da `informe["conjunta"]["s"]`.

## Calibración (T2.4) y excepciones de G2
Cifras de la cabeza conjunta ([fase 2](../model/informes/fase-2.md#t24-con-el-criterio-por-tarea-cifras-de-t22d-cabeza-cvtest-sin-cómputo-nuevo)).
Criterio: ECE ≤ 0,05.

| tarea | macro-F1 | ECE | cobertura a p 0,95 | resultado |
|---|---|---|---|---|
| clinc150 | 0,891 | 0,022 | 80 % | cumple |
| massive | 0,818 | 0,012 | 72 % | cumple |
| herramientas | 0,734 | 0,037 | 49 % | cumple |
| inyecciones | 0,922 | 0,053 | 84 % | **no cumple por ECE** (116 filas, sin calibrar) |
| hatecheck | 0,667 | 0,060 | 7 % | **no cumple por ECE** |

Decisión de Juan del 2026-10-28: **G2 pasa con dos excepciones anotadas** ([fase 2](../model/informes/fase-2.md#cierre-de-g2-2026-10-28)).

### Excepción 1: el ECE de hatecheck e inyecciones
- **hatecheck**: ni la temperatura ni Platt bajan su ECE de 0,058. Su macro-F1 es 0,667 y su cobertura a p 0,95 es del 7 %.
  No trates sus probabilidades como calibradas.
- **inyecciones**: queda a 0,003 del criterio con 116 filas. Ese margen está dentro del ruido.
- Con tus ejemplos, la cabeza se ajusta fuera de pliegue sobre tus datos, que rinde más en hatecheck
  ([fase 2](../model/informes/fase-2.md#para-juan-g2), punto 3).

### Excepción 2: la abstención
La abstención es el porcentaje de preguntas que escalan. **Objetivo con tráfico normal: ≤ 20 %, por ahora**
([fase 2](../model/informes/fase-2.md#cierre-de-g2-2026-10-28)).

Medido con el τ de `CALIB` anterior a T4.6b, en modo cascada
([`abstencion-20261028/LEEME.md`](../server/deploy/resultados/abstencion-20261028/LEEME.md)):

| tarea | n | escala | precisión en lo contestado | τ para abstención ≤ 20 % | precisión con ese τ |
|---|---|---|---|---|---|
| clinc150 | 5500 | 46 % | 0,984 | 0,791 | 0,949 |
| massive | 2974 | 43 % | 0,969 | 0,687 | 0,928 |
| injection (Arena) | 108 | 50 % | 1,000 | 0,902 | 1,000 |
| spam (Arena) | 108 | 84 % | 1,000 | 0,812 | 1,000 |

- Con ese τ, el objetivo del 20 % **no se cumplía**: escalaba entre el 43 % y el 84 %. La causa era el τ, no el modelo.
- T4.6b hace que `chispa train --conjunta` fije `tau_l2c` fuera de pliegue al 0,95 de precisión. **No hay una medida de la abstención
  con ese τ en el repo.** Mídela con tus datos antes de ir a producción
  ([`server/deploy/abstencion/`](../server/deploy/abstencion)).
- spam e injection tienen 108 filas: mucha varianza.
- Se puede fijar el τ por tarea con `-config`: los τ de la tabla dejan la abstención en el 20 %.

## Robustez ante ataques (Arena)
ASR (tasa de ataques que engañan al detector; ≤ 0,15 pedido). El detector cascada
([`arena-20261028/LEEME.md`](../server/deploy/resultados/arena-20261028/LEEME.md)):

| dimensión | ASR | el detector escala |
|---|---|---|
| injection | 0,021 | 47 % de los ataques |
| spam | 0,021 | 83 % de los ataques |

El ASR es bajo en parte porque el detector se abstiene mucho. Esa carga pasa a L3 o a una persona.
Las corridas quedaron incompletas por el tope de tiempo (22–27 k ataques de 37 k pedidos).

## Determinismo
Misma entrada, misma salida entre el servidor Go, `chispamovil` y Python, y con 1 o 64 peticiones a la vez.
El conjunto dorado común vive en [`server/decide/testdata/dorados/`](../server/decide/testdata/dorados): tres `.chispa` pequeños
(`l0l1`: L0 + L1 diminuto; `l0tf`: L0 TF-IDF; `l2`: L2 con ONNX falso), `peticiones.json` (165: choice, noul, score y multi),
`esperado.json` (la respuesta de cada capa y de la cascada L0→L1→L2→L3 falso), `claves.json` (claves de esquema) y `ort.json` (L2 con ORT real).
Lo genera el servidor amd64: `go test ./decide -run Dorados -regenerar` (desde `server/`; con `-tags ort` y `CHISPA_ORT_LIB`
y `-run DoradosORT` regenera `ort.json`). Regenerar dos veces da los mismos bytes.

| comprobación | qué compara | tolerancia | medido |
|---|---|---|---|
| servidor, amd64 | L0, L0TF, L1, L2 (sesión y torres falsas deterministas) y cascada, en los 4 tipos | **bit a bit** | 0 |
| servidor, otra arquitectura (arm64) | lo mismo | 1e-9 (el compilador de Go fusiona `x*y+z` en FMA en arm64 y mueve el último bit de float64) | sin medir |
| `chispamovil` (`go test -run Dorados`) | `DecidirL0`, `Decidir` (L1) y `PuntuarL2` con torres instaladas, frente al dorado | 1e-9 en probs y conf; mismas `answer`, `answers` y `opina` | 0 (bit a bit en amd64) |
| Python (`tests/test_dorados.py`) | formato (CRC, sha256, reescritura idéntica), `hash_esquema2` y `clave_conj` frente al servidor, L0TF en numpy (n-gramas `char_wb` de sklearn) | claves: iguales; L0TF: 1e-9 | 4,4e-16 |
| L2 con ORT real (`-tags ort`) | ONNX sintético de consulta y de torre | 1e-6 (float32 y ORT) | 0 en la misma máquina |
| concurrencia (`TestDoradosConcurrencia`, con `-race`) | 64 goroutines con las mismas peticiones, cachés frías, calientes y de 2 entradas, frente a 1 | **bit a bit** | iguales |

- Capas: L0 (modelo de kindling), L0TF, L1, L2 y L3 falso en el servidor; en `chispamovil` las que existen allí (L0, L0TF, L1, L2 sin ONNX).
  L2c (cabeza conjunta) no está en el dorado.
- Por qué 1e-9 y no 1e-6 en lo que es solo Go: el cálculo es float64 sobre pesos int8 o float32 ya leídos; solo el FMA de arm64 puede moverlo.
  1e-6 queda para donde entra ORT o float32 de otra implementación.
- Arm64: el nodo de pruebas no tiene `qemu-user`; `GOARCH=arm64 go test -c ./decide` compila, pero el binario **no se ha ejecutado**.
  En un arm64 real hay que correr `go test ./decide -run Dorados` y `go test -run Dorados` en `sdk/movil/chispamovil`.
- No se encontró no determinismo: ni por iteración de mapas (`-count=50` en cada test), ni en las cachés de esquemas y torres (64 goroutines con `-race`), ni en el orden de las opciones (la respuesta no cambia al invertirlas).

## Qué no se midió
- Throughput con ORT, e5 y torre al vuelo, y con el potion real en el arnés de carga: sin medir.
- Latencia de L1 por HTTP con el potion real: sin medir ([`server/README.md`](../server/README.md#medidas-de-l1-real-microvm-kindling-de-4-vcpu-xeon-33-ghz-cota-del-i3)).
- Tamaño de la imagen OCI.
- Los SDK de iOS (sin compilar) y Android con L2 (L2 solo con el tokenizador del motor o de la app; sin medir en dispositivo), y los proveedores de ORT en móvil.
- El hardware de destino: las cifras son de una microVM y de una c6a.xlarge.
