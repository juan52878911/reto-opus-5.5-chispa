# T1.4 Tarea «orquestar herramientas» (System One): catálogo y 300 casos de test

Encargo: `plan/fase-1/encargo.md` (criterio de aceptación congelado; no lo cambies tú).
Esquema: `model/esquema.md` (congelado).

## Hipótesis
- Con descripciones en español bien escritas, e5-small + kNN-32 elige bien la herramienta en lo
  común (≥ 0,8 de macro-F1) pero falla en el fuera de ámbito: el AUROC del escalate queda bajo
  (< 0,8). Se refuta midiendo sobre el test nuevo.

## Terminado cuando
- `model/herramientas/catalogo.json`: ≥ 30 entradas `{id, tipo: herramienta|mcp|agente, descripcion}`
  en español, de lo que usan los agentes de Juan: kindling (microVM), chrono (logs e historia de git),
  la bóveda de Obsidian, el navegador, subagentes (explorar, planear, revisar), correo, agenda, Drive,
  Slack, GitHub (PR, issues, CI), terminal, búsqueda web, delega, AWS, más `escalate` («ninguna
  sirve: preguntar a la persona»). Sin dos descripciones que se puedan confundir sin leer el mensaje.
- `model/herramientas/test.jsonl`: ≥ 300 filas en el esquema (`tarea: herramientas`, `tipo: choice`,
  `opciones` = todos los ids del catálogo), escritas a mano o por plantillas que revises una a una;
  ≥ 15 % con `etiqueta: escalate` (peticiones plausibles que ninguna herramienta cubre, y ambiguas);
  español colombiano informal además del neutro; sin texto repetido con `model/sondeo/`; `plantilla`
  rellena; `licencia: "propia (Chispa)"`, `uso_comercial: true`, `fuente: "chispa T1.4"`.
- `model/herramientas/train.jsonl`: 32 por clase para kNN, sin texto ni plantilla compartida con el test.
- `model/herramientas/medir.py`: e5-small (`~/hf`, prefijo `query: `) + kNN-8 y kNN-32, escribe
  predicciones en el formato del esquema y mide macro-F1, exactitud y AUROC del escalate. Resultado en
  `model/herramientas/README.md`. (El arnés `chispa eval` se está escribiendo a la vez en otra rama:
  calcula tú esas tres métricas con sklearn; se cambiará al integrar.)
- Tests con `unittest` en `model/herramientas/tests/`: el JSONL valida contra el esquema, ≥ 15 % de
  escalate, sin solapes con el sondeo ni entre train y test.
- `python -m unittest discover -s model -t .`, `make test` y `make smoke` en verde.
- Parada: si la medida falla 2 veces, entrega el conjunto sin medir y dilo.

## Zona
- Solo `model/herramientas/`. **No tocar**: `model/esquema.md`, `model/sondeo/` (solo leer), otras carpetas.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Python en `~/venv`, modelos en `~/hf` (sin red salvo la API de Claude).
- `data/` y `models/` no viajan con el repo; si `make smoke` los necesita, `make dataset` primero.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.

## Tope
- ≤ 150 min de reloj · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤15 líneas: qué cambiaste, rama y sha, qué verificaste ejecutando (con
números), qué quedó sin verificar y qué recomiendas a continuación.
