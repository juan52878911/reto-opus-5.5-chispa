# Verificación de punta a punta de la torre de L2 (checkpoint real): variantes

## Torre ninguna

| punto | resultado | cifra |
|---|---|---|
| coseno medio de `h` ONNX (con poda) vs PyTorch, 300 textos (objetivo ≥ 0,9990) | OK | 1,0000 (mín 1,0000); 0.0 % de tokens a `<unk>` |
| coseno medio de `h` sin `<unk>` (solo cuantización; objetivo ≥ 0,9990) | NO MEDIDO | — |
| top-1 de choice, torres ONNX (poda) vs PyTorch, 300 filas (objetivo ≥ 0,98) | OK | 1,0000 (margen medio 0,0524) |
| top-1 de choice sin `<unk>` (objetivo ≥ 0,98) | NO MEDIDO | — |
| tamaño del ONNX de la torre | NO MEDIDO | 471.6 MB (fp32: 471.6) |
| latencia de la torre, ORT 1 hilo, lote 1, por texto | OK | p50 15.5 ms, p99 21.2 ms (100 textos) |
| `max_len` / textos de calibración | NO MEDIDO | 256 / 0 |
| `metadata_props` chispa.torre.{dim,max_len,prefijo} en el ONNX | OK | dim=256 max_len prefijo='passage: ' |
| `chispa train --torre` y `chispa-server -tags ort` con la torre | OK | chispa train --torre y servidor |
| 5 esquemas de JevBench fuera del .chispa decididos por L2 en /v1/decide | FALLO | capas ['L2', 'L2', 'escalar', 'escalar', 'escalar']; aciertos 1/5 |
| JevBench por el servidor, 231/231 casos (exactitud a ≤ 0,01 de Python k=0) | FALLO | exactitud servidor 0,4632; Python k=0 sobre los mismos casos 0,4848; capas {'L2': 38, 'escalar': 193} |
| `chispa_torres_calculadas_total` > 0 y L2 entre las capas | OK | torres calculadas 368 (errores 0); capas por caso {'L2': 38, 'escalar': 193}; decididas {'L2': 38, 'escalar': 193} |

## Comunes

| punto | resultado | cifra |
|---|---|---|
| `go test -tags ort ./server/torre/...` (con CHISPA_TOK) | OK | 9 PASS |
| `TestIgualdadTransformersPasaje` (CHISPA_TOK) | OK | 1 PASS |
| `chispa-server -tags ort` compila | OK | -tags ort |

## `.chispa` con score K ≥ 3

| punto | resultado | cifra |
|---|---|---|
| `.chispa` con score K ≥ 3 subido a `$CHISPA_S3/score/l2-score.chispa` | OK | ["score4", "score4#1", "score4#2", "score5", "score5#1", "score5#2", "score5#3"] |

Claves `scoreK` de CALIB: `score4`, `score4#1`, `score4#2`, `score5`, `score5#1`, `score5#2`, `score5#3`
## JevBench por el servidor: CALIB y consulta (D1)

Python k=0 sobre los mismos casos: 0,4848.

| pasada | casos | exactitud | por tipo | capas |
|---|---|---|---|---|
| base: CALIB de `chispa train --torre`, consulta int8 con poda | 231 | 0,4632 | choice 0,4820 (Python 0,4676) · noul 0,4730 (Python 0,5541) · score 0,2778 (Python 0,3333) | L2 38; escalar 193 |
| CALIB global del checkpoint | 231 | 0,4805 | choice 0,4820 (Python 0,4676) · noul 0,5405 (Python 0,5541) · score 0,2222 (Python 0,3333) | L2 20; escalar 211 |
| CALIB global + consulta fp32 sin poda | 231 | 0,4805 | choice 0,4820 (Python 0,4676) · noul 0,5405 (Python 0,5541) · score 0,2222 (Python 0,3333) | L2 20; escalar 211 |

## Diagnóstico de paridad: base: CALIB de `chispa train --torre`, consulta int8 con poda

- Consulta del `.chispa`: max_len 256 (declarado en el ONNX; el checkpoint usa 256), 384 filas de embeddings (completo = 250037), int8: False.
- TORR: max_len 256.

