# Muestras para etiquetar

Estado T1.5b: **sin lote-1.jsonl**; la hipótesis queda refutada y el trabajo se detiene.

Filas de test disponibles (semilla 7, 300 por tarea pedidas):

| tarea | test | clases | resultado |
|---|---|---|---|
| whatsapp_comercio | 213 | 4 (52-54 c/u) | menos de 300: refutada |
| intencion | 390 | 13 (30 c/u) | sin `id`: `preparar.py` falla con KeyError |
| herramientas | 368 | escalate 58 + 30 clases de 10 | ok |
| toxicidad (HateCheck-ES) | 361 | true 257, false 104 | ok |
| pqrs | no hay test en el repo | - | no incluida |

Causas: `model/sondeo/*.jsonl` no trae `id` (lo exige `estratificar`), y `whatsapp_comercio` solo tiene 213 filas.
Hace falta decidir: añadir `id` a los sondeos, o bajar `--por-tarea` para esa tarea (o regenerar con más filas).
