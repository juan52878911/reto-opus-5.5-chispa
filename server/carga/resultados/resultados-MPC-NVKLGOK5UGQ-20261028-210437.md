# Carga de chispa-server — MPC-NVKLGOK5UGQ — 20261028-210437

## Entorno
- CPU: 12th Gen Intel(R) Core(TM) i7-1255U · núcleos lógicos: 12 · GOMAXPROCS: (sin fijar = 12)
- loadavg antes (1/5/15 min): 3.27 1.75 0.92 · máximo de loadavg(1 min) durante: 7.04
- Go: go version go1.27.1 linux/amd64 · ORT: no (stub)
- Parámetros: modos=[l1 l2] concurrencias=[1 4 16 64] duración=10s por punto · tandas=1 · textos=260 líneas (/home/administrador/orquestador/trabajos/20261028-210308-57666/wt/server/carga/textos.txt)
- Modelo: ninguno (solo .chispa de testdata en L0) · tok: ninguno · commit: 361dd04
- **L2 en stub** (sin ORT/modelo/tok): el modo l2 mide la cascada con L2 sin opinión, que acaba en «escalar»; no es la cifra de L2 real.

## Resultados (media de tandas; p50 = media, p99 = peor tanda)

Objetivos: l1 ≥ 5000 dec/s con p99 < 20 ms · l2 ≥ 300 dec/s.

| modo | c | dec/s | p50 ms | p99 ms | errores | tandas | objetivo |
|---|---|---|---|---|---|---|---|
| l1 | 1 | 1020 | 0.957 | 1.642 | 0 | 1 | NO cumple |
| l1 | 4 | 4170 | 0.938 | 1.939 | 0 | 1 | NO cumple |
| l1 | 16 | 13183 | 1.101 | 3.099 | 0 | 1 | cumple |
| l1 | 64 | 24968 | 2.157 | 7.504 | 0 | 1 | cumple |
| l2 | 1 | 2738 | 0.344 | 0.648 | 0 | 1 | cumple |
| l2 | 4 | 7006 | 0.558 | 0.963 | 0 | 1 | cumple |
| l2 | 16 | 13665 | 1.065 | 2.909 | 0 | 1 | cumple |
| l2 | 64 | 17209 | 2.845 | 12.425 | 0 | 1 | cumple |

Capas que decidieron (última tanda de cada punto) y datos por tanda: ver `resultados-MPC-NVKLGOK5UGQ-20261028-210437.csv`.

Log del servidor (l1):
```
```

Log del servidor (l2):
```
```
