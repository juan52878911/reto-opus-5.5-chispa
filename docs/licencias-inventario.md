# Inventario de licencias

**Decisión (2026-11-03): Apache-2.0 para todo lo propio** (código, SDK, servidor, pesos propios y `.chispa` publicados), titular Juan Bedoya. `LICENSE`, `sdk/LICENSE` y `NOTICE` ya reflejan esa decisión; el texto de abajo es el inventario previo, sin cambios (donde habla del `LICENSE` «propietario», se refiere a la situación anterior). Datasets con SA, NC o términos pendientes: no se redistribuyen y solo se usan como test. Se añadió `demo/wasm/LICENSE.go` (BSD de Go). Quedan sin su `LICENSE` de JevBench las copias de `model/` (`model/l2/tests/fixtures_largos/jevbench/`, `model/l2/resultados/ajuste-20261029/{g8,nuevo}/jev/`): son de otra sesión.

Fecha: 2026-11-03. Para que Juan elija una licencia open source. El `LICENSE` actual es propietario (`LICENSE` y `sdk/LICENSE`, el mismo texto: «Chispa — Licencia propietaria», © 2026 Juan Bedoya).
Cada licencia de un tercero lleva la **ruta del fichero donde se leyó**. Lo que no se pudo leer (sin red, sin caché) dice **«sin verificar»** y no se da por cierto.
Conteos: `git ls-files` de la rama `delega/chispa-zm`. `data/` y `models/` no se abrieron.

## 1. Lo propio que llevaría cabecera o aviso

**Ningún fichero propio lleva cabecera de copyright o SPDX** (`git grep -E "^\s*(//|#|/\*)\s*(copyright|spdx-license)"` solo da los dos `wasm_exec*.js` de Go, que son de terceros). Lo único que declara licencia hoy:
`LICENSE`, `sdk/LICENSE`, `sdk/python/pyproject.toml` (`license = {text = "Propietaria…"}` y el clasificador `License :: Other/Proprietary License`; autor Juan Bedoya),
`sdk/js/package.json` (`"license": "SEE LICENSE IN LICENSE"`, `private: true`; **no hay `LICENSE` dentro de `sdk/js/`**, solo `sdk/LICENSE` un nivel más arriba) y `sdk/python/README.md:18`.
Los `build.gradle.kts` de Android y `Package.swift` de iOS no declaran licencia.

| Zona | Tipo | Ficheros | ¿Cabecera? | Qué hay que decidir |
|---|---|---|---|---|
| `server/` | Go | 131 (`.go`; más 20 `.py` y 12 `.sh` de arneses) | no | cabecera o `SPDX-License-Identifier` en cada `.go`; `server/deploy/**` y `server/deploy/resultados/**` (informes de medida) incluidos |
| `format/chispa3/` | Go | 29 | no | el formato `.chispa` es la parte más reutilizable por terceros |
| `runtime/{l1,tok,torre}` | Go | 22 (+ `.py` de exportación) | no | exportadores `exportar.py` incluidos |
| `sdk/movil/chispamovil` | Go | 40 | no | se compila a AAR/xcframework (gomobile) |
| `sdk/go`, `sdk/python/chispa/entrenador_go` | Go | 6 + 9 | no | el wheel de Python **incluye** las fuentes de Go del entrenador (`pyproject.toml`, `package-data`) |
| `arena/` | Go | 38 (+ 2 `.html`, 2 `.sh`) | no | `arena/contracts/` está congelado |
| `demo/`, `deploy/`, `model/*.go` | Go | 6 + 1 + 8 | no | |
| `sdk/python`, `audio/`, `demos/` | Python | 54 + 8 + 20 | no | `sdk/python` es el que se publica (PyPI) |
| `model/` (solo lectura aquí) | Python | 205 (+ 37 `.sh`) | no | 793 ficheros en total, 158 `.md`; la mayoría son informes y resultados |
| `sdk/android` | Kotlin | 39 `.kt` + 4 `.kts` | no | |
| `sdk/ios` | Swift | 30 | no | |
| `sdk/js`, `demo/wasm` | JS | 5 + 4 propios (`arnes.js`, `cargador.js`, `prueba_*`) | no | `wasm_exec.js` y `wasm_exec_node.js` son de Go (ver §2) |
| `docs/`, `pilotos/`, `plan/`, `README.md` | Markdown | 12 + 9 + 95 + 1 (351 `.md` en todo el repo) | no | documentación: licencia aparte (p. ej. CC-BY-4.0) o la del código |
| `.chispa` generados de test | binario | 22 (`format/chispa3/testdata` 9, `server/testdata` 6, `server/decide/testdata` 5, `model/l2/tests/fixtures` 2) | n/a | ver «Pesos y goldens» |
| `server/torre/testdata/sintetico.onnx` | binario | 1 (4,5 MB) | n/a | nombre «sintético»; su generador no se verificó |
| Datos propios de test | json/jsonl/csv/txt | `model/herramientas/*` (368 de test y 1 024 de train: semillas escritas a mano y variantes de ellas, según `model/sondeo/README.md`), `server/carga/textos-es-co.txt` (2 400 mensajes inventados), `pilotos/esquemas/ejemplos/*.csv`, `server/e2e/datos/*`, `model/datos/fixtures/**` y `model/l2/tests/fixtures_espanol/**` (**inventados**: `model/datos/fixtures/generar.py:1` «filas inventadas, con la forma de cada fuente real», `generar_libres.py:3` «Nada aquí viene de datos reales»; sus tarjetas dicen «Tarjeta inventada») | no | propios; las «tarjetas» de `fixtures/` son inventadas |

