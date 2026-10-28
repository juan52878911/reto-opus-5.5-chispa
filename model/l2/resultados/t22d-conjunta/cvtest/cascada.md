# T2.7 Cascada L0 → L1 → L2 frente al listón (cvtest)

Reproducir: `python -m model.cascada.capas …` y `python -m model.cascada.informe …` (ver `model/cascada/aws/arranque.sh`).

**L0c = L0 con todo train** (`pred_l0/` de `model.l2.conjunta`), no la línea base de 32 por clase; «conjunta» = `pred/` de la misma ejecución. Las cascadas L0c → L2-sop, L0c → conjunta y la conjunta sola se comparan con el mismo L0. La conjunta cuesta L0 + L2 (30.7 ms: calcula las dos siempre).

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
| L0c | 2974 | 0,794 | 0,827 | 0,006 |
| conjunta | 2974 | 0,818 | 0,841 | 30,7 |
| L2b-sop | 2974 | 0,632 | 0,662 | 30,6 |

| cascada | n | mejor capa | oráculo | calidad F1 | pasa | % por capa | ms medio | p99 ms | rápida F1 | pasa | % por capa | ms medio | p99 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| L0c → conjunta | 2974 | 0,818 | 0,829 | 0,818 | sí | 73 % / 27 % | 8,171 | 30,706 | 0,818 | sí | 70 % / 30 % | 9,193 | 30,706 |
| conjunta | 2974 | 0,818 | 0,818 | 0,818 | sí | 100 % | 30,700 | 30,700 | 0,818 | sí | 100 % | 30,700 | 30,700 |
| L0c → L2b-sop | 2974 | 0,794 | 0,864 | 0,794 | sí | 100 % / 0 % | 0,006 | 0,006 | 0,750 | sí | 70 % / 30 % | 9,163 | 30,606 |

## hatecheck (n = 361, 2 clases)

Listón: 0,95 × máx(L0 0,530, kNN-32 0,579, maestro n/d) = **0,550**.

| capa sola | n | macro-F1 | exactitud | ms/consulta |
|---|---|---|---|---|
| L0c | 361 | 0,592 | 0,673 | 0,006 |
| conjunta | 361 | 0,667 | 0,759 | 30,7 |
| L2b-sop | 361 | 0,630 | 0,748 | 30,6 |

| cascada | n | mejor capa | oráculo | calidad F1 | pasa | % por capa | ms medio | p99 ms | rápida F1 | pasa | % por capa | ms medio | p99 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| L0c → conjunta | 361 | 0,667 | 0,754 | 0,650 | sí | 48 % / 52 % | 16,079 | 30,706 | 0,667 | sí | 0 % / 100 % | 30,706 | 30,706 |
| conjunta | 361 | 0,667 | 0,667 | 0,667 | sí | 100 % | 30,700 | 30,700 | 0,667 | sí | 100 % | 30,700 | 30,700 |
| L0c → L2b-sop | 361 | 0,630 | 0,814 | 0,649 | sí | 59 % / 41 % | 12,551 | 30,606 | 0,630 | sí | 0 % / 100 % | 30,606 | 30,606 |

## clinc150 (n = 5500, 151 clases)

Listón: 0,95 × máx(L0 0,811, kNN-32 0,794, maestro n/d) = **0,771**.

| capa sola | n | macro-F1 | exactitud | ms/consulta |
|---|---|---|---|---|
| L0c | 5500 | 0,877 | 0,850 | 0,006 |
| conjunta | 5500 | 0,891 | 0,864 | 30,7 |
| L2b-sop | 5500 | 0,775 | 0,723 | 30,6 |

| cascada | n | mejor capa | oráculo | calidad F1 | pasa | % por capa | ms medio | p99 ms | rápida F1 | pasa | % por capa | ms medio | p99 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| L0c → conjunta | 5500 | 0,891 | 0,905 | 0,890 | sí | 63 % / 37 % | 11,454 | 30,706 | 0,889 | sí | 74 % / 26 % | 8,066 | 30,706 |
| conjunta | 5500 | 0,891 | 0,891 | 0,891 | sí | 100 % | 30,700 | 30,700 | 0,891 | sí | 100 % | 30,700 | 30,700 |
| L0c → L2b-sop | 5500 | 0,877 | 0,919 | 0,877 | sí | 100 % / 0 % | 0,006 | 0,006 | 0,846 | sí | 74 % / 26 % | 8,040 | 30,606 |

