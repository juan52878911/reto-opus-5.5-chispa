# T0.3 Resultados x86 (medido fuera de kindling: ver CPU abajo)

- CPU: AMD EPYC 7R13 Processor, 4 vCPU, modelo 1 paso 1; flags relevantes: avx, avx2, fma
- Carga del host al informar (loadavg 1/5/15 min): 1.28 / 1.91 / 1.38. Máquina virtual compartida: cifras = cota pesimista; el i7-8700T se mide aparte.
- Python 3.11.17; onnxruntime/torch/transformers de ~/venv; 20 calentamientos + 200 repeticiones por celda; batch 1; semilla 20261027.
- Latencia = `session.run` + pooling medio + normalización sobre ids ya tokenizados (no incluye tokenizar). RSS pico = `ru_maxrss` del proceso de (variante, hilos), incluye la carga y todas las longitudes. Disco = fichero ONNX (potion: safetensors). Arranque en frío = crear sesión/cargar + primera inferencia, en proceso nuevo.
- Exportación: `torch.onnx.export` (opset 17) y no optimum: optimum 1.17.1 no importa con transformers 5.21 (`is_tf_available`). Int8 = `onnxruntime.quantization.quantize_dynamic` (QInt8, pesos de MatMul y de la tabla de embeddings vía Gather).
- mmBERT-small: pesos preentrenados (`pytorch_model.bin`/safetensors del caché).
- La poda conserva ids vistos en MASSIVE (es train+val, en y pt test) y hatecheck-es, más especiales, y rellena hasta ~55 k con piezas de alfabeto latino por orden de id; ids fuera se mapean a `<unk>`. Vocabularios en `vocab-podado-*.json`.

## Coseno de la poda (200 frases en español de MASSIVE test, no usadas para podar)

| modelo | pesos | vocab original→podado | podado vs original fp32 (mín / media; frases ≥0,999) | podado vs original int8 (mín / media; frases ≥0,999) | int8 vs fp32 (mín / media) |
|---|---|---|---|---|---|
| e5-small | preentrenados | 250037→55000 | 0.958061 / 0.999589; 198/200 | 0.955706 / 0.999576; 198/200 | 0.9723 / 0.9892 |
| mmBERT-small | preentrenados | 256000→55000 | 0.962421 / 0.999045; 187/200 | 0.999325 / 0.999972; 200/200 | -0.9388 / -0.8846 |

## Latencias (ms)