**Pesos y goldens binarios.** En git solo hay pesos de prueba: 22 `.chispa` (8,7 MB con el `.onnx`), todos de `testdata`/`fixtures`. Los `.chispa` reales, `potion.chispa-l1` (155 MB), `e5.chispa-tok` (12 MB), el AAR y el xcframework **no van a git**
(`.gitignore`: `data/`, `models/`, `*.chispa` salvo `testdata`; `sdk/android/settings.gradle.kts:14`, `sdk/ios/Package.swift`), pero **sí se distribuirían** en el tar, la imagen o el APK: su licencia es la del conjunto de §2 más la del entrenamiento.
Tres de esos `.chispa` llevan en su `META` una tabla de licencias de las fuentes (leída con `chispa.formato.leer`): `JevBench easy/hard/original: MIT` en `model/l2/tests/fixtures/calib-score.chispa` y `server/decide/testdata/calib-score.chispa`; `inventada: MIT` en `model/l2/tests/fixtures/esquemas-v2.chispa`.
Cinco `.chispa` (`server/testdata/{injection,intencion,urgencia}.chispa` y `format/chispa3/testdata/{injection,urgencia}.chispa`) son v1/v2 y no se pudieron abrir con el lector de v3: su origen (`injection` parece venir de deepset/prompt-injections, Apache-2.0) queda **sin verificar**.

## 2. Terceros

Leyenda de «¿Se redistribuye?»: **git** = está dentro del repo; **.chispa** = dentro de un `.chispa` real; **imagen/tar/APK** = en lo que se entrega; **no** = solo se usa al construir o evaluar.

### 2.1 Código

