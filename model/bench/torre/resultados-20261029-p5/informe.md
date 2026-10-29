# Verificación de punta a punta de la torre de L2 (checkpoint real): variantes

## Torre ninguna

| punto | resultado | cifra |
|---|---|---|
| coseno medio de `h` ONNX (con poda) vs PyTorch, 300 textos (objetivo ≥ 0,9990) | OK | 1,0000 (mín 1,0000); 0.0 % de tokens a `<unk>` |
| coseno medio de `h` sin `<unk>` (solo cuantización; objetivo ≥ 0,9990) | NO MEDIDO | — |
| top-1 de choice, torres ONNX (poda) vs PyTorch, 300 filas (objetivo ≥ 0,98) | OK | 1,0000 (margen medio 0,0528) |
| top-1 de choice sin `<unk>` (objetivo ≥ 0,98) | NO MEDIDO | — |
| tamaño del ONNX de la torre | NO MEDIDO | 471.6 MB (fp32: 471.6) |
| latencia de la torre, ORT 1 hilo, lote 1, por texto | OK | p50 16.2 ms, p99 22.0 ms (100 textos) |
| `max_len` / textos de calibración | NO MEDIDO | 256 / 0 |
| `metadata_props` chispa.torre.{dim,max_len,prefijo} en el ONNX | OK | dim=256 max_len prefijo='passage: ' |
| `chispa train --torre` y `chispa-server -tags ort` con la torre | FALLO | ver servidor-ninguna.log |
| servidor con torres al vuelo | NO MEDIDO | sin servidor-ninguna/servidor.json |

## Torre movil

| punto | resultado | cifra |
|---|---|---|
| coseno medio de `h` ONNX (con poda) vs PyTorch, 300 textos (objetivo ≥ 0,9990) | FALLO | 0,9053 (mín 0,6338); 6.8 % de tokens a `<unk>` |
| coseno medio de `h` sin `<unk>` (solo cuantización; objetivo ≥ 0,9990) | FALLO | 0,9705 (mín 0,9209) |
| top-1 de choice, torres ONNX (poda) vs PyTorch, 300 filas (objetivo ≥ 0,98) | FALLO | 0,8800 (margen medio 0,0524) |
| top-1 de choice sin `<unk>` (objetivo ≥ 0,98) | FALLO | 0,8800 |
| tamaño del ONNX de la torre | NO MEDIDO | 46.7 MB (fp32: 174.0) |
| latencia de la torre, ORT 1 hilo, lote 1, por texto | OK | p50 8.8 ms, p99 12.5 ms (100 textos) |
| `max_len` / textos de calibración | NO MEDIDO | 256 / 0 |
| `metadata_props` chispa.torre.{dim,max_len,prefijo} en el ONNX | NO MEDIDO | no llegó |
| `chispa train --torre` y `chispa-server -tags ort` con la torre | NO MEDIDO | no llegó |
| servidor con torres al vuelo | NO MEDIDO | sin servidor-movil/servidor.json |

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

Fallo del script: servidor ninguna sin torres calculadas o error; servidor ninguna tau 0.276
