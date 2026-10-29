# Verificación de punta a punta de la torre de L2 (checkpoint real): variantes

## Torre ninguna

| punto | resultado | cifra |
|---|---|---|
| coseno medio de `h` ONNX (con poda) vs PyTorch, 300 textos (objetivo ≥ 0,9990) | OK | 1,0000 (mín 1,0000); 0.0 % de tokens a `<unk>` |
| coseno medio de `h` sin `<unk>` (solo cuantización; objetivo ≥ 0,9990) | NO MEDIDO | — |
| top-1 de choice, torres ONNX (poda) vs PyTorch, 300 filas (objetivo ≥ 0,98) | OK | 1,0000 (margen medio 0,0528) |
| top-1 de choice sin `<unk>` (objetivo ≥ 0,98) | NO MEDIDO | — |
| tamaño del ONNX de la torre | NO MEDIDO | 471.6 MB (fp32: 471.6) |
| latencia de la torre, ORT 1 hilo, lote 1, por texto | OK | p50 16.5 ms, p99 23.3 ms (100 textos) |
| `max_len` / textos de calibración | NO MEDIDO | 256 / 0 |
| `metadata_props` chispa.torre.{dim,max_len,prefijo} en el ONNX | OK | dim=256 max_len prefijo='passage: ' |
| `chispa train --torre` y `chispa-server -tags ort` con la torre | OK | chispa train --torre y servidor |
| 5 esquemas de JevBench fuera del .chispa decididos por L2 en /v1/decide | FALLO | capas ['escalar', 'escalar', 'escalar', 'escalar', 'escalar']; aciertos 0/5 |
| JevBench por el servidor, 231/231 casos (exactitud a ≤ 0,01 de Python k=0) | FALLO | exactitud servidor 0,4372; Python k=0 sobre los mismos casos 0,4848; capas {'escalar': 216, 'L2': 15} |
| `chispa_torres_calculadas_total` > 0 y L2 entre las capas | OK | torres calculadas 368 (errores 0); capas por caso {'escalar': 216, 'L2': 15}; decididas {'L2': 15, 'escalar': 216} |
| `chispa_torres_calculadas_total` > 0 y L2 entre las capas [tau_l2_esquema_nuevo=0.276] | OK | torres calculadas 368 (errores 0); capas por caso {'L2': 185, 'escalar': 46}; decididas {'L2': 185, 'escalar': 46} |
| pasada con tau_l2_esquema_nuevo=0.276: 231/231 casos, contesta L2 en | NO MEDIDO | 185 de 231 (80.1 %); exactitud servidor 0,4372 |

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

Fallo del script: ninguno
