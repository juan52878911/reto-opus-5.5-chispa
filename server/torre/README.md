# server/torre — torre de L2 al vuelo

`torre.Codificador` implementa `decide.CodificadorTorre`: tokeniza el texto de la torre (`passage: pregunta · opción · descripción`,
runtime/tok `TokenizarPasaje`, truncado a 128 y a `max_len` de la sección), corre el ONNX de la sección `TORR` del `.chispa` y devuelve
`h` (256, normalizada). Contrato (resumen; el original, `model/l2/contrato-torre.md`, vive en la rama de modelos y no está en esta):
entradas `input_ids` y `attention_mask` int64 (B,T); salida `h` (B,256) float32 normalizada; prefijo `passage: `; max_len 128; opset 17.

- `Nuevo(ses, tk, chispa3.Torre)` con cualquier `Sesion`; `Abrir(chispa3.Torre, Tokenizador)` abre el ONNX con ORT (`-tags ort`; sin la etiqueta devuelve `ErrSinORT`).
- `IniciarORT(ruta)`: el entorno de ORT se inicializa una vez por proceso y lo comparten L2 (`decide.NuevaSesionORT`) y la torre.
- Cableado: `decide.ArmarDesde` monta `L2.ConTorres` si el `.chispa` trae `TORR` y el `Tokenizador` implementa `TokenizadorPasaje` (`chispa-server -tok`).
  La caché es por torre (clave `HashEsquema(pregunta, [opción, descripción])`), no por esquema.
- `testdata/sintetico.py` genera `sintetico.onnx` (4,3 MiB, semilla fija, opset 17) y `sintetico_ref.json` (h de onnxruntime de Python).
  `go test -tags ort ./torre` los compara con el ORT de Go (`CHISPA_ORT_LIB` = ruta de libonnxruntime.so). Necesita gcc y `go get github.com/yalue/onnxruntime_go`.
