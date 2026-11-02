# Esquemas nuevos: estado y trabajo pendiente

El esquema viaja en la petición a `/v1/decide`: pregunta, `kind`, ids y descripciones. Lo que decide sobre él depende de las capas
del `.chispa` que sirves. Cómo escribir el esquema: [02-inicio-rapido.md](02-inicio-rapido.md).

**Estado:** la torre de L2 al vuelo está cableada de punta a punta con ONNX Runtime real: sección `TORR` ([`torr.go`](../format/chispa3/torr.go)), tokenizador en modo
«passage: » (`TokenizarPasaje`, `runtime/tok`), [`server/torre`](../server/torre/README.md) y `ArmarDesde` en [`modelo.go`](../server/decide/modelo.go), que llama a `ConTorres`
si el `.chispa` trae `TORR`. Los tests con ORT (`go test -tags ort`, véase [`server/README.md`](../server/README.md#compilar-y-probar-con-ort)) usan ONNX **sintéticos** con pesos aleatorios:
prueban la mecánica, no la calidad. Falta el ONNX real de la torre: no hay paridad medida ni cifra de L2 en tareas no vistas. Este nodo no tiene Go ni ORT: lo de Go no se ejecutó aquí.

## Qué pasa con un esquema nuevo
Un esquema que llega en la petición y que ningún `.chispa` trae:
- **L1** lo decide: calcula el embedding de cada opción al vuelo y lo cachea por esquema ([`l1.go`](../server/decide/l1.go)). Necesita sección L1.
- **L2, con `TORR`**, calcula la torre de cada opción al vuelo (pasaje «pregunta · opción · descripción» —o «pregunta · descripción» con `texto_torre: "v2_sin_id"`, ver [Texto de torre](#texto-de-torre)— con prefijo de `TORR`, ONNX de la sección) y la guarda en un LRU por torre (clave `HashEsquema(pregunta, [opción, descripción])`). Hace falta `chispa-server -tok …` compilado con `-tags ort`. Si `ESQUEMAS` ya trae la torre, se usa esa. Una petición puede calcular como mucho `max_torres_nuevas` torres sin cachear (256 por defecto, una pregunta completa; si el tope corta, calcula y cachea las que caben y escala con `escalate_reason: "sin_presupuesto_torres"`, así que la petición siguiente avanza) y la caché guarda `cache_torres` (16 384 por defecto), ambas en `-config`.
- **L2, sin `TORR`**, busca en `ESQUEMAS` por `HashEsquema(pregunta, opciones)`; sin ella no opina y decide solo L1.
- **L0, L2c y L0TF** solo existen para el esquema con el que se entrenó el `.chispa`.

`chispa train --torre <onnx>` mete `TORR` en cualquier modo (zero-shot, few-shot, `--conjunta`):

```
PYTHONPATH=sdk/python python -m chispa train --esquema ferreteria.yaml --l2 l2.chispa --torre torre.onnx --salida ferreteria.chispa
```

- Valida el ONNX con `onnx` (se importa solo con `--torre`): entradas exactamente `input_ids` y `attention_mask` int64 de rango 2,
  salida `h` float32 (B, dim), opset ≥ 17. Si `onnxruntime` está, prueba un lote de 2 y exige norma de `h` ≈ 1 (1e-3); si no, avisa y sigue.
- `dim`, `max_len` y prefijo salen de `metadata_props` del ONNX (`chispa.torre.dim`, `chispa.torre.max_len`, `chispa.torre.prefijo`) y,
  si faltan, de la forma de `h` (dim) y de los defaults 128 y `"passage: "` (`max_len` hasta 512; el runtime trunca el pasaje a ese valor). `--torre-dim`, `--torre-max-len` y `--torre-prefijo` mandan;
  si chocan con los metadatos (o `--torre-dim` con la forma de `h`), error.
- `TORR` se añade al final, reescribiendo el `.chispa` ya escrito (el entrenador de Go lo escribe entero); las demás secciones no cambian. Sin `--torre`, la salida es la de siempre.

## Texto de torre

El texto «passage: …» que se codifica con e5 depende de `META.texto_torre` del `.chispa` (ausente = `v1`; valor desconocido = error de carga). Hay un vector de torre por opción en choice y multi, uno (la opción `true`) en noul y uno (el nivel máximo) en score; para cada uno, con `strip(descripción)` = la descripción sin espacios Unicode en los extremos, solo para decidir si está vacía:

| versión | descripción no vacía | descripción vacía |
|---|---|---|
| `v1` | `passage: pregunta · id · descripción` | `passage: pregunta · id · ` |
| `v2_sin_id` | `passage: pregunta · descripción` (la descripción tal cual, sin `strip`) | el texto v1 exacto: `passage: pregunta · id · ` |

Sin cambios entre versiones: las claves de caché y de `ESQUEMAS` (`HashEsquema`, siguen llevando el id), el prefijo de `TORR`, la tokenización, el ONNX, el texto de la consulta y la normalización de mayúsculas (solo del mensaje). Una sola función por plataforma, `TextoTorre(version, pregunta, id, descripcion)` en `runtime/torre`, la usan el servidor (todos los caminos de torre al vuelo) y `chispamovil`; los SDK de Android e iOS piden los textos a `chispamovil` (`textosTorreL2`) y no los construyen. `GET /healthz` expone `texto_torre` cuando hay torre al vuelo, y el log de arranque lo repite en «capas efectivas». Paridad con Python: `server/decide/testdata/texto_torre_v2.json`, que genera `gen_texto_torre_v2.py` (la referencia `model/l2/modelo.py` aún no tiene v2, así que la regla v2 está implementada en el generador).

## Zero-shot con torre al vuelo, paso a paso
1. Escribe el esquema con una descripción por opción ([02-inicio-rapido.md](02-inicio-rapido.md#1-el-esquema)).
2. `chispa train --esquema … --l1 … --l2 l2.chispa --torre torre.onnx --salida x.chispa` (arriba). Sin `--l2` ni `--ckpt` el fichero lleva L1 y `TORR`, pero L2 no tiene encoder de mensaje y no opina.
3. Sirve con `-tags ort -tok e5.chispa-tok` ([06-despliegue.md](06-despliegue.md#compilar)). El esquema nuevo llega en la petición; no hace falta reentrenar.
4. Si falta `-tok` con `TORR` en el fichero, el servidor lo dice en el log y L2 solo decide esquemas de `ESQUEMAS`.

## Few-shot con soporte opcional
Con ejemplos (k por opción) y `--l1`, `chispa train` añade `SOPL1` **por defecto** (`--sin-soporte` para no escribirla; `--shrinkage-lambda λ` es solo el valor sugerido del informe, 4 si falta): k y la media int8 de los embeddings de L1 de los ejemplos de cada opción.
El runtime mezcla `p = normaliza((1−w)·p_desc + w·media)` con `w = k/(k+λ)`. Es la fórmula de G.8 con κ ≡ λ: el peso de la descripción es `κ/(κ+n) = 1−w`, la media va sin normalizar antes de mezclar y κ = 0 es solo ejemplos y κ = ∞ solo descripción (detalle y las normas por ranura de L2c en [04](04-formato-chispa.md)):

- con k pequeño pesa la descripción (zero-shot) y con k grande pesan los ejemplos; λ gobierna la transición;
- λ vive en el servidor: `l1_shrinkage_lambda` y `l2_shrinkage_lambda` (≥ 0; **L1 ausente = 4**, `l1_shrinkage_apagado: true` lo apaga; **L2 ausente = apagado**; 0 = solo ejemplos; muy grande/∞ = solo descripción, también en L2c) en `-config`. En el móvil, `Abrir` usa λ = 4 en L1; `AbrirConSoporte` (`SoporteApagado` = apagado explícito, +∞ = solo descripción), `Chispa.abrir(lambdaSoporteL1/L2)` en Kotlin y Swift (`lambdaSoporteL1` = 4,0 por defecto; `null`/`nil` = apagado explícito; con solo L2, L1 queda en 4, no apagado) y `chispa train --shrinkage-lambda` (el valor sugerido del informe);
- `SOPL1` es opcional y no cambia nada de lo anterior: sin ella el comportamiento es el de siempre (el default 4 no tiene sobre qué mezclar). L2c mezcla `h` (la torre de la descripción) con cada una de las K ranuras de soporte de `CONJ` y normaliza por ranura, con el k de esta sección: cambia el simproto, no el MaxSim de la torre. Con SOPL1 v2 (`--conjunta`) la media lleva la norma de cada ranura, como `modelo.py`; con v1 usa la media normalizada;
- medido (`model/l2/resultados/barrido-20261029/LEEME.md` (rama de modelos; G.8b, checkpoint de G.8)): con `l1_shrinkage_lambda` = 4 frente a sin soporte: massive 0,395 frente a 0,266, inyecciones 0,740 frente a 0,326, hatecheck 0,492 frente a 0,224; en JevBench cuesta 2 puntos (0,379 frente a 0,398). L2 sin soporte propio por defecto.

## τ: cuándo escala
- Zero-shot: `CALIB` sin calibrar, τ = 0,6; sus probabilidades no están calibradas ([07](07-rendimiento-y-limites.md#zero-shot)).
- Few-shot: `chispa train` ajusta T (choice) o a, b, θ (noul) de L1 con los ejemplos (80 % entrena y 20 % valida por hash; con menos de 10 por opción, L1 se calibra con todos) y fija
  `tau_escalate` en el τ más bajo con 0,95 de precisión en esa validación (mínimo 10 ejemplos; si no se alcanza, 1,0 y L1 siempre escala). Con k = 5 la calibración es ruidosa. Ese τ se calibra sin el encogimiento de `SOPL1` (aviso en el informe).
- Con `-config`, la config manda sobre `CALIB`. Los τ por defecto de la config: L0 0,8, L1 0,8, L2 0,7, L3 0,6.
- Un τ alto sube la precisión de lo contestado y la abstención; un τ bajo, al revés. La abstención con datos del cliente: [07](07-rendimiento-y-limites.md#excepción-2-la-abstención).
- `score` en L1: la confianza es P(mediana); si la masa se reparte entre niveles lejanos, escala.

## τ de esquema nuevo (`tau_l2_esquema_nuevo`)
**Default 0,846.** Medido sobre tareas no vistas (`model/l2/resultados/barrido-20261029/LEEME.md`, rama de modelos; G.8b, checkpoint de G.8): τ = 0,846 da precisión 0,95 con ~97 % de escalado; τ = 0,276 escala ≤ 20 % con precisión ~0,53. Se eligió 0,846 como default por prudente: ante un esquema que L2 no ha visto, prefiere escalar a acertar a medias (decisión del dueño del producto); 0,276 queda como alternativa si se prioriza no escalar. Prioridad: `-config` > `tau_l2_esquema_nuevo` de `CALIB` > 0,846. Para volver al comportamiento anterior (L2 usa su τ de siempre), `"tau_l2_esquema_nuevo_apagado": true` en `-config` (ignora también el de `CALIB`; junto con un τ es error). En móvil, `SinTauEsquemaNuevo(true)` en el motor antes de construir la cascada.

## Qué falta
1. **El ONNX real de la torre.** En esta base `model/l2/exportar.py` solo exporta el lado de la consulta; no hay exportador de la torre (e5 de pasaje + `Torre`) ni paridad medida contra PyTorch. Sin medir. (`server/torre/README.md` cita `model/l2/contrato-torre.md`, que no está en el repo.)
2. Un checkpoint de L2 entrenado para generalizar a esquemas no vistos. El repositorio no trae ninguno y las cabezas (`choice`, `noul`) se calibraron con los esquemas del entrenamiento.
3. Medir en tareas no vistas (massive, clinc150 y otras como pruebas) antes de llamar a esto «modo por defecto».
4. El efecto de `SOPL1` y de λ de L1 está medido (arriba); el de λ de L2 y el τ de zero-shot calibrado, sin medir.

Los tests de la torre usan un codificador falso, como `sesionFalsa` en `l2_test.go`, o ONNX sintéticos.
