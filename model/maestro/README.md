# Maestro: etiquetas blandas (T1.6)

`blandas.py` añade `blanda: {opcion: prob}` (esquema v1) a las filas. Qwen (D4) es la única fuente de distribuciones
para destilar; Haiku nunca.

    python -m model.maestro.blandas --entrada a.jsonl b.jsonl --salida <dir> --modelo <id HF o ruta> [--lote 16] [--max-filas N]

## Cómo puntúa
- Prompt de chat (sistema + pregunta, mensaje y opciones `A. id: descripción`), sin razonamiento
  (`enable_thinking=False`). Cada opción se puntúa por el logprob, sobre todo el vocabulario, del primer token de su
  letra; la distribución es el softmax sobre esas letras.
- bf16 en CUDA (fp32 en CPU). Batching por longitud (lote ≤ `--lote` y ≤ 16 384 tokens), relleno a la izquierda y solo
  los logits de la última posición.
- **Más de 26 opciones: dos pasadas con candidatos** (elegida frente al softmax sobre logprobs de bloques). Razón: el
  logprob de una letra en un bloque no es comparable con el de otro bloque (cada prompt reparte su masa solo entre sus
  letras, y la masa fuera de las letras varía), así que mezclar bloques con un softmax común mide el sesgo de
  posición/bloque, no la plausibilidad. Pasada 1: bloques equilibrados de ≤ 26 (151 → 6 de 26/25); softmax dentro de
  cada uno. Pasada 2: los `26 // n_bloques` mejores de cada bloque (≤ 26 en total) compiten en un solo prompt; su softmax
  recibe `1 − 0.02` de la masa. El `0.02` restante se reparte entre las no candidatas en proporción a su probabilidad
  dentro de su bloque. Suma 1 exacta (se renormaliza). Coste: n_bloques + 1 prompts por fila. Límite: una opción que
  Qwen no ponga entre las mejores de su bloque solo recibe masa de relleno.
- Sin barajar el orden de opciones: hay sesgo de posición (las letras tempranas), no medido.

## Salida
Por cada entrada `<n>.jsonl`: `<salida>/<n>.jsonl` (`uso_comercial` true) y `<salida>/<n>.solo-medir.jsonl`
(`uso_comercial` false: solo para medir; no destilar con ellas). Se escribe fila a fila y **reanuda** saltando los `id`
ya escritos. `--max-filas N` es un tope total repartido entre entradas en proporción a su tamaño, con paso regular
(cubre todos los splits; mínimo 1 por entrada, así que puede pasarse por unas pocas).

`resumen.json`: modelo pedido y usado (con motivo), `filas_por_s` y `horas_gpu` de esta ejecución (las filas nuevas),
`acuerdo_top1` por `tarea|split|fuente[|solo-medir]` y global (top-1 de `blanda` frente a `etiqueta`, sobre todo lo
escrito, también lo reanudado) y `ece_maestro` (15 cubos, `model.evaluacion.metricas.ece`, confianza = prob máxima).

## Modelo
Por defecto `Qwen/Qwen3.5-4B-Instruct`; si no existe en el Hub cae a `Qwen/Qwen3.5-4B` y luego a
`Qwen/Qwen3-4B-Instruct-2507`, y lo registra. Nunca se ha cargado un Qwen real aquí (sin red).

## AWS
`aws/empaquetar.sh > codigo.tgz` y `aws/arranque.sh` (user-data; `__CHISPA_S3__`, `__MAX_FILAS__`). Pasos: Python de la
AMI (`/opt/pytorch/bin/python` o el primero que importe torch; lista `/opt` en el log), `pip install -U` de
transformers/accelerate/huggingface_hub, datasets públicos como `.delega/golden.sh` (HF_HOME=`~/hf`, porque
`model/datos/comun.py` lee ahí; se borra el snapshot de banking77 sin parquet), `model.datos.convertir`, y puntuación
de todo lo convertido + `model/herramientas/{train,test}.jsonl` + el corpus (`corpus.tgz`, opcional, espera 10 min).
Sube `blandas.tgz` y `log.txt`. `shutdown -h +200`; la puntuación tiene tope de 170 min y se reintenta una vez
(reanudando).

Prueba en seco: `CHISPA_LOCAL=1 CHISPA_MODELO=<Qwen diminuto> bash arranque.sh` (ver los tests para construirlo).
