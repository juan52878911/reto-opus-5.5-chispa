# El formato `.chispa` v3

Un solo fichero lleva L0, L1, L2, los esquemas compilados y la calibración. Se valida entero antes de usar nada.
Especificación y validaciones: [`format/chispa3/README.md`](../format/chispa3/README.md). Cargador: `chispa3.Abrir`.

## Estructura
Little endian.

- Cabecera de 32 bytes: magia, versión 3, número de secciones, tamaño total y CRC-32C.
- Tabla de secciones: tipo, offset, longitud y sha256 de cada una.
- Datos: las secciones, alineadas a 16 bytes.

Hasta diez secciones (una por tipo), sin tipos repetidos ni desconocidos. El escritor ordena por tipo, así que la salida es determinista.
El sha256 de una sección se comprueba una vez, al pedir sus bytes. Abrir no lee los datos.

## Secciones
Una sección es opcional. La cascada arma las capas con las que encuentra.

| Tipo | Sección | Qué lleva | Quién la usa |
|---|---|---|---|
| 1 | `META` | JSON: versión, tareas, licencias y `dorado` (sha256 hex o vacío) | trazabilidad |
| 2 | `L0` | el `.chispa` v2 de kindling, tal cual (Chispa lineal) | L0 |
| 3 | `L1` | el `.chispa-l1` de `runtime/l1` (embedding estático), tal cual | L1 |
| 4 | `L2` | ONNX int8 del codificador y las ranuras (blob) | L2 y L2c |
| 5 | `ESQUEMAS` | torres de opción int8, una por hash `HashEsquema(pregunta, opciones)` | L2 |
| 6 | `CALIB` | JSON: `tipos` (T, a, b, θ por tipo de pregunta), `tau_escalate` y `tau_l2c` opcional | τ y calibración |
| 7 | `CONJ` | cabeza conjunta L0 + L2 por esquema: pesos, T, β y prototipos int8 por clase | L2c |
| 8 | `L0TF` | L0 TF-IDF de caracteres con regresión logística; vocabulario ordenado, coeficientes f32 o f16 | L0, y entrada de L2c |
| 9 | `TORR` | ONNX de la torre de esquemas (e5 de pasaje + cabeza de torre) con dim, max_len y prefijo | L2 al vuelo |
| 10 | `SOPL1` | por pregunta y opción: k (ejemplos) y media int8 de sus embeddings de L1 | prototipo encogido en L1 y L2c (v2: con la norma de cada ranura de L2c) |

Los números salen del enum de [`chispa3.go`](../format/chispa3/chispa3.go).

### Notas por sección
- **META**: `dorado` guarda la huella del conjunto dorado con que se evaluó, si la hay.
- **L0**: elegido por el conjunto de etiquetas igual al de ids de las opciones. Un modelo por esquema.
- **L1**: `choice` y `noul`. Los parámetros de calibración están en `CALIB`.
- **L2**: el ONNX acepta los ids del tokenizador de e5. El servidor necesita `-tok` ([06-despliegue.md](06-despliegue.md)).
- **ESQUEMAS**: el hash se calcula sobre la pregunta y las opciones. Cambiar la pregunta cambia el hash.
- **CALIB**: la clave `scoreK` guarda a y b de la cabeza ordinal; los incrementos van en `scoreK#j`.
- **CONJ**: el hash es `HashEsquema(pregunta, ids ordenados)`. La pregunta debe ser la misma que al entrenar. Solo `choice`.
- **L0TF**: si está, el servidor usa este L0 y no el de la sección `L0`.
- **TORR**: `u32 versión(1) · u32 dim · u32 max_len · u32 len_prefijo · prefijo UTF-8 · ONNX` (little endian; [`torr.go`](../format/chispa3/torr.go)). `max_len` es el truncado del pasaje que aplica el runtime (por defecto 128; tope duro 512, `chispa3.MaxLenTope`; por encima, error al escribir o abrir). El del mensaje no va en ninguna sección: es la clave `chispa.consulta.max_len` de `metadata_props` del ONNX de la sección `L2` (misma convención que `chispa.torre.*`; sin ella, 128; tope 512 con error claro; [`maxlen.go`](../format/chispa3/maxlen.go), que lo lee en Go puro sin ORT). `chispa train --l2 <fichero>` no la escribe: la pone el exportador del modelo. El servidor y el núcleo móvil la leen al abrir (`MaxLenConsulta`/`MaxLenPasaje`); Kotlin y Swift no recortan por su cuenta. El escritor Python (`formato.torr`) da los mismos bytes: `format/chispa3/testdata/torre.chispa` lo escribe Python y lo lee un test de Go.
- **SOPL1**: `u32 versión(1 o 2) · u32 dim · u32 n` y, por pregunta (hash = `ClaveConj`, como CONJ, ordenado), `u32 C · C×(u16 len · id) · C×u32 k · C×f32 escala · C×dim×int8 media` y, **solo en la versión 2**, `u32 K · C×K×f32 normas` ([`sopl1.go`](../format/chispa3/sopl1.go)). La media de los embeddings de L1 de los ejemplos de cada opción va en int8 con escala por opción (decisión: 4× menos que f32 y error de cuantización ≤ 0,4 %). El runtime mezcla `p = normaliza((1−w)·p_desc + w·media)` con `w = k/(k+λ)`. **Equivalencia con la fórmula de G.8** (`model/l2/formula-shrinkage.md`): κ ≡ nuestra λ; el peso de la descripción es `λ_c = κ/(κ+n_c) = 1−w` (`chispa3.LambdaClase`, `PesoSoporte`), la media de los ejemplos va **sin normalizar** antes de mezclar (la norma se aplica después) y κ = 0 da solo ejemplos. En L1 es un vector por opción (`Mezclar`). En L2c se mezclan los prototipos del simproto, no la torre: `Q_j = λ_c·h + (1−λ_c)·M_j` con el mismo `h` (torre de la descripción) en las K ranuras, `P_j = Q_j/‖Q_j‖` por ranura y `simproto = mean_s max_j s·P_j` (`SimprotoMezclado`, `ProtosMezclados`); `sim_opción` no cambia. Una opción sin ejemplos conserva el simproto de CONJ. **Normas por ranura (versión 2).** CONJ guarda las ranuras de soporte ya normalizadas, pero `modelo.py` mezcla la media **sin normalizar** (`M_j = (1/n)·Σ S_i,j`, norma ≤ 1). La versión 2 añade a cada entrada `u32 K · C×K×f32 normas` (`normas[c·K+j] = ‖M_c,j‖`, en [0, 1]; K = 0 = entrada sin normas); el runtime reconstruye `M_j = proto_j·escala_j·norma_j` (`EntradaSopl1.NormasDe`, `ProtosMezclados`) y la fórmula coincide con `modelo.py` para todo n. El escritor emite la versión 2 solo si alguna entrada trae normas (si no, los bytes son los de la versión 1 de siempre); el lector acepta las dos. Un `.chispa` con SOPL1 v1, o con v2 pero con K distinto del de CONJ, usa la media normalizada: con n = 1 coincide con `modelo.py` y con n ≥ 2 la media pesa algo más que allí. Las normas salen de `chispa train --conjunta --shrinkage-lambda …` (`conjunta.normas_ranuras`: ‖Σ S‖/n con las mismas filas de soporte que `prototipos`); L1 no las usa. Con n distinto entre el soporte de CONJ (los `SOPORTE` por clase) y el k de SOPL1 (todos los ejemplos que L1 ve), la norma es la del primero y λ_c usa el segundo.

