# Fase 0: informe de la puerta G0

Fecha: 2026-10-27. Encargo: `plan/fase-0/encargo.md`. Todo lo midieron workers de delega con la cuenta
personal en microVM de kindling (host kling-ascci, un i3-3220 virtualizado **sin AVX2**). Gasto: unos
10,3 $ de cuenta y 0 USD de AWS.

## Decisiones

| Decisión | Resultado | Estado |
|---|---|---|
| D2: ¿modelo abierto o propio? | **e5-small propio.** Ningún abierto saca +5 puntos de macro-F1 media sobre e5 + kNN-32 y todos son 10-40× más lentos | firme en calidad; latencia pendiente del i7 |
| D3: codificador | **e5-small.** mmBERT-small va 1,3-2× más lento y su calidad no se pudo medir (la imagen no traía sus pesos) | provisional hasta medir mmBERT con pesos |
| T0.1: monorepo | Arena en `arena/` con historial; `make test` y `make smoke` en verde | hecho |

## Modelos abiertos frente a e5 (T0.4)

Macro-F1 media en 4 tareas en español (intención de MASSIVE, toxicidad de HateCheck-ES, WhatsApp de la
Arena y orquestar herramientas), 1 hilo, mismos 120 ejemplos por tarea. Sondeo congelado en `7b33239`.

| Modelo | Macro-F1 media | Δ vs e5 kNN-32 | Licencia |
|---|---|---|---|
| e5-small + kNN-32 | 75,9 | referencia | MIT |
| THX-01 | 73,3 | −2,6 | Apache 2.0 |
| e5-small + kNN-8 | 65,6 | −10,3 | MIT |
| Laya (multilingual) | 62,1 | −13,8 | Apache 2.0 |
| Julia-1 | 43,0 | −32,9 | Apache 2.0 |
| GLiClass base v3 | 30,7 | −45,3 (no concluyente) | Apache 2.0 |

- THX-01 gana en intención (93,3 frente a 87,2) y en herramientas (82,2 frente a 80,5), y pierde en
  WhatsApp y toxicidad. Sirve como **etiquetador o maestro** de intención y herramientas en la fase 1, no para servir.
- Los modelos de decisión meten las opciones en la secuencia: p50 de 0,5-5 s por petición en esta VM.
- GLiClass se reimplementó sin su paquete: su cifra puede ser un error del arnés.
- Con 120 ejemplos, diferencias de ±3 puntos no son concluyentes; las de 10 o más sí.
- WhatsApp y herramientas son datos sintéticos que favorecen a e5 (train y test salen de las mismas plantillas o semillas).

## Codificadores en x86 (T0.3, cota pesimista)

p99 en ms, 1 hilo (con 4 hilos va peor en esta VM), sin contar la tokenización.

| Variante | 16 tokens | 64 tokens | 256 tokens | Disco | RSS |
|---|---|---|---|---|---|
| e5-small int8, podado a 55 k | 49 | 200 | 800 | 43 MB | 127 MB |
| e5-small fp32, podado | 50 | 160 | 735 | 171 MB | 305 MB |
| e5-small fp32, sin podar | 45 | 163 | 675 | 470 MB | 877 MB |
| mmBERT-small int8, podado (pesos aleatorios) | 115 | 301 | 1597 | 64 MB | 152 MB |
| potion-multilingual-128M (static) | 0,12 | 0,16 | 0,34 | 512 MB | 1,9 GB |

- La poda a 55 k tokens mantiene el coseno medio en 0,9996 (198 de 200 frases ≥ 0,999) y deja e5 int8 en 43 MB.
  Hay que ampliar el corpus de poda para las dos frases que pierden una pieza.
- Sin AVX2, int8 no acelera. **El objetivo de p99 < 50 ms a 64 tokens no se cumple en esta máquina.**
  Es el riesgo principal para el criterio (b) de G1.

## Pendiente antes de G1

1. **Medir e5-small y mmBERT-small (con pesos) en el i7-8700T** (AVX2). Necesita que pve, o una VM suya,
   sea nodo de delega con la cuenta personal. Decide si el p99 < 50 ms a 64 tokens es alcanzable o hay que
   cambiar el umbral o el hardware objetivo.
2. Dorado nuevo de kindling (commit `45903ef`: módulos de Go, pesos `.bin` de mmBERT, sin optimum). No cabe
   mientras sigan vivas `golden-90389` y `golden-66731`, que el clasificador no me deja borrar.
3. Ampliar el corpus de poda de vocabulario.
