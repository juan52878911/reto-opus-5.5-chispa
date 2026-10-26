# T0.2 + T0.4 Conjunto de sondeo en español y comparación de los modelos abiertos contra e5

Encargo: `plan/fase-0/encargo.md` (criterio de aceptación congelado; no lo cambies tú).

## Hipótesis
- En español y en CPU, ningún modelo abierto (Julia-1, THX-01, GLiClass, Laya) saca ≥ 5 puntos de
  macro-F1 sobre e5-small con kNN a 32 ejemplos por clase sin pasar de 50 ms p99. Se refuta midiendo.

## Terminado cuando
1. **Sondeo (T0.2)**: `model/sondeo/*.jsonl`, ≥ 200 ejemplos de test por tarea, cada fila con
   `texto`, `opciones`, `etiqueta`, `tarea`, `fuente` y `licencia`:
   - intención: `mteb/amazon_massive_intent` (es), 10-15 intenciones;
   - toxicidad: `Paul/hatecheck-spanish` (noul);
   - WhatsApp de comercio: casos de la Arena (`arena/` o la raíz, según el estado del repo; lee
     los JSON con un script, no los cargues en contexto);
   - orquestar herramientas: 200 peticiones en español colombiano que eligen entre ~15 herramientas
     o agentes con su descripción, un 15 % sin herramienta adecuada (etiqueta `escalate`). Escríbelas
     tú con variedad de registro; márcalas `fuente: sintetico-worker`.
   - Aparte, un conjunto de entrenamiento para kNN (8 y 32 por clase) sin solaparse con el test.
   Congela con `shasum -a 256 model/sondeo/*.jsonl > model/sondeo/SHA256` y commitea **antes** de evaluar.
2. **Comparación (T0.4)**: `model/eval0/` con un script por modelo y `model/eval0/resultados.md`:
   por modelo y tarea, macro-F1, ECE (15 cubos), p50/p99 por ejemplo y RSS pico en CPU (4 hilos).
   Modelos en `~/hf`: e5-small + kNN (8 y 32), `knowledgator/gliclass-modern-base-v3.0`,
   `SupersonicLabs/Julia-1`, `doofz/THX-01`, `convaiinnovations/laya-multilingual`. Lee el README
   de cada uno para usarlo como su autor indica (zero-shot con las opciones como etiquetas).
   Licencia de cada modelo anotada.
- Un modelo que no carga o no cabe en 4 GB de RAM tras 2 intentos se marca «no medido» con el error.
- Si vas por la mitad del tope sin el sondeo congelado, avisa con `milestone`.

## Zona
- Solo `model/sondeo/` y `model/eval0/`. **No tocar** nada más.
- No cargues en contexto `data/`, `models/` ni `ledger.jsonl` (CLAUDE.md del repo): léelos con scripts.
- Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Python en `~/venv`, modelos y datos en `~/hf` (sin red salvo la API de Claude).
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan (está en tu contexto de delega).

## Tope
- ≤ 220 min de reloj · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤15 líneas: qué cambiaste, rama y sha, qué verificaste ejecutando (con
números), qué quedó sin verificar y qué recomiendas a continuación.
