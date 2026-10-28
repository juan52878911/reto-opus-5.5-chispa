# model/l2: L2 de Chispa (T2.1)

Ranuras de lectura, torres de opción y cabezas `choice` / `noul` / `score` (CORAL) sobre `intfloat/multilingual-e5-small`
congelado. Diseño y criterio: `plan/fase-2/encargo.md`. Esquema de filas: `model/esquema.md`.

| Fichero | Qué hace |
|---|---|
| `modelo.py` | `Codificador` (e5 congelado, `query: ` a 128 tokens, caché de vectores de pasaje por hash), `Ranuras` (K=16, atención cruzada de 4 cabezas), `Torre` (MLP 384→512→256), `maxsim`, `Coral`, `ModeloL2` (pérdida CE + KL + InfoNCE + Brier) |
| `datos.py` | JSONL / JSONL.gz, submuestreo del metaentrenamiento, `aplicar_blandas`, `Muestreador` (p ∝ n^0,5, función pura de `(semilla, paso)`) |
| `entrenar.py` | AdamW (3e-4 / 1e-4 en la torre), warmup 5 % + coseno, checkpoint cada 10 min, `--s3`, reanuda, `--minutos` |
| `evaluar.py` | predice a `{id, probs, ms}`, llama a `chispa_eval` y escribe `delta.md` frente a `lineas_base/resultados.json` |
| `calibrar.py` | T2.4: T (choice), a/b (noul, Platt), T de CORAL (score) y θ por tipo y tarea sobre las similitudes crudas de dev; τ de escalate a precisión 0,95; ECE antes/después y AUROC |
| `exportar.py` | T2.6: ONNX (codificador + ranuras → S) opset 17, int8 dinámico, vocabulario podado, torres int8 de ESQUEMAS, paridad y latencia; empaqueta con `empaquetar_go/` |
| `empaquetar_go/` | `go run` que importa `format/chispa3` (`replace`) y escribe el `.chispa` v3 (META, L2, ESQUEMAS, CALIB); `go test` con ida y vuelta |
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

## Calibración y exportación (T2.4, T2.6)
    python -m model.l2.calibrar --ckpt DIR --dev dev.jsonl… --salida calib.json
    python -m model.l2.exportar --ckpt DIR --calib calib.json --esquemas filas.jsonl… --salida l2.chispa [--paridad dev.jsonl] [--sin-poda]
    cd model/l2/empaquetar_go && GOFLAGS=-mod=mod GOPROXY=off go test ./...
- `calib.json`: `tareas` (ajuste, ECE, τ, cobertura y AUROC por tarea), `tipos` (ajuste agrupado por cabeza), `tau_escalate` (todas las
  tareas juntas) y `chispa` (lo que va a CALIB). Las similitudes s son las de `maxsim`; con ellas `choice`: softmax(s/T); `noul`:
  σ(a·s+b); `scoreK`: P(y>j)=σ(a·s−b_j). La sección CALIB solo admite {T,a,b,θ} por clave: `scoreK` guarda a=w/T y b=b_1, y los
  incrementos b_j−b_{j-1} van en claves `scoreK#j` (campo `a`). θ es el umbral de p(true) de `noul` que maximiza el F1 macro (0,5 en el resto).
  El formato solo tiene un τ; el de cada tarea está en `calib.json`.
- ESQUEMAS: en `choice` una entrada por opción (`HashEsquema(pregunta, [opción])`); en `noul`/`score` una por pregunta con la lista
  completa de opciones (vector de consulta). Un vector int8 con su escala (`q·escala ≈ h`).
- El ONNX acepta los ids del tokenizador original de e5 (con la poda, la tabla id→id podado va dentro del grafo). La atención de las
  ranuras se reescribe en `RanurasExportable` (el trazado de `nn.MultiheadAttention` fija el lote); `exportar` comprueba que coincide.
