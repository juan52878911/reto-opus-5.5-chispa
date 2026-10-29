# G.7 Variantes de la torre: fp32, int8 dinámico por canal e int8 estático calibrado

## Antecedentes
G.6 (`model/bench/torre/resultados-20261029/LEEME.md`) midió la torre de L2 con el checkpoint real y la exportación int8
dinámica por canal: coseno de `h` frente a PyTorch 0,986 sin `<unk>` y top-1 0,937. El objetivo es coseno ≥ 0,999 y
top-1 ≥ 0,98. Además, la poda del vocabulario manda un 7,5 % de tokens a `<unk>`.

## Hipótesis
- fp32 (sin cuantizar) cumple la paridad y pesa unos 175 MB.
- int8 **estático** calibrado con unas 500 frases de train, con QDQ y escalas por canal en los pesos y por tensor en las
  activaciones, ajustadas con esas frases, llega a coseno ≥ 0,995 y top-1 ≥ 0,98 con unos 50 MB.

Se refuta midiendo con el checkpoint real en la c6a.

## Terminado cuando
- **`model/l2/exportar.py --torre-onnx`:**
  - `--cuant-torre ninguna|dinamico|estatico` (por defecto `dinamico`, el de hoy);
  - `--calib-torre <jsonl>` y `--n-calib 500` para el estático, con `onnxruntime.quantization.quantize_static` y un
    `CalibrationDataReader` sobre textos de torre reales (`texto_opcion` de filas de train);
  - `--sin-poda` también para la torre;
  - las `metadata_props` de siempre en las tres variantes;
  - tests con pesos aleatorios.
- **`model/bench/torre/e2e.sh`:** un bucle por variantes (`CHISPA_VARIANTES`, por defecto `ninguna dinamico estatico`). En
  cada una:
  - paridad (coseno y top-1, con poda y sin `<unk>`);
  - tamaño;
  - latencia p50/p99 de la torre en ORT con 1 hilo, por texto;
  - `chispa train --torre`, `chispa-server -tags ort` y `/v1/decide` con un esquema no visto de JevBench (que responda L2).

  `informe.md` lleva una tabla por variante. Exporta `CHISPA_TOK=$TOK` también en el paso de `go test -tags ort` del
  paquete de la torre (hoy solo lo lleva el paso del tokenizador, así que `TestTorreConTokenizadorReal` se salta). Debe seguir cabiendo en 16 KB; si no, comprímelo con gzip.
- **Contrato:** `model/l2/contrato-torre.md` explica las variantes.
- **max_len configurable.**
  - `exportar.py` escribe `chispa.consulta.max_len` en el ONNX de consulta y `chispa.torre.max_len` en el de la torre, con
    el max_tok con que se entrenó el checkpoint: si el ckpt lo guarda, ese; si no, `--max-tok`, por defecto 128. G.8
    entrena con 256.
  - Quita el 128 fijo del exportador y del contrato. Sin `chispa.consulta.max_len`, el runtime se queda en 128.
- **Un `.chispa` real con score K ≥ 3 para la otra sesión.** En la c6a, `e2e.sh` corre `calibrar.py` y `exportar.py` sobre
  un dev que incluya al menos una tarea `score` de 3 o más niveles: sácala del meta de tsjev o de JevBench. Sube el
  `.chispa` resultante a `$CHISPA_S3/score/l2-score.chispa` y anota en `informe.md` las claves de CALIB que lleva
  (`scoreK`, `scoreK#j`). Lo usa la sesión del SDK para un test de paridad.
- **Prueba en seco:** `CHISPA_LOCAL=1` con fixtures y `bash -n`. Tests y `make test`/`make smoke` en verde **después** del
  último cambio.
- **Parada:** si algo falla 2 veces, márcalo y para.

## Zona
- `model/l2/exportar.py`, `model/l2/contrato-torre.md`, `model/l2/tests/test_exportar_torre*.py` y `model/bench/torre/**`.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Python en `~/venv` y modelos en `~/hf`. Sin GPU y sin red salvo la API de Claude.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.

## Tope
- ≤ 75 min de reloj · ≤ 5 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 8 líneas:
- rama y sha;
- la prueba en seco;
- qué sustituyo para lanzar.
