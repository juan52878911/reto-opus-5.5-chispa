# T1.1 Conversor de datasets públicos al esquema tipado de Chispa

Encargo: `plan/fase-1/encargo.md` (criterio de aceptación congelado; no lo cambies tú).
Esquema: `model/esquema.md` (congelado; si algo no encaja, avisa con `question`, no lo cambies).

## Hipótesis
- Cada fuente se puede llevar al esquema con una función pequeña por fuente y una capa común que
  valida filas y aplica la regla de licencias. Se refuta si alguna fuente no tiene licencia clara o
  no encaja en `choice`/`noul`/`score`: entonces se marca y se sigue.

## Terminado cuando
- Paquete `model/datos/` con `convertir.py` (`python -m model.datos.convertir --salida <dir>
  [--fuentes a,b]`), un módulo por fuente y `validar.py` (valida contra el esquema y la regla de
  `uso_comercial`).
- Fuentes: MASSIVE es (`mteb/amazon_massive_intent`, ya en `~/hf`), HateCheck-ES
  (`Paul/hatecheck-spanish`, ya en `~/hf`), Banking77, CLINC150 (`oos` → `escalate`),
  deepset/prompt-injections, XNLI es (CC-BY-NC: `uso_comercial: false`, solo `test`). NECOS-TOX: busca
  si está en `~/hf`; si no, «no disponible» en el informe.
- **La imagen de esta VM puede no traer aún Banking77, CLINC150, deepset ni XNLI** (llegan en el
  próximo dorado). Para cada fuente ausente: escribe el conversor contra su formato documentado y un
  fixture de ≤ 20 filas inventadas con la misma forma en `model/datos/fixtures/`; el conversor real se
  corre después. Di en el informe cuáles corriste de verdad y cuántas filas salieron por split.
- `descripciones` en español para todas las clases (Banking77 y CLINC están en inglés: la definición
  va en español, el `texto` se queda en inglés con `idioma: en`).
- Tests con `unittest` en `model/datos/tests/`: uno por fuente sobre su fixture, uno que **falla** si
  una fila NC cae en train o dev, uno de reparto por `plantilla` sin fugas.
- `python -m unittest discover -s model -t .`, `make test` y `make smoke` en verde.
- Licencias: escribe en `model/datos/LICENCIAS.md` la licencia de cada fuente y de dónde la sacaste
  (la tarjeta del dataset en `~/hf`). Si una no está clara: `uso_comercial: false`.
- Parada: si una fuente falla 2 veces, se marca «no convertida» con el error y sigues.

## Zona
- Solo `model/datos/`. **No tocar**: `model/esquema.md`, `arena/contracts/`, `model/sondeo/`, otras
  carpetas de `model/`. No metas salidas grandes en git: solo código, fixtures y `LICENCIAS.md`.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Python en `~/venv`, datos y modelos en `~/hf` (sin red salvo la API de Claude).
- `data/` y `models/` no viajan con el repo; si `make test` los necesita, `make dataset` primero.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.

## Tope
- ≤ 150 min de reloj · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤15 líneas: qué cambiaste, rama y sha, qué verificaste ejecutando (con
números: filas por fuente y split), qué quedó sin verificar y qué recomiendas a continuación.
