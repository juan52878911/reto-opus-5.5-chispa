# model/l2: L2 de Chispa (T2.1)

Ranuras de lectura, torres de opción y cabezas `choice` / `noul` / `score` (CORAL) sobre `intfloat/multilingual-e5-small`
congelado. Diseño y criterio: `plan/fase-2/encargo.md`. Esquema de filas: `model/esquema.md`.

| Fichero | Qué hace |
|---|---|
| `modelo.py` | `Codificador` (e5 congelado, `query: ` a 128 tokens, caché de vectores de pasaje por hash), `Ranuras` (K=16, atención cruzada de 4 cabezas), `Torre` (MLP 384→512→256), `maxsim`, `Coral`, `ModeloL2` (pérdida CE + KL + InfoNCE + Brier) |
| `datos.py` | JSONL / JSONL.gz, submuestreo del metaentrenamiento, `aplicar_blandas`, `Muestreador` (p ∝ n^0,5, función pura de `(semilla, paso)`) |
| `entrenar.py` | AdamW (3e-4 / 1e-4 en la torre), warmup 5 % + coseno, checkpoint cada 10 min, `--s3`, reanuda, `--minutos` |
| `evaluar.py` | predice a `{id, probs, ms}`, llama a `chispa_eval` y escribe `delta.md` frente a `lineas_base/resultados.json` |
| `aws/` | `arranque.sh` (user-data de la g5.xlarge) y `empaquetar.sh` |

## Decisiones donde el diseño admitía varias lecturas
- Cabezas «una por tipo de pregunta»: `T_choice` única, `(a, b)` única para `noul`, y una `Coral` (w, θ) por número de niveles
  (`score3`, `score5`…; θ tiene K−1 umbrales).
- Torre de `noul` y `score`: `passage: {pregunta} · {última opción} · {descripción}` (`true`, o el nivel máximo en `score`).
- InfoNCE: el positivo es la opción correcta; el denominador abarca todas las opciones distintas del lote (las de la propia
  fila y las de las demás).
- KL: solo en las filas con `blanda`; se renormaliza sobre `opciones` (claves ausentes = 0) y se promedia sobre esas filas.
- Brier: sobre la distribución completa y la etiqueta dura. Las cuatro pérdidas se promedian por fila aplicable.
- `ms` de `evaluar.py` es el tiempo del lote repartido entre sus filas, no la latencia de una consulta suelta.

## Uso
    python -m model.l2.entrenar --salida DIR --datos CONVERTIDOS --herramientas --meta META --blandas BLANDAS [--s3 PREFIJO]
    python -m model.l2.evaluar --ckpt DIR/mejor.pt --salida OUT --datos CONVERTIDOS [--liston DIR]
    python -m unittest discover -s model -t .
AWS: `bash model/l2/aws/empaquetar.sh > codigo.tgz`; prueba en seco: `empaquetar.sh --fixtures` y `CHISPA_LOCAL=1 bash model/l2/aws/arranque.sh`.
