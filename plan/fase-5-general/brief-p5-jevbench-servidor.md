# P5 JevBench a través del servidor sobre la rama unificada, con torres al vuelo comprobadas

## Antecedentes
- `model/bench/torre/e2e.sh` empaqueta **dos** ramas: el modelo desde esta y el servidor desde la del SDK, que ya no
  existe. Desde ahora todo está en una sola rama (`integracion`).
- **Medidas anteriores** (`model/bench/torre/resultados-20261029-*`): JevBench por el servidor dio 0,411–0,429, pero sin
  comprobar en `/metrics` que la torre se calculara (`chispa_torres_calculadas_total`). Todas las respuestas salieron
  «escalar» por el τ de CALIB.
- **Comportamiento actual de `chispa-server`:**
  - arranca en 127.0.0.1 sin `api_keys`;
  - rechaza claves de config desconocidas;
  - la ruta de ORT se pasa con `-ort-lib`, `CHISPA_ORT_LIB` o ldflags;
  - existe `tau_l2_esquema_nuevo`.
  - Lee la ayuda (`-h`) y `server/README.md`.

## Hipótesis
Con el checkpoint de G.8 corrida 2 (`s3://chispa-pruebas-879381269751/general-20261029b/ckpt/mejor.pt`, max_tok 256), el
servidor decide los 231 casos de JevBench, ninguno metido en el `.chispa`, con torres al vuelo, y su exactitud queda a
≤ 1 punto de la de Python con el mismo checkpoint (0,463). Se refuta midiendo.

## Terminado cuando
- **`model/bench/torre/e2e.sh`** pasa a modo de una rama: un solo `codigo.tgz`, de esta rama, con `model/`, `server/`,
  `runtime/`, `format/` y `sdk/` y el proxy de módulos. El modo de dos ramas queda como opción o se quita.
- **Checkpoint y exportación.** Usa el de G.8 corrida 2, configurable con `CHISPA_CKPT_S3`, y respeta su max_tok 256.
  - Si el exportador de esta base ya tiene `--perfil servidor`, úsalo con `CHISPA_EXPORT_ARGS`.
  - Si no, usa `--cuant-torre ninguna --sin-poda` y dilo.
- **Comprobación obligatoria.** Tras las peticiones, lee `/metrics`.
  - Si `chispa_torres_calculadas_total` es 0 o L2 no aparece en las capas, la corrida es FALLO.
  - Escribe en `informe.md` las capas por caso.
  - Lanza también una pasada con `tau_l2_esquema_nuevo` = 0,276, el que deja la abstención en el 20 % según
    `model/l2/resultados/barrido-20261029/`, para ver cuánto contesta L2.
- **Prueba en seco aquí** (`CHISPA_LOCAL=1` con fixtures y sin ORT), `bash -n`, `make test` y `make smoke` en verde.
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- `model/bench/torre/**`.
- Rama: la que te da delega. Base: `integracion`. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Python en `~/venv`, Go en `~/go-sdk/bin` y modelos en `~/hf`. Sin GPU, sin S3 y sin red salvo la
  API de Claude.

## Tope
- ≤ 75 min de reloj · ≤ 5 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 8 líneas:
- rama y sha;
- la prueba en seco;
- qué sustituyo para lanzar.