CALIB (servidor frente a checkpoint):

| cabeza | parámetros del `.chispa` | parámetros del checkpoint |
|---|---|---|
| choice | — | T=0.02211, a=0, b=0, theta=0.5 |
| noul | — | T=1, a=4.25, b=-3.804, theta=0.5 |
| score4 | — | T=1, a=3.945, b=2.046, theta=0.5 |
| score4#1 | — | T=1, a=0.7147, b=0, theta=0.5 |
| score4#2 | — | T=1, a=0.709, b=0, theta=0.5 |
| score5 | — | T=1, a=3.95, b=2.032, theta=0.5 |
| score5#1 | — | T=1, a=0.7182, b=0, theta=0.5 |
| score5#2 | — | T=1, a=0.7253, b=0, theta=0.5 |
| score5#3 | — | T=1, a=0.7216, b=0, theta=0.5 |

| tipo | casos | discrepan | truncados Python / servidor | textos de torre distintos | ‖Δp‖ medio | replay fiel (máx |Δp|) | causas |
|---|---|---|---|---|---|---|---|
| choice | 30 | 0 | 0 / 0 | 0 | 0.002 | 0.339 | — |
| noul | 30 | 13 | 16 / 16 | 30 | 0.319 | 0.000 | calib: 10, combinada(calib+texto_torre): 3 |
| score | 18 | 0 | 5 / 5 | 18 | — | — | — |
| todos | 78 | 13 | 21 / 21 | 48 | 0.160 | 0.339 | calib: 10, combinada(calib+texto_torre): 3 |

«replay fiel» mide si el recálculo en Python reproduce lo que devolvió el servidor (debe ser ≈ 0: si no, la atribución no vale).

## Diagnóstico de paridad: CALIB global del checkpoint

- Consulta del `.chispa`: max_len 256 (declarado en el ONNX; el checkpoint usa 256), 384 filas de embeddings (completo = 250037), int8: False.
- TORR: max_len 256.

CALIB (servidor frente a checkpoint):

| cabeza | parámetros del `.chispa` | parámetros del checkpoint |
|---|---|---|
| choice | T=0.02211, a=0, b=0, theta=0.5 | T=0.02211, a=0, b=0, theta=0.5 |
| noul | T=1, a=4.25, b=-3.804, theta=0.5 | T=1, a=4.25, b=-3.804, theta=0.5 |
| score4 | T=1, a=3.945, b=2.046, theta=0.5 | T=1, a=3.945, b=2.046, theta=0.5 |
| score4#1 | T=1, a=0.7147, b=0, theta=0.5 | T=1, a=0.7147, b=0, theta=0.5 |
| score4#2 | T=1, a=0.709, b=0, theta=0.5 | T=1, a=0.709, b=0, theta=0.5 |
| score5 | T=1, a=3.95, b=2.032, theta=0.5 | T=1, a=3.95, b=2.032, theta=0.5 |
| score5#1 | T=1, a=0.7182, b=0, theta=0.5 | T=1, a=0.7182, b=0, theta=0.5 |
| score5#2 | T=1, a=0.7253, b=0, theta=0.5 | T=1, a=0.7253, b=0, theta=0.5 |
| score5#3 | T=1, a=0.7216, b=0, theta=0.5 | T=1, a=0.7216, b=0, theta=0.5 |

| tipo | casos | discrepan | truncados Python / servidor | textos de torre distintos | ‖Δp‖ medio | replay fiel (máx |Δp|) | causas |
|---|---|---|---|---|---|---|---|
| choice | 30 | 0 | 0 / 0 | 0 | 0.002 | 0.000 | — |
| noul | 30 | 6 | 16 / 16 | 30 | 0.018 | 0.000 | texto_torre: 6 |
| score | 18 | 2 | 5 / 5 | 18 | 0.016 | 0.000 | texto_torre: 2 |
| todos | 78 | 8 | 21 / 21 | 48 | 0.012 | 0.000 | texto_torre: 8 |

«replay fiel» mide si el recálculo en Python reproduce lo que devolvió el servidor (debe ser ≈ 0: si no, la atribución no vale).

## Diagnóstico de paridad: CALIB global + consulta fp32 sin poda

