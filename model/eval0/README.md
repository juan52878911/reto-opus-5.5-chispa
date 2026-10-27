# T0.4: modelos abiertos frente a e5-small + kNN

Un script por modelo (`e5_knn.py --k 8|32`, `gliclass.py`, `julia1.py`, `thx01.py`, `laya.py`); `common.py` es el arnés
(métricas, tiempos, RSS), `_decision.py` el runtime compartido de THX-01 y Laya, `correr.sh` lanza las 4 tareas
(un proceso por modelo×tarea, uno a la vez) y `agregar.py` genera `resultados_tablas.md` desde `out/*.json`.
Resultados e interpretación: `resultados.md`.

```sh
source ~/.profile
N1=120 N4=30 ./correr.sh julia1.py      # 1 hilo con 120 ejemplos fijos + 4 hilos con 30
python agregar.py
```
