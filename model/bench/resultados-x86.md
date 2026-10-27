# T0.3 Resultados x86 (microVM kindling)

- CPU: Intel(R) Xeon(R) Processor @ 3.30GHz, 4 vCPU, modelo 58 paso 9; flags relevantes: avx (sin avx2/VNNI)
- Carga del host al informar (loadavg 1/5/15 min): 0.62 / 1.14 / 2.00. Máquina virtual compartida: cifras = cota pesimista; el i7-8700T se mide aparte.
- Python 3.11.2; onnxruntime/torch/transformers de ~/venv; 20 calentamientos + 200 repeticiones por celda; batch 1; semilla 20261027.
- Latencia = `session.run` + pooling medio + normalización sobre ids ya tokenizados (no incluye tokenizar). RSS pico = `ru_maxrss` del proceso de (variante, hilos), incluye la carga y todas las longitudes. Disco = fichero ONNX (potion: safetensors). Arranque en frío = crear sesión/cargar + primera inferencia, en proceso nuevo.
- Exportación: `torch.onnx.export` (opset 17) y no optimum: optimum 1.17.1 no importa con transformers 5.21 (`is_tf_available`). Int8 = `onnxruntime.quantization.quantize_dynamic` (QInt8, pesos de MatMul y de la tabla de embeddings vía Gather).
- **mmBERT-small: el caché `~/hf` solo trae config y tokenizador, sin pesos.** Se instancia la arquitectura real con pesos aleatorios (semilla fija): la latencia, RSS y tamaño son válidos; calidad/coseno no se pueden juzgar (el coseno de poda sí es válido como prueba de la mecánica, no del contenido).
- La poda conserva ids vistos en MASSIVE (es train+val, en y pt test) y hatecheck-es, más especiales, y rellena hasta ~55 k con piezas de alfabeto latino por orden de id; ids fuera se mapean a `<unk>`. Vocabularios en `vocab-podado-*.json`.

## Coseno de la poda (200 frases en español de MASSIVE test, no usadas para podar)

| modelo | pesos | vocab original→podado | podado vs original fp32 (mín / media; frases ≥0,999) | podado vs original int8 (mín / media; frases ≥0,999) | int8 vs fp32 (mín / media) |
|---|---|---|---|---|---|
| e5-small | preentrenados | 250037→55000 | 0.958061 / 0.999589; 198/200 | 0.958764 / 0.999589; 198/200 | 0.9719 / 0.9894 |
| mmBERT-small | ALEATORIOS (sin pesos en el caché) | 256000→55000 | 0.640938 / 0.992019; 187/200 | 0.640886 / 0.992019; 187/200 | 1.0000 / 1.0000 |

## Latencias (ms)

