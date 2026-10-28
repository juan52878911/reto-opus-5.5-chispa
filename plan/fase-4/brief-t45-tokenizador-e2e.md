# T4.5 Tokenizador de e5 en Go y prueba de punta a punta de L2c en el servidor (AWS)

## Antecedentes
- T2.6b (`663d4e0`) dejó la capa L2c («L2 conjunta», sección `CONJ`) en `server/decide/`, con paridad Go ↔ Python de 8e-8.
  Tiene tres huecos:
  1. **No hay tokenizador de e5 en Go.** `server/cmd/chispa-server/main.go` pasa `nil` y L2 queda en stub incluso con
     `-tags ort` (`server/decide/l2.go`, `ErrSinTokenizador`).
  2. **L0 distinto.** La cabeza conjunta se entrena con el L0 de sklearn de `model/l2/conjunta.py`, pero el servidor le
     pasa el L0 de Chispa (`pkg/chispa`, el que entrena `sdk/python/chispa/entrenador_go/`). No está medido cuánto cambia.
  3. **Sin compilar con ORT.** `l2_ort.go` no se ha compilado (`NuevaSesionORT`), y la latencia de simproto, unos 10 ms con
     150 clases, no está optimizada.
- `runtime/l1/tokenizar.go` ya implementa en Go, de forma exacta, un tokenizador unigram con Metaspace y Viterbi (el de
  potion). El de e5 (XLM-R, sentencepiece unigram) es de la misma familia: cambian el vocabulario, la normalización
  (precompiled charsmap, NFKC) y los tokens especiales.
- Patrón de AWS: `server/deploy/aws/arranque.sh` (T4.4: imagen y `-tags ort` en una c6a), `model/l2/aws/arranque.sh`
  (dependencias y descargas por fichero) y `model/l2/exportar.py` (T2.6: ONNX int8 de L2 con paridad).

## Hipótesis
- H1: reusando el motor de `runtime/l1` con el `tokenizer.json` de e5, un tokenizador en Go da los mismos ids que
  `transformers` en el 100 % de las 2.274 frases del sondeo y en un conjunto de frases difíciles (emojis, tildes
  compuestas NFD, espacios raros, URL, mayúsculas y textos de más de 512 piezas truncados igual).
- H2: de punta a punta, con L2 real (ONNX int8 de T2.1b) y `CONJ` entrenado por `chispa train --conjunta` con el L0 de
  Chispa, el macro-F1 de `/v1/decide` en el test de massive queda a ≤ 1 punto del de `conjunta.py` (0,817, T2.2c).
  Si no, el L0 distinto es la causa y hay que medir cuánto.
- H3: con simproto vectorizado (prototipos int8 contiguos y producto entero), L2c cuesta ≤ 2 ms con 150 clases en una
  c6a, sin contar el codificador.
- Se refuta midiendo.

## Terminado cuando
- **Tokenizador.**
  - Paquete `runtime/tok/` (Go puro): carga el vocabulario de e5 desde un fichero propio, exportado desde
    `tokenizer.json` con un script Python incluido.
  - `Tokenizar(texto) []int32`, con el prefijo `query: ` y truncado a 128 como `model/l2/modelo.py`.
  - Reusa `runtime/l1`: si hace falta exportar algo de ese paquete, hazlo **sin cambiar** su comportamiento ni su test dorado.
  - Test de igualdad frente a ids de referencia generados con `transformers` (fixture en el repo, ≤ 2 MB) y fuzz de 2 min.
- **Servidor.**
  - `chispa-server` usa ese tokenizador cuando el `.chispa` trae L2.
  - simproto optimizado en `server/decide/`, con un bench antes y después.
  - `go test ./...` y `go vet ./...` sin la etiqueta `ort`.
- **AWS.** `server/deploy/aws/e2e.sh`, user-data para una c6a.xlarge spot con el patrón de siempre: marcador
  `__CHISPA_S3__`, `shutdown -h +90`, trap que sube `log.txt` y `resultados.tgz`, y descargas por fichero.
  - Pasos:
    1. instala Go, Python, ORT y las dependencias;
    2. baja de S3 el checkpoint `s3://chispa-pruebas-879381269751/l2-20261028b/ckpt/mejor.pt` y los datasets como
       `model/l2/aws/arranque.sh`;
    3. exporta L2 a ONNX int8 con `model/l2/exportar.py`;
    4. corre `chispa train --conjunta` sobre el train de massive y de clinc150;
    5. compila `chispa-server -tags ort` y lo arranca;
    6. manda el test completo de massive y clinc150 por `/v1/decide`;
    7. calcula el macro-F1 con `chispa_eval`, la fracción por capa y el p50/p99 por capa y total;
    8. compara con `conjunta.py` (T2.2c).
  - Su `empaquetar` usa `find` y `tar` portables, sin `-C` combinado con `-T`, porque se ejecuta con bsdtar.
- **Prueba en seco aquí.**
  - Tests del tokenizador: en la VM está e5 en `~/hf` con su `tokenizer.json`.
  - El bench de simproto.
  - `CHISPA_LOCAL=1 bash server/deploy/aws/e2e.sh` con fixtures, sin ORT: L2 en stub y L2c con similitudes falsas.
  - `bash -n` del script.
- `make test` y `make smoke` en verde. Parada: si algo falla 2 veces, márcalo y para.

## Zona
- `runtime/tok/**`, `server/**` y `runtime/l1/**`, este último solo para exportar lo necesario, sin cambiar su
  comportamiento.
- No toques `format/`, `sdk/`, `model/` ni `contracts/`.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Go en `~/go-sdk/bin`, Python en `~/venv` y modelos en `~/hf`. Sin GPU, sin S3 y sin red salvo la
  API de Claude.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.
- No vuelques datos en el contexto. Las PQRS no entran.

## Tope
- ≤ 150 min de reloj · ≤ 8 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 15 líneas:
- rama y sha;
- igualdad del tokenizador (n y %);
- simproto antes y después;
- la cola de la prueba en seco;
- qué sustituyo para lanzar `e2e.sh`;
- qué quedó sin verificar.
