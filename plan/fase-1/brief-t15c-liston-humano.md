# T1.5c Listón humano con datasets de varios anotadores (sustituye al etiquetado a mano)

Encargo: `plan/fase-1/encargo.md` (ver la sección de cambios del 2026-10-27). Esquema: `model/esquema.md`, congelado.
El criterio de la fase era «300 ejemplos de test por tarea, etiquetados por dos personas, con
κ ≥ 0,7». Ahora se cumple con datasets públicos que ya traen la etiqueta de cada anotador.

## Hipótesis
- MultiPICo, la muestra humana de ALIA, toxicity-protests-ES y toxicity-Constitution-ES, y GoEmotions
  `raw` traen etiquetas por anotador. De ellas salen: un test con `etiqueta` por mayoría, `blanda` con
  la distribución de los anotadores y el acuerdo entre humanos (κ o α de Krippendorff). Ese acuerdo es
  el techo contra el que se mide a Chispa.
- Se refuta si alguna fuente no publica las etiquetas individuales.

## Terminado cuando
- `model/liston/` con un conversor por fuente al esquema:
  - `split: test`;
  - `etiqueta` = mayoría, con empate → la clase de menor índice, documentado;
  - `blanda` = proporción de anotadores por clase;
  - un campo extra `anotadores: n` en la fila. Es un campo opcional nuevo: **no cambies
    `model/esquema.md`**; añádelo y pon una nota en el README para que el orquestador lo apruebe.
  Fuentes:
  - **MultiPICo**: solo el subconjunto en español, tarea `ironia`, noul. Guarda la variedad de
    español del anotador si viene (Colombia, México, Argentina, España) para un desglose.
  - **ALIA**: solo las filas con 3 anotadores humanos, tarea `odio`.
  - **toxicity-protests-ES y toxicity-Constitution-ES**: tarea `toxicidad`, 2 codificadores.
  - **GoEmotions `raw`**: está en inglés, así que mide el acuerdo pero márcalo `idioma: en`.
    Úsalo solo si el texto en español de `go_emotions-es-mt` se puede unir por id; si no, dilo.
- `model/liston/acuerdo_humano.py` usa `model/etiquetado/acuerdo.py` donde sirva. Calcula por
  tarea el κ de Fleiss o el α de Krippendorff, y el acuerdo medio de un anotador con la mayoría de
  los demás (el «techo humano» de exactitud). Lo escribe en `model/liston/README.md`.
- Licencias en `model/liston/LICENCIAS.md`, leídas de la tarjeta. Si no son comerciales, igual valen
  para test, con `uso_comercial: false`.
- Tests con `unittest` y fixtures inventados (mayoría, empate, blanda que suma 1, κ en casos conocidos).
- `python -m unittest discover -s model -t .`, `make test` y `make smoke` en verde.
- Parada: si una fuente falla 2 veces, márcala y sigue.

## Zona
- Solo `model/liston/`. **No tocar**: `model/esquema.md`, `model/etiquetado/` (solo usar), otras carpetas.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge. Las salidas convertidas,
  a `/tmp`, nunca a git.

## Entorno
- `source ~/.profile`. Python en `~/venv`, datos en `~/hf`. No hay red salvo la API de Claude.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.

## Tope
- ≤ 120 min de reloj · ≤ 6 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 15 líneas: qué cambiaste, rama y sha, una tabla por tarea (filas,
anotadores por fila, κ o α, techo humano), qué no se pudo y qué recomiendas.
