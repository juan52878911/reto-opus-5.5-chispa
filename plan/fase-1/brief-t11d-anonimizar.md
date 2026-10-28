# T1.1d Anonimizador de PQRS endurecido, y ALIA solo para test hasta que Juan decida

Encargo: `plan/fase-1/encargo.md`. Parte de lo que dejó T1.1c en `model/datos/`: `anonimizar.py`,
`pqrs_comun.py`, `informe_pqrs.py` y `libres.py`.

## Hipótesis
- En las PQRS de datos.gov.co, los nombres que siguen visibles van casi todos en MAYÚSCULAS, donde
  fallan las listas y la heurística de mayúscula inicial.
- Comparar en forma normalizada (sin tildes, insensible a mayúsculas), añadir reglas para tramos en
  mayúsculas de 2 a 4 palabras con un nombre o apellido de la lista, y revisar los contextos «C.C.»,
  «identificado con», «el ciudadano/la ciudadana», «firma», «atentamente» y «cordialmente», deja
  ≤ 1 fila con nombre visible en 300.
- Se refuta si, al revisar 300 filas al azar de las tres fuentes de texto libre, quedan más.

## Terminado cuando
- Anonimizador:
  - `anonimizar.py` cubre los casos de la hipótesis;
  - tests con frases inventadas en mayúsculas, con tildes y con nombres compuestos;
  - **no rompe** el sentido: los nombres de entidades («ALCALDÍA DE FLANDES», «SECRETARÍA DE SALUD»)
    se quedan, con una lista de exclusión y un test.
- Revisión:
  - `informe_pqrs.py` saca una muestra de 300 (semilla fija) y la revisa con la heurística más una
    pasada manual tuya;
  - en el informe pones **solo recuentos** (cuántas filas aún tienen nombre, por fuente y por patrón),
    **nunca** el texto.
- ALIA:
  - el conversor de `odio_alia` marca `uso_comercial: false` y manda todo a `test`. Sus etiquetas son
    una fusión de LLMs (Apertus, Gemma, MiniMax) con términos que pueden restringir entrenar con ellas,
    y es decisión de Juan;
  - la muestra humana de 3.000 sigue en test;
  - anótalo en `LICENCIAS.md` como «pendiente de decisión».
- PQRS: añade en `LICENCIAS.md` que CC BY-SA 4.0 obliga a atribuir. Si los datos convertidos se
  redistribuyen, van con la misma licencia. Lo que eso implique para el modelo entrenado queda como
  pregunta abierta para Juan.
- `python -m unittest discover -s model -t .` y `make test` en verde. Corre también `make smoke`:
  - si falla por «no contestó /health» en un detector de la Arena, repítelo una vez;
  - si vuelve a fallar, corre `git stash`-free: compara contra la línea base con `git worktree add`
    del sha base y `make smoke` ahí;
  - informa si falla también sin tus cambios.
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- Solo `model/datos/`.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.
- Datos reales nunca a git ni al informe.

## Entorno
- `source ~/.profile`. Python en `~/venv`, datos en `~/hf` y `~/datos/datosgov`. No hay red.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.

## Tope
- ≤ 90 min de reloj · ≤ 5 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 15 líneas: qué cambiaste, rama y sha, recuentos de la revisión de 300 por
fuente, el resultado de `make smoke` con y sin cambios, y qué recomiendas.
