# T0.3 Resultados x86 (medido fuera de kindling: ver CPU abajo)

- CPU: Intel(R) Xeon(R) Platinum 8375C CPU @ 2.90GHz, 4 vCPU, modelo 106 paso 6; flags relevantes: avx, avx2, avx512f, avx512_vnni, fma
- Carga del host al informar (loadavg 1/5/15 min): 1.51 / 1.98 / 1.19. Máquina virtual compartida: cifras = cota pesimista; el i7-8700T se mide aparte.
- Python 3.11.17; onnxruntime/torch/transformers de ~/venv; 20 calentamientos + 200 repeticiones por celda; batch 1; semilla 20261027.
- Latencia = `session.run` + pooling medio + normalización sobre ids ya tokenizados (no incluye tokenizar). RSS pico = `ru_maxrss` del proceso de (variante, hilos), incluye la carga y todas las longitudes. Disco = fichero ONNX (potion: safetensors). Arranque en frío = crear sesión/cargar + primera inferencia, en proceso nuevo.
- Exportación: `torch.onnx.export` (opset 17) y no optimum: optimum 1.17.1 no importa con transformers 5.21 (`is_tf_available`). Int8 = `onnxruntime.quantization.quantize_dynamic` (QInt8, pesos de MatMul y de la tabla de embeddings vía Gather).
- mmBERT-small: pesos preentrenados (`pytorch_model.bin`/safetensors del caché).
- La poda conserva ids vistos en MASSIVE (es train+val, en y pt test) y hatecheck-es, más especiales, y rellena hasta ~55 k con piezas de alfabeto latino por orden de id; ids fuera se mapean a `<unk>`. Vocabularios en `vocab-podado-*.json`.

## Coseno de la poda (200 frases en español de MASSIVE test, no usadas para podar)

| modelo | pesos | vocab original→podado | podado vs original fp32 (mín / media; frases ≥0,999) | podado vs original int8 (mín / media; frases ≥0,999) | int8 vs fp32 (mín / media) |
|---|---|---|---|---|---|
| e5-small | preentrenados | 250037→55000 | 0.958061 / 0.999589; 198/200 | 0.958764 / 0.999591; 198/200 | 0.9719 / 0.9894 |
| mmBERT-small | preentrenados | 256000→55000 | 0.962421 / 0.999045; 187/200 | 0.951779 / 0.992744; 0/200 | 0.9355 / 0.9833 |

## Latencias (ms)

