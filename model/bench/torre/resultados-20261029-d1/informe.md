# Verificación de punta a punta de la torre de L2 (checkpoint real): variantes

## Torre ninguna

| punto | resultado | cifra |
|---|---|---|
| coseno medio de `h` ONNX (con poda) vs PyTorch, 300 textos (objetivo ≥ 0,9990) | OK | 1,0000 (mín 1,0000); 0.0 % de tokens a `<unk>` |
| coseno medio de `h` sin `<unk>` (solo cuantización; objetivo ≥ 0,9990) | NO MEDIDO | — |
| top-1 de choice, torres ONNX (poda) vs PyTorch, 300 filas (objetivo ≥ 0,98) | OK | 1,0000 (margen medio 0,0524) |
| top-1 de choice sin `<unk>` (objetivo ≥ 0,98) | NO MEDIDO | — |
| tamaño del ONNX de la torre | NO MEDIDO | 471.6 MB (fp32: 471.6) |
| latencia de la torre, ORT 1 hilo, lote 1, por texto | OK | p50 15.4 ms, p99 21.3 ms (100 textos) |
| `max_len` / textos de calibración | NO MEDIDO | 256 / 0 |
| `metadata_props` chispa.torre.{dim,max_len,prefijo} en el ONNX | OK | dim=256 max_len prefijo='passage: ' |
| `chispa train --torre` y `chispa-server -tags ort` con la torre | OK | chispa train --torre y servidor |
| 5 esquemas de JevBench fuera del .chispa decididos por L2 en /v1/decide | FALLO | capas ['escalar', 'escalar', 'escalar', 'escalar', 'escalar']; aciertos 0/5 |
| JevBench por el servidor, 231/231 casos (exactitud a ≤ 0,01 de Python k=0) | FALLO | exactitud servidor 0,4372; Python k=0 sobre los mismos casos 0,4848; capas {'escalar': 216, 'L2': 15} |
| `chispa_torres_calculadas_total` > 0 y L2 entre las capas | OK | torres calculadas 368 (errores 0); capas por caso {'escalar': 216, 'L2': 15}; decididas {'L2': 15, 'escalar': 216} |

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
| base: CALIB de `chispa train --torre`, consulta int8 con poda | 231 | 0,4372 | choice 0,4388 (Python 0,4676) · noul 0,4730 (Python 0,5541) · score 0,2778 (Python 0,3333) | L2 15; escalar 216 |
| CALIB global del checkpoint | 231 | 0,4372 | choice 0,4388 (Python 0,4676) · noul 0,4865 (Python 0,5541) · score 0,2222 (Python 0,3333) | L2 20; escalar 211 |

## Diagnóstico de paridad: CALIB global del checkpoint

- Consulta del `.chispa`: max_len 256 (declarado en el ONNX; el checkpoint usa 256), 384 filas de embeddings (completo = 250037), int8: True.
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
| choice | 30 | 3 | 0 / 0 | 0 | 0.071 | 0.000 | onnx: 3 |
| noul | 30 | 9 | 16 / 16 | 30 | 0.042 | 0.000 | combinada(texto_torre+onnx): 2, onnx: 4, texto_torre: 1, texto_torre+onnx: 2 |
| score | 18 | 4 | 5 / 5 | 18 | 0.033 | 0.000 | onnx: 2, texto_torre: 1, texto_torre+onnx: 1 |
| todos | 78 | 16 | 21 / 21 | 48 | 0.051 | 0.000 | combinada(texto_torre+onnx): 2, onnx: 9, texto_torre: 2, texto_torre+onnx: 3 |

«replay fiel» mide si el recálculo en Python reproduce lo que devolvió el servidor (debe ser ≈ 0: si no, la atribución no vale).


Fallo del script: diagnóstico de paridad base
