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
