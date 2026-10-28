# model/l1 — L1 propio: embedding estático destilado de e5-small (T3.1c, preparación offline)

Destila `intfloat/multilingual-e5-small` a un embedding estático (vocabulario podado a 55 000 piezas,
`model/bench/vocab-podado-e5-small.json`), lo exporta al formato `.chispa-l1` de `runtime/l1` (sin cambiarlo) y lo
compara con potion-multilingual-128M. Resultados en `resultados/<fecha>/informe.md`.

## Regenerar (todo fuera de git: los modelos pesan > 5 MB y viven en /tmp)
```
source ~/.profile && cd <raíz>
python runtime/l1/exportar.py ~/hf/hub/models--minishlab--potion-multilingual-128M/snapshots/* /tmp/potion.chispa-l1   # ~30 s
python -m model.l1.destilar --dims 256 128          # ~6 min la 1.ª vez (55 000 pasadas por e5), ~1 min con caché
python -m model.datos.convertir --salida /tmp/lb_datos --fuentes massive,hatecheck,clinc150,inyecciones
python -m model.l1.evaluar --propio 256=/tmp/l1propio/d256/propio-256.chispa-l1 128=/tmp/l1propio/d128/propio-128.chispa-l1 \
    --potion /tmp/potion.chispa-l1 --salida model/l1/resultados/<fecha>      # ~10 min
python -m model.l1.informe model/l1/resultados/<fecha>
```
- `destilar.py`: destilación mínima (el `distill` de model2vec no corre aquí: le falta `skeletoken`). Diferencias en su docstring.
- `cabeza.py`: prototipos + capa lineal, KL contra un maestro. `--maestro l0` (L0 fuera de pliegue, k = 5) o
  `--maestro <jsonl {id, probs}>` con una línea por fila del soporte (32 por clase del train, ids de `model.lineas_base.correr.soporte`)
  para enchufar las distribuciones de L2 con soporte. La cabeza se guarda en int8 (`cabeza-<tarea>.npz`).
- `evaluar.py` / `informe.py`: macro-F1 (métrica de `chispa eval`), tamaño, latencia (`runtime/l1/cmd/l1medir`) y coseno con e5.
  `evaluar.py --maestro <jsonl>` repite la columna «cabeza» con otro maestro (la misma interfaz).
- `ablacion.py`: barrido de la ponderación SIF.
- `go/`: módulo Go aparte (`replace` a `runtime/l1`, solo lectura) con `cmd/embeber` (embeddings para Python) y el test dorado.

## Determinismo
`dorado.py` es una referencia independiente en Python (tokenizador recortado de `tokenizers`, aritmética entera, mismo
orden de suma) y fija `go/testdata/dorado-<dim>.json` (hash del cuerpo y de los 200 primeros embeddings del sondeo).
`cd model/l1/go && go test ./...` exige ese hash a `runtime/l1` (`CHISPA_L1_PROPIO=<ruta>` para otro modelo, por defecto
`/tmp/l1propio/d256/propio-256.chispa-l1`; si falta, el test se salta y lo dice). `tests/test_l1.py` compara además
300 frases bit a bit entre Go y la referencia. Solo se ha ejecutado en amd64; la aritmética no depende de la plataforma
(enteros + IEEE-754), pero arm64 no se ha probado aquí.
