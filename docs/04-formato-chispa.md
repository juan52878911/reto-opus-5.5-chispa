# El formato `.chispa` v3

Un solo fichero lleva L0, L1, L2, los esquemas compilados y la calibración. Se valida entero antes de usar nada.
Especificación y validaciones: [`format/chispa3/README.md`](../format/chispa3/README.md). Cargador: `chispa3.Abrir`.

## Estructura
Little endian.

- Cabecera de 32 bytes: magia, versión 3, número de secciones, tamaño total y CRC-32C.
- Tabla de secciones: tipo, offset, longitud y sha256 de cada una.
- Datos: las secciones, alineadas a 16 bytes.

Sin tipos repetidos ni desconocidos. El escritor ordena por tipo, así que la salida es determinista.
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

## Compatibilidad
- **v2 se carga.** Un `.chispa` v2 de kindling se abre como un v3 con solo `L0`.
- **v1 no se carga.** kindling v0.17.0 no la conoce; da `ErrVersion`.
- **Los ficheros viejos cargan.** `CONJ` y `L0TF` se añadieron al final del enum sin renumerar. Un fichero sin ellas carga igual. (`README` del formato cita `CONJ`; `L0TF` sigue el mismo criterio.)
- **Un servidor viejo no abre un fichero nuevo.** Los tipos desconocidos se rechazan.
- **Cambio de pregunta.** Cambia el hash de `ESQUEMAS` y `CONJ`. L2c cae a L2 y L2 no encuentra la torre de esa pregunta: reentrena con la pregunta nueva.
- Un servidor `chispa-server` admite un solo `-modelo`. Para unir secciones de varios ficheros: `deploy/mkmodelo -unir`
  ([`server/deploy/README.md`](../server/deploy/README.md)).

## Robustez
`FuzzAbrir` y `FuzzL0TF` corrieron sin fallos: ver el log al final de [`format/chispa3/README.md`](../format/chispa3/README.md#log-del-fuzzing).

## Qué no se probó
- Windows y macOS: `mmap_otros.go` es un respaldo con lectura.
- Una sección `L1` real de 155 MB pasada por `l1.Desde` desde el cargador (la prueba usó una cabecera sintética).