- Consulta del `.chispa`: max_len 256 (declarado en el ONNX; el checkpoint usa 256), 384 filas de embeddings (completo = 250037), int8: False.
- TORR: max_len 256.

CALIB (servidor frente a checkpoint):

| cabeza | parámetros del `.chispa` | parámetros del checkpoint |
|---|---|---|
| choice | T=0.02211, a=0, b=0, theta=0.5 | T=0.02211, a=0, b=0, theta=0.5 |
| noul | T=1, a=4.25, b=-3.804, theta=0.5 | T=1, a=4.25, b=-3.804, theta=0.5 |
| score4 | T=1, a=3.945, b=2.046, theta=0.5 | T=1, a=3.945, b=2.046, theta=0.5 |
| score4#1 | T=1, a=0.7147, b=0, theta=0.5 | T=1, a=0.7147, b=0, theta=0.5 |
| score4#2 | T=1, a=0.709, b=0, theta=0.5 | T=1, a=0.709, b=0, theta=0.5 |
| score5 | T=1, a=3.95, b=2.032, theta=0.5 | T=1, a=3.95, b=2.032, theta=0.5 |
| score5#1 | T=1, a=0.7182, b=0, theta=0.5 | T=1, a=0.7182, b=0, theta=0.5 |
| score5#2 | T=1, a=0.7253, b=0, theta=0.5 | T=1, a=0.7253, b=0, theta=0.5 |
| score5#3 | T=1, a=0.7216, b=0, theta=0.5 | T=1, a=0.7216, b=0, theta=0.5 |

| tipo | casos | discrepan | truncados Python / servidor | textos de torre distintos | ‖Δp‖ medio | replay fiel (máx |Δp|) | causas |
|---|---|---|---|---|---|---|---|
| choice | 30 | 0 | 0 / 0 | 0 | 0.002 | 0.000 | — |
| noul | 30 | 6 | 16 / 16 | 30 | 0.018 | 0.000 | texto_torre: 6 |
| score | 18 | 2 | 5 / 5 | 18 | 0.016 | 0.000 | texto_torre: 2 |
| todos | 78 | 8 | 21 / 21 | 48 | 0.012 | 0.000 | texto_torre: 8 |

«replay fiel» mide si el recálculo en Python reproduce lo que devolvió el servidor (debe ser ≈ 0: si no, la atribución no vale).

## Perfil móvil con la poda corregida (D1)

Frente a PyTorch fp32 (checkpoint real, max_tok 256). Cumple = top-1 ≥ 0,93 y consulta y torre ≤ 60 MB.

Poda ampliada: 55000 ids → 55016 con 1360 textos del corpus. `<unk>` en la comprobación (2160 textos que no están en el corpus): 7,25 % antes, 7,23 % después.

`<unk>` de lo medido (antes → después de ampliar): torres de `h` 7,55 → 6,76 %, opciones 7,89 → 7,11 %, mensajes 0,00 → 0,00 %. La fila «+ textos medidos» amplía además con esos textos: aísla la poda de los `<unk>`.

| variante | vocabulario | consulta MB | torre MB | coseno h (media / mín) | coseno S | top-1 | torre p50 / p99 ms | consulta p50 / p99 ms | `<unk>` % | cumple |
|---|---|---|---|---|---|---|---|---|---|---|
| fp16 | poda ampliada | 88,9 | 88,2 | 0,931 / 0,813 | 1,000 | 0,90 | 16,4 / 22,3 | 10,2 / 21,3 | 7,23 | no |
| fp16 | poda ampliada + textos medidos | 88,9 | 88,2 | 1,000 / 1,000 | 1,000 | 1,00 | 16,2 / 22,3 | 10,1 / 21,6 | 0,00 | no |
| fp32 | poda ampliada | 175,5 | 174,0 | 0,931 / 0,813 | 1,000 | 0,90 | 15,4 / 21,2 | 9,7 / 20,3 | 7,23 | no |
| fp32 | poda ampliada + textos medidos | 175,5 | 174,0 | 1,000 / 1,000 | 1,000 | 1,00 | 15,5 / 21,1 | 9,7 / 20,4 | 0,00 | no |

Cumplen: ninguna.


Fallo del script: ninguno
