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
| 10 | `SOPL1` | por pregunta y opción: k (ejemplos) y media int8 de sus embeddings de L1 | prototipo encogido en L1 y L2c (v2: con la norma de cada ranura de L2c; v3: y el n del soporte de CONJ) |

Los números salen del enum de [`chispa3.go`](../format/chispa3/chispa3.go).

### Notas por sección
- **META**: `dorado` guarda la huella del conjunto dorado con que se evaluó, si la hay.
- **L0**: elegido por el conjunto de etiquetas igual al de ids de las opciones. Un modelo por esquema.
- **L1**: `choice` y `noul`. Los parámetros de calibración están en `CALIB`.
- **L2**: el ONNX acepta los ids del tokenizador de e5. El servidor necesita `-tok` ([06-despliegue.md](06-despliegue.md)).
- **ESQUEMAS**: el hash se calcula sobre la pregunta y las opciones. Cambiar la pregunta cambia el hash. Versión 1: `HashEsquema(pregunta, ids)` (32 bytes; no ve descripción ni `kind`). Versión 2: `HashEsquema2` (16 bytes, ver «Clave de esquema v2»); la versión va en la cabecera.
- **CALIB**: la clave `scoreK` guarda a y b de la cabeza ordinal; los incrementos van en `scoreK#j`.
- **CONJ**: el hash es `HashEsquema(pregunta, ids ordenados)` (v1) o `HashEsquema2(pregunta, kind, opciones)` (v2). La pregunta debe ser la misma que al entrenar. Solo `choice`.
- **L0TF**: si está, el servidor usa este L0 y no el de la sección `L0`.
- **TORR**: `u32 versión(1) · u32 dim · u32 max_len · u32 len_prefijo · prefijo UTF-8 · ONNX` (little endian; [`torr.go`](../format/chispa3/torr.go)). `max_len` es el truncado del pasaje que aplica el runtime (por defecto 128; tope duro 512, `chispa3.MaxLenTope`; por encima, error al escribir o abrir). El del mensaje no va en ninguna sección: es la clave `chispa.consulta.max_len` de `metadata_props` del ONNX de la sección `L2` (misma convención que `chispa.torre.*`; sin ella, 128; tope 512 con error claro; [`maxlen.go`](../format/chispa3/maxlen.go), que lo lee en Go puro sin ORT). `chispa train --l2 <fichero>` no la escribe: la pone el exportador del modelo. El servidor y el núcleo móvil la leen al abrir (`MaxLenConsulta`/`MaxLenPasaje`); Kotlin y Swift no recortan por su cuenta. El escritor Python (`formato.torr`) da los mismos bytes: `format/chispa3/testdata/torre.chispa` lo escribe Python y lo lee un test de Go.
- **SOPL1**: `u32 versión(1, 2 o 3) · u32 dim · u32 n` y, por pregunta (hash = `ClaveConj`, como CONJ, ordenado), `u32 C · C×(u16 len · id) · C×u32 k · C×f32 escala · C×dim×int8 media` y, **desde la versión 2**, `u32 K · C×K×f32 normas` y, **solo en la versión 3**, `u32 M · M×u32 n_l2` (M = 0 o C) ([`sopl1.go`](../format/chispa3/sopl1.go)). La media de los embeddings de L1 de los ejemplos de cada opción va en int8 con escala por opción (decisión: 4× menos que f32 y error de cuantización ≤ 0,4 %). El runtime mezcla `p = normaliza((1−w)·p_desc + w·media)` con `w = k/(k+λ)`. **Equivalencia con la fórmula de G.8** (`model/l2/formula-shrinkage.md`): κ ≡ nuestra λ; el peso de la descripción es `λ_c = κ/(κ+n_c) = 1−w` (`chispa3.LambdaClase`, `PesoSoporte`), la media de los ejemplos va **sin normalizar** antes de mezclar (la norma se aplica después) y κ = 0 da solo ejemplos. En L1 es un vector por opción (`Mezclar`). En L2c se mezclan los prototipos del simproto, no la torre: `Q_j = λ_c·h + (1−λ_c)·M_j` con el mismo `h` (torre de la descripción) en las K ranuras, `P_j = Q_j/‖Q_j‖` por ranura y `simproto = mean_s max_j s·P_j` (`SimprotoMezclado`, `ProtosMezclados`); `sim_opción` no cambia. Una opción sin ejemplos conserva el simproto de CONJ. **Normas por ranura (versión 2).** CONJ guarda las ranuras de soporte ya normalizadas, pero `modelo.py` mezcla la media **sin normalizar** (`M_j = (1/n)·Σ S_i,j`, norma ≤ 1). La versión 2 añade a cada entrada `u32 K · C×K×f32 normas` (`normas[c·K+j] = ‖M_c,j‖`, en [0, 1]; K = 0 = entrada sin normas); el runtime reconstruye `M_j = proto_j·escala_j·norma_j` (`EntradaSopl1.NormasDe`, `ProtosMezclados`) y la fórmula coincide con `modelo.py` para todo n. El escritor emite la versión 2 solo si alguna entrada trae normas (si no, los bytes son los de la versión 1 de siempre); el lector acepta las dos. Un `.chispa` con SOPL1 v1, o con v2 pero con K distinto del de CONJ, usa la media normalizada: con n = 1 coincide con `modelo.py` y con n ≥ 2 la media pesa algo más que allí. Las normas salen de `chispa train --conjunta --shrinkage-lambda …` (`conjunta.normas_ranuras`: ‖Σ S‖/n con las mismas filas de soporte que `prototipos`); L1 no las usa. **n_l2 (versión 3).** El soporte de CONJ (los `SOPORTE` por clase) puede ser un subconjunto de los ejemplos que ve L1 (k), y `modelo.py` pesa con el n del primero: `λ_c = κ/(κ+n)`. La versión 3 añade a cada entrada, tras las normas, `u32 M · M×u32 n_l2` (M = 0 = sin dato, o M = C con el n de cada clase; `n_l2[c] = 0` también = sin dato). L2c usa `n_l2` si está (`EntradaSopl1.NL2De`, en `SimprotoMezclado`: servidor y `chispamovil`) y si no el k de siempre; **L1 sigue con k**. Se escribe desde el mismo recuento de filas de soporte que las normas (`conjunta.n_soporte`; `chispa train --conjunta --shrinkage-lambda …`). Va como versión 3 y no como ampliación de la 2 porque las entradas no llevan longitud: un lector de la 2 rechazaría los bytes de más. El escritor emite la 3 solo si alguna entrada trae `n_l2` (si no, los bytes son los de la 1 o la 2 de siempre); el lector acepta las tres. Caso a mano (`TestShrinkageL2cUsaNL2`): k = 5, n_l2 = 3, κ = 3 ⇒ λ_c = 0,5 como en `modelo.py` (con k saldría 3/8).

