# Torre de esquemas en ONNX int8: paridad

Generado con `python -m model.l2.exportar --torre-onnx SALIDA --ckpt-aleatorio --medir-torre DIR --fixture-torre DIR`
(semilla 20261029). e5 de `~/hf`, **pesos de L2 aleatorios con semilla fija** (aquí no está el checkpoint real): la fidelidad de la
cuantización de e5 y de la torre no depende de que estén entrenados.

| medida | objetivo | resultado | cumple |
|---|---|---|---|
| coseno medio de `h`, ONNX tal como se exporta (poda) vs PyTorch fp32, 300 textos | ≥ 0,999 | 0,9997 | sí |
| coseno mínimo / p1 (ídem) | — | 0,9992 / 0,9993 | — |
| coseno medio, solo cuantización (vocabulario ampliado, sin `<unk>`) | ≥ 0,999 | 0,9998 | sí |
| coseno mínimo (ídem) | — | 0,9995 | — |
| top-1 de choice, torres ONNX (poda) vs torres PyTorch, 300 filas × 8 opciones | ≥ 0,98 | 0,8067 | NO |
| top-1 de choice, solo cuantización (sin `<unk>`) | ≥ 0,98 | 0,7500 | NO |
| ídem, mitad de filas con más margen (margen medio 0,0016) | — | 0,9267 | — |
| tamaño del ONNX de la torre (vocabulario podado: sí) | ≤ 50 MB | 47.8 MB (fp32: 178.4) | sí |

Cuantización de la torre: dinamico, por canal=True, opset 17, `Torre` en fp32. El ONNX de consulta pesa 49.3 MB.

Textos de coseno: tarea massive-es del repo (pregunta real y 6 redacciones × cada intención, con descripciones), en el formato
del contrato (`passage: pregunta · opción · descripción`). Top-1: 300 mensajes de validación de massive-es, 8 opciones cada
uno, con las S del ONNX de consulta en los dos lados: solo cambian las torres.


Poda frente a cuantización: con el vocabulario podado 0.5 % de los tokens de estos textos caen en `<unk>` y el coseno
baja por eso. Con el mismo vocabulario ampliado con los ids de estos textos (sin `<unk>`; solo cuantización, 47.8 MB) el
coseno medio es 0.999758 y el mínimo 0.999454.

Top-1 con pesos aleatorios: el margen medio entre la mejor opción y la segunda es 0,0010 (softplus·maxsim), así que el acuerdo
mide en buena parte ruido sobre empates casi exactos y no es extrapolable a un checkpoint entrenado. Hay que repetir la
medida con el real.
