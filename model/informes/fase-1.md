# Fase 1: datos y evaluación, y la puerta G1

Fecha: 2026-10-27. Encargo: `plan/fase-1/encargo.md` (con sus cambios: datos de libre uso en lugar
de etiquetado humano, corpus con un modelo abierto en lugar de Haiku, `--over-budget` solo en la
cuenta personal). Todo lo hicieron workers de delega con la cuenta personal en kindling, más
instancias de AWS que se apagaron solas.

## Qué hay

| Pieza | Estado | Dónde |
|---|---|---|
| Esquema de filas v1.1 (choice, noul, score; `blanda`, `anotadores`) | congelado | `model/esquema.md` |
| Arnés `chispa eval`: exactitud, macro-F1, ECE, Brier, cobertura a 0,95 y 0,99, AUROC del escalate, latencia, deriva; adaptadores de la Arena y de JevBench | hecho | `model/evaluacion/` |
| Conversores: MASSIVE es, HateCheck-ES, CLINC150, deepset, XNLI (solo test) y 12 fuentes en español con licencia comercial | hecho | `model/datos/` |
| PQRS reales de datos.gov.co, anonimizadas (~1 nombre visible por cada 300 filas) | solo test; nunca salen de kindling ni del bucket | `model/datos/` |
| Tarea «orquestar herramientas» (System One): catálogo y 368 casos de test | hecho | `model/herramientas/` |
| Listón humano: MultiPICo, ALIA (3 anotadores), toxicity-ES y GoEmotions, con el acuerdo entre humanos | hecho; sustituye al etiquetado a mano | `model/liston/` |
| Metaentrenamiento: 3,26 M filas y 430 tareas (tasksource-jev con licencia comercial, 581 k) | en S3 | `model/meta/` |
| Maestro Qwen3.5-4B: etiquetas blandas, 18 k filas | en S3 | `model/maestro/` |
| Corpus sintético con un modelo abierto (Qwen, Apache-2.0) | **no entregado**: 3 intentos fallidos | `model/corpus/` |

## Líneas base (T1.7a)

Macro-F1 en los test reales, con 32 ejemplos por clase (`model/lineas_base/informe.md`):

| Tarea | L0 (TF-IDF + logística) | e5 kNN-32 | AUROC escalate (L0 / kNN-32) |
|---|---|---|---|
| MASSIVE es | 0,678 | 0,635 | — |
| HateCheck-ES | 0,530 | 0,579 | — |
| CLINC150 | 0,811 | 0,794 | 0,912 / 0,563 |
| deepset (inyección) | 0,835 | 0,800 | — |
| Herramientas (System One) | 0,696 | 0,632 | 0,922 / 0,838 |

- Ninguna tarea llega a 0,9.
- e5 con kNN calibra mejor (ECE 0,04-0,07 frente a 0,09-0,35), pero escala mal en CLINC.
- THX-01 solo se midió en herramientas (40 filas, 0,70): sirve como orientación, no como cifra.

## Maestro (T1.6)

Qwen3.5-4B con logprob por letra, en una g5.xlarge (18 k filas, 2,3 h de GPU):
- acuerdo top-1 con el oro de 0,820 y ECE de 0,034;
- por tarea: herramientas 0,94, CLINC 0,83-0,88, toxicidad 0,85, MASSIVE 0,74.
- Queda por debajo del 0,85 que pedía el plan, por MASSIVE. En la destilación conviene mezclarlo con las
  etiquetas duras y con bge-m3-zeroshot-v2.0-c, el segundo maestro de la nota de datos de libre uso.

## Listón humano (T1.5c)

| Tarea | Filas | κ / α entre humanos | Techo humano (exactitud con la mayoría) |
|---|---|---|---|
| Toxicidad (protests-ES) | 1000 | κ 0,944 | 0,972 |
| Toxicidad (Constitution-ES) | 1000 | κ 0,654 | 0,835 |
| Odio (ALIA) | 3000 | κ 0,255 | 0,853 |
| Ironía (MultiPICo) | 4683 | α 0,238 | 0,705 |
| Emoción (GoEmotions) | 52 944 | α 0,287 | 0,376 |

En ironía, odio y emoción los humanos no se ponen de acuerdo. Ahí Chispa se mide contra la
distribución de los anotadores (log-loss o Brier sobre `blanda`), no solo contra la mayoría.

## Corpus sintético (T1.3): no entregado

Tres intentos en una g5.xlarge (≈ 2 USD en total):
1. Qwen3.5-9B con vLLM: sin memoria de GPU (A10G de 22 GB).
2. Qwen3.5-4B con vLLM: falla al arrancar porque flashinfer pide `nvcc`. Ya está arreglado el respaldo a transformers (T1.3c).
3. Qwen3.5-4B con transformers: corre 41 min, pero el 77 % de los lotes no da JSON válido. Solo salen 320 filas (whatsapp 19,
   pqrs 128, fintech 173, herramientas 0). La causa probable es JSON truncado: 20 textos por llamada y, en herramientas, el
   prompt largo del catálogo. El texto que sí sale es bueno.

Con la regla de «dos fallos, parar», queda escalado. El entrenamiento no depende de él: los datos de libre uso y el
metaentrenamiento cubren las tareas. Si se retoma: lotes de 5 a 8 textos, más `max_new_tokens`, el catálogo resumido en
herramientas y un modelo instruct (`Qwen/Qwen3-4B-Instruct-2507`) en lugar del base.

## Puerta G1

| Criterio | Estado |
|---|---|
| (a) Hay un hueco medible que L2 puede cerrar | **Sí.** Ninguna base llega a 0,9 de macro-F1. Toxicidad (0,53-0,58) y el escalate de CLINC con e5 (AUROC 0,56) son los huecos mayores, y la cobertura a precisión 0,95 queda en 0,03-0,61 |
| (b) p99 < 50 ms en el i7 con la base elegida | **Sí, por sustituto.** e5 int8 a 64 tokens da 19,3 ms en c6a (AVX2) y 10,7 ms en c6i (fase 0). La medida en el i7 real es opcional |
| (c) ≥ 2 de 5 conversaciones con clientes quieren un piloto | **Pendiente de Juan.** No hay datos en el repo ni en la bóveda |
| (d) Gasto por debajo de 15 USD | **Sí.** AWS ≈ 6 USD en total, API 0. Las cuentas de workers van aparte |

Recomendación: **seguir a la fase 2** en lo técnico. (a), (b) y (d) están en verde. El criterio (c)
es de Juan: si falla, el plan dice dejar Chispa como router System One interno, y lo hecho (servidor,
runtime L1, datos) sirve igual.

## Lo que queda abierto

- La comparación con Jev (T1.7 completo) necesita acceso a su API. No se ha medido el coste de Jev.
- ALIA (etiquetas de LLMs) y las PQRS (CC BY-SA, con nombres residuales) quedan solo en test,
  salvo que Juan diga otra cosa.
- Banking77 no tiene datos descargables en el Hub, y `somosnlp/suicide-comments-es` no es público.
- Bug de delega: el presupuesto diario suma el gasto de todos los perfiles. Hay que arreglarlo aparte.
