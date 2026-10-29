# Carga de chispa-server — MPC-NVKLGOK5UGQ — 20261028-230235

## Entorno
- CPU: 12th Gen Intel(R) Core(TM) i7-1255U · núcleos lógicos: 12 · GOMAXPROCS: (sin fijar = 12)
- loadavg antes (1/5/15 min): 2.93 1.09 0.99 · máximo de loadavg(1 min) durante: 4.00
- Go: go version go1.27.1 linux/amd64 · ORT: no (stub)
- Parámetros: modos=[l1] concurrencias=[1 4 16] duración=10s por punto · tandas=1 · esquemas=carga/esquemas-carga.json lote=ocho · textos=2400 líneas (carga/textos-es-co.txt)
- Modelo: ninguno (solo .chispa de testdata en L0) · tok: ninguno · commit: a5f578e
- **L2 en stub** (sin ORT/modelo/tok): el modo l2 mide la cascada con L2 sin opinión, que acaba en «escalar»; no es la cifra de L2 real.

## Resultados (media de tandas; p50 = media, p99 = peor tanda; preg/s = preguntas decididas por segundo, pet/s = peticiones por segundo)

Las tandas que fallaron enteras (errores=-1 en el CSV) no entran en las medias; si hay, la fila dice FALLÓ.

Objetivos: l1 ≥ 5000 dec/s con p99 < 20 ms · l2 ≥ 300 dec/s.

| modo | c | preg/s | pet/s | p50 ms | p99 ms | errores | tandas | objetivo |
|---|---|---|---|---|---|---|---|---|
| l1 | 1 | 14815 | 1852 | 0.510 | 0.945 | 0 | 1 | cumple |
| l1 | 4 | 36953 | 4619 | 0.816 | 1.756 | 0 | 1 | cumple |
| l1 | 16 | 57474 | 7184 | 1.889 | 5.949 | 0 | 1 | cumple |

Capas que decidieron (última tanda de cada punto) y datos por tanda: ver `resultados-MPC-NVKLGOK5UGQ-20261028-230235.csv`.

Log del servidor (l1):
```
```
