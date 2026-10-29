# Verificación de punta a punta de la torre de L2 (checkpoint real)

| punto | resultado | cifra |
|---|---|---|
| coseno medio de `h` ONNX (con poda) vs PyTorch, 300 textos | FALLO | 0,9540 (mín 0,9011); 7.5 % de tokens a `<unk>` |
| coseno medio de `h` sin `<unk>` (solo cuantización) | FALLO | 0,9859 |
| top-1 de choice, torres ONNX (poda) vs PyTorch, 300 filas | FALLO | 0,8867 (margen medio 0,0368) |
| top-1 de choice sin `<unk>` | FALLO | 0,9367 |
| tamaño del ONNX de la torre | OK | 46.7 MB |
| `metadata_props` chispa.torre.{dim,max_len,prefijo} en el ONNX | OK | dim=256 max_len=128 prefijo='passage: ' |
| `go test -tags ort ./server/torre/...` | FALLO | rc=0 pass=6 skip=1 (ver go_test_ort.log) |
| `TestIgualdadTransformersPasaje` (CHISPA_TOK) | OK | 1 PASS |
| `chispa train --torre` | OK | chispa train --torre y servidor |
| `chispa-server -tags ort` compila | OK | -tags ort |
| 5 esquemas de JevBench fuera del .chispa decididos por L2 en /v1/decide | FALLO | capas ['escalar', 'escalar', 'escalar', 'escalar', 'escalar']; aciertos 0/5 |
| JevBench por el servidor, 231/231 casos | NO MEDIDO | exactitud servidor 0,4113; Python k=0 sobre los mismos casos 0,4069; capas {'escalar': 231} |

Fallo del script: ninguno
