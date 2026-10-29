# Benchmarks del servidor

Nodo `nodo-b`: Intel Core i7-1255U (12 hilos), Linux 6.18 WSL2, Go 1.27, `-benchmem -benchtime 2s`, sin otra carga.
Reproducir: `cd server && GOMAXPROCS=N go test -run '^$' -bench '<nombre>' -benchmem -benchtime 2s ./decide/`

| Benchmark | Qué mide | GOMAXPROCS=1 | GOMAXPROCS=4 | B/op | allocs/op |
|---|---|---|---|---|---|
| `BenchmarkL0` | L0 (L0 clásico, `RunParallel`) | 1464 ns | 608 ns | 713 | 11 |
| `BenchmarkL0TF150Clases` | L0 TF-IDF/logística, 150 clases | 35.2 µs | 35.9 µs | 7144 | 18 |
| `BenchmarkL1Lote16` | L1 (Model2Vec), 16 decisiones en serie | 70.4 µs | 71.3 µs | 49536 | 496 |
| `BenchmarkL2cCabeza` | cabeza conjunta L2c | 1.13 ms | 1.15 ms | 32871 | 16 |
| `BenchmarkCascadaHTTP` | cascada completa + handler `/v1/decide` (`RunParallel`) | 9.18 µs | 6.06 µs | 10211 | 63 |

Notas:
- `L0` y `CascadaHTTP` usan `RunParallel`, por eso escalan con GOMAXPROCS; los demás son de un solo hilo.
- `BenchmarkL1Real` se salta en este nodo (no hay modelo real); `L1Lote16` usa el modelo tiny de los tests.
- L2 (e5 ONNX) no se mide aquí: no hay ONNX Runtime con modelo en este nodo.
- `CascadaHTTP` usa `httptest.ResponseRecorder`, sin red ni TLS.

## Contadores de /metrics de lo nuevo (torres, esquema nuevo, timeouts)
Mediana de 3 repeticiones alternadas (`-benchtime 2s`), HEAD `55373d1` contra el árbol con los contadores nuevos. B/op y allocs/op idénticos.

| Benchmark | GOMAXPROCS | antes | después | Δ |
|---|---|---|---|---|
| `BenchmarkL0` | 1 | 1497 ns | 1517 ns | +1.3 % |
| `BenchmarkL0` | 4 | 648 ns | 649 ns | +0.2 % |
| `BenchmarkCascadaHTTP` | 1 | 10056 ns | 9825 ns | −2.3 % |
| `BenchmarkCascadaHTTP` | 4 | 6308 ns | 6358 ns | +0.8 % |

Dentro del ruido (<5 %): en el camino caliente solo hay un `atomic.Add` por pregunta de esquema nuevo y una comprobación de `ctx.Err()` ya existente; el resto vive en el camino de torres al vuelo. No se midió L2 con ONNX (no hay modelo en este nodo).
