# model/cascada — T2.7: la cascada L0 → L1 → L2 frente al listón

Mide lo que ve el producto (`server/decide/cascada.go`): cada capa responde si su confianza top-1 es ≥ τ y, si no, pasa a la siguiente.
Qué se mide, cómo y de dónde sale cada cifra: cabecera de `resultados/<fecha>/informe.md`.

- `capas.py` — predicciones `{id, probs, ms}` de L0 (reusa `model/lineas_base/pred`), L1-zs (= `server/decide/l1.go`), L1-proto
  (candidata) y lectura de las de L2.
- `cascada.py` — cascada, τ por validación cruzada a 2 pliegues (hash del `id`), puntos «calidad» y «rápida», oráculo.
- `informe.py` — `informe.md` y `resultados.json`.
- `verificar_l1.py` + `verificar_l1/` (Go) — L1-zs de Python frente a `runtime/l1` en 50 frases (mismo top-1: 50/50).
- `aws/arranque.sh`, `aws/empaquetar.sh` — la corrida real en una instancia CPU con las predicciones de L2 de S3.
- `fixtures.py` — 3 tareas inventadas para las pruebas y para `CHISPA_LOCAL=1 bash model/cascada/aws/arranque.sh`.
- `resultados/2026-10-28-seco/` — prueba en seco sin L2 (L0 → L1-zs y L0 → L1-proto sobre los test reales).

```
python -m unittest discover -s model/cascada -t .
python -m model.cascada.capas --datos /tmp/lb_datos --salida /tmp/cas_pred          # datos: model.datos.convertir
python -m model.cascada.informe --datos /tmp/lb_datos --pred /tmp/cas_pred [--l2b DIR --l2c DIR]
```
