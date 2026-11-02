# Licencias de las fuentes (T1.1)

Regla: `uso_comercial: false` si la licencia es NC, ND o no está clara; esas filas solo van a `test`.
El conversor lee la tarjeta (`README.md`) del dataset en `~/hf` y solo da por buena la licencia esperada si la
tarjeta la confirma; si la tarjeta falta o dice otra cosa, la licencia queda «sin verificar», `uso_comercial: false`
y solo se emite `test` (test: `test_reglas.py::test_tarjeta_que_no_confirma_la_licencia_deja_solo_test`).

| Fuente | Licencia | De dónde sale | uso_comercial | Splits emitidos |
|---|---|---|---|---|
| MASSIVE es (`mteb/amazon_massive_intent`) | apache-2.0 | tarjeta en `~/hf` (`license: apache-2.0`). Ojo: MASSIVE original (Amazon) es CC-BY-4.0; ambas permiten uso comercial | true | train, dev (validation), test |
| HateCheck-ES (`Paul/hatecheck-spanish`) | cc-by-4.0 | tarjeta en `~/hf` (`license: cc-by-4.0`) | true | train/dev/test por plantilla (80/10/10); se excluyen los casos con desacuerdo de anotadores |
| Banking77 (`PolyAI/banking77`) | cc-by-4.0 | Tarjeta en `~/hf`: `cc-by-4.0` (confirmada). Pero el snapshot solo trae el script de carga y `dataset_infos.json`, sin datos: **no convertida** | true solo si la tarjeta lo confirma | train, dev (10 % de train), test |
| CLINC150 (`clinc/clinc_oos`) | cc-by-3.0 | Tarjeta en `~/hf`: `cc-by-3.0` (confirmada) | true solo si la tarjeta lo confirma | train, dev (validation), test |
| deepset/prompt-injections | apache-2.0 | Tarjeta en `~/hf`: `apache-2.0` (confirmada) | true solo si la tarjeta lo confirma | train, dev (15 % de train), test |
| XNLI es (`facebook/xnli`) | CC-BY-NC-4.0 | Fijada en el código (el plan la da como NC); no necesita tarjeta | **false** | solo test |
| NECOS-TOX | — | No está en `~/hf`: no disponible | — | — |

Comprobado con el dorado nuevo: CLINC150 y deepset convierten con licencia confirmada por la tarjeta; Banking77 no tiene datos en `~/hf` (solo script de carga que descarga de GitHub).

## Fuentes de libre uso en español y PQRS de Colombia (T1.1c)

Misma regla. Además de la cabecera YAML, `libres.licencia_estricta` lee el cuerpo de la tarjeta: si dice NC en una línea
de licencia, o `cc-by-nc` en cualquier parte, la licencia queda «contradictoria», `uso_comercial: false` y todo va a `test`.
Para datos.gov.co la licencia sale de `licenseId` del `*.meta.json`, confirmada con el enlace de términos.

| Fuente | Tarea | Licencia | De dónde sale | uso_comercial | Splits |
|---|---|---|---|---|---|
| SINAI/ALIA-es-discriminative-hate-speech | `odio` | cc-by-4.0 | tarjeta | **false: pendiente de decisión de Juan.** La etiqueta `foe_class` es una fusión de tres LLM (Apertus, Gemma, MiniMax); los términos de esos modelos pueden restringir entrenar con sus salidas | solo test (todas las filas; la muestra humana de 3000 con 3 anotadores también) |
| bgonzalezbustamante/toxicity-protests-ES | `toxicidad` | cc-by-4.0 | tarjeta | true | train/dev/test por hash del `id_obs` |
| bgonzalezbustamante/toxicity-Constitution-ES | `toxicidad` | cc-by-4.0 | tarjeta | true | idem |
| mrm8488/go_emotions-es-mt | `emocion` | apache-2.0 | tarjeta (GoEmotions original: Apache-2.0). Traducción automática (EasyNMT) | true | los de origen (ya 80/10/10) |
| tanaos/synthetic-spam-detection-dataset-spanish | `spam` | mit | tarjeta. Sintético | true | 80/10/10 por hash del texto |
| tasksource/it-support-tickets | `soporte_ti` | cc-by-4.0 | tarjeta (CC BY 4.0, Zenodo 10.5281/zenodo.7648117) | true | 80/10/10 por plantilla, estratificado |
| FelipeGuerra/Colombian_Spanish_Cyberbullying_Dataset_1 y _2 | `ciberacoso` | mit | tarjetas | true | 80/10/10 por hash del texto |
| somosnlp/spa_climate_detection | `clima` | **contradictoria** | la cabecera dice cc-by-4.0, pero el texto de la tarjeta dice cc-by-nc-sa-4.0 «por herencia de los datos» | **false** | solo test (todas las filas) |
| somosnlp/suicide-comments-es | `riesgo_suicida` | — | no está en `~/hf` | — | no disponible |
| datos.gov.co gb9w-jt96 (Alcaldía de Flandes) | `pqrs` | cc-by-sa-4.0 | `meta.json`: `CC_40_BY_SA` | **false: solo test por decisión de Juan** (SA: ver el informe) | solo test (todas las filas) |
| datos.gov.co e86p-frfd (ISVIMED) | `pqrs` | cc-by-sa-4.0 | `meta.json`: `CC_40_BY_SA` | **false: solo test por decisión de Juan** (SA) | solo test (todas las filas) |
| datos.gov.co xtj2-ipwy (Concejo de Pereira) | `pqrs` | cc-by-sa-4.0 | `meta.json`: `CC_40_BY_SA` | **false: solo test por decisión de Juan** (SA) | solo test (todas las filas) |
| datos.gov.co m3mt-c275 (Sanidad Militar) | `pqrs_enrutamiento` | cc-by-4.0 | `meta.json`: `CC_40_BY` | **false: solo test por decisión de Juan** | solo test (todas las filas) |