| Tercero | Licencia | Fuente donde se comprobó | ¿Se redistribuye? | Obligación |
|---|---|---|---|---|
| `github.com/juan52878911/kindling` v0.17.0 (único `require` de Go junto a onnxruntime_go: `*/go.mod`, `*/go.sum`) | Apache-2.0 | `LICENSE` y `NOTICE` del módulo en la caché de módulos de Go (`kindling@v0.17.0/`). El `NOTICE` dice «Copyright the kindling authors» y añade atribuciones de datasets de **ejemplos** que el módulo «no distribuye» | **imagen/tar/APK**: enlazado estático en `chispa-server`, `format/chispa3` (`l0.go`, `l0multi.go`), `chispamovil`, el entrenador y `arena` | Apache-2.0 §4: copia de la licencia y `NOTICE`. Es de la misma cuenta de GitHub que este repo: si todos sus «authors» son Juan, no obliga a nada (puede relicenciarlo); **sin verificar** la titularidad |
| `github.com/yalue/onnxruntime_go` v1.38.0 | MIT (© 2023 Nathan Otterness) | `LICENSE` del módulo en la caché de Go | **imagen/tar/APK** solo con `-tags ort` (`server/decide/l2_ort.go`, `server/torre/ort.go`); en `sdk/movil/chispamovil/go.mod` como indirecta | aviso de copyright y texto MIT con el binario |
| Biblioteca estándar y runtime de Go 1.27 | BSD-3-Clause («Copyright 2009 The Go Authors») | `LICENSE` de la instalación de Go | **imagen/tar/APK**: todo binario de Go lo lleva | aviso BSD-3 con el binario |
| `demo/wasm/wasm_exec.js`, `wasm_exec_node.js` | BSD «de Go» (cabecera: «Copyright 2018 / 2021 The Go Authors. All rights reserved … BSD-style license … LICENSE file») | línea 1 de cada fichero; **el `LICENSE` de Go no está en el repo** | **git** | conservar la cabecera y añadir el texto BSD-3 (hoy falta) |
| ONNX Runtime (`libonnxruntime.so` 1.31.1, `deploy/kindling/Dockerfile:12,50`, descarga de la release de Microsoft) | MIT | `onnxruntime/LICENSE` y `ThirdPartyNotices.txt` del paquete Python `onnxruntime` 1.31.1 (mismo proyecto; el `.tgz` de la release no se descargó) y metadato `License: MIT License` | **imagen** (`imagen-ort`) | MIT + incluir `ThirdPartyNotices.txt` de la release (agrupa avisos de otros componentes) |
| `com.microsoft.onnxruntime:onnxruntime-android:1.19.2` (`sdk/android/chispa/build.gradle.kts:27`) | MIT (por ser el mismo proyecto) | **sin verificar**: no hay Gradle ni pom en este nodo | **APK** | MIT + avisos de terceros del AAR |
| `onnxruntime-swift-package-manager` ≥ 1.19.2 (`sdk/ios/Package.swift`) | MIT (por ser de Microsoft) | **sin verificar**: no está el paquete | **app iOS** | ídem |
| Plugins Gradle: AGP 8.5.2, Kotlin 2.0.20 (`sdk/android/build.gradle.kts:2-4`) | Apache-2.0 (conocimiento general) | **sin verificar** | no (solo construcción) | ninguna al distribuir el APK; el runtime de Kotlin sí va en el APK (Apache-2.0, sin verificar) |
| Tests Android: `junit:junit:4.13.2`, `org.json:json:20240303`, `androidx.test*` (`sdk/android/*/build.gradle.kts`) | EPL-1.0 / «JSON License» / Apache-2.0 (conocimiento general) | **sin verificar** | no (solo test) | ninguna al distribuir |
| SDK de JS (`sdk/js/package.json`) | sin dependencias | `package.json` (sin `dependencies`) | n/a | — |
| SDK de Python (`sdk/python/pyproject.toml`) | `dependencies = []`; opcionales: `pyyaml`, `numpy`, `onnx`, `onnxruntime`, `torch`, `transformers`, `scikit-learn` | `pyproject.toml` | **no** (el usuario los instala con pip; el wheel lleva las fuentes de Go del entrenador) | ninguna al publicar el wheel |

Versiones y licencias de los paquetes de Python (leídas del `METADATA` instalado en el entorno de trabajo; **las versiones no están fijadas por el repo**):

| Paquete | Licencia leída | Usado en |
|---|---|---|
| PyYAML 6.0.3 | MIT | `sdk/python`, `model/` |
| numpy 2.5.4 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | `sdk/python`, `runtime/`, `model/`, `audio/` |
| onnx 1.23.2 | Apache-2.0 | `sdk/python` (`--torre`), `model/` |
| onnxruntime 1.31.1 | MIT | ídem |
| torch 2.15.0+cpu | Apache-2.0 AND Apache-2.0 WITH LLVM-exception AND BSD-2-Clause AND BSD-3-Clause AND BSL-1.0 AND ISC AND MIT AND Zlib | `sdk/python` (`--ckpt`/`--conjunta`), `model/` |
| transformers 5.21.0 | Apache 2.0 | `model/`, `runtime/tok` |
| scikit-learn 1.9.1 | BSD-3-Clause | `sdk/python` (`l0tf.py`), `model/` |
| pyarrow 26.0.0 | Apache-2.0 | `model/`, `runtime/l1` |
| huggingface_hub 2.3.0 | Apache-2.0 | `model/` |
| safetensors 0.8.0, tokenizers 0.23.3 | Apache Software License (clasificador) | `model/`, `runtime/` |
| scipy 1.18.1 | BSD (clasificador y cabecera «Copyright … SciPy Developers») | `model/` |
| setuptools 78.1.0 | MIT (clasificador) | `sdk/python/setup.py` |
| model2vec, sentence-transformers, boto3/botocore, vllm, pytest | **sin verificar** (no instalados aquí) | `model/`, `runtime/l1`, `server/` (solo exportación, medida y pruebas) |
| pillow 12.0.0, imageio-ffmpeg 0.6.0 (`demos/caida/requirements-render.txt`) | **sin verificar**. Aviso: `imageio-ffmpeg` trae un binario de FFmpeg (GPL o LGPL según la compilación; conocimiento general, no leído) | `demos/caida` (solo para renderizar un vídeo de demostración) |

