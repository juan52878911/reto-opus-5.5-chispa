# Pesos y licencias: qué datos entraron en el entrenamiento de cada checkpoint (2026-11-03)

Antes de publicar pesos con Apache-2.0. Auditoría de solo lectura del código con que se lanzó cada ajuste (`80ab8ef` ajuste 1,
`23b38e6` v2, `ff35977` v3) y de los resultados en git. No se abrió `data/` ni `models/`.

## Conclusión
- **Ningún L2 entrenado (G.8, ajuste 1 = línea base oficial, v2, v3) es publicable bajo Apache tal cual.**
  - **Motivo:** SIB-200 (CC-BY-SA-4.0) entró en train.
    - En el ajuste 1, v2 y v3: 701 filas por `--datos`, porque `model/datos/sib200.py:15` tiene `COMERCIAL = True` desde siempre.
    - En G.8: otras 701 por el meta (`model/meta/sib200_es.py`; `model/meta/resultados/conversion-20261027.json`: `sib200 choice train 701`).
    - El recuento cuadra: 128 828 filas locales del ajuste − 78 726 de G.8 = 49 401 (PAWS-X train) + 701 (SIB-200 train).
  - **El origen del error:** `LICENCIAS.md` marca SIB-200 como `uso_comercial: true` con «SA sin decidir por Juan». El inventario de `sdk` lo da por «solo test», y no lo es.
  - **Para publicar hay que:**
    1. pasar SIB-200 a solo test, con `COMERCIAL = False` en `sib200.py` y también en `meta/sib200_es.py`;
    2. reentrenar G.8 sin él y repetir los ajustes encima.
  - **La alternativa** es que Juan decida que SA en train no contamina los pesos.
- **Los filtros sí funcionan.**
  - `model/l2/entrenar.py:97-100` carga solo `split="train"` con `solo_comercial=True`, y `model/l2/datos.py:252` hace lo mismo en el meta.
  - Por eso XNLI (NC), clima (NC-SA), ALIA (etiquetas de LLM) y las PQRS de datos.gov.co (SA), marcadas solo test, **no entraron**.
  - El fallo es solo el marcado de SIB-200.
- **Quedan dudosos, aunque no bloquean igual:**
  - **El meta tasksource** (tsjev, 171 172 filas en el ajuste 1; tsjev y tsinst en G.8): el filtro `validar.py` quita NC/ND pero no SA. Falta la licencia por tarea del `sources.yaml`.
  - **Las blandas del maestro Qwen** (Qwen3.5-4B): falta verificar su licencia en la tarjeta.
  - **Clandestino**, solo en v3: es MIT, pero con condiciones de uso de Microsoft.
- **Haiku no entra en ningún entrenamiento:** su corpus no está en `--datos` y `maestro/README.md` dice «Haiku nunca».
- **e5, potion y los L0 de ejemplo:** publicables, con el aviso MIT (pendiente de confirmar en las tarjetas).
- **Binarios en git:** todos son fixtures (pesos aleatorios o datos inventados o sintéticos); ninguno sale de un entrenamiento real.

## Checkpoint × dataset

| checkpoint | dataset (split que entró) | licencia | ¿publicable bajo Apache? | prueba |
|---|---|---|---|---|
| G.8 (`general-20261029b`; base de v1, v2 y v3) | e5-small (inicialización) | MIT (tarjeta sin verificar) | sí, con aviso | `model/l2/modelo.py:20`; `sdk/NOTICE` |
| G.8 | locales: clinc150, toxicidad ×2, goemociones-es, spam tanaos, soporte_ti, ciberacoso, herramientas (train) | CC-BY-3.0/4.0, Apache, MIT, propio | sí, con atribución | `general.sh` (`--datos --herramientas`); 78 726 filas |
| G.8 | massive, hatecheck, inyecciones | Apache / CC-BY | no entran (excluidos) | `general.sh` `EXCLUIR`; `entrenamiento.json` |
| G.8 | meta tsjev (train, «commercial» según tasksource) | por tarea; SA no filtrado | **dudoso** | `conversion-20261027.json`: 469 112 filas, 421 tareas |
| G.8 | meta tsinst (175 tareas «commercial») | por tarea | **dudoso** | `general-20261029/conversion-instruct.json`: 689 392 filas |
| G.8 | meta synzs (sintético de Mixtral) | Apache-2.0 | sí | `model/meta/synthetic_zeroshot.py` |
| G.8 | meta pawsx-es (train) | libre para cualquier uso | sí | `conversion-20261027.json` |
| G.8 | **meta sib200-es (train, 701)** | **CC-BY-SA-4.0** | **no** | `model/meta/sib200_es.py`; `conversion-20261027.json` |
| G.8 | blandas del maestro Qwen3.5-4B | Apache según un comentario; tarjeta sin verificar | dudoso | `maestro/resultados/ronda1-18000.json`; `blandas: 512944` |
| **ajuste 1 = línea base oficial** | todo lo de G.8 (arranca `--desde` G.8) | ver G.8 | ver G.8 | `ajuste.sh@80ab8ef`; `estado.tsv` |
| ajuste 1 | locales de G.8 más pawsx (train, 49 401) | libre | sí | 128 828 − 78 726 |
| ajuste 1 | **sib200 (train, 701)** | **CC-BY-SA-4.0** | **no** | `sib200.py@80ab8ef:15`; `estado.tsv` «16 fuentes (sib200 pawsx …)» |
| ajuste 1 | meta tsjev (train, 171 172) | por tarea | **dudoso** | `ajuste-20261029/entrenamiento.json` |
| ajuste 1 | blandas Qwen (ronda1) | sin verificar | dudoso | `blandas: 178365` |
| ajuste 1 | XNLI, clima, ALIA, PQRS ×4 | NC / NC-SA / etiquetas de LLM / SA | no entran (solo test, filtro aplicado) | `xnli.py`, `clima.py`, `odio_alia.py`, `pqrs_comun.py` |
| ajuste 1 | aumento (`--aumento`) | por reglas, sin LLM | sí | `model/l2/aumento.py` |
| v2 (`ajuste-v2-23b38e6`) | lo mismo que el ajuste 1 | idem | idem (con sib200) | `ajuste.sh` 80ab8ef→23b38e6: solo texto_torre y épocas |
| v3 (`v3-ff359773`) | lo de v2 | idem | idem | `ajuste.sh@ff35977` |
| v3 | Clandestino (train 23 963, humanas y sin PII) | MIT más condiciones de uso de Microsoft | **dudoso** | `ajuste-v3-20261102/LEEME.md` |
| L1 potion | modelo de terceros, re-codificado sin entrenar | MIT (sin verificar; destilado de bge-m3) | sí, con aviso | `runtime/l1/exportar.py`; `sdk/NOTICE` |
| e5 multilingual-small | — | MIT (sin verificar) | sí, con aviso | `sdk/NOTICE` |
| L0 de los ejemplos | ejemplos inventados (`sdk/python/ejemplos/`, `pilotos/esquemas/ejemplos/`) | propios | sí | `pilotos/esquemas/README.md` |