### Notas por fuente
- **Toxicidad (bgonzalezbustamante):** la columna `consensus` NO es la etiqueta, es una marca de acuerdo entre `coder_1` y
  `coder_2` (ambos 0 → `consensus=1`; en desacuerdo → 0; ambos 1 puede venir `NA`). Etiqueta = la de los codificadores cuando
  coinciden; los desacuerdos se descartan y se cuentan. `anotadores=2`, `blanda` = proporción de votos, `variedad` ar/cl.
- **ALIA (pendiente de decisión):** mientras Juan no decida, sirve solo para evaluar. Texto repetido se descarta (gana la fila de la muestra humana). Etiqueta humana (mayoría de 3) en la muestra.
- **GoEmotions-es:** multietiqueta; se usa la **primera** etiqueta de la lista (no «neutral»). 36 308 de 43 410 filas de train
  tienen una sola.
- **Tickets de TI:** el texto va en inglés, alemán, portugués o español; `idioma` se estima con palabras vacías.
- **Ciberacoso:** se quita el autor y las @menciones pasan a «@usuario»; los repetidos entre _1 y _2 se descartan.

### Mapeo del campo «tipo» de las PQRS
Opciones comunes: `peticion, queja, reclamo, sugerencia, denuncia, felicitacion`.
- **gb9w «Tipo de solicitud»:** Petición, Solicitud de información y Solicitud de datos personales → `peticion`; Queja, Reclamo,
  Sugerencia, Denuncia → su tipo. «Agenda tu cita» se descarta (no es un tipo de PQRS).
- **e86p «CLASIFICACIÓN»:** DERECHO DE PETICION y SOLICITUD DE INFORMACION → `peticion`; QUEJA → `queja`; SUGERENCIA → `sugerencia`.
  Se descartan DERECHO (ambiguo), QUEJA - RECLAMO (dos tipos), ENTES DE CONTROL y RECURSOS (no son tipos) y los vacíos.
- **xtj2 (una columna SI/NO por tipo):** Peticion y Solicitud → `peticion`; el resto, su tipo. Sin marca o con dos tipos distintos: descartada.
  Texto = «RESUMEN INFORMACIÓN SOLICITADA»; el nombre del peticionario sirve solo para enmascarar y no se guarda.
- **m3mt «Dependencia» (enrutamiento):** las 30 dependencias más frecuentes (agrupadas ignorando mayúsculas y acentos) y `otra`.
- Los textos idénticos comparten `plantilla` y split. Las PQRS se anonimizan (`anonimizar.py`) antes de construir la fila.

### PQRS de datos.gov.co: atribución y SA (pregunta abierta para Juan)
- **Decisión de Juan: todas las PQRS de datos.gov.co (gb9w, e86p, xtj2, m3mt / `pqrs_enrutamiento`) llevan `uso_comercial: false` y
  van solo a `test`, igual que ALIA.** Solo test por decisión de Juan; conservan ~1 nombre visible por cada 300 filas; nunca salen de kindling ni del bucket.