## inyecciones (n = 116, 2 clases)

Listón: 0,95 × máx(L0 0,835, kNN-32 0,800, maestro n/d) = **0,793**.

| capa sola | n | macro-F1 | exactitud | ms/consulta |
|---|---|---|---|---|
| L0c | 116 | 0,843 | 0,845 | 0,006 |
| conjunta | 116 | 0,922 | 0,922 | 30,7 |
| L2b-sop | 116 | 0,922 | 0,922 | 30,6 |

| cascada | n | mejor capa | oráculo | calidad F1 | pasa | % por capa | ms medio | p99 ms | rápida F1 | pasa | % por capa | ms medio | p99 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| L0c → conjunta | 116 | 0,922 | 0,957 | 0,940 | sí | 88 % / 12 % | 3,711 | 30,706 | 0,922 | sí | 73 % / 27 % | 8,210 | 30,706 |
| conjunta | 116 | 0,922 | 0,922 | 0,922 | sí | 100 % | 30,700 | 30,700 | 0,922 | sí | 100 % | 30,700 | 30,700 |
| L0c → L2b-sop | 116 | 0,922 | 0,966 | 0,931 | sí | 64 % / 36 % | 11,085 | 30,606 | 0,922 | sí | 73 % / 27 % | 8,184 | 30,606 |

## herramientas (n = 368, 32 clases)

Listón: 0,95 × máx(L0 0,696, kNN-32 0,632, maestro n/d) = **0,661**.

| capa sola | n | macro-F1 | exactitud | ms/consulta |
|---|---|---|---|---|
| L0c | 368 | 0,696 | 0,693 | 0,006 |
| conjunta | 368 | 0,734 | 0,745 | 30,7 |
| L2b-sop | 368 | 0,504 | 0,484 | 30,6 |

| cascada | n | mejor capa | oráculo | calidad F1 | pasa | % por capa | ms medio | p99 ms | rápida F1 | pasa | % por capa | ms medio | p99 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| L0c → conjunta | 368 | 0,734 | 0,770 | 0,720 | sí | 39 % / 61 % | 18,610 | 30,706 | 0,732 | sí | 21 % / 79 % | 24,116 | 30,706 |
| conjunta | 368 | 0,734 | 0,734 | 0,734 | sí | 100 % | 30,700 | 30,700 | 0,734 | sí | 100 % | 30,700 | 30,700 |
| L0c → L2b-sop | 368 | 0,696 | 0,792 | 0,680 | sí | 80 % / 20 % | 5,993 | 30,606 | 0,552 | no | 21 % / 79 % | 24,037 | 30,606 |

## Resumen por cascada

| cascada — punto | pasan el listón | superan a su mejor capa | pierden > 1 punto | hipótesis |
|---|---|---|---|---|
| L0c → conjunta — calidad | 5/5 | 2/5 | 2/5 | refutada |
| L0c → conjunta — rapida | 5/5 | 1/5 | 0/5 | cumple |
| conjunta — calidad | 5/5 | 0/5 | 0/5 | refutada |
| conjunta — rapida | 5/5 | 0/5 | 0/5 | refutada |
| L0c → L2b-sop — calidad | 5/5 | 2/5 | 1/5 | cumple |
| L0c → L2b-sop — rapida | 4/5 | 1/5 | 3/5 | refutada |

H3 (L0c → L2b-sop por debajo de la conjunta en ≥ 3 tareas, punto calidad): 4/5 → CUMPLE. massive 0,794 vs 0,818; hatecheck 0,649 vs 0,667; clinc150 0,877 vs 0,891; inyecciones 0,931 vs 0,922; herramientas 0,680 vs 0,734
