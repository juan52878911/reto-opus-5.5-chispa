# T4.6c τ de L2c desde dev, o fuera de pliegue con margen

## Antecedentes
T4.6b (`server/deploy/resultados/abstencion-20261028-tau/LEEME.md`) fija el τ de L2c con la cabeza conjunta fuera de
pliegue sobre train, en `sdk/python/chispa/` (`--precision-objetivo`, campo `tau_l2c` de CALIB):
- **massive:** precisión real 0,949 frente a 0,950 estimada. Bien.
- **clinc150:** la estimación fuera de pliegue da 0,953 aceptándolo todo, así que τ = 0,128. En test la precisión es
  0,859: el train fuera de pliegue es optimista. Juan fijó la abstención máxima en 20 % y la precisión objetivo es 0,95.

## Hipótesis
- H1: si `chispa train` recibe filas de validación (`--validacion <jsonl>`; en el arnés de AWS, el split dev de
  `model.datos.convertir`) y elige el τ sobre ellas con la cabeza ya entrenada en todo el train, la precisión en test queda
  a ≤ 0,02 de la de dev en clinc150 y massive.
- H2: si no hay validación, basta un margen conservador: el τ de precisión `objetivo + m`, con `m` de 0,02 por defecto,
  y un suelo de τ (por defecto, el τ que deja fuera el 5 % fuera de pliegue). Evita el caso de clinc150 sin romper
  massive. Mídelo con los fixtures y explica la elección.
- Se refuta en AWS con `server/deploy/abstencion/aws.sh`, que pasará `--validacion`.

## Terminado cuando
- `sdk/python/chispa/`:
  - `--validacion` y el margen y suelo de H2;
  - el informe de `chispa train` dice qué método usó y la precisión y cobertura esperadas.
- `server/deploy/abstencion/aws.sh`:
  - pasa a `chispa train` el dev de cada tarea si existe; en la Arena, un 20 % reservado del train;
  - el informe lleva una columna con la precisión estimada frente a la real.
- Tests en Python. `make test` y `make smoke` en verde **después** del último cambio. Parada: si algo falla 2 veces,
  márcalo y para.

## Zona
- `sdk/python/**` y `server/deploy/abstencion/**`.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Go en `~/go-sdk/bin` y Python en `~/venv`. Sin GPU y sin red salvo la API de Claude.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.

## Tope
- ≤ 60 min de reloj · ≤ 4 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 8 líneas:
- rama y sha;
- el método;
- los tests;
- qué sustituyo para lanzar `aws.sh`.
