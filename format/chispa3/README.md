# format/chispa3 — contenedor `.chispa` v3 y su cargador en Go (T2.5)

Módulo Go propio (`go 1.27`, biblioteca estándar; `kindling v0.17.0` solo para `L0Modelo`). Un único fichero con
L0, L1, L2, los esquemas compilados y la calibración, validado entero antes de usar nada.

```go
f, err := chispa3.Abrir("modelo.chispa")   // mmap; también acepta un .chispa v2 (solo sección L0)
defer f.Close()
l1, _ := f.L1()                            // sha256 de la sección comprobado antes de entregar los bytes
chispa3.Escribir(w, []chispa3.Seccion{{Tipo: chispa3.META, Datos: meta}, ...})
```

## Formato (little endian)
```
cabecera (32)  magia "\x89CHI\r\n\x1a\n" (la misma de v1/v2) · u16 versión=3 · u16 banderas=0 · u32 n secciones
               · u64 tamaño total del fichero · u32 CRC-32C de cabecera (con este campo a 0) + tabla · 4 bytes a 0
tabla (n × 56) u32 tipo · u32 0 · u64 offset · u64 longitud · [32]byte sha256 de la sección
datos          secciones en el orden de la tabla; offsets relativos al fin de la tabla
```
Reglas: cada sección empieza en `alinear16(fin de la anterior)` (la primera en 0) y el relleno es cero; no hay
bytes tras la última; sin tipos repetidos ni desconocidos. `Escribir` ordena por tipo, así que la salida es
determinista. Tipos: 1 `META`, 2 `L0`, 3 `L1`, 4 `L2`, 5 `ESQUEMAS`, 6 `CALIB`, 7 `CONJ` (T2.6b; se añadió al final del enum sin renumerar: los ficheros sin `CONJ` cargan igual), 8 `L0TF`, 9 `TORR` (igual: los `.chispa` sin ella cargan idéntico; lo comprueba `TestTORRAusenteEnTestdata`), 10 `SOPL1` (igual; `TestSOPL1AusenteEnTestdata`).

| sección | contenido |
|---|---|
| `META` | JSON `{version, tareas[], licencias{}, dorado}`; `dorado` = sha256 hex o vacío |
| `L0` | el `.chispa` v2 de kindling tal cual |
| `L1` | el `.chispa-l1` de `runtime/l1` (v1) tal cual. Sus offsets absolutos desde el inicio de su fichero ya son relativos al inicio de la sección, así que `l1.Desde(sección)` sirve sin cambios; el sha256 de la sección sustituye al del cuerpo |
| `L2` | ONNX int8, blob |
| `ESQUEMAS` | `u32 dim · u32 n · n×[32]hash (estrictamente crecientes) · n×f32 escala · n×dim×int8`; hash = `HashEsquema(pregunta, opciones)` (sha256 con prefijos de longitud). Búsqueda binaria sin copiar |
| `CALIB` | JSON `{tipos{tipo:{T,a,b,theta}}, tau_escalate}`; T>0, θ y τ en [0,1] |
| `CONJ` | cabeza conjunta L0 + L2 por esquema (`conj.go`): `u32 versión(1) · u32 n ·` n entradas con hash creciente: `[32]hash · u32 cabeza(1=lr) · u32 K · u32 d · u32 C · u32 nw(6) · f32 T · f32 β · 3×f32 esc · nw×f32 pesos · C×(u16 len · nombre UTF-8) clases crecientes · C·K×f32 escala · C·K·d×int8 prototipos`. El hash es `HashEsquema(pregunta, ids ordenados)`. Con 150 clases, K=16, d=256: ≈ 625 KB |
| `L0TF` | L0 TF-IDF de caracteres + regresión logística multinomial (`l0tf.go`), el de `model/lineas_base/correr.py`: `u32 versión(1) · u32 V · u32 C · u32 dtype(1=f32, 2=f16) ·` C×(u16 len · nombre) etiquetas crecientes (orden de `classes_`) `· C×f32 intercepciones · V×f32 idf · (V+1)×u32 desplazamientos · blob UTF-8 · V·C coeficientes` (por n-grama: `coef[f·C+c]`). El vocabulario son los n-gramas de 2 a 5 puntos de código en cadenas, estrictamente crecientes por bytes: la búsqueda es binaria, exacta y sin copiar, sin las colisiones de un hash (que mezclarían coeficientes de n-gramas distintos); cuesta ~10 bytes por n-grama frente a los C·4 de sus coeficientes. `DecodificarL0TF` valida el orden, los rangos y que todo sea finito; `Probs(texto)` hace el analizador `char_wb` de sklearn (minúsculas de Python incl. U+0130 y sigma final, espacios de `str.isspace`), sublinear tf, idf, norma l2 y softmax en doble precisión. Con 2 clases el escritor expande la fila única de sklearn a `[0, w]` |
| `TORR` | torre de esquemas de L2 al vuelo (`torr.go`, contrato en `model/l2/contrato-torre.md`): `u32 versión(1) · u32 dim(256) · u32 max_len(128) · u32 len_prefijo · prefijo UTF-8 («passage: ») · ONNX hasta el final`. El ONNX (e5 de pasaje + `Torre`, opset 17) recibe `input_ids`/`attention_mask` int64 (B,T) y devuelve `h` float32 (B,dim) normalizada. `DecodificarTORR` valida versión, rangos (dim ≤ 4096, max_len ≤ 8192, prefijo ≤ 256 B), UTF-8 del prefijo y que haya ONNX; no lo abre. `Fichero.Torre()` → `ErrNoHay` si falta. Con la sección, `chispa-server` calcula las torres de los esquemas que ESQUEMAS no trae (caché por torre en `decide.L2`); sin ella, L2 no opina sobre ellos |
| `SOPL1` | soporte few-shot por pregunta y opción (`sopl1.go`): `u32 versión(1) · u32 dim · u32 n` y n entradas con hash estrictamente creciente: `[32]byte hash · u32 C · C×(u16 len · id UTF-8) estrictamente crecientes · C×u32 k · C×f32 escala · C×dim×int8 media`. El hash es `ClaveConj` (`HashEsquema` de la pregunta y los ids ordenados: la clave de CONJ, que el runtime ya sabe calcular desde la petición); `k` es el número de ejemplos de la opción; `media` es la media de los embeddings de L1 de esos ejemplos, en int8 con escala máx\|x\|/127 por opción (como las torres de ESQUEMAS: 4× menos que f32 y un error ≤ 0,4 % por componente, muy por debajo del ruido de unos pocos ejemplos; una opción sin ejemplos lleva k=0, escala 0 y ceros). Con ella el runtime mezcla `p = normaliza((1−w)·p_desc + w·media)`, `w = k/(k+λ)` (`PesoSoporte`, `Mezclar`), con λ propio en L1 (`l1_shrinkage_lambda`) y en L2c (`l2_shrinkage_lambda`); por defecto ∞ (w=0: el comportamiento de antes). En L2 la media sale de las K ranuras de soporte de CONJ (`EntradaConj.MediaSoporte`) y el k, de esta sección: CONJ no cambia y los CONJ existentes se leen igual (`MezclarSimsL2`). Lector/escritor Go (`CodificarSopl1`, `DecodificarSopl1`, `Fichero.Sopl1()` → `ErrNoHay` si falta) y Python (`formato.sopl1`) dan los mismos bytes: `testdata/soporte.chispa` lo escribe Python y lo lee un test de Go |