| modelo | precisión | poda | tokens | hilos | p50 | p99 | RSS pico (MB) | disco (MB) | frío (ms) |
|---|---|---|---|---|---|---|---|---|---|
| potion-multilingual-128M (static) | fp32 | no | 16 | 4 | 0.01 | 0.02 | 1886 | 512 | 4791 |
| potion-multilingual-128M (static) | fp32 | no | 64 | 4 | 0.03 | 0.04 | 1886 | 512 | 4791 |
| potion-multilingual-128M (static) | fp32 | no | 256 | 4 | 0.07 | 0.09 | 1886 | 512 | 4791 |
| potion-multilingual-128M (static) | fp32 | no | 16 | 1 | 0.01 | 0.02 | 1886 | 512 | 4800 |
| potion-multilingual-128M (static) | fp32 | no | 64 | 1 | 0.03 | 0.03 | 1886 | 512 | 4800 |
| potion-multilingual-128M (static) | fp32 | no | 256 | 1 | 0.08 | 0.11 | 1886 | 512 | 4800 |
| e5-small | int8 | sí | 16 | 4 | 3.66 | 4.26 | 133 | 43 | 202 |
| e5-small | int8 | sí | 64 | 4 | 11.52 | 12.05 | 133 | 43 | 202 |
| e5-small | int8 | sí | 256 | 4 | 45.12 | 46.87 | 133 | 43 | 202 |
| e5-small | fp32 | sí | 16 | 4 | 5.50 | 5.79 | 308 | 171 | 436 |
| e5-small | fp32 | sí | 64 | 4 | 16.94 | 17.44 | 308 | 171 | 436 |
| e5-small | fp32 | sí | 256 | 4 | 65.66 | 70.47 | 308 | 171 | 436 |
| e5-small | int8 | sí | 16 | 1 | 4.95 | 5.20 | 133 | 43 | 188 |
| e5-small | int8 | sí | 64 | 1 | 18.93 | 19.31 | 133 | 43 | 188 |
| e5-small | int8 | sí | 256 | 1 | 88.21 | 90.38 | 133 | 43 | 188 |
| e5-small | fp32 | sí | 16 | 1 | 10.12 | 11.01 | 308 | 171 | 430 |
| e5-small | fp32 | sí | 64 | 1 | 32.09 | 33.27 | 308 | 171 | 430 |
| e5-small | fp32 | sí | 256 | 1 | 130.67 | 134.13 | 308 | 171 | 430 |
| mmBERT-small | int8 | sí | 16 | 4 | 7.51 | 7.79 | 154 | 64 | 660 |
| mmBERT-small | int8 | sí | 64 | 4 | 23.55 | 24.06 | 154 | 64 | 660 |
| mmBERT-small | int8 | sí | 256 | 4 | 90.46 | 108.35 | 154 | 64 | 660 |
| mmBERT-small | fp32 | sí | 16 | 4 | 12.64 | 13.57 | 429 | 254 | 992 |
| mmBERT-small | fp32 | sí | 64 | 4 | 36.55 | 37.95 | 429 | 254 | 992 |
| mmBERT-small | fp32 | sí | 256 | 4 | 133.04 | 134.74 | 429 | 254 | 992 |
| mmBERT-small | int8 | sí | 16 | 1 | 10.22 | 10.41 | 154 | 64 | 654 |
| mmBERT-small | int8 | sí | 64 | 1 | 37.35 | 37.94 | 154 | 64 | 654 |
| mmBERT-small | int8 | sí | 256 | 1 | 159.25 | 162.86 | 154 | 64 | 654 |
| mmBERT-small | fp32 | sí | 16 | 1 | 19.42 | 20.99 | 430 | 254 | 964 |
| mmBERT-small | fp32 | sí | 64 | 1 | 61.86 | 64.31 | 430 | 254 | 964 |
| mmBERT-small | fp32 | sí | 256 | 1 | 255.10 | 260.26 | 430 | 254 | 964 |
| e5-small | int8 | no | 16 | 4 | 3.51 | 4.25 | 271 | 118 | 342 |
| e5-small | int8 | no | 64 | 4 | 11.43 | 11.86 | 271 | 118 | 342 |
| e5-small | int8 | no | 256 | 4 | 44.99 | 45.91 | 271 | 118 | 342 |
| e5-small | fp32 | no | 16 | 4 | 5.77 | 6.36 | 879 | 470 | 1053 |
| e5-small | fp32 | no | 64 | 4 | 17.69 | 24.26 | 879 | 470 | 1053 |
| e5-small | fp32 | no | 256 | 4 | 65.59 | 66.55 | 879 | 470 | 1053 |
| e5-small | int8 | no | 16 | 1 | 4.97 | 5.23 | 271 | 118 | 337 |
| e5-small | int8 | no | 64 | 1 | 19.24 | 20.15 | 271 | 118 | 337 |
| e5-small | int8 | no | 256 | 1 | 88.13 | 90.16 | 271 | 118 | 337 |
| e5-small | fp32 | no | 16 | 1 | 10.03 | 10.92 | 879 | 470 | 1047 |
| e5-small | fp32 | no | 64 | 1 | 32.06 | 39.73 | 879 | 470 | 1047 |
| e5-small | fp32 | no | 256 | 1 | 130.67 | 134.25 | 879 | 470 | 1047 |
| mmBERT-small | int8 | no | 16 | 4 | 7.44 | 7.71 | 301 | 141 | 806 |
| mmBERT-small | int8 | no | 64 | 4 | 23.44 | 24.73 | 301 | 141 | 806 |
| mmBERT-small | int8 | no | 256 | 4 | 89.44 | 91.15 | 301 | 141 | 806 |
| mmBERT-small | fp32 | no | 16 | 4 | 12.22 | 15.25 | 981 | 562 | 1591 |
| mmBERT-small | fp32 | no | 64 | 4 | 36.25 | 37.77 | 981 | 562 | 1591 |
| mmBERT-small | fp32 | no | 256 | 4 | 133.05 | 155.07 | 981 | 562 | 1591 |
| mmBERT-small | int8 | no | 16 | 1 | 10.86 | 12.60 | 301 | 141 | 815 |
| mmBERT-small | int8 | no | 64 | 1 | 36.91 | 38.01 | 301 | 141 | 815 |
| mmBERT-small | int8 | no | 256 | 1 | 160.27 | 162.08 | 301 | 141 | 815 |
| mmBERT-small | fp32 | no | 16 | 1 | 19.28 | 20.80 | 981 | 562 | 1592 |
| mmBERT-small | fp32 | no | 64 | 1 | 62.39 | 62.58 | 981 | 562 | 1592 |
| mmBERT-small | fp32 | no | 256 | 1 | 254.60 | 259.11 | 981 | 562 | 1592 |

