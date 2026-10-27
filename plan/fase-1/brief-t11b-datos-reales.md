# T1.1b Correr el conversor sobre los datos reales del dorado nuevo

Encargo: `plan/fase-1/encargo.md` (criterio de aceptación congelado; no lo cambies tú).
Sigue el trabajo de T1.1, que está en tu rama: `model/datos/` ya tiene un conversor por fuente,
probado solo con fixtures para Banking77, CLINC150, deepset y XNLI.

## Hipótesis
- El dorado `personal-chispa` (rehecho en `5404117`) trae en `~/hf` `PolyAI/banking77`,
  `clinc/clinc_oos`, `deepset/prompt-injections` y `facebook/xnli` (solo `es/`). El T1.1 anterior no
  los encontró: o corrió en un dorado viejo, o los buscó en otra ruta. Se refuta en 1 minuto con
  `ls ~/hf/hub` y `find ~/hf -maxdepth 3 -name 'datasets--*'`.

## Terminado cuando
- Primero, en el informe: la lista de `datasets--*` y `models--*` en `~/hf/hub`, con su tamaño (`du -sh`).
- Para cada fuente presente: `python -m model.datos.convertir --salida /tmp/conv --fuentes <f>` corre
  sin error; arregla los nombres de clase y las descripciones que no coincidan con los datos reales
  (Banking77: 77 clases, CLINC150: 150 + `oos` → `escalate`) y lee la licencia de la tarjeta (README)
  que trae el snapshot. Filas por fuente y split en una tabla.
- Si una fuente no está en `~/hf`: dilo y no la inventes.
- Añade `__pycache__/` al `.gitignore` de la raíz (solo esa línea).
- `python -m unittest discover -s model -t .`, `make test` y `make smoke` en verde.
- Parada: si una fuente falla 2 veces, «no convertida» con el error y sigues.

## Zona
- `model/datos/` y la línea de `.gitignore`. **No tocar**: `model/esquema.md`, `model/evaluacion/`,
  `arena/contracts/`, otras carpetas. Las salidas convertidas no van a git (van a `/tmp`).
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Python en `~/venv`, datos en `~/hf` (sin red salvo la API de Claude).
- `data/` y `models/` no viajan con el repo; si `make smoke` los necesita, `make dataset` primero.
- Línea base: la rama de T1.1 en el sha con el que te lanzan.

## Tope
- ≤ 60 min de reloj · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤15 líneas: qué cambiaste, rama y sha, qué verificaste ejecutando (con
números: filas por fuente y split), qué quedó sin verificar y qué recomiendas a continuación.
