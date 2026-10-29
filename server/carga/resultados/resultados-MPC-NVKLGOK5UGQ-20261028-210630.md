# Carga de chispa-server — MPC-NVKLGOK5UGQ — 20261028-210630

## Entorno
- CPU: 12th Gen Intel(R) Core(TM) i7-1255U · núcleos lógicos: 12 · GOMAXPROCS: (sin fijar = 12)
- loadavg antes (1/5/15 min): 5.32 3.21 1.57 · máximo de loadavg(1 min) durante: 12.07
- Go: go version go1.27.1 linux/amd64 · ORT: no (stub)
- Parámetros: modos=[l1 l2] concurrencias=[1 4 16 64] duración=10s por punto · tandas=1 · textos=260 líneas (/home/administrador/orquestador/trabajos/20261028-210308-57666/wt/server/carga/textos.txt)
- Modelo: ninguno (solo .chispa de testdata en L0) · tok: ninguno · commit: 7c34cb1
- **L2 en stub** (sin ORT/modelo/tok): el modo l2 mide la cascada con L2 sin opinión, que acaba en «escalar»; no es la cifra de L2 real.

## Resultados (media de tandas; p50 = media, p99 = peor tanda)

Objetivos: l1 ≥ 5000 dec/s con p99 < 20 ms · l2 ≥ 300 dec/s.

| modo | c | dec/s | p50 ms | p99 ms | errores | tandas | objetivo |
|---|---|---|---|---|---|---|---|
| l1 | 1 | 1531 | 0.637 | 1.099 | 0 | 1 | NO cumple |
| l1 | 4 | 4709 | 0.824 | 1.484 | 0 | 1 | NO cumple |
| l1 | 16 | 10432 | 1.399 | 3.854 | 0 | 1 | cumple |
| l1 | 64 | 19797 | 2.668 | 9.869 | 0 | 1 | cumple |
| l2 | 1 | 2534 | 0.338 | 0.912 | 0 | 1 | n/a (L2 stub) |
| l2 | 4 | 6444 | 0.597 | 1.166 | 0 | 1 | n/a (L2 stub) |
| l2 | 16 | 13208 | 1.097 | 3.062 | 0 | 1 | n/a (L2 stub) |
| l2 | 64 | 16890 | 2.884 | 12.538 | 0 | 1 | n/a (L2 stub) |

Capas que decidieron (última tanda de cada punto) y datos por tanda: ver `resultados-MPC-NVKLGOK5UGQ-20261028-210630.csv`.

Log del servidor (l1):
```
```

Log del servidor (l2):
```
```