### 2.2 Modelos y vocabularios

| Tercero | Licencia | Fuente donde se comprobó | ¿Se redistribuye? | Obligación |
|---|---|---|---|---|
| `intfloat/multilingual-e5-small` (L2, torres y `ESQUEMAS`; exportado a ONNX int8/fp16 y ajustado por Chispa: `model/l2/modelo.py:20`) | MIT | **sin verificar**: `model/eval0/resultados.md:62` dice «ficha del autor; no está el README en el snapshot, dato de memoria: verificar»; también `model/eval0/e5_knn.py:36` | **.chispa** (secciones `L2`, `TORR`, `ESQUEMAS`, `CONJ`) y `server/torre/*.onnx` generados | MIT: aviso de copyright. Los pesos ajustados son además derivados de los datasets de §2.3 |
| Tokenizador de e5 (SentencePiece de XLM-RoBERTa, 250 037 piezas; `runtime/tok/exportar.py:44`, `model/bench/vocab-podado-e5-small.json`) | el de e5 (MIT) y el de XLM-R | **sin verificar**. En git solo está la **lista de ids conservados** (55 000 de 250 037), no las piezas | **.chispa** y `e5.chispa-tok` (12 MB, no va a git) | avisos de ambos; revisar la licencia del `sentencepiece.bpe.model` |
| `minishlab/potion-multilingual-128M` (L1 «Model2Vec», 500 353 piezas × 256 dim, int8: `runtime/l1/README.md:7-13`) | MIT | **sin verificar**: `runtime/l1/README.md:9-13` dice que la copia local no trae tarjeta ni licencia y que «según mi conocimiento … MIT … confírmalo contra la tarjeta en Hugging Face antes de redistribuir el `.chispa-l1`» | **.chispa** (sección `L1`; 155 MB) | aviso MIT. Su tokenizador y su destilación vienen de `BAAI/bge-m3` (licencia **sin verificar**) |
| `jhu-clsp/mmBERT-small` | **sin verificar** | solo existe `model/bench/vocab-podado-mmBERT-small.json` (lista de ids) | no (solo comparación) | — |
| Modelos solo evaluados (no se redistribuyen): `knowledgator/gliclass-modern-base-v3.0`, `SupersonicLabs/Julia-1`, `doofz/THX-01`, `convaiinnovations/laya-multilingual`, `bge-m3-zeroshot-v2.0` (`model/evaluacion/profesor.py`) | «no consta en el snapshot (sin README ni LICENSE); verificar» | `model/eval0/resultados.md:60-68` (las cuatro primeras) | **no** | — (ver §4 para Laya) |
| Qwen (`Qwen/Qwen3.5-*`, comentario «abierto (Apache-2.0)» en `model/corpus/backends.py:39`) y Claude Haiku 5.5 por Bedrock (`backends.py:21`, backend opcional) | Qwen: Apache-2.0 **según el comentario del código, sin verificar**; Haiku: términos de Anthropic **sin leer** | `model/corpus/backends.py` | **no** los modelos; sí, si se usaron, **textos sintéticos generados** que acabaron en `data/` | **sin verificar** qué backend generó el corpus real de `data/` (no se abrió). Si fue Haiku, hay que leer sus términos sobre entrenar con las salidas |

### 2.3 Datasets y benchmarks

Fuente de las licencias de datasets: `model/datos/LICENCIAS.md` (leída entera; cita la tarjeta de cada dataset en la caché local de Hugging Face, no el repo). En el repo hay datos de terceros **solo** donde se indica en «¿Se redistribuye?».

