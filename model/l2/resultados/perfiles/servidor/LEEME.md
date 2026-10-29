# Torre de esquemas en ONNX int8: paridad

Generado con `python -m model.l2.exportar --torre-onnx SALIDA --ckpt-aleatorio --medir-torre DIR --fixture-torre DIR`
(semilla 20261029). e5 de `~/hf`, **pesos de L2 aleatorios con semilla fija** (aquí no está el checkpoint real): la fidelidad de la
cuantización de e5 y de la torre no depende de que estén entrenados.

| medida | objetivo | resultado | cumple |
|---|---|---|---|
| coseno medio de `h`, ONNX tal como se exporta (poda) vs PyTorch fp32, 300 textos | ≥ 0,999 | 1,0000 | sí |
| coseno mínimo / p1 (ídem) | — | 1,0000 / 1,0000 | — |
| top-1 de choice, torres ONNX (poda) vs torres PyTorch, 300 filas × 8 opciones | ≥ 0,98 | 1,0000 | sí |
| tamaño del ONNX de la torre (vocabulario podado: no) | ≤ 50 MB | 471.6 MB (fp32: 471.6) | NO |

Cuantización de la torre: ninguna, por canal=True, opset 17, `Torre` en fp32. El ONNX de consulta pesa 473.0 MB.

Textos de coseno: tarea massive-es del repo (pregunta real y 6 redacciones × cada intención, con descripciones), en el formato
del contrato (`passage: pregunta · opción · descripción`). Top-1: 300 mensajes de validación de massive-es, 8 opciones cada
uno, con las S del ONNX de consulta en los dos lados: solo cambian las torres.


Top-1 con pesos aleatorios: el margen medio entre la mejor opción y la segunda es 0,0010 (softplus·maxsim), así que el acuerdo
mide en buena parte ruido sobre empates casi exactos y no es extrapolable a un checkpoint entrenado. Hay que repetir la
medida con el real.
