# T2.7 Cascada L0 → L1 → L2 frente al listón (2026-10-28-seco)

Reproducir: `python -m model.cascada.capas …` y `python -m model.cascada.informe …` (ver `model/cascada/aws/arranque.sh`).

**Prueba en seco, sin L2**: no hay predicciones de L2 en esta máquina (están en S3). Solo L0 → L1-zs y L0 → L1-proto, con L1 como última capa (responde siempre). Las cifras de las cascadas con L2 se miden en la instancia de AWS.

## Cómo se midió
- Test de `model.datos.convertir` (MASSIVE es, CLINC150 con `oos`→`escalate`, HateCheck-ES, deepset) y `model/herramientas/test.jsonl`. Los conjuntos del listón humano (ALIA, GoEmotions, MultiPICo, toxicidad Constitución/protestas) **quedan fuera**: no tienen train para L0.
- Capas: L0 = TF-IDF de caracteres + regresión logística (32 por clase, `model/lineas_base`); L1-zs = lo que hace `server/decide/l1.go` (coseno de potion con «pregunta · opción · descripción», T = 0,05; noul σ(4·cos−2), θ = 0,5); **L1-proto = capa candidata, no la del servidor**: prototipos por clase (media normalizada del train completo), softmax(coseno/0,05); L2 = predicciones ya hechas de T2.1b (`b`) y T2.2 (`c`), con soporte (`-sop`) y sin él.
- Cascada: una capa responde si su confianza top-1 es > 0 y ≥ τ; si no pasa a la siguiente; la última responde siempre.
- τ por capa y tarea, **sin mirar el fragmento que se evalúa**: validación cruzada a 2 pliegues sobre test (hash del `id`, semilla 0); se ajusta en un pliegue y se evalúa en el otro. Las cifras de cascada son la unión de los dos pliegues evaluados.
- Puntos de operación: **calidad** (τ que maximiza el macro-F1 en el pliegue de ajuste) y **rápida** (mayor cobertura de las capas tempranas con precisión ≥ 0,95 sobre lo que aceptan, ≥ 5 aceptadas).
- Listón = 0,95 × máx(L0, e5 kNN-32, maestro Qwen). L0 y kNN-32 salen de `model/lineas_base/resultados.json` (las cifras de `informe.md`; coinciden con `model/l2/resultados/ronda3-t22/delta.md`). **Las cifras del maestro Qwen por tarea no están en el repo**: se da `maestro n/d` y el listón sale de L0 y kNN-32; en `ronda3-t22/LEEME.md` el listón coincide con 0,95 × L0 en massive, CLINC y herramientas.
- Latencia esperada en el i7 (no medida aquí): coste fijo por capa, suma de las capas recorridas. Fuentes: L0 ≈ 6 µs/op, `go test -bench L0` sin HTTP, 1 hilo (`server/README.md`); L1 166 µs, p99 a 64 tokens (66 reales), potion en Go, 1 hilo (`model/bench/i7/resultados.md`); L1-proto cuesta lo mismo: una multiplicación por prototipos precalculados en lugar de por los vectores de opción; L2 30,6 ms, mediana de los p99 a 64 tokens, e5-small int8 podado, 1 hilo (`model/bench/i7/resultados.md`).
- Oráculo = la mejor capa por fila (acierta si alguna capa de la cascada acierta): techo, no alcanzable.
- Hipótesis (T2.7): cumple si pasa el listón en ≥ 4 de 5 tareas; se refuta si la cascada no supera a su mejor capa sola en ninguna tarea o pierde más de 1 punto frente a ella en ≥ 2.

## massive (n = 2974, 59 clases)

Listón: 0,95 × máx(L0 0,678, kNN-32 0,635, maestro n/d) = **0,644**.

| capa sola | n | macro-F1 | exactitud | ms/consulta |
|---|---|---|---|---|
| L0 | 2974 | 0,678 | 0,698 | 0,006 |
| L1-zs | 2974 | 0,406 | 0,435 | 0,166 |
| L1-proto | 2974 | 0,639 | 0,659 | 0,166 |

| cascada | n | mejor capa | oráculo | calidad F1 | pasa | % por capa | ms medio | p99 ms | rápida F1 | pasa | % por capa | ms medio | p99 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| L0 → L1-zs | 2974 | 0,678 | 0,735 | 0,678 | sí | 100 % / 0 % | 0,006 | 0,006 | 0,460 | no | 23 % / 77 % | 0,133 | 0,172 |
| L0 → L1-proto | 2974 | 0,678 | 0,763 | 0,681 | sí | 86 % / 14 % | 0,030 | 0,172 | 0,651 | sí | 23 % / 77 % | 0,133 | 0,172 |

## clinc150 (n = 5500, 151 clases)

Listón: 0,95 × máx(L0 0,811, kNN-32 0,794, maestro n/d) = **0,771**.