**Semántica de λ** (L1 y L2c, igual): ausente/`nil` = **apagado** (el comportamiento de antes del soporte); λ = 0 → `λ_c = 0`, solo ejemplos; λ = +∞ → `λ_c = 1`, solo descripción (en L2c antes +∞ apagaba; ya no). La config es `l1_shrinkage_lambda` y `l2_shrinkage_lambda` (JSON no tiene ∞: un valor enorme, p. ej. 1e300, hace de ∞); en el núcleo móvil `AbrirConSoporte(ruta, λL1, λL2)` con `SoporteApagado` (−1; negativo o NaN también) como apagado, y en Kotlin/Swift `lambdaSoporteL1/L2` nulos = apagado. `chispa train --l1 … --ejemplos … --shrinkage-lambda λ` la escribe (sin la opción no se escribe nada). `formato.sopl1` (Python) da los mismos bytes: `format/chispa3/testdata/soporte.chispa` (v1) `soporte-v2.chispa` (v2, con normas, caso a mano n = 3) y `soporte-v3.chispa` (v3, con n_l2).

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

## Clave de esquema v2 (`HashEsquema2`)

La clave v1 no recoge la descripción ni el `kind`: dos esquemas con las mismas opciones y descripciones distintas compartían torres. La v2 sí:

```
HashEsquema2 = sha256( pregunta · 0x1f · kind · 0x1f ·
                       por cada opción ordenada por id (orden de bytes): id · 0x1e · descripción · 0x1d )[:16]
```

Todo en UTF-8, sin prefijos de longitud; `kind` es `choice`, `score`, `noul` o `multi`; la descripción ausente es la cadena vacía. Son 16 bytes (los 16 primeros del sha256).

- **ESQUEMAS v2**: `u32 (versión<<16 | dim) · u32 n · n×[16]byte clave (estrictamente crecientes) · n×f32 escala · n×dim×int8`. En v1 la primera palabra es `dim` (≤ 4096), o sea versión 0 = v1; un lector viejo rechaza la v2 por dim fuera de rango. La clave de cada torre es `HashEsquema2(pregunta, kind, [opción])` en `choice` y `multi` (una torre por opción), y `HashEsquema2(pregunta, kind, opciones)` en `score` (todas) y `noul` (`false` y `true`, con la descripción de la petición si la trae, si no vacía).
- **CONJ v2**: igual que la v1 con `u32 versión = 2` y el hash de cada entrada de 16 bytes: `HashEsquema2(pregunta, "choice", todas las opciones)`.
- **Lector**: acepta v1 y v2 (`Esquemas.Version()`, `Conj.Version()`). El runtime (servidor `decide`, `chispamovil`) elige la función de clave con la versión de cada sección (`BuscarEsquema`); una sección v2 no responde a claves v1 ni al revés, así que no se mezclan. Con v2, la misma pregunta con otra descripción (u otro `kind`) es otro esquema: sus torres se calculan al vuelo. La caché de torres al vuelo se indexa por `HashEsquema(pregunta, [id, descripción])` (una torre por opción, no depende del fichero) y la de resultados por `ClaveEsquema` (ya incluye `kind` y descripciones).
- **SOPL1** no cambia: sigue con `ClaveConj` (v1).
- **Vectores de prueba**: `format/chispa3/vectores-clave-v2.json` (choice con descripciones, noul, score, opciones desordenadas, otra descripción), comprobados en Go (`clave2_test.go`) y Python (`tests/test_claves_v2.py`). Escritor Python: `formato.hash_esquema2`, `formato.esquemas(…, version=2)`, `formato.conj(…, version=2)`.
