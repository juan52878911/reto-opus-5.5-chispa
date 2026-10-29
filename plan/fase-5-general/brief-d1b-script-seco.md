# D1b Arreglar `e2e.sh` y `paridad_servidor.py`, y una prueba en seco que recorra todos los pasos

## Antecedentes
- La corrida D1 de `model/bench/torre/e2e.sh` en c6a falló dos veces por bugs del script, no del producto. Resultados en
  `model/bench/torre/resultados-20261029-d1/LEEME.md`.
- **Bug 1.** En `e2e.sh`, `pasada calib-l2fp32 1` (≈ línea 255) llama a `pasada()` con 2 argumentos, pero la función
  espera 3 (`nombre .chispa restantes`). Bajo `set -u` aborta con `$3: unbound variable`, y se pierden la pasada (c) y el
  paso móvil que va detrás. Debe pasar `"$RES/calib-global-l2fp32.chispa"`.
- **Bug 2.** `model/bench/torre/paridad_servidor.py`, en `probs_calib`, solo rellena con `CALIB_DEFECTO` los tipos
  `choice` y `noul`. Con la CALIB de `chispa train`, que no trae `score4`/`score5` ni sus incrementos `scoreK#j`, falla
  con `KeyError: 'score4'`.
  - Lee cómo resuelve el servidor un score sin CALIB, en `server/decide` (solo lectura), y usa exactamente esos
    valores: `a`, `b` y los incrementos por defecto.
  - Si el servidor no tiene valores por defecto para score, el diagnóstico marca ese caso como «sin CALIB» y sigue, sin
    abortar.
- La prueba en seco que hay hoy (`CHISPA_LOCAL=1`) omite los pasos Go si no hay ORT. Por eso no vio ninguno de los dos
  bugs.

## Terminado cuando
- Los dos bugs están arreglados y cada uno tiene un test:
  - un test Python de `probs_calib` con una CALIB sin `score4` ni `score5`;
  - una comprobación de `e2e.sh` que detecte llamadas a `pasada` y `diagnosticar` con un número de argumentos
    distinto del que esperan. Vale `bash -n` más un grep o un test de shell sencillo.
- **Modo en seco completo**, `CHISPA_LOCAL=1` (o `CHISPA_SECO=1` si hace falta otro), que **recorra todos los pasos**
  de `e2e.sh` sin AWS, sin dnf y sin shutdown:
  - checkpoint aleatorio pequeño y un `.chispa` pequeño;
  - JevBench de fixture (unos 10 casos de choice, noul y score);
  - `chispa-server` compilado de verdad con Go y ORT, si están en el nodo (`~/ort`, `~/go-sdk/bin`); si no están,
    dilo en el informe;
  - pasos que tiene que recorrer: pasada base, `tipos-l2`, `diagnosticar base`, la reescritura de CALIB, la pasada
    calib, `diagnosticar calib`, la exportación fp32, la pasada `calib-l2fp32` con su diagnóstico y el paso móvil;
  - **criterio:** al final `estado.tsv` no tiene ningún `FALLO` ni ningún `OMITIDO` por un error del script. Las
    exactitudes con pesos aleatorios dan igual.
- `python -m unittest discover -s model -t .`, `make test` y `make smoke` en verde **después** del último cambio, y la
  prueba en seco completa pasada al menos una vez después del último cambio.
- **Parada.** Si algo falla 2 veces, márcalo y para. Si sale un bug del producto (`server/`, `sdk/`), descríbelo en el
  informe y no lo arregles.

## Zona
- `model/bench/torre/**` y `model/l2/tests/**`.
- No toques `server/`, `sdk/` ni `format/`; léelos si hace falta.
- Rama: la que te da delega. Base: `integracion`. Commits simples, sin firmas ni `Co-Authored-By`. Sin push ni merge.

## Entorno
- `source ~/.profile`. Python en `~/venv`, Go en `~/go-sdk/bin`, ORT en `~/ort` y modelos en `~/hf`. Sin red salvo la
  API de Claude.

## Tope
- ≤ 75 min de reloj · ≤ 5 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 10 líneas:
- rama y sha;
- los dos arreglos, con los valores de score por defecto y de dónde salen;
- qué pasos recorre la prueba en seco y la tabla de `estado.tsv` resultante;
- si hubo pasos con ORT o Go reales o simulados;
- tests.
