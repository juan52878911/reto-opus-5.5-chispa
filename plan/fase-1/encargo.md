# Encargo: Chispa fase 1, datos y evaluación (primer tramo)

Acordado con Juan el 2026-10-26 (plan aprobado, G1 con los criterios (a)-(d)). Arranca el 2026-10-27
con D2 = e5-small propio y D3 = e5-small (provisional hasta medir en el i7).

## Objetivo y entregable de este tramo
Las tres piezas de la fase 1 que no necesitan API ni GPU, en paralelo en kindling:
- **T1.1** conversor de datasets públicos al esquema `model/esquema.md`, con licencia por fila;
- **T1.2** el arnés `chispa eval` con todas las métricas, probado con cifras conocidas;
- **T1.4** la tarea «orquestar herramientas» (System One): catálogo y 300 casos de test.

Fuera de este tramo, y con su propio brief más adelante: T1.3 (corpus sintético, API de Haiku),
T1.6 (etiquetas de Qwen, AWS), T1.5 (etiquetado humano) y T1.7 (líneas base frente a Jev).

## Criterio de aceptación (congelado)
- T1.1: `python -m model.datos.convertir --salida <dir>` produce JSONL válidos contra el esquema para
  cada fuente disponible en `~/hf`; un test falla si una fila `uso_comercial: false` cae en train o
  dev (caso XNLI, CC-BY-NC); un test por fuente con un fixture de ≤ 20 filas en el repo.
  Fuentes del plan: MASSIVE es, Banking77, CLINC150 (con `oos` → `escalate`), HateCheck-ES,
  deepset/prompt-injections, XNLI es. NECOS-TOX solo si se encuentra; si no, «no disponible».
- T1.2: `python -m model.evaluacion.chispa_eval --datos <jsonl> --pred <jsonl>` imprime y guarda en
  JSON: exactitud, macro-F1, ECE (15 cubos), Brier, cobertura a precisión 0,95 y 0,99, AUROC del
  escalate, latencia p50/p99 (si hay `ms`) y deriva entre dos predicciones; ASR de la Arena con un
  adaptador al formato de `arena/`. Cada métrica con un test de cifras calculadas a mano. Adaptador de
  JevBench detrás de una interfaz, probado con un fixture (la API de Jev no es alcanzable desde la VM).
- T1.4: catálogo de ≥ 30 herramientas, MCP y agentes con descripción en español; ≥ 300 casos de test
  escritos a mano o por plantilla revisada, ≥ 15 % fuera de ámbito con `etiqueta: escalate`, sin
  texto repetido con `model/sondeo/`; e5-small + kNN-8 y kNN-32 medidos sobre ellos con `chispa eval`
  (o, si T1.2 no está aún, con un script propio que se reemplaza al integrar).
- Todo: `make test` y `make smoke` en verde, más los tests de Python de cada pieza con la biblioteca estándar
  (`python -m unittest discover -s model -t .`; el dorado actual no trae pytest).

## Línea base
la rama `claude/chispa-plan-83616c`.

## Presupuesto
- Reloj: ≤ 8 h de workers. Cuenta: ≤ 25 $ (`delega spend`). Cómputo externo de pago: 0 USD.
- Por pieza: ≤ 3 h y ≤ 8 $.

## Fuera de alcance
Entrenar, AWS, la API de Haiku o Jev, cambiar `arena/contracts/` o `model/esquema.md`.

## Decisiones que son de Juan
Gasto extra, datos de clientes reales, incluir datasets con licencia dudosa en train.

## Cambios
| Fecha | Qué cambió | Por qué | OK de Juan |
|---|---|---|---|
| 2026-10-27 | T1.5: el etiquetado humano se sustituye por datasets de libre uso con varios anotadores (listón humano); el lote T1.5b queda aparcado. Se añaden datos de libre uso en español, PQRS de datos.gov.co y metaentrenamiento con tasksource-jev filtrado a `commercial`. Profesor adicional: bge-m3-zeroshot-v2.0-c (MIT) | Juan no etiqueta; la nota de la bóveda `01-investigacion/07-datos-de-libre-uso.md` lo justifica | «Perfecto entonces usemos esto, continua sin mi supervision…» (vía la sesión principal) |
