# Encargo: Chispa fase 0, repo y medidas

Acordado con Juan el 2026-10-26 (plan aprobado en el artifact «Plan de Chispa»: D1 monorepo, D2 base
abierta solo si gana, D3 e5-small, D4 Qwen + Haiku solo para textos, G1 con los criterios (a)-(d)).

## Objetivo y entregable
Una tabla, guardada en `model/informes/fase-0.md`, que decide dos cosas: (1) si Chispa parte de un
modelo abierto (Julia-1, THX-01, GLiClass, Laya) o de e5-small propio, y (2) qué codificador usa.
Más el monorepo montado con la Arena dentro y sus pruebas en verde.

## Criterio de aceptación (congelado)
- Monorepo: `arena/` conserva el historial (`git log --follow` sobre un fichero movido muestra los
  commits anteriores); `make test` y `make smoke` en verde desde la raíz.
- Codificadores (T0.3): e5-small y mmBERT-small, fp32 e int8, con y sin vocabulario podado, más
  potion-multilingual-128M como capa static: p50/p99 a 16, 64 y 256 tokens (≥ 200 repeticiones, 1 hilo
  y 4 hilos), RSS pico, tamaño en disco y arranque en frío, en la microVM x86.
- Modelos abiertos (T0.4): sobre el mismo conjunto de sondeo congelado, por modelo y tarea:
  macro-F1, ECE (15 cubos), p99 y RSS en CPU, frente a e5-small con kNN (8 y 32 ejemplos por clase).
- Regla de D2: se parte de un abierto solo si saca ≥ 5 puntos de macro-F1 de media en las tareas en
  español **y** su p99 cabe en 50 ms en x86. Si no, e5 propio.
- Regla de D3: mmBERT-small solo si gana ≥ 3 puntos sin pasar de 50 ms p99.
- El conjunto de sondeo se congela con `shasum -a 256 model/sondeo/*.jsonl` antes de evaluar nada, y
  el hash va en el informe.

## Línea base
la rama `claude/chispa-plan-83616c`.

## Presupuesto
- Reloj: ≤ 8 h de workers. Cuenta: ≤ 25 $ (`delega spend`). Cómputo externo de pago: 0 USD.
- Por pieza: ≤ 4 h y ≤ 10 $.

## Fuera de alcance
Entrenar nada, AWS, el móvil, la API de Jev, generar el corpus sintético grande (fase 1).

## Decisiones que son de Juan
Gasto extra, cambiar los umbrales de D2/D3, datos de clientes reales.

## Cambios
| Fecha | Qué cambió | Por qué | OK de Juan |
|---|---|---|---|