- CC BY-SA 4.0 (gb9w, e86p, xtj2) **obliga a atribuir**: cada entidad (Alcaldía de Flandes, ISVIMED, Concejo de Pereira), la
  licencia con su enlace y la indicación de que los datos se transformaron (anonimizados, reetiquetados). m3mt es CC BY 4.0: solo atribución.
- Si los datos convertidos se redistribuyen, van con la **misma licencia** (CC BY-SA 4.0), tarjeta con la atribución incluida.
- **Pregunta abierta:** qué implica SA para el modelo entrenado con ellos (¿obra derivada que debe compartirse igual, o uso
  de datos sin adaptación del modelo?). No se ha decidido; hasta entonces no se publican datos ni pesos derivados de esas tres fuentes.

## Español nuevo para el ajuste fino (W3)

| Fuente | Tarea | Licencia | De dónde sale | uso_comercial | Splits |
|---|---|---|---|---|---|
| Davlan/sib200 `spa_Latn` (`sib200.py`) | `tema` | cc-by-sa-4.0 | tarjeta (`license: cc-by-sa-4.0` y «CC 4.0 Commercial» en el cuerpo) | true. **SA sin decidir por Juan** (como en las fuentes PQRS): `COMERCIAL = False` en `sib200.py` lo deja en solo test. `model/meta/sib200_es.py` ya aceptaba la misma licencia | train, dev, test (el test es el de M4: no entra en train) |
| google-research-datasets/paws-x `es` (`pawsx.py`) | `parafrasis` | libre para cualquier uso (Google) | tarjeta: `license: other` y «may be freely used for any purpose»; sin esa frase queda «sin verificar» y solo test | true | train, dev (validation), test (el de M4: no entra en train) |

`odio_alia` sigue en solo test (pendiente de Juan, ver arriba): el ajuste no la usa. `toxicidad_protestas` y `toxicidad_constitucion` (cc-by-4.0) ya entraban en train.

## Traducción de tsjev al español (W10)

| Fuente | Licencia | De dónde sale | uso_comercial | Splits |
|---|---|---|---|---|
| Traductor `Helsinki-NLP/opus-mt-en-es` (OPUS-MT) | CC-BY-4.0 (esperada; **no verificada**: sin red en kindling) | `model/meta/traducir.py` lee `license:` de la tarjeta del snapshot y aborta si no es `cc-by-4.0` o `apache-2.0` | true | — |
| `tsjev-es` (`model/meta/traducir.py`, salida `$CHISPA_S3/tsjev-es/`) | la de la fila original (solo `commercial`) más la del traductor, en `licencia`: «<original>; traducción: CC-BY-4.0 (Helsinki-NLP/opus-mt-en-es)» | traducción automática de `texto`, `pregunta` y `descripciones` de las filas tsjev `commercial` | true | los mismos que la fila original (id con sufijo `:es`, misma `plantilla`; el test sigue siendo test) |

- **Atribución obligatoria** (CC-BY-4.0): Opus-MT, Tiedemann y Thottingal (2020), Universidad de Helsinki; los datos se transformaron (traducidos automáticamente). Va con cualquier redistribución de `tsjev-es` y de los pesos entrenados con ellos.
- **NLLB no** (no comercial). MADLAD-400 (`google/madlad400-3b-mt`, Apache-2.0) solo si Opus-MT no valiera.
- Cada fila lleva `traducida: {modelo, revision, de}`; las filas con traductor `FALSO:*` son de prueba y no se usan.

## Clandestino (W9, ajuste v3)

| Fuente | Licencia | De dónde sale | uso_comercial | Splits |
|---|---|---|---|---|
| Clandestino (`microsoft/Clandestino`), solo filas con `Is AI Generated == false` | MIT, **con la condición de uso de Microsoft: no dañar, no vigilancia**; aceptada por Juan, 2026-11-02 | la tarjeta del snapshot (`license: mit`); si no la confirma, «sin verificar», `uso_comercial: false` y solo `test` | true solo si la tarjeta lo confirma | train/dev/test por plantilla (80/10/10), sin fugas. Opcional en `model.datos.convertir` (`--con-opcionales`): solo se mide con ella en el ajuste v3 (`ajuste.sh` con `CHISPA_V3=1`). Fuente real: GitHub `microsoft/Clandestino` (`data/clandestino_no_ontology_42023.json`), no HF. Filtro: `IsAIGenerated == "False"` y ningún anotador con Q7 (PII) = Yes **o Maybe**. Filas conservadas: **pendiente del `contar` del fichero completo en AWS** (≈ 40 % estimado) |