| capa sola | n | macro-F1 | exactitud | ms/consulta |
|---|---|---|---|---|
| L0 | 5500 | 0,811 | 0,754 | 0,006 |
| L1-zs | 5500 | 0,444 | 0,429 | 0,166 |
| L1-proto | 5500 | 0,756 | 0,703 | 0,166 |

| cascada | n | mejor capa | oráculo | calidad F1 | pasa | % por capa | ms medio | p99 ms | rápida F1 | pasa | % por capa | ms medio | p99 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| L0 → L1-zs | 5500 | 0,811 | 0,843 | 0,811 | sí | 100 % / 0 % | 0,006 | 0,006 | 0,719 | no | 59 % / 41 % | 0,075 | 0,172 |
| L0 → L1-proto | 5500 | 0,811 | 0,860 | 0,811 | sí | 87 % / 13 % | 0,027 | 0,172 | 0,795 | sí | 59 % / 41 % | 0,075 | 0,172 |

## herramientas (n = 368, 32 clases)

Listón: 0,95 × máx(L0 0,696, kNN-32 0,632, maestro n/d) = **0,661**.

| capa sola | n | macro-F1 | exactitud | ms/consulta |
|---|---|---|---|---|
| L0 | 368 | 0,696 | 0,693 | 0,006 |
| L1-zs | 368 | 0,398 | 0,397 | 0,166 |
| L1-proto | 368 | 0,595 | 0,603 | 0,166 |

| cascada | n | mejor capa | oráculo | calidad F1 | pasa | % por capa | ms medio | p99 ms | rápida F1 | pasa | % por capa | ms medio | p99 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| L0 → L1-zs | 368 | 0,696 | 0,783 | 0,679 | sí | 90 % / 10 % | 0,023 | 0,172 | 0,495 | no | 21 % / 79 % | 0,136 | 0,172 |
| L0 → L1-proto | 368 | 0,696 | 0,806 | 0,700 | sí | 81 % / 19 % | 0,037 | 0,172 | 0,617 | no | 21 % / 79 % | 0,136 | 0,172 |

## hatecheck (n = 361, 2 clases)

Listón: 0,95 × máx(L0 0,530, kNN-32 0,579, maestro n/d) = **0,550**.

| capa sola | n | macro-F1 | exactitud | ms/consulta |
|---|---|---|---|---|
| L0 | 361 | 0,530 | 0,579 | 0,006 |
| L1-zs | 361 | 0,224 | 0,288 | 0,166 |
| L1-proto | 361 | 0,571 | 0,632 | 0,166 |

| cascada | n | mejor capa | oráculo | calidad F1 | pasa | % por capa | ms medio | p99 ms | rápida F1 | pasa | % por capa | ms medio | p99 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| L0 → L1-zs | 361 | 0,530 | 0,732 | 0,517 | no | 88 % / 12 % | 0,027 | 0,172 | 0,224 | no | 0 % / 100 % | 0,172 | 0,172 |
| L0 → L1-proto | 361 | 0,571 | 0,721 | 0,569 | sí | 28 % / 72 % | 0,126 | 0,172 | 0,571 | sí | 0 % / 100 % | 0,172 | 0,172 |

## inyecciones (n = 116, 2 clases)

Listón: 0,95 × máx(L0 0,835, kNN-32 0,800, maestro n/d) = **0,793**.

| capa sola | n | macro-F1 | exactitud | ms/consulta |
|---|---|---|---|---|
| L0 | 116 | 0,835 | 0,836 | 0,006 |
| L1-zs | 116 | 0,326 | 0,483 | 0,166 |
| L1-proto | 116 | 0,853 | 0,853 | 0,166 |

| cascada | n | mejor capa | oráculo | calidad F1 | pasa | % por capa | ms medio | p99 ms | rápida F1 | pasa | % por capa | ms medio | p99 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| L0 → L1-zs | 116 | 0,835 | 0,948 | 0,775 | no | 67 % / 33 % | 0,060 | 0,172 | 0,706 | no | 39 % / 61 % | 0,108 | 0,172 |
| L0 → L1-proto | 116 | 0,853 | 0,922 | 0,853 | sí | 57 % / 43 % | 0,078 | 0,172 | 0,853 | sí | 39 % / 61 % | 0,108 | 0,172 |

## Resumen por cascada

| cascada — punto | pasan el listón | superan a su mejor capa | pierden > 1 punto | hipótesis |
|---|---|---|---|---|
| L0 → L1-zs — calidad | 3/5 | 0/5 | 3/5 | refutada |
| L0 → L1-zs — rapida | 0/5 | 0/5 | 5/5 | refutada |
| L0 → L1-proto — calidad | 5/5 | 2/5 | 0/5 | cumple |
| L0 → L1-proto — rapida | 4/5 | 0/5 | 3/5 | refutada |