**Semántica de λ** (L1 y L2c, igual): ausente/`nil` = **apagado** (el comportamiento de antes del soporte); λ = 0 → `λ_c = 0`, solo ejemplos; λ = +∞ → `λ_c = 1`, solo descripción (en L2c antes +∞ apagaba; ya no). La config es `l1_shrinkage_lambda` y `l2_shrinkage_lambda` (JSON no tiene ∞: un valor enorme, p. ej. 1e300, hace de ∞); en el núcleo móvil `AbrirConSoporte(ruta, λL1, λL2)` con `SoporteApagado` (−1; negativo o NaN también) como apagado, y en Kotlin/Swift `lambdaSoporteL1/L2` nulos = apagado. `chispa train --l1 … --ejemplos … --shrinkage-lambda λ` la escribe (sin la opción no se escribe nada). `formato.sopl1` (Python) da los mismos bytes: `format/chispa3/testdata/soporte.chispa` (v1) y `soporte-v2.chispa` (v2, con normas, caso a mano n = 3).

## Compatibilidad
- **v2 se carga.** Un `.chispa` v2 de kindling se abre como un v3 con solo `L0`.
- **v1 no se carga.** kindling v0.17.0 no la conoce; da `ErrVersion`.
- **Los ficheros viejos cargan.** `CONJ`, `L0TF`, `TORR` y `SOPL1` se añadieron al final del enum sin renumerar. Un fichero sin ellas carga igual
  (el README del formato lo comprueba con `TestTORRAusenteEnTestdata` y `TestSOPL1AusenteEnTestdata`).
- **Un servidor viejo no abre un fichero nuevo.** Los tipos desconocidos se rechazan: un `.chispa` con `TORR` o `SOPL1` pide un servidor que las conozca.
- **Cambio de pregunta.** Cambia el hash de `ESQUEMAS` y `CONJ`. L2c cae a L2 y L2 no encuentra la torre de esa pregunta: reentrena con la pregunta nueva.
- Un servidor `chispa-server` admite un solo `-modelo`. Para unir secciones de varios ficheros: `deploy/mkmodelo -unir`
  ([`server/deploy/README.md`](../server/deploy/README.md)).

## Robustez
`FuzzAbrir` y `FuzzL0TF` corrieron sin fallos: ver el log al final de [`format/chispa3/README.md`](../format/chispa3/README.md#log-del-fuzzing).

## Qué no se probó
- Una corrida registrada de fuzzing de `TORR` (existen `FuzzDecodificarTORR` y `FuzzAbrirTORR`) y de `SOPL1`: el README del formato solo documenta las de `FuzzAbrir` y `FuzzL0TF`.
- El límite de secciones: el README del formato dice «6» por defecto, pero el código usa `numTipos-1` (10, el enum de `chispa3.go`); aquí manda el código.
- Windows y macOS: `mmap_otros.go` es un respaldo con lectura.
- Una sección `L1` real de 155 MB pasada por `l1.Desde` desde el cargador (la prueba usó una cabecera sintética).
