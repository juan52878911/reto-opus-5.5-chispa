# M5 diagnóstico de score (max_tok 256)

18 casos score de JevBench, 7 esquemas.

## (a) ranking y (b) cabeza

| | exactitud |
|---|---|
| clase mayoritaria | 0.556 |
| umbrales del checkpoint | 0.278 |
| umbrales reajustados (esquema fuera) | 0.278 |
| oráculo de umbrales por esquema | 0.667 |

Spearman s↔nivel: media por esquema -0.153; global por K: K=4 -0.279 (oráculo con un solo juego 0.412, n=17), K=5 nan (oráculo con un solo juego 1.000, n=1)

| esquema | K | n | ckpt | reajuste | oráculo | mayoría | ρ | MAE ckpt | MAE reajuste |
|---|---|---|---|---|---|---|---|---|---|
| jev:4511e47344 | 5 | 1 | 0.000 | 0.000 (sin dev) | 1.000 | 1.000 | nan | 1.00 | 1.00 |
| jev:4bfd05e7fa | 4 | 1 | 0.000 | 0.000 (sin dev) | 1.000 | 1.000 | nan | 2.00 | 2.00 |
| jev:63d23e6a93 | 4 | 1 | 0.000 | 0.000 (sin dev) | 1.000 | 1.000 | nan | 1.00 | 1.00 |
| jev:88c2b9c394 | 4 | 1 | 1.000 | 1.000 (sin dev) | 1.000 | 1.000 | nan | 0.00 | 0.00 |
| jev:8fb226adc2 | 4 | 12 | 0.333 | 0.333 (sin dev) | 0.500 | 0.333 | -0.15 | 1.08 | 1.08 |
| jev:c015c7d85b | 4 | 1 | 0.000 | 0.000 (sin dev) | 1.000 | 1.000 | nan | 2.00 | 2.00 |
| jev:cdbcfe3d27 | 4 | 1 | 0.000 | 0.000 (sin dev) | 1.000 | 1.000 | nan | 3.00 | 3.00 |

## (c) datos de entrenamiento

```
{
 "origen": "ficheros del meta",
 "por_k": {
  "K=10": {
   "tareas": 7,
   "bruto": 40444,
   "sin_fuera": 34755,
   "con_tope": 12000
  },
  "K=3": {
   "tareas": 119,
   "bruto": 146386,
   "sin_fuera": 136403,
   "con_tope": 75823
  },
  "K=4": {
   "tareas": 61,
   "bruto": 60980,
   "sin_fuera": 52614,
   "con_tope": 36351
  },
  "K=5": {
   "tareas": 80,
   "bruto": 75172,
   "sin_fuera": 66280,
   "con_tope": 47292
  },
  "K=6": {
   "tareas": 1,
   "bruto": 4760,
   "sin_fuera": 4760,
   "con_tope": 2000
  },
  "K=7": {
   "tareas": 2,
   "bruto": 2268,
   "sin_fuera": 2268,
   "con_tope": 2268
  }
 },
 "tareas_score": 270,
 "tareas_score_dentro": 242,
 "filas_score_con_tope": 175734,
 "filas_tsjev_con_tope": 270760,
 "peso_score_en_muestreo_tsjev": 0.11528353546706703,
 "mayores": [
  {
   "tarea": "WANLI",
   "k": 5,
   "n": 11509
  },
  {
   "tarea": "FOL-nli",
   "k": 3,
   "n": 11444
  },
  {
   "tarea": "doc-nli",
   "k": 3,
   "n": 11240
  },
  {
   "tarea": "procedural-typed-decisions/arithmetic",
   "k": 10,
   "n": 6022
  },
  {
   "tarea": "procedural-typed-decisions/record_eligibility",
   "k": 10,
   "n": 5988
  },
  {
   "tarea": "corr2cause",
   "k": 3,
   "n": 5943
  },
  {
   "tarea": "spartqa-yn",
   "k": 3,
   "n": 5882
  },
  {
   "tarea": "procedural-typed-decisions/table_lookup",
   "k": 10,
   "n": 5874
  }
 ]
}
```

## Causas y arreglo más barato

- ranking: s apenas ordena los niveles (ρ medio -0.15; el oráculo de umbrales llega a 0.667 frente a 0.556 de la clase mayoritaria)
- calibración: los umbrales del checkpoint dejan 0.389 sobre la mesa frente al oráculo; reajustar en un dev (esquema fuera) recupera el 0 % de esa brecha (0.278 → 0.278)

**Arreglo:** continuar el entrenamiento solo con episodios score (muestreo por tipo), reanudando de mejor.pt; las cabezas y las ranuras aprenden el orden, la torre se queda como está. GPU (g5.xlarge), ≈ 1.50 h, ≈ 1.60 USD.
