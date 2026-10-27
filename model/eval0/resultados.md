# T0.4: modelos abiertos frente a e5-small + kNN (español, CPU)

Sondeo congelado antes de evaluar (commit 7b33239): `model/sondeo/SHA256`, hash de ese fichero
`shasum -a 256 model/sondeo/SHA256` (lista de los 8 `.jsonl`; verificada con `shasum -c` al terminar: 0 diferencias).
Tareas: `intencion` (MASSIVE es, 13 clases), `toxicidad` (HateCheck es, 2 clases), `whatsapp_comercio`
(Arena, 4 clases), `herramientas` (212 peticiones, 15 herramientas + `escalate`). Tablas completas en `resultados_tablas.md`
(generadas por `agregar.py` desde `out/*.json`).

## Veredicto sobre la hipótesis y la regla de D2
**La hipótesis se sostiene: ningún modelo abierto llega a +5 puntos de macro-F1 sobre e5-small + kNN-32 ni cabe en 50 ms.**
Media de macro-F1 en las 4 tareas (1 hilo, mismos 120 ejemplos por tarea para todos):

| modelo | macro-F1 media | Δ vs e5 kNN-32 | p99 máx (ms) | RSS pico (MB) | cumple D2 |
|---|---|---|---|---|---|
| e5-small + kNN-32 | 75.9 | — | 290 | ~1010 | (referencia) |
| e5-small + kNN-8 | 65.6 | −10.3 | 370 | ~995 | — |
| THX-01 | 73.3 | −2.6 | 5652 | ~2320 | no |
| Laya | 62.1 | −13.8 | 8775 | ~2320 | no |
| Julia-1 | 43.0 | −32.9 | 2838 | ~875 | no |
| GLiClass | 30.7 | −45.3 | 5722 | ~1555 | no |

Por tarea (macro-F1, kNN-32 → THX-01): intención 87,2 → **93,3** (+6,1), herramientas 80,5 → **82,2** (+1,7),
WhatsApp 78,1 → 64,6 (−13,5), toxicidad 57,9 → 53,0 (−4,9). THX-01 es el único que gana en alguna tarea, y es el mejor
calibrado en intención (ECE 0,067) y herramientas (0,092); en WhatsApp y toxicidad queda peor calibrado que e5 (0,33 y 0,30 frente a 0,07 y 0,16).

## Lo que hay que leer con cuidado
1. **Latencia absoluta.** Esta microVM es lenta: e5-small + kNN-32 (la referencia) da p99 de 90–290 ms según la pasada,
   así que **ningún modelo, ni siquiera e5, cumple 50 ms aquí**; la regla de los 50 ms no se puede evaluar en términos
   absolutos con esta máquina (eso es de T0.3 en la microVM x86 definitiva). Lo que sí es robusto es la razón: los modelos
   de decisión (THX-01, Laya, Julia-1, GLiClass) meten las opciones dentro de la secuencia y su coste crece con el número de
   opciones: p50 de 0,5–2 s en tareas de 2–4 opciones y de 2–5 s con 13–16 opciones, es decir 10–40 veces e5. Hay que mirar
   a ver si un x86 con AVX2 los baja 10×, pero seguirían por encima de e5.
2. **Hilos.** Con espera activa de OpenMP, 4 hilos van ~10× más lento que 1 en esta VM; con `OMP_WAIT_POLICY=passive` mejoran
   pero siguen sin ganar a 1 hilo (e5: 1 hilo ≈ 90 ms, 4 hilos ≈ 150 ms en una prueba suelta). Por eso la tabla principal es de **1 hilo**;
   4 hilos se midió en 30 ejemplos por tarea (tabla C, p99 sobre 30 ≈ máximo) y no cambia el orden.
3. **Muestra.** Los cuatro modelos lentos se evaluaron en 120 ejemplos por tarea (subconjunto aleatorio fijo, semilla 0, el
   mismo para todos, e5 incluido) por tiempo; con 120 ejemplos y 13 clases el error de la macro-F1 es de varios puntos
   (e5 kNN-32 en test completo: 87,2/55,5/77,1/80,5 frente a 87,2/57,9/78,1/80,5 en el subconjunto). Las diferencias de ±3 no son concluyentes; las de 10+ sí.