| Dataset / benchmark | Licencia | Fuente | ¿Se redistribuye? | Obligación y uso permitido por el repo |
|---|---|---|---|---|
| JevBench (`fstandhartinger/jevbench`, MIT, © 2026 Florian Standhartinger) | MIT | `model/evaluacion/tests/fixtures/jevbench/LICENSE` y `README.md`; cada fila trae `provenance.license: MIT` | **git**: 13 filas en `model/evaluacion/tests/fixtures/jevbench/`, **otra copia sin `LICENSE`** en `model/l2/tests/fixtures_largos/jevbench/` y `jevbench_filas.jsonl` en `model/l2/resultados/ajuste-20261029/{g8,nuevo}/jev/` | aviso MIT con cada copia (falta en las dos últimas) |
| MASSIVE es (`mteb/amazon_massive_intent`) | Apache-2.0 (la tarjeta de mteb); el original de Amazon es CC-BY-4.0 | `model/datos/LICENCIAS.md` fila 1 | **git**: extractos en `model/sondeo/{intencion,train_intencion}.jsonl` | CC-BY-4.0: atribución (Amazon, FitzGerald et al.) e indicar los cambios. `uso_comercial: true` |
| HateCheck-ES (`Paul/hatecheck-spanish`) | CC-BY-4.0 | ídem, fila 2 | **git**: `model/sondeo/{toxicidad,train_toxicidad}.jsonl` | atribución |
| CLINC150 (`clinc/clinc_oos`) | CC-BY-3.0 | ídem, fila 4 | no (el fixture es inventado) | atribución si entra en pesos |
| Banking77 | CC-BY-4.0 | ídem, fila 3 (no convertida: sin datos) | no | — |
| deepset/prompt-injections | Apache-2.0 | ídem, fila 5 | no | — |
| spam (`tanaos/synthetic-spam-detection-dataset-spanish`) | MIT (sintético) | ídem, tabla de libres | no | — |
| `bgonzalezbustamante/toxicity-protests-ES` y `-Constitution-ES` | CC-BY-4.0 | ídem | no | atribución |
| `mrm8488/go_emotions-es-mt` (traducción automática de GoEmotions) | Apache-2.0 | ídem | no | — |
| `tasksource/it-support-tickets` | CC-BY-4.0 (Zenodo 10.5281/zenodo.7648117) | ídem | no | atribución |
| `FelipeGuerra/Colombian_Spanish_Cyberbullying_Dataset_1` y `_2` | MIT | ídem | no | — |
| PAWS-X es (Google) | «other»: «may be freely used for any purpose» | ídem (W3) | no | citar la fuente |
| **XNLI es** | **CC-BY-NC-4.0** | ídem, fila 6: `uso_comercial: false`, solo test | no (fixture inventado con tarjeta «inventada» que declara cc-by-nc-4.0) | **no puede entrar en pesos que se redistribuyan** |
| **`somosnlp/spa_climate_detection`** | **contradictoria** (cabecera cc-by-4.0, cuerpo cc-by-nc-sa-4.0) | ídem | no | solo test |
| `SINAI/ALIA-es-discriminative-hate-speech` | CC-BY-4.0, pero etiquetas fusionadas de tres LLM (Apertus, Gemma, MiniMax) | ídem: «pendiente de decisión de Juan», solo test | no | los términos de esos LLM pueden restringir entrenar con sus salidas: **sin leer** |
| `Davlan/sib200` `spa_Latn` | CC-BY-SA-4.0 | ídem (W3): `COMERCIAL = False`, solo test | no | SA sin decidir por Juan |
| PQRS de datos.gov.co (`gb9w-jt96`, `e86p-frfd`, `xtj2-ipwy`: CC-BY-SA-4.0; `m3mt-c275`: CC-BY-4.0) | ver columna | ídem: «solo test por decisión de Juan» | no (fixtures inventados) | SA: pregunta abierta sobre qué implica para el modelo; no se publican datos ni pesos derivados |
| Corpus sintético generado por LLM (`model/corpus/`) | depende del modelo generador | ver §2.2 | no (`data/`) | sin verificar |

**Qué entró realmente en los pesos que se distribuirían: sin verificar.** `LICENCIAS.md` dice qué fuentes están marcadas para `train` (`uso_comercial: true`), pero el checkpoint real de L2 y su `META.licencias` (que escribe `model/l2/exportar.py:657`) están en `models/`/`data/`, que no se abrieron.
`tasksource/tasksource-jev-typed-decisions` solo se baja la tarjeta y `sources.yaml` (`model/l2/aws/{ajuste,general,contar_noul}.sh`) «para `--excluir-fuera`»: no se usa como datos de entrenamiento según esos scripts.

## 3. Compatibilidad con Apache-2.0 y con AGPL-3.0

