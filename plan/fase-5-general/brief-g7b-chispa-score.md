# G.7b `.chispa` con score K ≥ 3: arreglar la exportación y generarlo en el barrido

## Antecedentes
G.7 (`model/bench/torre/e2e.sh`, paso «3b. .chispa score») debía generar con `calibrar.py` y `exportar.py` un `.chispa`
real con una tarea `score` de K ≥ 3. La sesión del SDK lo necesita para un test de paridad: L2 no opinaba en score porque
el runtime buscaba otra clave.

En la c6a falló con `[chispa_score] FALLO ver exportar-score.log`, y ese log no se subió. El dev eran 231 filas de
JevBench (`datos_g7.py`). En local G.7 lo daba por bueno, con las claves `score4`, `score4#1` y `score4#2`.

## Terminado cuando
- **Reproducir aquí el paso** con pesos aleatorios y las filas de JevBench del fixture
  (`model/evaluacion/tests/fixtures/jevbench`). Si el fixture no tiene `score` de K ≥ 3, usa el sintético que haga falta.
- **Encontrar la causa probable del fallo en la c6a.**
  - Pistas: `--min-top1` de la paridad con el checkpoint real; filas de JevBench con estados largos o vacíos; `go run` de
    `empaquetar_go` sin el proxy de módulos (GOPROXY); `calibrar.py` con muy pocas filas por tipo.
  - Arréglala.
  - Que `e2e.sh` suba siempre `exportar-score.log` a `resultados.tgz`.
- **Añadir el mismo paso a `model/l2/aws/barrido.sh`** con el checkpoint de G.8 (`$CHISPA_G8_S3/ckpt/mejor.pt`).
  - Subir el resultado a `$CHISPA_S3/score/l2-score.chispa`.
  - Anotar en el informe las claves de CALIB (`scoreK`, `scoreK#j`).
  - Si falla, no tumba el barrido y el log se sube igual.
- `barrido.sh` ≤ 16 KB.
- Prueba en seco, tests, y `make test`/`make smoke` en verde.
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- `model/l2/calibrar.py`, `model/l2/exportar.py`, `model/l2/aws/barrido.sh`, `model/bench/torre/**`, `model/l2/tests/**` y
  `model/evaluacion/**`.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Python en `~/venv`, Go en `~/go-sdk/bin` y modelos en `~/hf`. Sin GPU y sin red salvo la API de Claude.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.

## Tope
- ≤ 45 min de reloj · ≤ 3 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 6 líneas:
- rama y sha;
- causa;
- arreglo;
- qué sustituyo en `barrido.sh`.