| modelo | precisión | poda | tokens | hilos | p50 | p99 | RSS pico (MB) | disco (MB) | frío (ms) |
|---|---|---|---|---|---|---|---|---|---|
| potion-multilingual-128M (static) | fp32 | no | 16 | 4 | 0.01 | 0.01 | 1887 | 512 | 4435 |
| potion-multilingual-128M (static) | fp32 | no | 64 | 4 | 0.03 | 0.03 | 1887 | 512 | 4435 |
| potion-multilingual-128M (static) | fp32 | no | 256 | 4 | 0.07 | 0.08 | 1887 | 512 | 4435 |
| potion-multilingual-128M (static) | fp32 | no | 16 | 1 | 0.01 | 0.01 | 1887 | 512 | 4436 |
| potion-multilingual-128M (static) | fp32 | no | 64 | 1 | 0.03 | 0.03 | 1887 | 512 | 4436 |
| potion-multilingual-128M (static) | fp32 | no | 256 | 1 | 0.07 | 0.08 | 1887 | 512 | 4436 |
| e5-small | int8 | sí | 16 | 4 | 2.59 | 2.64 | 132 | 43 | 192 |
| e5-small | int8 | sí | 64 | 4 | 6.76 | 6.89 | 132 | 43 | 192 |
| e5-small | int8 | sí | 256 | 4 | 25.35 | 25.49 | 132 | 43 | 192 |
| e5-small | fp32 | sí | 16 | 4 | 5.23 | 5.32 | 308 | 171 | 360 |
| e5-small | fp32 | sí | 64 | 4 | 13.04 | 13.32 | 308 | 171 | 360 |
| e5-small | fp32 | sí | 256 | 4 | 45.53 | 51.07 | 308 | 171 | 360 |
| e5-small | int8 | sí | 16 | 1 | 3.08 | 3.20 | 148 | 43 | 182 |
| e5-small | int8 | sí | 64 | 1 | 10.31 | 10.66 | 148 | 43 | 182 |
| e5-small | int8 | sí | 256 | 1 | 48.21 | 48.85 | 148 | 43 | 182 |
| e5-small | fp32 | sí | 16 | 1 | 8.87 | 9.26 | 308 | 171 | 352 |
| e5-small | fp32 | sí | 64 | 1 | 22.91 | 23.39 | 308 | 171 | 352 |
| e5-small | fp32 | sí | 256 | 1 | 87.86 | 88.63 | 308 | 171 | 352 |
| mmBERT-small | int8 | sí | 16 | 4 | 6.15 | 6.58 | 181 | 64 | 659 |
| mmBERT-small | int8 | sí | 64 | 4 | 15.76 | 16.21 | 181 | 64 | 659 |
| mmBERT-small | int8 | sí | 256 | 4 | 58.70 | 61.25 | 181 | 64 | 659 |
| mmBERT-small | fp32 | sí | 16 | 4 | 10.88 | 10.99 | 418 | 254 | 903 |
| mmBERT-small | fp32 | sí | 64 | 4 | 27.71 | 28.45 | 418 | 254 | 903 |
| mmBERT-small | fp32 | sí | 256 | 4 | 99.42 | 99.76 | 418 | 254 | 903 |
| mmBERT-small | int8 | sí | 16 | 1 | 7.11 | 7.43 | 154 | 64 | 638 |
| mmBERT-small | int8 | sí | 64 | 1 | 19.56 | 20.30 | 154 | 64 | 638 |
| mmBERT-small | int8 | sí | 256 | 1 | 97.55 | 99.30 | 154 | 64 | 638 |
| mmBERT-small | fp32 | sí | 16 | 1 | 18.79 | 19.17 | 392 | 254 | 902 |
| mmBERT-small | fp32 | sí | 64 | 1 | 46.15 | 47.04 | 392 | 254 | 902 |
| mmBERT-small | fp32 | sí | 256 | 1 | 187.24 | 189.26 | 392 | 254 | 902 |
| e5-small | int8 | no | 16 | 4 | 2.65 | 2.72 | 271 | 118 | 286 |
| e5-small | int8 | no | 64 | 4 | 6.96 | 7.09 | 271 | 118 | 286 |
| e5-small | int8 | no | 256 | 4 | 25.29 | 25.43 | 271 | 118 | 286 |
| e5-small | fp32 | no | 16 | 4 | 5.11 | 5.25 | 880 | 470 | 783 |
| e5-small | fp32 | no | 64 | 4 | 13.33 | 13.45 | 880 | 470 | 783 |
| e5-small | fp32 | no | 256 | 4 | 45.48 | 46.73 | 880 | 470 | 783 |
| e5-small | int8 | no | 16 | 1 | 2.99 | 3.03 | 271 | 118 | 277 |
| e5-small | int8 | no | 64 | 1 | 10.30 | 10.72 | 271 | 118 | 277 |
| e5-small | int8 | no | 256 | 1 | 47.90 | 48.55 | 271 | 118 | 277 |
| e5-small | fp32 | no | 16 | 1 | 8.56 | 8.73 | 880 | 470 | 796 |
| e5-small | fp32 | no | 64 | 1 | 22.83 | 23.28 | 880 | 470 | 796 |
| e5-small | fp32 | no | 256 | 1 | 87.54 | 88.29 | 880 | 470 | 796 |
| mmBERT-small | int8 | no | 16 | 4 | 6.17 | 6.42 | 302 | 141 | 754 |
| mmBERT-small | int8 | no | 64 | 4 | 15.57 | 16.27 | 302 | 141 | 754 |
| mmBERT-small | int8 | no | 256 | 4 | 58.89 | 59.40 | 302 | 141 | 754 |
| mmBERT-small | fp32 | no | 16 | 4 | 10.80 | 10.93 | 981 | 562 | 1338 |
| mmBERT-small | fp32 | no | 64 | 4 | 27.71 | 28.18 | 981 | 562 | 1338 |
| mmBERT-small | fp32 | no | 256 | 4 | 99.48 | 112.93 | 981 | 562 | 1338 |
| mmBERT-small | int8 | no | 16 | 1 | 7.05 | 7.41 | 302 | 141 | 750 |
| mmBERT-small | int8 | no | 64 | 1 | 19.01 | 20.00 | 302 | 141 | 750 |
| mmBERT-small | int8 | no | 256 | 1 | 97.62 | 99.03 | 302 | 141 | 750 |
| mmBERT-small | fp32 | no | 16 | 1 | 17.48 | 17.87 | 981 | 562 | 1316 |
| mmBERT-small | fp32 | no | 64 | 1 | 45.07 | 45.91 | 981 | 562 | 1316 |
| mmBERT-small | fp32 | no | 256 | 1 | 183.13 | 184.65 | 981 | 562 | 1316 |

