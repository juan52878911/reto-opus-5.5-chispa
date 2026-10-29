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

## Antes y después de las revisiones

Pregunta: ¿han costado rendimiento los arreglos de seguridad? Tres shas en worktrees de /tmp: `3a99102` (inicio), `57e0385` (antes de las revisiones de seguridad) y `24fee0c` (rama `delega/chispa-pf`). Nodo `nodo-b` (12 hilos, compartido, WSL2), 2026-10-29. Hipótesis (coste < 10 % en decisiones/s y p99 con L0/L1): **refutada** para el camino HTTP; L0, L0TF y L1Lote16 sí quedan en < 5 %.

### Microbenchmarks (`go test ./decide -run '^$' -bench . -benchtime 2s -cpu 1,4 -benchmem`)

Solo los cinco benchmarks comunes a los tres shas. ns/op; entre paréntesis, variación frente a `3a99102` y frente a `57e0385`.

| Benchmark | cpu | 3a99102 | 57e0385 | 24fee0c | 24fee0c vs 3a99102 | 24fee0c vs 57e0385 |
|---|---|---|---|---|---|---|
| `L0` | 1 | 1451 | 1486 | 1471 | +1,4 % | −1,0 % |
| `L0` | 4 | 592 | 637 | 612 | +3,4 % | −3,9 % |
| `L0TF150Clases` | 1 | 36455 | 36905 | 37702 | +3,4 % | +2,2 % |
| `L0TF150Clases` | 4 | 36374 | 36137 | 36945 | +1,6 % | +2,2 % |
| `L1Lote16` | 1 | 73589 | 74277 | 76997 | +4,6 % | +3,7 % |
| `L1Lote16` | 4 | 71711 | 71758 | 73413 | +2,4 % | +2,3 % |
| `CascadaHTTP` | 1 | 9359 | 11017 | 13126 | **+40,2 %** | **+19,1 %** |
| `CascadaHTTP` | 4 | 5543 | 6123 | 7604 | **+37,2 %** | **+24,2 %** |
| `L2cCabeza` | 1 | 1141629 | 1743052 | 1752981 | **+53,5 %** | +0,6 % |
| `L2cCabeza` | 4 | 1155190 | 1872835 | 1806788 | **+56,4 %** | −3,5 % |

Memoria: `CascadaHTTP` 63 → 65 → 126 allocs/op (10,2 → 10,3 → 12,4 KB/op); `L2cCabeza` 33 KB → 1,69 MB/op desde `57e0385`.

loadavg (1 min) al empezar → al acabar los benchmarks de cada sha: 3a99102 0,32 → 1,06; 57e0385 1,06 → 1,52; 24fee0c 1,52 → 1,54. Carga baja y estable; sin repetir.

### Carga (`server/carga/correr.sh -m l1 -c "1 4 16 64" -d 10s -n 1`, `server/testdata`)

Dos juegos, porque `3a99102` no trae `correr.sh`, ni `-textos`, `-csv` ni `-E/-L` en `cmd/carga`:

- **Juego A (los tres shas, una pregunta por petición):** se construyó el servidor de cada sha y se usó el **mismo** binario `carga` de `24fee0c` y el `correr.sh` de `24fee0c` (copiado a /tmp, sin cambiar el repo), con `-t textos.txt`. Dos corridas por sha, intercaladas; se promedian. Decisiones/s (= peticiones/s):

| c | 3a99102 | 57e0385 | 24fee0c | 24fee0c vs 3a99102 | 24fee0c vs 57e0385 |
|---|---|---|---|---|---|
| 1 | 2616 | 2442 | 2402 | −8,2 % | −1,6 % |
| 4 | 6985 | 6450 | 5812 | **−16,8 %** | **−9,9 %** |
| 16 | 13023 | 12228 | 10579 | **−18,8 %** | **−13,5 %** |
| 64 | 23574 | 21594 | 18760 | **−20,4 %** | **−13,1 %** |

p99 (ms), mismo orden: c=1 0,64 / 0,70 / 0,78 (+22 %); c=4 1,05 / 1,12 / 1,21 (+15 %); c=16 2,99 / 3,24 / 4,18 (+40 %); c=64 8,05 / 8,91 / 10,47 (+30 %). p50 a c=64: 2,26 / 2,46 / 2,82 ms. 0 errores en todas.