## Validaciones
`Desde`/`Abrir` (todas devuelven errores con `errors.Is`): magia (`ErrMagia`), versión (`ErrVersion`), truncado
(`ErrTruncado`), cabecera/banderas/reservados/bytes sobrantes (`ErrCabecera`), CRC (`ErrCRC`), nº de secciones
(`ErrTabla`), tipo (`ErrTipo`, `ErrDuplicado`), solape (`ErrSolape`), hueco o desalineación (`ErrHueco`), fuera del
fichero (`ErrFuera`), desborde de enteros (`ErrDesborde`: offset o longitud > MaxInt64 o offset+longitud > MaxUint64),
relleno no nulo (`ErrRelleno`), tamaños (`ErrTamano`, `Limites`: fichero, nº de secciones, sección y por tipo; por
defecto 1 GiB, 6, 512 MiB). El sha256 de una sección se comprueba **una vez, de forma perezosa, en `Bytes`** (el
error es persistente); abrir no lee los datos. Los decodificadores de contenido (`DecodificarMeta/Calib/Esquemas`,
`ValidarL1`) validan rangos y tamaños con aritmética sin desborde.

**Compatibilidad:** si la versión es 2, `Desde` comprueba el CRC-32C final y devuelve un `Fichero` con solo `L0`
(`Compat()`); `L0Modelo()` lo carga con kindling. kindling v0.17.0 solo conoce la versión 2 (`FormatVersion`), así
que una «v1» se rechaza con `ErrVersion`. Los tests usan dos `.chispa` reales de `server/testdata`
(`testdata/`, entrenados con la Arena).

## Pruebas
```
cd format/chispa3 && go vet ./... && go test -race ./...
go test -run '^$' -fuzz=FuzzAbrir -fuzztime=10m -parallel=2 .
```
`FuzzAbrir` parte de ficheros completos, parciales, los dos v2 reales y cabeceras mínimas; ejercita `Desde`, los
decodificadores sobre bytes crudos (el sha256 haría fallar casi siempre antes un fichero mutado) y, en cada sección
cuyo sha256 cuadra, su decodificador.

## Sin verificar
- `L1` se probó con una cabecera sintética; no se cargó un `.chispa-l1` real (155 MB, no va a git) ni se pasó por `l1.Desde`.
- El sha256 de la cabecera del `.chispa-l1` (del cuerpo) no se recalcula: lo cubre el de la sección.
- No hay lector de v1 (no existe en kindling v0.17.0). No se probó en Windows/macOS (`mmap_otros.go` es un respaldo con lectura).

## L0TF (T4.5c)
Fuzz de la sección: `FuzzL0TF` 3 min (1 315 985 ejecuciones) y `FuzzAbrir` 2 min (194 744, con L0TF en el corpus), 2026-10-28, sin fallos;
lo aceptado recodifica byte a byte igual. Paridad con sklearn en `server/decide` (|Δp| 4e-8 en f32; ~3e-4 en f16).

## Log del fuzzing
`go test -run '^$' -fuzz=FuzzAbrir -fuzztime=10m -parallel=2 .` (microVM de 4 vCPU, go1.27.1 linux/amd64, 2026-10-28):
```
2026-10-28T02:39:38Z … 2026-10-28T02:50:39Z
fuzz: elapsed: 10m0s, execs: 1613937 (3838/sec), new interesting: 347 (total: 356)
PASS
ok  	chispa/format/chispa3	601.088s
```
Sin pánicos ni lecturas fuera de rango: la hipótesis de refutación no se cumplió. El rendimiento oscila (104–18 000
ejec./s) por el coste de `kindling.Unmarshal` en mutantes de v2 con CRC válido.