La columna de «Exige/riesgo» sale de las licencias leídas arriba; los juicios de compatibilidad entre licencias son **conocimiento general, no asesoría legal ni leídos en un fichero del repo**: confirmar con un abogado antes de publicar.

| Elemento | Con Apache-2.0 (el proyecto) | Con AGPL-3.0 (el proyecto) |
|---|---|---|
| Código MIT / BSD-3 / Apache-2.0 de terceros (onnxruntime_go, Go, ORT, kindling, PyYAML, scikit-learn, numpy, transformers, onnx…) | compatible; conservar avisos y `NOTICE` (kindling) | compatible (Apache-2.0 → GPLv3/AGPLv3 es de una sola vía: el conjunto queda AGPL) |
| Pesos MIT (e5, potion) | compatible; aviso MIT con los `.chispa` | compatible |
| **Código AGPL de terceros** | **no se puede** meter en un proyecto Apache-2.0 | n/a — no hay ninguno hoy (los únicos `require` de Go son MIT y Apache-2.0) |
| Datasets CC-BY-4.0 / CC-BY-3.0 (HateCheck, CLINC150, Banking77, toxicidad, tickets) y MASSIVE | compatible: atribución y cambios indicados (en datos y en pesos derivados) | compatible: ídem |
| **CC-BY-NC-4.0** (XNLI) y **CC-BY-NC-SA** (clima, por herencia) | **incompatible**: una restricción de uso comercial no cabe en una licencia que lo permite | **incompatible** (AGPL tampoco admite restricciones de campo de uso). Solo evaluación, **nunca en pesos que se publiquen** |
| **CC-BY-SA-4.0** (PQRS de datos.gov.co, SIB-200) | los datos convertidos y, quizá, los pesos entrenados con ellos exigen CC-BY-SA: **no compatible** con distribuirlos bajo Apache-2.0 sin más. Pregunta abierta de Juan | CC-BY-SA-4.0 tiene vía hacia GPLv3 (conocimiento general; **sin verificar** que cubra AGPL-3.0 ni pesos entrenados) |
| Dataset con términos propios o contradictorios (ALIA: etiquetas de LLM; PAWS-X «other») | ALIA: **sin leer** los términos de Apertus/Gemma/MiniMax; PAWS-X «libre para cualquier uso»: compatible | ídem |
| Salidas de Claude Haiku (si generaron corpus) | **sin leer** los términos de Anthropic | ídem |
| Salidas de Jev (TypeSafe AI) | **riesgo**: no usar para entrenar ni calibrar hasta leer el MCA (ver §4) | ídem |
| Salidas de Laya (Apache-2.0) | compatible (aviso y NOTICE si se redistribuyen pesos) | compatible |
| ONNX Runtime + `ThirdPartyNotices.txt` (MIT y avisos varios) | compatible; incluir los avisos con la imagen | compatible |
| `imageio-ffmpeg` (trae FFmpeg: GPL o LGPL según compilación; **sin verificar**) | no se distribuye; solo la demo | ídem |
| Cláusula de red AGPL §13 | n/a | quien use `chispa-server` por red debe poder pedir el código fuente. Un SDK (Python, Kotlin, Swift, JS) bajo AGPL obligaría al código del cliente que lo enlaza: considerar otra licencia para los SDK |
| Apache-2.0 §4 y §3 | NOTICE, aviso de cambios y concesión de patentes con terminación por litigio | — |

## 4. Terceros consultados por la orquestación (2026-11-03)

Texto recibido de la orquestación; **no se verificó** (este nodo no tiene red). Se copia tal cual:

- **Laya** (Convai Innovations, `convaiinnovations/laya`): ficha de Hugging Face con `License: apache-2.0`; el paquete PyPI `laya` 0.4.21 declara `License: Apache-2.0` en sus metadatos. La ficha no añade restricciones de uso ni menciona destilación. Apache-2.0 permite usar salidas y pesos para entrenar, con aviso y NOTICE si se redistribuyen pesos. Pendiente: leer el LICENSE del repo de pesos.
- **Jev** (TypeSafe AI): modelo solo por API, sin pesos publicados. Los términos web (typesafe.ai/legal/terms-of-service, actualizados el 19-09-2026) no hablan de destilación. Una reseña de terceros (wunderlandmedia.com) del **Master Customer Agreement** (27-08-2026, para API y consola) dice que su cláusula 2.3 prohíbe «destilar el Output para entrenar a un competidor»; no encontré el texto primario. **Riesgo:** no usar salidas de Jev para entrenar ni calibrar Chispa hasta leer el MCA.

