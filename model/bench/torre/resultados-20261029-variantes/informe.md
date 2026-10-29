# Verificación de punta a punta de la torre de L2 (checkpoint real): variantes

## Torre ninguna

| punto | resultado | cifra |
|---|---|---|
| coseno medio de `h` ONNX (con poda) vs PyTorch, 300 textos (objetivo ≥ 0,9990) | FALLO | 0,9665 (mín 0,9333); 7.5 % de tokens a `<unk>` |
| coseno medio de `h` sin `<unk>` (solo cuantización; objetivo ≥ 0,9990) | OK | 1,0000 (mín 1,0000) |
| top-1 de choice, torres ONNX (poda) vs PyTorch, 300 filas (objetivo ≥ 0,98) | FALLO | 0,9167 (margen medio 0,0368) |
| top-1 de choice sin `<unk>` (objetivo ≥ 0,98) | OK | 1,0000 |
| tamaño del ONNX de la torre | NO MEDIDO | 174.0 MB (fp32: 174.0) |
| latencia de la torre, ORT 1 hilo, lote 1, por texto | OK | p50 16.1 ms, p99 21.8 ms (100 textos) |
| `max_len` / textos de calibración | NO MEDIDO | 128 / 0 |
| `metadata_props` chispa.torre.{dim,max_len,prefijo} en el ONNX | OK | dim=256 max_len prefijo='passage: ' |
| `chispa train --torre` y `chispa-server -tags ort` con la torre | OK | chispa train --torre y servidor |
| 5 esquemas de JevBench fuera del .chispa decididos por L2 en /v1/decide | FALLO | capas ['escalar', 'escalar', 'escalar', 'escalar', 'escalar']; aciertos 0/5 |

## Torre dinamico

| punto | resultado | cifra |
|---|---|---|
| coseno medio de `h` ONNX (con poda) vs PyTorch, 300 textos (objetivo ≥ 0,9990) | FALLO | 0,9540 (mín 0,9011); 7.5 % de tokens a `<unk>` |
| coseno medio de `h` sin `<unk>` (solo cuantización; objetivo ≥ 0,9990) | FALLO | 0,9859 (mín 0,9671) |
| top-1 de choice, torres ONNX (poda) vs PyTorch, 300 filas (objetivo ≥ 0,98) | FALLO | 0,8867 (margen medio 0,0368) |
| top-1 de choice sin `<unk>` (objetivo ≥ 0,98) | FALLO | 0,9367 |
| tamaño del ONNX de la torre (≤ 50 MB) | OK | 46.7 MB (fp32: 174.0) |
| latencia de la torre, ORT 1 hilo, lote 1, por texto | OK | p50 9.5 ms, p99 13.3 ms (100 textos) |
| `max_len` / textos de calibración | NO MEDIDO | 128 / 0 |
| `metadata_props` chispa.torre.{dim,max_len,prefijo} en el ONNX | OK | dim=256 max_len prefijo='passage: ' |
| `chispa train --torre` y `chispa-server -tags ort` con la torre | OK | chispa train --torre y servidor |
| 5 esquemas de JevBench fuera del .chispa decididos por L2 en /v1/decide | FALLO | capas ['escalar', 'escalar', 'escalar', 'escalar', 'escalar']; aciertos 0/5 |

## Torre estatico

| punto | resultado | cifra |
|---|---|---|
| coseno medio de `h` ONNX (con poda) vs PyTorch, 300 textos (objetivo ≥ 0,9950) | FALLO | 0,8978 (mín 0,8444); 7.5 % de tokens a `<unk>` |
| coseno medio de `h` sin `<unk>` (solo cuantización; objetivo ≥ 0,9950) | FALLO | 0,9066 (mín 0,8512) |
| top-1 de choice, torres ONNX (poda) vs PyTorch, 300 filas (objetivo ≥ 0,98) | FALLO | 0,8400 (margen medio 0,0368) |
| top-1 de choice sin `<unk>` (objetivo ≥ 0,98) | FALLO | 0,8100 |
| tamaño del ONNX de la torre (≤ 50 MB) | OK | 46.8 MB (fp32: 174.0) |
| latencia de la torre, ORT 1 hilo, lote 1, por texto | OK | p50 10.4 ms, p99 14.8 ms (100 textos) |
| `max_len` / textos de calibración | NO MEDIDO | 128 / 500 |
| `metadata_props` chispa.torre.{dim,max_len,prefijo} en el ONNX | OK | dim=256 max_len prefijo='passage: ' |
| `chispa train --torre` y `chispa-server -tags ort` con la torre | OK | chispa train --torre y servidor |
| 5 esquemas de JevBench fuera del .chispa decididos por L2 en /v1/decide | FALLO | capas ['escalar', 'escalar', 'escalar', 'escalar', 'escalar']; aciertos 0/5 |
| JevBench por el servidor, 231/231 casos | NO MEDIDO | exactitud servidor 0,4286; Python k=0 sobre los mismos casos 0,4156; capas {'escalar': 231} |

## Comunes

| punto | resultado | cifra |
|---|---|---|
| `go test -tags ort ./server/torre/...` (con CHISPA_TOK) | OK | 7 PASS |
| `TestIgualdadTransformersPasaje` (CHISPA_TOK) | OK | 1 PASS |
| `chispa-server -tags ort` compila | OK | -tags ort |

## `.chispa` con score K ≥ 3

| punto | resultado | cifra |
|---|---|---|
| `.chispa` con score K ≥ 3 subido a `$CHISPA_S3/score/l2-score.chispa` | FALLO | ver exportar-score.log |

Claves `scoreK` de CALIB: —

Fallo del script: chispa score K>=3
