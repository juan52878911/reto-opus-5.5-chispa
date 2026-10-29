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
- ESQUEMAS: en `choice` una entrada por opción (v2: `HashEsquema(pregunta, [opción, descripción])`; v1 sin descripción); en `noul`/`score` una por pregunta con
  `[o1, d1, o2, d2, …]` (vector de consulta). El exportador escribe v2 (`META.version` 2); ver `contrato-torre.md`. Un vector int8 con su escala (`q·escala ≈ h`).
- El ONNX acepta los ids del tokenizador original de e5 (con la poda, la tabla id→id podado va dentro del grafo). La atención de las
  ranuras se reescribe en `RanurasExportable` (el trazado de `nn.MultiheadAttention` fija el lote); `exportar` comprueba que coincide.

## T2.2: ajuste del codificador, renombrado y segundo maestro
Con los valores por defecto el comportamiento es el de T2.1.
- `entrenar --descongelar N`: las últimas N capas de e5 se entrenan (lr `--lr-enc` 2e-5, sin weight decay; recorte de gradiente 1,0 sobre
  todos los parámetros). **Coste:** la torre de opción comparte el codificador, así que sus vectores cambian en cada paso: se recalculan
  con gradiente para todos los textos únicos del lote (en CLINC, 150 opciones por fila → cientos de textos por paso) y la caché de
  vectores/mensajes se invalida tras cada `opt.step()`. En T2.1 la caché dejaba casi todo el trabajo en el mensaje. Las capas
  descongeladas van en `ck["enc"]` (`ultimo.pt` y `mejor.pt`); `evaluar.py` las carga solo.
- `--renombrar P`: con probabilidad P por fila `choice` (decidido por semilla, paso e id), las opciones pasan a A, B, …, Z, AA… en el
  texto de la torre; descripciones, etiqueta y blanda se remapean. `noul` y `score` no se tocan. `datos.renombrar_fila` es idempotente.
- `--maestro-extra DIR… --peso-extra W`: blandas `{id, blanda}` (JSONL/.gz) de un segundo maestro; `(1−W)·existente + W·extra`, cada una
  normalizada; si la fila no tenía, queda la extra.
- `--inicial CKPT`: pesos de un checkpoint de T2.1 (sin optimizador); `ultimo.pt` tiene prioridad al reanudar.
- `evaluar --renombrar`: evalúa también con las opciones renombradas y escribe `caida.md` (macro-F1 original − renombrado por tarea).
- `aws/arranque.sh`: `__L2_ARGS__` y `__CKPT_INICIAL__`; las descargas de S3 son por fichero (sin `--recursive` ni `sync`) a partir de
  `model/meta/resultados/conversion-20261027.json`; `CHISPA_EXTRA_S3/extra.tgz` opcional para el segundo maestro.

## T2.1b: prototipos de soporte y entrenamiento por episodios
- `modelo.prototipos`: P_c ∈ R^{K×d} por clase = media normalizada, ranura a ranura, de las ranuras de k ejemplos de soporte.
  Puntuación `sim_opción(c) + β·simproto(c)` con `simproto = mean_k max_k' (s_k · P_c,k')`; β por tipo (`choice`, `noul`, `score`),
  inicial 1. En `noul` y `score` el término es la combinación de `simproto` ponderada de −1 a +1 por la posición de la clase
  (con 2 clases, `sp(true) − sp(false)`) y se suma a la `sim` de la cabeza. Sin `protos` (o con β = 0) sale exactamente la ronda 1;
  los checkpoints sin β cargan (β = 1).
- `datos.Episodios` (`--episodios`): función pura de (semilla, paso). 25 % de los pasos sin soporte (`--frac-zeroshot`), de meta
  mientras `--frac-meta` lo permita; el resto, un episodio de una tarea local: k ejemplos por clase (k ∈ [`--k-min`, `--k-max`]) de
  soporte y consultas disjuntas, clases uniformes. En las `choice` con más de `--vias` (16) clases se eligen `--vias` y las opciones de
  las consultas se reducen a ellas (si no, una tarea de 151 clases costaría ~4800 mensajes por paso). Las épocas se cuentan sobre las
  filas locales.
- `evaluar --soporte K`: soporte = `datos.soporte_t17a` (mismo algoritmo y semilla 0 que `lineas_base.correr.soporte`: los mismos
  ejemplos que kNN-32), prototipos en caché por (tarea, hash del soporte) y calculados una vez; `delta.md` lleva las dos columnas. La
  evaluación renombrada sigue sin soporte. Sin train (listón) no hay soporte: esas filas salen igual en las dos columnas.
- `aws/arranque.sh`: `L2_ARGS="--episodios --k-min 4 --k-max 32 --frac-meta 0.5 --frac-zeroshot 0.25"`; con `--episodios` evalúa con
  `--soporte <k-max>`. Las descargas de S3 ya eran por fichero.
- Dev durante el entrenamiento: sin y con soporte (k = `--k-max`, soporte de los train locales); `mejor.pt` por el segundo.
