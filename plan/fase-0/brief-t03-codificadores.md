# T0.3 Medir e5-small, mmBERT-small y potion en CPU x86

Encargo: `plan/fase-0/encargo.md` (criterio de aceptación congelado; no lo cambies tú).

## Hipótesis
- e5-small int8 con el vocabulario podado (~50-60 k tokens de es, en y pt) da p99 < 15 ms a 64
  tokens con 4 hilos en x86, y mmBERT-small va 1,5-2× más lento. Se refuta midiendo.

## Terminado cuando
- `model/bench/codificadores.py` reproducible (semilla fija) y `model/bench/resultados-x86.md`
  con una fila por variante: modelo, precisión (fp32/int8), poda (sí/no), tokens (16/64/256),
  hilos (1/4), p50, p99, RSS pico, tamaño en disco, arranque en frío. ≥ 200 repeticiones tras 20 de
  calentamiento. Exporta a ONNX con optimum y cuantiza int8 dinámico con onnxruntime.
- La poda: guarda el vocabulario resultante y comprueba que los embeddings podados coinciden
  (coseno ≥ 0,999) con los originales en 200 frases en español.
- potion-multilingual-128M (model2vec) medido igual, como capa static.
- Anota la CPU (`lscpu`) y la carga del host; es una VM en un i3-3220 compartido: las cifras son una
  cota pesimista, el i7-8700T se mide aparte.
- Parada: si una variante falla 2 veces, se marca «no medida» con el error y sigues.

## Zona
- Solo `model/bench/`. **No tocar** nada fuera de esa carpeta.
- Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Python en `~/venv`, modelos en `~/hf` (sin red salvo la API de Claude).
- Línea base: `25d934f`.

## Tope
- ≤ 150 min de reloj · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤15 líneas: qué cambiaste, rama y sha, qué verificaste ejecutando (con
números), qué quedó sin verificar y qué recomiendas a continuación.
