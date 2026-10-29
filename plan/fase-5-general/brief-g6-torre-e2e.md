# G.6 Verificación de punta a punta de la torre de L2 con el checkpoint real (c6a)

## Antecedentes
- **Esta rama.** G.5 (`model/l2/exportar.py --torre-onnx`) exporta la torre a ONNX int8. El contrato está en
  `model/l2/contrato-torre.md` y el fixture en `model/l2/tests/fixtures_torre/torre.json`.
  - Con pesos aleatorios, el coseno de `h` da 0,9987 con la poda; el top-1 no se pudo juzgar.
  - **Falta** escribir en `metadata_props` del ONNX `chispa.torre.dim` (256), `chispa.torre.max_len` (128) y
    `chispa.torre.prefijo` («passage: »). Los lee `chispa train --torre`.
- **La rama `claude/chispa-sdk-6773ef`**, de otra sesión, que **no se integra**:
  - sección TORR (tipo 9: `u32 versión · u32 dim · u32 max_len · u32 len_prefijo · prefijo · ONNX`);
  - `server/torre` (runtime ORT, `ort_test.go`);
  - `chispa train --torre <onnx>`;
  - torres al vuelo en `chispa-server`;
  - el prefijo «passage» en `runtime/tok` (`TestIgualdadTransformersPasaje` con `CHISPA_TOK`).
  - Ves su contenido con `git show claude/chispa-sdk-6773ef:<ruta>`, que está en el mismo repo.
- **El checkpoint real** está en `s3://chispa-pruebas-879381269751/l2-20261028b/ckpt/mejor.pt`. JevBench lo baja
  `model/evaluacion/aws/jevbench.sh` (este script también lo usa).

## Hipótesis
Con el checkpoint real:
- la `h` del ONNX tiene coseno ≥ 0,999 frente a PyTorch, sin `<unk>`, y declara el que tiene con la poda;
- el top-1 de choice con torres al vuelo frente a PyTorch es ≥ 0,98;
- en `chispa-server` de la rama del SDK, un esquema de JevBench que no está en ningún `.chispa` lo decide L2 por
  `/v1/decide`.

Se refuta midiendo.

## Terminado cuando
- **`exportar.py`** escribe esas tres `metadata_props` al exportar la torre. Un test las comprueba y van al contrato.
- **`model/bench/torre/e2e.sh`**: user-data de una c6a.xlarge spot (≤ 16 KB) con el patrón de siempre: marcador
  `__CHISPA_S3__`, `shutdown -h +75`, un trap que sube `log.txt` y `resultados.tgz`, y descargas por fichero.
  - **Dos paquetes:**
    - `$CHISPA_S3/codigo-modelo.tgz`: esta rama, con `model/`;
    - `$CHISPA_S3/codigo-sdk.tgz`: la rama del SDK, con `server/`, `runtime/`, `format/`, `sdk/python/` y `go.work`
      si existe.
  - Añade `model/bench/torre/empaquetar.sh <rama-o-sha> <rutas…>` con `git archive`, que no depende de bsdtar.
  - **Pasos:**
    1. Instala Go, gcc, ORT y Python con torch CPU.
    2. Exporta la consulta y la torre con el checkpoint real.
    3. Paridad: coseno de `h` y top-1 de choice en 300 filas de massive-es, con la poda y sin `<unk>` si cabe en memoria.
    4. En la rama del SDK:
       - `go get github.com/yalue/onnxruntime_go` en `server/go.mod`, **solo en la instancia**;
       - `go test -tags ort ./server/torre/...` con `CHISPA_ORT_LIB`;
       - `TestIgualdadTransformersPasaje` con `CHISPA_TOK`.
    5. `chispa train --torre` sobre un esquema mínimo, `chispa-server -tags ort`, y 5 esquemas de JevBench que no estén en el
       `.chispa` por `/v1/decide`. Comprueba que responde L2 y cuál es su exactitud. Si cabe en el tiempo, los 231 casos de
       JevBench a través del servidor, junto a la cifra de Python (0,407).
    6. `informe.md` con cada punto en OK/FALLO y las cifras.
- **Prueba en seco aquí:** `CHISPA_LOCAL=1` con fixtures, sin ORT y sin checkpoint, hasta donde se pueda, y `bash -n`.
- Tests de Python y `make test`/`make smoke` en verde.
- **Parada:** si algo falla 2 veces, márcalo y para.

## Zona
- `model/l2/exportar.py`, `model/l2/contrato-torre.md`, `model/l2/tests/test_exportar_torre.py` y `model/bench/torre/**`.
- La rama del SDK se lee y no se cambia.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Python en `~/venv`, Go en `~/go-sdk/bin` y modelos en `~/hf`. Sin GPU, sin S3 y sin red salvo la API
  de Claude.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.

## Tope
- ≤ 90 min de reloj · ≤ 5 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 10 líneas:
- rama y sha;
- la prueba en seco;
- cómo empaqueto las dos ramas;
- qué sustituyo para lanzar.
