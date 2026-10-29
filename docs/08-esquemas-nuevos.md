# Esquemas nuevos: estado y trabajo pendiente

El esquema viaja en la petición a `/v1/decide`: pregunta, `kind`, ids y descripciones. Lo que decide sobre él depende de las capas
del `.chispa` que sirves. Cómo escribir el esquema: [02-inicio-rapido.md](02-inicio-rapido.md).

**Estado:** la torre de L2 al vuelo está cableada de punta a punta: sección `TORR` ([`torr.go`](../format/chispa3/torr.go)), tokenizador en modo
«passage: » (`TokenizarPasaje`, `runtime/tok`), [`server/torre`](../server/torre) y `ArmarDesde` en [`modelo.go`](../server/decide/modelo.go), que llama a `ConTorres`
si el `.chispa` trae `TORR`. Falta el ONNX real de la torre: no hay paridad medida ni cifra de L2 en tareas no vistas.

## Qué pasa con un esquema nuevo
Un esquema que llega en la petición y que ningún `.chispa` trae:
- **L1** lo decide: calcula el embedding de cada opción al vuelo y lo cachea por esquema ([`l1.go`](../server/decide/l1.go)). Necesita sección L1.
- **L2, con `TORR`**, calcula la torre de cada opción al vuelo (pasaje «pregunta · opción · descripción» con prefijo de `TORR`, ONNX de la sección) y la guarda en un LRU por hash
  de esquema. Hace falta `chispa-server -tok …` compilado con `-tags ort`. Si `ESQUEMAS` ya trae la torre, se usa esa.
- **L2, sin `TORR`**, busca en `ESQUEMAS` por `HashEsquema(pregunta, opciones)`; sin ella no opina y decide solo L1.
- **L0, L2c y L0TF** solo existen para el esquema con el que se entrenó el `.chispa`.

`chispa train --torre <onnx>` mete `TORR` en cualquier modo (zero-shot, few-shot, `--conjunta`):

```
PYTHONPATH=sdk/python python -m chispa train --esquema ferreteria.yaml --l2 l2.chispa --torre torre.onnx --salida ferreteria.chispa
```

- Valida el ONNX con `onnx` (se importa solo con `--torre`): entradas exactamente `input_ids` y `attention_mask` int64 de rango 2,
  salida `h` float32 (B, dim), opset ≥ 17. Si `onnxruntime` está, prueba un lote de 2 y exige norma de `h` ≈ 1 (1e-3); si no, avisa y sigue.
- `dim`, `max_len` y prefijo salen de `metadata_props` del ONNX (`chispa.torre.dim`, `chispa.torre.max_len`, `chispa.torre.prefijo`) y,
  si faltan, de la forma de `h` (dim) y de los defaults 128 y `"passage: "`. `--torre-dim`, `--torre-max-len` y `--torre-prefijo` mandan;
  si chocan con los metadatos (o `--torre-dim` con la forma de `h`), error.
- `TORR` se añade al final, reescribiendo el `.chispa` ya escrito (el entrenador de Go lo escribe entero); las demás secciones no cambian. Sin `--torre`, la salida es la de siempre.

## Qué falta
1. **El ONNX real de la torre.** En esta base `model/l2/exportar.py` solo exporta el lado de la consulta; no hay exportador de la torre (e5 de pasaje + `Torre`) ni paridad medida contra PyTorch. Sin medir.
2. Un checkpoint de L2 entrenado para generalizar a esquemas no vistos. El repositorio no trae ninguno y las cabezas (`choice`, `noul`) se calibraron con los esquemas del entrenamiento.
3. Medir en tareas no vistas (massive, clinc150 y otras como pruebas) antes de llamar a esto «modo por defecto».

Los tests de la torre usan un codificador falso, como `sesionFalsa` en `l2_test.go`.