| modelo | precisión | poda | tokens | hilos | p50 | p99 | RSS pico (MB) | disco (MB) | frío (ms) |
|---|---|---|---|---|---|---|---|---|---|
| potion-multilingual-128M (static) | fp32 | no | 16 | 4 | 0.07 | 1.16 | 1878 | 512 | 17696 |
| potion-multilingual-128M (static) | fp32 | no | 64 | 4 | 0.11 | 0.46 | 1878 | 512 | 17696 |
| potion-multilingual-128M (static) | fp32 | no | 256 | 4 | 0.23 | 0.44 | 1878 | 512 | 17696 |
| potion-multilingual-128M (static) | fp32 | no | 16 | 1 | 0.08 | 0.12 | 1883 | 512 | 12629 |
| potion-multilingual-128M (static) | fp32 | no | 64 | 1 | 0.11 | 0.16 | 1883 | 512 | 12629 |
| potion-multilingual-128M (static) | fp32 | no | 256 | 1 | 0.23 | 0.34 | 1883 | 512 | 12629 |
| e5-small | int8 | sí | 16 | 4 | 94.32 | 219.74 | 127 | 43 | 1071 |
| e5-small | int8 | sí | 64 | 4 | 295.46 | 743.77 | 127 | 43 | 1071 |
| e5-small | int8 | sí | 256 | 4 | 970.23 | 1611.05 | 127 | 43 | 1071 |
| e5-small | fp32 | sí | 16 | 4 | 85.82 | 274.57 | 306 | 171 | 1107 |
| e5-small | fp32 | sí | 64 | 4 | 227.17 | 506.79 | 306 | 171 | 1107 |
| e5-small | fp32 | sí | 256 | 4 | 586.85 | 843.74 | 306 | 171 | 1107 |
| e5-small | int8 | sí | 16 | 1 | 34.05 | 49.02 | 127 | 43 | 435 |
| e5-small | int8 | sí | 64 | 1 | 112.55 | 200.08 | 127 | 43 | 435 |
| e5-small | int8 | sí | 256 | 1 | 528.07 | 800.11 | 127 | 43 | 435 |
| e5-small | fp32 | sí | 16 | 1 | 27.75 | 50.09 | 305 | 171 | 740 |
| e5-small | fp32 | sí | 64 | 1 | 94.71 | 159.95 | 305 | 171 | 740 |
| e5-small | fp32 | sí | 256 | 1 | 434.19 | 735.37 | 305 | 171 | 740 |
| mmBERT-small | int8 | sí | 16 | 4 | 124.88 | 208.18 | 152 | 64 | 1871 |
| mmBERT-small | int8 | sí | 64 | 4 | 342.82 | 550.50 | 152 | 64 | 1871 |
| mmBERT-small | int8 | sí | 256 | 4 | 1180.23 | 1835.19 | 152 | 64 | 1871 |
| mmBERT-small | fp32 | sí | 16 | 4 | 94.97 | 195.56 | 414 | 254 | 4412 |
| mmBERT-small | fp32 | sí | 64 | 4 | 308.61 | 496.88 | 414 | 254 | 4412 |
| mmBERT-small | fp32 | sí | 256 | 4 | 1067.66 | 1579.06 | 414 | 254 | 4412 |
| mmBERT-small | int8 | sí | 16 | 1 | 66.39 | 114.64 | 152 | 64 | 1503 |
| mmBERT-small | int8 | sí | 64 | 1 | 217.87 | 300.70 | 152 | 64 | 1503 |
| mmBERT-small | int8 | sí | 256 | 1 | 989.67 | 1597.30 | 152 | 64 | 1503 |
| mmBERT-small | fp32 | sí | 16 | 1 | 52.49 | 83.00 | 412 | 254 | 1826 |
| mmBERT-small | fp32 | sí | 64 | 1 | 183.27 | 290.18 | 412 | 254 | 1826 |
| mmBERT-small | fp32 | sí | 256 | 1 | 839.50 | 1400.64 | 412 | 254 | 1826 |
| e5-small | int8 | no | 16 | 4 | 53.48 | 113.45 | 268 | 118 | 619 |
| e5-small | int8 | no | 64 | 4 | 179.65 | 346.39 | 268 | 118 | 619 |
| e5-small | int8 | no | 256 | 4 | 632.91 | 1102.68 | 268 | 118 | 619 |
| e5-small | fp32 | no | 16 | 4 | 42.22 | 126.11 | 878 | 470 | 2437 |
| e5-small | fp32 | no | 64 | 4 | 156.74 | 323.59 | 878 | 470 | 2437 |
| e5-small | fp32 | no | 256 | 4 | 594.67 | 980.58 | 878 | 470 | 2437 |
| e5-small | int8 | no | 16 | 1 | 32.39 | 54.87 | 268 | 118 | 568 |
| e5-small | int8 | no | 64 | 1 | 111.07 | 178.19 | 268 | 118 | 568 |
| e5-small | int8 | no | 256 | 1 | 511.31 | 784.07 | 268 | 118 | 568 |
| e5-small | fp32 | no | 16 | 1 | 26.88 | 45.05 | 877 | 470 | 1442 |
| e5-small | fp32 | no | 64 | 1 | 93.54 | 163.20 | 877 | 470 | 1442 |
| e5-small | fp32 | no | 256 | 1 | 418.31 | 674.56 | 877 | 470 | 1442 |
| mmBERT-small | int8 | no | 16 | 4 | 112.14 | 304.33 | 299 | 141 | 1761 |
| mmBERT-small | int8 | no | 64 | 4 | 336.57 | 541.85 | 299 | 141 | 1761 |
| mmBERT-small | int8 | no | 256 | 4 | 1190.21 | 1858.31 | 299 | 141 | 1761 |
| mmBERT-small | fp32 | no | 16 | 4 | 110.30 | 229.78 | 978 | 562 | 8790 |
| mmBERT-small | fp32 | no | 64 | 4 | 347.22 | 663.17 | 978 | 562 | 8790 |
| mmBERT-small | fp32 | no | 256 | 4 | 1083.54 | 1573.57 | 978 | 562 | 8790 |
| mmBERT-small | int8 | no | 16 | 1 | 67.65 | 133.82 | 299 | 141 | 1703 |
| mmBERT-small | int8 | no | 64 | 1 | 222.44 | 330.78 | 299 | 141 | 1703 |
| mmBERT-small | int8 | no | 256 | 1 | 981.34 | 1531.52 | 299 | 141 | 1703 |
| mmBERT-small | fp32 | no | 16 | 1 | 53.19 | 94.32 | 979 | 562 | 3158 |
| mmBERT-small | fp32 | no | 64 | 1 | 183.88 | 270.85 | 979 | 562 | 3158 |
| mmBERT-small | fp32 | no | 256 | 1 | 833.89 | 1348.26 | 979 | 562 | 3158 |

## Lectura (escrita a mano tras la medición; ver cifras arriba)

- Hipótesis refutada en esta VM: e5-small int8 podado a 64 tokens da p99 ≈ 200 ms con 1 hilo y ≈ 744 ms con 4 (no < 15 ms). La CPU no tiene AVX2 ni VNNI (Ivy Bridge), así que int8 dinámico no acelera: es igual o más lento que fp32 (p50 64 tok, 1 hilo: 113 vs 95 ms) y solo gana en RSS y disco.
- 4 hilos es más lento que 1 en los modelos transformer (vCPU compartidas/hiperhilos, hay robo de CPU): usar 1 hilo en esta VM. El i7-8700T (AVX2) debe medirse aparte; no extrapolar de aquí.
- mmBERT-small frente a e5-small (p50 64 tok, 1 hilo, fp32 podado): 183 vs 95 ms (≈1,9×), dentro del 1,5-2× previsto, pero con pesos aleatorios y sin saber su calidad.
- La poda no cambia el cómputo (p50 igual dentro del ruido) pero reduce RSS pico (e5 fp32: 877→305 MB) y disco (470→171 MB; int8 118→43 MB).
- Potion (static) es 100-1000× más rápido (p50 ≈ 0,1 ms), pero su RSS pico es ≈ 1,9 GB y arranca en 12-18 s (carga de model2vec + 512 MB fp32); habría que podar/cuantizar su tabla para móvil.
- Coseno de la poda de e5: media 0,99959 (cumple ≥ 0,999) pero 2/200 frases bajan a ≥ 0,958 porque una pieza léxica (`▁medioambiental`, `▁faculta`) cayó fuera del vocabulario y se mapea a `<unk>`; la regla «cada frase ≥ 0,999» no se cumple del todo. Arreglo: más corpus en es/pt/en en el recorte, o reconvertir las piezas ausentes en subpiezas conservadas.