4. **Zero-shot frente a kNN.** Los modelos abiertos van zero-shot con las descripciones en español como opciones; e5 usa 8 o 32
   ejemplos etiquetados por clase. Es la comparación que pide el encargo, pero no es "mismos datos". En `herramientas` los ejemplos de
   entrenamiento son semillas a mano más envolturas de registro de esas mismas semillas, y en `whatsapp_comercio` el train y el test salen
   de las mismas plantillas de la Arena (separadas por plantilla): ambos favorecen a e5 y no son datos reales.
5. **Arreglos de compatibilidad (no se tocó código de los autores, solo mi arnés).** (a) Julia-1: su ruta especializada necesita
   transformers 5.0.x (`_update_attention_mask`); aquí hay 5.21, así que se usa el `forward` original de ModernBERT que el propio
   paquete conserva (`_julia_original_forward`); max_length 512/head 256 (defecto del autor, no 1024/512 de su informe CPU). (b) THX-01 y Laya: la
   inicialización aleatoria previa a cargar los pesos tardaba minutos en esta CPU; se envolvió en `no_init_weights` (los pesos se cargan con
   `strict=True`). (c) Laya no trae README ni código en el snapshot (la config dice «See README»): se cargó con el runtime de THX-01, porque comparten
   `rl_agent_config.json` y los pesos casan con `strict=True`; el resultado es válido solo si Laya usa realmente esa arquitectura (los pesos cargaron sin error). THX-01: checkpoint raíz;
   el subdirectorio `multilingual` que cita su código no está en el snapshot.
   (d) GLiClass: el paquete `gliclass` no está instalado y no hay red; se reimplementó la arquitectura uni-encoder desde `config.json` y los
   nombres de pesos (los pesos cargaron sin claves sobrantes ni faltantes). La implementación no se pudo contrastar con la referencia; F1 de 12–54 podría deberse a que
   el modelo es solo inglés (ModernBERT-base inglés, vocab 50 368) o a un error mío en el pooling/proyector, **sin distinguir**. Se descartó el factor exp(logit_scale) porque
   saturaba el softmax (el argmax no cambia). Tomar GLiClass como «no concluyente», no como «malo».
6. **RSS.** `ru_maxrss` por proceso (carga + inferencia, un proceso por modelo×tarea). Julia-1 es bajo porque mapea los pesos en memoria (archivo, no RSS anónimo).
   Todos caben en 4 GB; ninguno quedó «no medido».
7. **Calibración.** ECE de 15 cubos sobre la probabilidad de la clase predicha. e5: softmax(sim/0,05) ponderado sobre 10 vecinos (T no ajustada). Los modelos de decisión: su salida softmax con
   las temperaturas del autor (THX-01) o sin ellas (Laya, Julia-1: 1,0).

## Licencias
| modelo | licencia |
|---|---|
| intfloat/multilingual-e5-small | MIT (ficha del autor; no está el README en el snapshot, dato de memoria: verificar) |
| knowledgator/gliclass-modern-base-v3.0 | no consta en el snapshot (sin README ni LICENSE); verificar antes de usar |
| SupersonicLabs/Julia-1 | no consta en el snapshot (solo provenance.json); verificar |
| doofz/THX-01 | no consta en el snapshot; verificar |
| convaiinnovations/laya-multilingual | no consta en el snapshot; verificar |

Ningún snapshot en `~/hf` trae README ni LICENSE; no hay red para consultarlos. La licencia de e5 es de memoria y las otras cuatro quedan **sin confirmar**.

## Recomendación para D2
Partir de **e5-small propio** (regla de D2 no cumplida). THX-01 merece seguir mirándose solo como teacher/etiquetador de intención y herramientas
(+6 y +2 con cero ejemplos), no como modelo de servicio: 2–5 s por petición en CPU, 2,3 GB de RSS. Si se quiere cerrar la duda de latencia, repetir
solo e5 y THX-01 en la microVM x86 de T0.3.
