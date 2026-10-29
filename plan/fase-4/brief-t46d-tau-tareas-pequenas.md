# T4.6d τ de L2c en tareas pequeñas: sin elegirlo sobre dev con < 500 filas, y con tope

## Antecedentes
T4.6c (`sdk/python/chispa/conjunta.py`, `elegir_tau`) fija el τ sobre las filas de validación cuando hay ≥ `MIN_VALID`
(50). En spam e injection de la Arena hay 152 filas de validación, todas correctas y muy confiadas, así que τ queda en
0,99. En test, que sale de plantillas nunca vistas, la cascada escala el 84 % en spam y el 24 % en injection
(`server/deploy/resultados/abstencion-20261028-c/`).

Juan fijó para T2.4 que las tareas con ≤ 500 filas no se calibren. Se aplica la misma idea.

## Hipótesis
- `MIN_VALID = 500`: con menos filas, se usa el camino fuera de pliegue + margen + suelo que ya existe.
- Un tope de τ, `--tope-tau`, 0,9 por defecto, **solo en ese camino**.

Con eso, spam e injection escalan ≤ 20 % de tráfico normal sin que el ASR de la Arena pase de 0,15, y clinc150 y massive
no cambian, porque tienen ≥ 2.000 filas de dev. Se mide en AWS.

## Terminado cuando
- `sdk/python/chispa/conjunta.py`: `MIN_VALID = 500` y el tope, más `--tope-tau` en `cli.py`. El informe de `chispa train`
  dice si se aplicó el tope.
- Tests actualizados y uno nuevo:
  - con validación de 152 filas, todas correctas y confiadas, y fuera de pliegue igual, el τ resultante es ≤ 0,9;
  - con ≥ 500 filas, el camino de validación no cambia.
- `make test` y `make smoke` en verde, o sus recetas a mano si no hay `make`. Corre también los tests de `sdk/python` después
  del último cambio.
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- `sdk/python/**`.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- Host Linux. Si te hacen falta, Go y el venv están en `~/orquestador/herr` (`. ~/orquestador/herr/env.sh`).
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.

## Tope
- ≤ 30 min de reloj · ≤ 3 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 6 líneas:
- rama y sha;
- los tests.