El `.chispa` oficial de 945 MB solo añade 16 frases inventadas al checkpoint. Su `META.licencias` sale del esquema y no del
entrenamiento (`sdk/python/chispa/train.py:349`), así que **no sirve como prueba de licencias**.

## Veredicto por checkpoint
| peso | veredicto |
|---|---|
| G.8 | **no publicable**: sib200 en el meta |
| ajuste 1 (línea base oficial) | **no publicable**: sib200 en datos y en G.8. Reentrenar sin él; luego revisar tsjev y las blandas de Qwen |
| v2 | **no publicable**: mismos motivos |
| v3 | **no publicable**: mismos motivos, más Clandestino por decidir |
| L1 potion, e5 | publicables con aviso MIT, tras confirmar las tarjetas |
| L0 de los ejemplos | publicables |

## Binarios de pesos en git (todos fixtures)
| fichero | bytes | qué es | ¿publicable? |
|---|---|---|---|
| `server/torre/testdata/sintetico.onnx` | 4 536 655 | pesos aleatorios | sí |
| `server/decide/testdata/l2_sintetico.onnx` | 4 005 423 | pesos aleatorios | sí |
| `server/decide/testdata/l2_sintetico_ml256.onnx` | 21 417 | pesos aleatorios | sí |
| `server/testdata/{intencion,injection,urgencia}.chispa` | 29 127 / 9 016 / 18 104 | L0 de la Arena con datos sintéticos; el generador no está en el repo | probablemente sí; origen sin verificar |
| `format/chispa3/testdata/{injection,urgencia}.chispa` | 9 016 / 18 104 | copias de los anteriores | idem |
| `server/decide/testdata/dorados/l0l1.chispa` | 20 237 | L0 `injection` más un L1 falso | idem |
| `server/decide/testdata/dorados/l0tf.chispa`, `l0tf/modelo*.l0tf` | 42 289 | TF-IDF sobre frases inventadas | sí |
| `server/decide/testdata/dorados/l2.chispa` | 717 | ONNX falso | sí |
| `server/testdata/caida/*.chispa`, `format/chispa3/testdata/l0multi.chispa` | 3–28 KB | partidas generadas de Caída | sí |
| `server/decide/testdata/conj-v2.chispa`, `server/torre/testdata/torre_train.chispa` | 42 937 / 52 979 | tarea inventada con torre sintética | sí |
| `server/decide/testdata/calib-score.chispa`, `model/l2/tests/fixtures/calib-score.chispa` | 1 133 | CALIB ajustado con JevBench (MIT) | sí, con aviso MIT |
| `model/l2/tests/fixtures/esquemas-v2.chispa`, `format/chispa3/testdata/*` (resto) | < 3 KB | fixtures del formato | sí |

## Qué falta para cerrar
- **Filas exactas por fuente del ajuste 1:** están en `convertir.log` y `log.txt` dentro de `s3://…/ajuste-80ab8ef/resultados.tgz`.
- **Licencia por tarea de tsjev y tsinst:** hace falta el `sources.yaml` del dataset de tasksource.
- **Contenido y licencia de las 512 944 blandas de G.8:** `s3://…/maestro-20261027/ronda1/blandas.tgz` y la tarjeta de Qwen3.5-4B.
- **Commit exacto de G.8:** no aparece en su LEEME.
- **Tarjetas de e5, potion y bge-m3, y el generador de la Arena:** sin leer.