### ¿Hay algo derivado de salidas de Jev o de Laya en el repo?
Búsqueda por nombre en todo el repo (`git ls-files` y `git grep -i` de `jev`, `laya`, `typesafe`, `convai`; en `model/` y `docs/`, `arena/`, `audio/`) y por nombre de fichero en `data/` sin abrirlo (no hay `data/` ni `models/` en git). Resultado:

- **Jev: no se encontró nada derivado de salidas de Jev.**
  - `model/evaluacion/jevbench*.py`, `tests/fixtures/jevbench/**`, `model/l2/tests/fixtures_largos/jevbench/**`, `model/l2/resultados/ajuste-20261029/{g8,nuevo}/jev/**`, `model/evaluacion/resultados/jevbench-20261029/**`: son **JevBench**, un benchmark público MIT de terceros (Florian Standhartinger). Sus filas declaran `label_basis: "Answer named or stated explicitly in the text; authored and reviewed before inference"` (`…/fixtures/jevbench/datasets/public/easy.jsonl`): etiquetas escritas y revisadas antes de cualquier inferencia, no salidas de un modelo. Las predicciones guardadas (`pred/l2_k0.jsonl`) son del L2 de Chispa.
  - `tasksource/tasksource-jev-typed-decisions`: solo tarjeta y `sources.yaml`, para excluir solapes (`model/l2/aws/*.sh`). Su procedencia de etiquetas **no se leyó**.
  - `audio/` («Jev de audio», `audio/DISENO.md`) y `docs/05-sdks.md:61`, `server/README.md` («`/v1/systemone` de Jev no se ha visto … suposición sin verificar»): menciones de diseño/nombre; no hay salidas de Jev. `arena/README.md:79` apunta a «Laya/Jev» como trabajo futuro (D).
  - **Sin verificar:** que `data/` (no abierto) no tenga etiquetas de Jev; que el contrato de `/v1/decide` no copie el de Jev (los docs dicen que no se vio).
- **Laya: solo evaluación, nada derivado en el entrenamiento.**
  - `model/eval0/laya.py` carga `convaiinnovations/laya-multilingual` desde la caché local de Hugging Face (los pesos **no** están en git) como línea de comparación; `.delega/golden.sh:32` los descarga.
  - `model/eval0/out/laya__*.json` (8 ficheros): solo agregados (`macro_f1`, `exactitud`, `ece`, latencias, `licencia: "no consta (el snapshot no trae README ni LICENSE)"`), sin predicciones por fila. `model/eval0/resultados.md` y `model/informes/fase-0.md` citan sus cifras.
  - La licencia que consta en el repo («no consta») **no coincide** con la de la orquestación (Apache-2.0): hasta leer el LICENSE del repo de pesos, vale la de la orquestación como no verificada.
  - **Sin verificar:** que `data/` no contenga salidas de Laya usadas como etiquetas.

## 5. Antes de elegir licencia (acciones, sin hacerlas aquí)
1. Verificar con la tarjeta/LICENSE de origen: e5, su tokenizador, potion y bge-m3, y la licencia de las fuentes que entraron al checkpoint real de L2 (`META.licencias` del `.chispa` real).
2. Añadir el texto BSD-3 de Go junto a `demo/wasm/wasm_exec*.js` y el `LICENSE` de JevBench a la copia de `model/l2/tests/fixtures_largos/jevbench/` y a los `jevbench_filas.jsonl` (o quitar esas copias).
3. Preparar un `NOTICE`/`THIRD_PARTY` con kindling (Apache-2.0), onnxruntime_go y ORT (MIT, con `ThirdPartyNotices.txt`), Go (BSD-3), e5, potion y las atribuciones CC-BY de §2.3 para el tar, la imagen y el APK.
4. Decidir lo de CC-BY-SA (datos.gov.co, SIB-200), XNLI/clima (NC) y ALIA antes de publicar pesos; ninguno de esos conjuntos debería entrar en pesos públicos hoy.
5. Si la licencia es AGPL-3.0: pensar en los SDK y en §13 (servidor por red). Si es Apache-2.0: ningún tercero actual impide el código; los pesos dependen del punto 1 y del 4.
6. Confirmar que `sdk/js` y `sdk/python` apuntan a un `LICENSE` que exista dentro de su paquete.
