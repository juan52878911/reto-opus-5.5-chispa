# T4.6b τ de L2c a partir de la cabeza conjunta, en `chispa train --conjunta`

## Antecedentes
T4.6 (`server/deploy/resultados/abstencion-20261028/LEEME.md`): con tráfico normal, la cascada escala entre el 43 % y el
84 %, y lo que contesta tiene una precisión de 0,97–1,0. El objetivo era 0,95. La causa: el τ de L2 sale de `tau_escalate`
de CALIB, que se calibró para L2 solo (T2.4, `model/l2/calibrar.py`), no para la cabeza conjunta que responde de verdad.
Con el τ por tarea que deja la abstención en el 20 %, clinc150 queda en una precisión de 0,949.

## Hipótesis
Fijar en `chispa train --conjunta` el τ de L2c con las probabilidades fuera de pliegue de la cabeza conjunta (el menor τ
cuya precisión en lo aceptado sea ≥ 0,95, sobre las filas fuera de pliegue que ya calcula) deja la abstención con tráfico
normal ≤ 30 % en clinc150 y la precisión de lo contestado en ≥ 0,94. Lo de L0 se queda igual. Se mide en AWS después con
`server/deploy/abstencion/aws.sh`.

## Terminado cuando
- `sdk/python/chispa/`:
  - con `--conjunta`, escribe el τ de L2c en CALIB, o en CONJ si es más limpio sin cambiar el formato, a partir de las
    probabilidades fuera de pliegue, con un objetivo de precisión `--precision-objetivo` (0,95 por defecto);
  - el informe de `chispa train` lo muestra, junto con la cobertura esperada;
  - si hay menos de 200 filas fuera de pliegue, usa el τ de CALIB de siempre y lo avisa.
- `server/decide/`: si el `.chispa` trae ese τ, la cascada lo usa para L2c en lugar de `tau_escalate`. Si no lo trae, todo
  sigue igual.
- Tests en Python y en Go. `make test` y `make smoke` en verde. Parada: si algo falla 2 veces, márcalo y para.

## Zona
- `sdk/python/**` y `server/decide/**`.
- `format/chispa3/**` solo si hace falta un campo nuevo en CONJ; ida y vuelta compatible.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Go en `~/go-sdk/bin` y Python en `~/venv`. Sin GPU y sin red salvo la API de Claude.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.

## Tope
- ≤ 60 min de reloj · ≤ 4 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 8 líneas:
- rama y sha;
- dónde va el τ;
- los tests;
- qué quedó sin verificar.