- **Juego B (`57e0385` y `24fee0c`, con `-E carga/esquemas-carga.json -L ocho`, 8 preguntas por petición):** tres corridas por sha (una primera y dos intercaladas), promedio. Decisiones/s:

| c | 57e0385 | 24fee0c | variación | p99 ms 57e0385 → 24fee0c |
|---|---|---|---|---|
| 1 | 14517 | 13354 | −8,0 % | 0,97 → 1,19 (+22 %) |
| 4 | 38336 | 31657 | **−17,4 %** | 1,59 → 1,95 (+23 %) |
| 16 | 61369 | 54856 | **−10,6 %** | 5,23 → 5,82 (+11 %) |
| 64 | 83799 | 71075 | **−15,2 %** | 20,5 → 26,2 (+28 %) |

Los dos juegos no son comparables entre sí en decisiones/s (1 contra 8 preguntas por petición). Los 8× de B sobre A no son una mejora.

loadavg: en la carga el nodo no estaba quieto. Valores de 1 min al empezar cada corrida: de 1,5 (primera tanda) a 5,9–9,9 (repeticiones), y eso **incluye mi propio generador** (c=64) de la corrida anterior: no puedo separar la parte ajena. Las diferencias entre shas salen en el mismo sentido en todas las repeticiones, con shas intercalados, y la dispersión entre repeticiones de un mismo sha es de hasta ~15 % a c=4 (57e0385 B: 41339, 40978, 32690), así que lo fiable es el orden y el orden de magnitud, no el decimal.

### Causas probables

- **Camino HTTP (+19–24 % ns y −10/−17 % decisiones/s desde `57e0385`): `a481348`** («LB HTTP: cuerpo con plazo antes de adquirir el modelo, escaneo acotado y JSON estricto, nonce por clave, /metrics protegible, cubo por pregunta y tope de peticiones en curso»). Comparado su padre `9e1a00d` con él: `CascadaHTTP` 9866 → 13242 ns/op (cpu 1), 5805 → 9466 (cpu 4), y allocs 65 → 126 por petición (+2 KB). `L1Lote16` no cambia en ese par (78084 → 76020 ns), luego el coste está en el manejador (escaneo previo + JSON estricto + plazo de lectura + semáforo), no en L0/L1. El tramo `3a99102..57e0385` ya había añadido ~+10 % (9359 → 11017 ns, +2 allocs).
- **`L2cCabeza` (+53 %, 33 KB → 1,69 MB/op): `b8a5df1`** («chispa3: protos empaquetados de CONJ dentro de cada entrada, sin caché global»), hallado con `git bisect` entre `3a99102` y `55f79a9`. No es una revisión de seguridad. El benchmark mide la cabeza sin ONNX; probablemente el desempaquetado de protos por llamada (150 × 16 × 256 × 4 B = 1,5 MB) ya no está en una caché global. No se midió con L2/ONNX real.
  - **Aclaración (medida):** no es una regresión del camino real. El benchmark armaba la `EntradaConj` a mano (sin celda de caché) y recalculaba los protos en cada llamada. `BenchmarkL2cCabeza` ahora tiene dos subbenchmarks (mediana de 3, `-benchtime 2s`): `decodificada` (CONJ de `CodificarConj`→`DecodificarConj`→`Buscar`, el camino real) 1,15 ms, 32,9 KB/op, 16 allocs/op, igual que antes de `b8a5df1`; `armada` (a mano) 1,94 ms, 1,69 MB/op, 18 allocs/op. Fuera de los tests, solo `DecodificarConj` construye entradas, y siempre con celda. La cifra de referencia es `decodificada`; las filas `L2cCabeza` de la tabla anterior eran la variante `armada`.

### Sin verificar

