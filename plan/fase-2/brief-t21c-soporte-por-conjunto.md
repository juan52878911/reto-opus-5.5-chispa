# T2.1c Soporte de L2 agrupado por conjunto, no por el campo `tarea`

## Antecedentes
`model/l2/evaluar.py` (`train_por_tarea`) y `model/l2/entrenar.py` (`SoporteEval(por_tarea, …)` en dev, y los episodios)
agrupan el train por el campo `tarea` de cada fila. Como massive y clinc150 tienen los dos `tarea = "intencion"`, el
soporte de uno mezcla filas del otro. El efecto en las cifras publicadas está medido y es menor de 0,5 puntos
(`model/l2/resultados/t22c-conjunta/LEEME.md`), pero hay que corregirlo antes de la próxima ronda de entrenamiento.
`model/l2/conjunta.py` ya lo hace bien (`cargar_tareas`): úsalo de referencia.

## Hipótesis
Agrupar por conjunto (el fichero de origen o el prefijo del `id`, lo que sea más robusto: decídelo y justifícalo) separa
massive y clinc150 sin cambiar nada en las tareas que no comparten `tarea`. Se refuta si algún test existente cambia de
resultado en una tarea que no comparte `tarea`.

## Terminado cuando
- `train_por_tarea` (o una función nueva que la sustituya en todos sus usos) devuelve claves por conjunto: `massive`,
  `clinc150`, `hatecheck`, `inyecciones` y `herramientas`, las mismas que `conjuntos_test`. Los episodios de `datos.py`
  usan la misma agrupación si hoy agrupan por `tarea`.
- Un test con fixtures en el que dos conjuntos comparten `tarea` comprueba que el soporte de cada uno solo trae filas suyas.
- `conjunta.py` pasa a usar la función común, si eso no cambia sus salidas. Su test lo comprueba.
- `python -m unittest discover -s model -t .`, `make test` y `make smoke` en verde.
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- `model/l2/evaluar.py`, `model/l2/entrenar.py`, `model/l2/datos.py`, `model/l2/conjunta.py` y `model/l2/tests/**`.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Python en `~/venv`. Sin GPU y sin red salvo la API de Claude.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.
- No vuelques datos en el contexto.

## Tope
≤ 45 min de reloj · ≤ 3 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
≤ 8 líneas:
- rama y sha;
- qué clave usaste y por qué;
- los tests.
