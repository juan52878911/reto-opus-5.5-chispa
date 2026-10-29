# Esquemas nuevos: estado y trabajo pendiente

## Qué pasa hoy
Un esquema que llega en la petición y que ningún `.chispa` trae:
- **L1** lo decide: calcula el embedding de cada opción al vuelo y lo cachea por esquema ([`l1.go`](../server/decide/l1.go)). Necesita sección L1.
- **L2 no opina.** Busca la torre de cada opción en `ESQUEMAS` por `HashEsquema(pregunta, opciones)`; sin ella devuelve «sin opinión» y no llama al ONNX
  ([`l2.go`](../server/decide/l2.go)). Test: `TestL2MaxSim` y `TestEsquemaNuevoLoDecideL1`.
- **L0, L2c y L0TF** solo existen para el esquema con el que se entrenó el `.chispa`.

Por eso el servidor no puede servir un esquema nuevo con solo L2: la hipótesis «zero-shot con L2» queda **refutada con el código actual**. El zero-shot real es L1,
con las cifras de [02](02-inicio-rapido.md#tres-modos).

## Qué falta (trabajo pendiente, no implementado)
La torre de una opción es el pasaje «pregunta · opción · descripción» pasado por e5 y por el módulo `Torre` ([`model/l2/modelo.py`](../model/l2/modelo.py)).
El ONNX de la sección L2 solo exporta el lado de la consulta (`input_ids`, `attention_mask` → `S`; [`exportar.py`](../model/l2/exportar.py)). Para calcular torres al vuelo hace falta:
1. Exportar un segundo ONNX (e5 + `Torre`: ids de pasaje → vector) y guardarlo en una sección nueva del formato `.chispa` ([04](04-formato-chispa.md)).
2. Tokenizar con el prefijo «passage: » en lugar de «query: » (hoy `Tokenizador.IDs` solo pone el de consulta).
3. En `L2.Similitudes`, si `Buscar` falla: calcular la torre, cuantizarla a int8 con escala y guardarla en un LRU por hash de esquema (como la caché de L1).
4. Un checkpoint de L2 entrenado para generalizar a esquemas no vistos. El repositorio no trae ninguno y las cabezas (`choice`, `noul`) se calibraron con los esquemas del entrenamiento.
5. Medir en tareas no vistas (massive, clinc150 y otras como pruebas) antes de llamar a esto «modo por defecto».

Es un cambio de formato, de exportador, de tokenizador y de entrenamiento; no cabe en `server/decide`. Tests previstos con un codificador falso, como `sesionFalsa` en `l2_test.go`.
