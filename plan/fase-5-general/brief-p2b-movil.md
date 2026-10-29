# P2b Perfil móvil: poda ampliada con corpus, QDQ estático solo en las FFN y fp16 como referencia

## Antecedentes
P5 (`model/bench/torre/resultados-20261029-p5/LEEME.md`) midió el perfil `movil` frente a PyTorch con el checkpoint real
de G.8 corrida 2 (max_tok 256). Esa variante es int8 dinámico por canal, con la poda ampliada solo con los 500 textos de
calibración:
- coseno 0,905 con un 6,8 % de `<unk>`;
- coseno 0,971 sin `<unk>`;
- top-1 0,88 (objetivo ≥ 0,93).

El perfil `servidor` (fp32, vocabulario completo) da paridad exacta con 472 MB.

**Objetivo:** top-1 ≥ 0,93 con ≤ 60 MB por modelo (consulta y torre, cada uno).

## Hipótesis
- **Corpus:** ampliar la poda con un corpus amplio en español (las tareas en español de `~/datos` más su train) baja los
  `<unk>` por debajo del 1 % en textos que **no** están en ese corpus.
- **Cuantización:** int8 estático QDQ por canal **solo en las FFN** de e5 (los MatMul de intermediate y output dense), con
  la atención y LayerNorm en fp32, recupera el top-1 a ≥ 0,93 con unos 60 MB.
- **Referencia:** fp16 de todo, para saber cuánto cuesta la fidelidad en MB (≈ 2× int8).
- Se refuta midiendo con el checkpoint real.

## Terminado cuando
- **`model/l2/exportar.py`:** `--cuant-torre` y `--cuant` aceptan dos valores nuevos.
  - `ffn-estatico`: QDQ por canal solo en las FFN, calibrado con `--calib-torre` / `--n-calib`. Usa `nodes_to_quantize` u
    `op_types` de `onnxruntime.quantization`; documenta qué nodos entran.
  - `fp16`: con `onnxruntime.transformers.float16` o `onnxconverter_common`, el que haya en `~/venv`; si no hay ninguno,
    dilo. Las salidas siguen en fp32.
  - Tests con pesos aleatorios.
- **Poda ampliada.**
  - `--vocab-ampliar` acepta un directorio con jsonl.
  - Un script `model/bench/torre/corpus_poda.py` arma el corpus de ampliación en la instancia: los conversores de
    `model.datos` en español y su train. Saca **aparte** un conjunto de comprobación (massive-es test y JevBench) que no se
    usa para ampliar.
  - El informe da el % de `<unk>` sobre ese conjunto de comprobación.
- **`model/bench/torre/movil.sh`:** user-data de una c6a.2xlarge spot con el patrón de `e2e.sh`.
  - Paquete de una rama, `shutdown -h +60`, descargas por fichero, checkpoint de G.8 corrida 2 y ≤ 16 KB.
  - Mide estas variantes de **consulta y torre**: `dinamico` (lo actual), `ffn-estatico`, `fp16` y `fp32` (referencia),
    cada una con vocabulario completo y con la poda ampliada.
  - Para cada una: MB, coseno y top-1 frente a PyTorch (300 filas), latencia p50 y p99 en ORT con 1 hilo, y % de `<unk>`
    en la comprobación.
  - Tabla en `informe.md`, marcando las que cumplen top-1 ≥ 0,93 y ≤ 60 MB.
  - Coste ≤ 1 USD.
- **Prueba en seco** con `CHISPA_LOCAL=1` y pesos aleatorios, `bash -n`, `make test` y `make smoke` en verde.
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- `model/l2/exportar.py`, `model/l2/tests/**` y `model/bench/torre/**`.
- Rama: la que te da delega. Base: `integracion`. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Python en `~/venv`, modelos en `~/hf` y datos en `~/datos`. Sin GPU y sin red salvo la API de Claude.

## Tope
- ≤ 90 min de reloj · ≤ 5 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 10 líneas:
- rama y sha;
- variantes implementadas;
- la prueba en seco;
- qué sustituyo para lanzar.