- No se midió L2 con ONNX ni modelo real (no hay en el nodo); no se pidió.
- Sin `-race` ni `-tags ort`.
- Carga con 1 tanda y 10 s, nodo compartido; el efecto de c=1 (−2 % a −8 %) está dentro del ruido.
- Entre `57e0385` y `24fee0c` solo se bisectó `CascadaHTTP` hasta `a481348`; el resto del tramo (p. ej. +2 allocs hasta `57e0385`) no se desglosó.
- No se cambió código. El `correr.sh` y el `carga` usados para `3a99102` son los de `24fee0c`.

## Recuperar el camino HTTP (escáner sin asignaciones)

Hipótesis: el coste era el doble recorrido del JSON (`Token()` + decodificación) y sus asignaciones. **Confirmada.** Perfil de `CascadaHTTP` (`-cpu 1`, `alloc_objects`) antes: `json.(*Decoder).Token` 31 % de los objetos (6,7 M de 21 M), `esquemaPeticion` 8 % (el árbol de esquema se rehacía en cada petición), `jsontext.Token.String` 7 %; en CPU `mallocgc` 24 % y el lector `jsonwire` repartido en decenas de nodos. Después: `Token()` y `esquemaPeticion` desaparecen del perfil; lo que queda es la decodificación (`json/v2`), `Cascada.Decidir`, `ClaveEsquema`, `json.Marshal` y `httptest.NewRecorder`.

Cambio (`server/decide/http.go`, solo `escaneaPeticion`): un escáner recursivo sobre los bytes ya leídos, sin asignar (máscara de bits por objeto para claves repetidas, `switch` sobre el nombre exacto, sin mapas ni `Token()`). Solo asigna si una clave o el `id` de pregunta traen escapes (`\u…`), para compararlos ya desescapados como antes. Ante un fallo de sintaxis devuelve nil y el 400 `JSON no válido` lo da la decodificación posterior (mismo código; el texto del mensaje de esos casos viene de `json` y no del escáner). Se mantienen todas las garantías: plazo de cuerpo, topes de tamaño/profundidad/preguntas/opciones, JSON estricto, nonce, cubo por pregunta, tope en curso; `r7_b_test.go` y de contrato sin tocar y en verde.

| `CascadaHTTP` (`-benchtime 2s -count 3`) | antes (`f796b45`) | después |
|---|---|---|
| cpu 1 ns/op | 12744 | 10216–10295 |
| cpu 4 ns/op | ≈ 7600 | 6069–6295 |
| allocs/op, B/op | 126, 12430 | 67, 10387 |

Objetivo (≤ 10.500 ns/op y ≤ 80 allocs): cumplido. Verde: `go vet ./...`, `go test -race ./...`, `-race -tags ort ./decide` (con `CHISPA_ORT_LIB` del venv) y `bash server/e2e/correr.sh`.

### Carga local `l1` c = 4/16/64: **no concluyente**
Se midió `9e1a00d` frente a este cambio, intercalados, 10 s, 3 tandas, pero el nodo se saturó con otros trabajos (loadavg 1 min de 2,7 a 15,9 durante las tandas; mis propias tandas suman a esa carga). Decisiones/s base → nuevo, por tanda (c=4 / 16 / 64): r1 (load 2,7 / 7,9) 5502/11306/17003 → 3978/9682/17010; r2 (10,7 / 12,5) 4169/9796/17646 → 4689/9059/16918; r3 (12,4 / 15,0) 4087/9379/16713 → 3913/9091/15873. Una primera pasada con load 2–11: base 7080/13675/22191, 6055/12130/20958, 4616/9691/17239; nuevo 6058/12096/21291, 5650/10860/16311, 4034/9217/15957. La variación entre tandas del mismo sha (hasta −35 %) supera la diferencia que se busca: no se puede afirmar ni negar el 5 % de `9e1a00d`. Pendiente: repetir con el nodo vacío. Lo que sí es determinista: −47 % de allocs y −20 % de ns/op por petición en el camino HTTP.

### Coste restante
`CascadaHTTP` queda ≈ 4 % sobre `9e1a00d` (9.866 ns/op, 65 allocs → 10.2 k, 67): lo explican el plazo de cuerpo (`SetReadDeadline` dos veces por petición) y el cubo por pregunta/clave de nonce; el escaneo ya cuesta ≈ 0,5 µs.
