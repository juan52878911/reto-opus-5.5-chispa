# T2.7 Cascada L0 → L1 → L2 frente al listón (2026-10-28)

Reproducir: `python -m model.cascada.capas …` y `python -m model.cascada.informe …` (ver `model/cascada/aws/arranque.sh`).

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
| L2b-sop | 2974 | 0,636 | 0,668 | 30,6 |
| L2b | 2974 | 0,487 | 0,557 | 30,6 |
| L2c-sop | 2974 | 0,604 | 0,641 | 30,6 |
| L2c | 2974 | 0,473 | 0,532 | 30,6 |

| cascada | n | mejor capa | oráculo | calidad F1 | pasa | % por capa | ms medio | p99 ms | rápida F1 | pasa | % por capa | ms medio | p99 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| L0 → L2b-sop | 2974 | 0,678 | 0,776 | 0,689 | sí | 63 % / 37 % | 11,180 | 30,606 | 0,653 | sí | 23 % / 77 % | 23,496 | 30,606 |
| L0 → L1-zs → L2b-sop | 2974 | 0,678 | 0,799 | 0,689 | sí | 63 % / 1 % / 35 % | 10,860 | 30,772 | 0,653 | sí | 23 % / 0 % / 76 % | 23,480 | 30,772 |
| L0 → L1-proto → L2b-sop | 2974 | 0,678 | 0,816 | 0,699 | sí | 63 % / 14 % / 22 % | 6,868 | 30,772 | 0,653 | sí | 23 % / 0 % / 77 % | 23,624 | 30,772 |
| L1-proto → L2b-sop | 2974 | 0,639 | 0,755 | 0,655 | sí | 54 % / 46 % | 14,334 | 30,766 | 0,639 | no | 9 % / 91 % | 28,050 | 30,766 |
| L0 → L2b | 2974 | 0,678 | 0,760 | 0,678 | sí | 91 % / 9 % | 2,691 | 30,606 | 0,557 | no | 23 % / 77 % | 23,496 | 30,606 |
| L0 → L1-zs → L2b | 2974 | 0,678 | 0,789 | 0,678 | sí | 91 % / 0 % / 9 % | 2,696 | 30,772 | 0,557 | no | 23 % / 0 % / 76 % | 23,480 | 30,772 |
| L0 → L1-proto → L2b | 2974 | 0,678 | 0,810 | 0,685 | sí | 82 % / 9 % / 9 % | 2,896 | 30,772 | 0,557 | no | 23 % / 0 % / 77 % | 23,624 | 30,772 |
| L1-proto → L2b | 2974 | 0,639 | 0,730 | 0,643 | no | 88 % / 12 % | 3,973 | 30,766 | 0,500 | no | 9 % / 91 % | 28,050 | 30,766 |
| L0 → L2c-sop | 2974 | 0,678 | 0,781 | 0,678 | sí | 71 % / 29 % | 9,030 | 30,606 | 0,627 | no | 23 % / 77 % | 23,496 | 30,606 |
| L0 → L1-zs → L2c-sop | 2974 | 0,678 | 0,807 | 0,678 | sí | 71 % / 1 % / 29 % | 8,842 | 30,772 | 0,627 | no | 23 % / 0 % / 76 % | 23,480 | 30,772 |
| L0 → L1-proto → L2c-sop | 2974 | 0,678 | 0,823 | 0,683 | sí | 65 % / 25 % / 10 % | 3,131 | 30,772 | 0,627 | no | 23 % / 0 % / 77 % | 23,624 | 30,772 |
| L1-proto → L2c-sop | 2974 | 0,639 | 0,741 | 0,636 | no | 72 % / 28 % | 8,593 | 30,766 | 0,607 | no | 9 % / 91 % | 28,050 | 30,766 |
| L0 → L2c | 2974 | 0,678 | 0,768 | 0,677 | sí | 99 % / 1 % | 0,274 | 0,006 | 0,538 | no | 23 % / 77 % | 23,496 | 30,606 |
| L0 → L1-zs → L2c | 2974 | 0,678 | 0,797 | 0,677 | sí | 99 % / 0 % / 1 % | 0,275 | 0,006 | 0,539 | no | 23 % / 0 % / 76 % | 23,480 | 30,772 |
| L0 → L1-proto → L2c | 2974 | 0,678 | 0,825 | 0,683 | sí | 86 % / 13 % / 2 % | 0,585 | 30,772 | 0,538 | no | 23 % / 0 % / 77 % | 23,624 | 30,772 |
| L1-proto → L2c | 2974 | 0,639 | 0,729 | 0,639 | no | 96 % / 4 % | 1,534 | 30,766 | 0,486 | no | 9 % / 91 % | 28,050 | 30,766 |

## clinc150 (n = 5500, 151 clases)

Listón: 0,95 × máx(L0 0,811, kNN-32 0,794, maestro n/d) = **0,771**.

| capa sola | n | macro-F1 | exactitud | ms/consulta |
|---|---|---|---|---|
| L0 | 5500 | 0,811 | 0,754 | 0,006 |
| L1-zs | 5500 | 0,444 | 0,429 | 0,166 |
| L1-proto | 5500 | 0,756 | 0,703 | 0,166 |
| L2b-sop | 5500 | 0,776 | 0,723 | 30,6 |
| L2b | 5500 | 0,544 | 0,515 | 30,6 |
| L2c-sop | 5500 | 0,762 | 0,716 | 30,6 |
| L2c | 5500 | 0,565 | 0,547 | 30,6 |

| cascada | n | mejor capa | oráculo | calidad F1 | pasa | % por capa | ms medio | p99 ms | rápida F1 | pasa | % por capa | ms medio | p99 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| L0 → L2b-sop | 5500 | 0,811 | 0,879 | 0,812 | sí | 69 % / 31 % | 9,581 | 30,606 | 0,812 | sí | 59 % / 41 % | 12,680 | 30,606 |
| L0 → L1-zs → L2b-sop | 5500 | 0,811 | 0,889 | 0,812 | sí | 69 % / 0 % / 31 % | 9,516 | 30,772 | 0,812 | sí | 59 % / 0 % / 41 % | 12,749 | 30,772 |
| L0 → L1-proto → L2b-sop | 5500 | 0,811 | 0,896 | 0,812 | sí | 69 % / 4 % / 27 % | 8,359 | 30,772 | 0,812 | sí | 59 % / 1 % / 41 % | 12,476 | 30,772 |
| L1-proto → L2b-sop | 5500 | 0,776 | 0,854 | 0,787 | sí | 60 % / 40 % | 12,489 | 30,766 | 0,787 | sí | 38 % / 62 % | 19,255 | 30,766 |
| L0 → L2b | 5500 | 0,811 | 0,854 | 0,811 | sí | 100 % / 0 % | 0,006 | 0,006 | 0,756 | no | 59 % / 41 % | 12,680 | 30,606 |
| L0 → L1-zs → L2b | 5500 | 0,811 | 0,871 | 0,811 | sí | 100 % / 0 % / 0 % | 0,006 | 0,006 | 0,756 | no | 59 % / 0 % / 41 % | 12,749 | 30,772 |
| L0 → L1-proto → L2b | 5500 | 0,811 | 0,885 | 0,806 | sí | 81 % / 8 % / 11 % | 3,493 | 30,772 | 0,757 | no | 59 % / 1 % / 41 % | 12,476 | 30,772 |
| L1-proto → L2b | 5500 | 0,756 | 0,818 | 0,755 | no | 95 % / 5 % | 1,807 | 30,766 | 0,658 | no | 38 % / 62 % | 19,255 | 30,766 |
| L0 → L2c-sop | 5500 | 0,811 | 0,881 | 0,812 | sí | 69 % / 31 % | 9,581 | 30,606 | 0,811 | sí | 59 % / 41 % | 12,680 | 30,606 |
| L0 → L1-zs → L2c-sop | 5500 | 0,811 | 0,890 | 0,810 | sí | 69 % / 2 % / 30 % | 9,149 | 30,772 | 0,811 | sí | 59 % / 0 % / 41 % | 12,749 | 30,772 |
| L0 → L1-proto → L2c-sop | 5500 | 0,811 | 0,899 | 0,812 | sí | 69 % / 3 % / 29 % | 8,854 | 30,772 | 0,811 | sí | 59 % / 1 % / 41 % | 12,476 | 30,772 |
| L1-proto → L2c-sop | 5500 | 0,762 | 0,856 | 0,783 | sí | 56 % / 44 % | 13,702 | 30,766 | 0,781 | sí | 38 % / 62 % | 19,255 | 30,766 |
| L0 → L2c | 5500 | 0,811 | 0,862 | 0,812 | sí | 89 % / 11 % | 3,333 | 30,606 | 0,763 | no | 59 % / 41 % | 12,680 | 30,606 |
| L0 → L1-zs → L2c | 5500 | 0,811 | 0,878 | 0,812 | sí | 89 % / 0 % / 11 % | 3,351 | 30,772 | 0,763 | no | 59 % / 0 % / 41 % | 12,749 | 30,772 |
| L0 → L1-proto → L2c | 5500 | 0,811 | 0,892 | 0,809 | sí | 81 % / 3 % / 16 % | 4,794 | 30,772 | 0,764 | no | 59 % / 1 % / 41 % | 12,476 | 30,772 |
| L1-proto → L2c | 5500 | 0,756 | 0,829 | 0,755 | no | 84 % / 16 % | 4,990 | 30,766 | 0,666 | no | 38 % / 62 % | 19,255 | 30,766 |

## herramientas (n = 368, 32 clases)

Listón: 0,95 × máx(L0 0,696, kNN-32 0,632, maestro n/d) = **0,661**.

| capa sola | n | macro-F1 | exactitud | ms/consulta |
|---|---|---|---|---|
| L0 | 368 | 0,696 | 0,693 | 0,006 |
| L1-zs | 368 | 0,398 | 0,397 | 0,166 |
| L1-proto | 368 | 0,595 | 0,603 | 0,166 |
| L2b-sop | 368 | 0,504 | 0,484 | 30,6 |
| L2b | 368 | 0,328 | 0,315 | 30,6 |
| L2c-sop | 368 | 0,527 | 0,519 | 30,6 |
| L2c | 368 | 0,403 | 0,391 | 30,6 |

| cascada | n | mejor capa | oráculo | calidad F1 | pasa | % por capa | ms medio | p99 ms | rápida F1 | pasa | % por capa | ms medio | p99 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| L0 → L2b-sop | 368 | 0,696 | 0,792 | 0,680 | sí | 80 % / 20 % | 5,993 | 30,606 | 0,552 | no | 21 % / 79 % | 24,037 | 30,606 |
| L0 → L1-zs → L2b-sop | 368 | 0,696 | 0,839 | 0,681 | sí | 86 % / 9 % / 5 % | 1,443 | 30,772 | 0,554 | no | 21 % / 1 % / 78 % | 24,001 | 30,772 |
| L0 → L1-proto → L2b-sop | 368 | 0,696 | 0,837 | 0,699 | sí | 81 % / 14 % / 5 % | 1,617 | 30,772 | 0,552 | no | 21 % / 0 % / 79 % | 24,167 | 30,772 |
| L1-proto → L2b-sop | 368 | 0,595 | 0,705 | 0,581 | no | 82 % / 18 % | 5,737 | 30,766 | 0,510 | no | 9 % / 91 % | 28,105 | 30,766 |
| L0 → L2b | 368 | 0,696 | 0,755 | 0,696 | sí | 100 % / 0 % | 0,006 | 0,006 | 0,453 | no | 21 % / 79 % | 24,037 | 30,606 |
| L0 → L1-zs → L2b | 368 | 0,696 | 0,819 | 0,677 | sí | 89 % / 11 % / 1 % | 0,274 | 0,172 | 0,460 | no | 21 % / 1 % / 78 % | 24,001 | 30,772 |
| L0 → L1-proto → L2b | 368 | 0,696 | 0,832 | 0,701 | sí | 81 % / 17 % / 2 % | 0,619 | 30,772 | 0,453 | no | 21 % / 0 % / 79 % | 24,167 | 30,772 |
| L1-proto → L2b | 368 | 0,595 | 0,689 | 0,595 | no | 100 % / 0 % | 0,166 | 0,166 | 0,353 | no | 9 % / 91 % | 28,105 | 30,766 |
| L0 → L2c-sop | 368 | 0,696 | 0,802 | 0,698 | sí | 88 % / 12 % | 3,831 | 30,606 | 0,572 | no | 21 % / 79 % | 24,037 | 30,606 |
| L0 → L1-zs → L2c-sop | 368 | 0,696 | 0,852 | 0,684 | sí | 85 % / 9 % / 6 % | 1,943 | 30,772 | 0,572 | no | 21 % / 1 % / 78 % | 24,001 | 30,772 |
| L0 → L1-proto → L2c-sop | 368 | 0,696 | 0,852 | 0,695 | sí | 81 % / 10 % / 9 % | 2,698 | 30,772 | 0,572 | no | 21 % / 0 % / 79 % | 24,167 | 30,772 |
| L1-proto → L2c-sop | 368 | 0,595 | 0,739 | 0,583 | no | 82 % / 18 % | 5,737 | 30,766 | 0,531 | no | 9 % / 91 % | 28,105 | 30,766 |
| L0 → L2c | 368 | 0,696 | 0,764 | 0,689 | sí | 98 % / 2 % | 0,671 | 30,606 | 0,487 | no | 21 % / 79 % | 24,037 | 30,606 |
| L0 → L1-zs → L2c | 368 | 0,696 | 0,825 | 0,684 | sí | 89 % / 7 % / 5 % | 1,439 | 30,772 | 0,495 | no | 21 % / 1 % / 78 % | 24,001 | 30,772 |
| L0 → L1-proto → L2c | 368 | 0,696 | 0,840 | 0,697 | sí | 81 % / 17 % / 2 % | 0,619 | 30,772 | 0,487 | no | 21 % / 0 % / 79 % | 24,167 | 30,772 |
| L1-proto → L2c | 368 | 0,595 | 0,714 | 0,592 | no | 96 % / 4 % | 1,496 | 30,766 | 0,417 | no | 9 % / 91 % | 28,105 | 30,766 |

## hatecheck (n = 361, 2 clases)

Listón: 0,95 × máx(L0 0,530, kNN-32 0,579, maestro n/d) = **0,550**.

| capa sola | n | macro-F1 | exactitud | ms/consulta |
|---|---|---|---|---|
| L0 | 361 | 0,530 | 0,579 | 0,006 |
| L1-zs | 361 | 0,224 | 0,288 | 0,166 |
| L1-proto | 361 | 0,571 | 0,632 | 0,166 |
| L2b-sop | 361 | 0,630 | 0,748 | 30,6 |
| L2b | 361 | 0,610 | 0,751 | 30,6 |
| L2c-sop | 361 | 0,616 | 0,753 | 30,6 |
| L2c | 361 | 0,528 | 0,737 | 30,6 |

| cascada | n | mejor capa | oráculo | calidad F1 | pasa | % por capa | ms medio | p99 ms | rápida F1 | pasa | % por capa | ms medio | p99 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| L0 → L2b-sop | 361 | 0,630 | 0,829 | 0,636 | sí | 9 % / 91 % | 27,724 | 30,606 | 0,630 | sí | 0 % / 100 % | 30,606 | 30,606 |
| L0 → L1-zs → L2b-sop | 361 | 0,630 | 0,974 | 0,602 | sí | 22 % / 6 % / 71 % | 21,919 | 30,772 | 0,630 | sí | 0 % / 0 % / 100 % | 30,772 | 30,772 |
| L0 → L1-proto → L2b-sop | 361 | 0,630 | 0,880 | 0,594 | sí | 22 % / 28 % / 49 % | 15,223 | 30,772 | 0,624 | sí | 0 % / 5 % / 95 % | 29,331 | 30,772 |
| L1-proto → L2b-sop | 361 | 0,630 | 0,805 | 0,630 | sí | 31 % / 69 % | 21,188 | 30,766 | 0,624 | sí | 5 % / 95 % | 29,325 | 30,766 |
| L0 → L2b | 361 | 0,610 | 0,832 | 0,575 | sí | 22 % / 78 % | 23,740 | 30,606 | 0,610 | sí | 0 % / 100 % | 30,606 | 30,606 |
| L0 → L1-zs → L2b | 361 | 0,610 | 0,987 | 0,594 | sí | 22 % / 6 % / 71 % | 21,919 | 30,772 | 0,610 | sí | 0 % / 0 % / 100 % | 30,772 | 30,772 |
| L0 → L1-proto → L2b | 361 | 0,610 | 0,882 | 0,575 | sí | 22 % / 28 % / 49 % | 15,223 | 30,772 | 0,603 | sí | 0 % / 5 % / 95 % | 29,331 | 30,772 |
| L1-proto → L2b | 361 | 0,610 | 0,812 | 0,616 | sí | 31 % / 69 % | 21,188 | 30,766 | 0,603 | sí | 5 % / 95 % | 29,325 | 30,766 |
| L0 → L2c-sop | 361 | 0,616 | 0,823 | 0,579 | sí | 22 % / 78 % | 23,740 | 30,606 | 0,616 | sí | 0 % / 100 % | 30,606 | 30,606 |
| L0 → L1-zs → L2c-sop | 361 | 0,616 | 0,987 | 0,587 | sí | 22 % / 6 % / 71 % | 21,919 | 30,772 | 0,616 | sí | 0 % / 0 % / 100 % | 30,772 | 30,772 |
| L0 → L1-proto → L2c-sop | 361 | 0,616 | 0,874 | 0,581 | sí | 22 % / 37 % / 40 % | 12,510 | 30,772 | 0,610 | sí | 0 % / 5 % / 95 % | 29,331 | 30,772 |
| L1-proto → L2c-sop | 361 | 0,616 | 0,803 | 0,635 | sí | 31 % / 69 % | 21,188 | 30,766 | 0,610 | sí | 5 % / 95 % | 29,325 | 30,766 |
| L0 → L2c | 361 | 0,530 | 0,789 | 0,522 | no | 22 % / 78 % | 23,740 | 30,606 | 0,528 | no | 0 % / 100 % | 30,606 | 30,606 |
| L0 → L1-zs → L2c | 361 | 0,530 | 0,997 | 0,550 | no | 22 % / 8 % / 69 % | 21,326 | 30,772 | 0,528 | no | 0 % / 0 % / 100 % | 30,772 | 30,772 |
| L0 → L1-proto → L2c | 361 | 0,571 | 0,858 | 0,559 | sí | 22 % / 41 % / 37 % | 11,324 | 30,772 | 0,536 | no | 0 % / 5 % / 95 % | 29,331 | 30,772 |
| L1-proto → L2c | 361 | 0,571 | 0,789 | 0,566 | sí | 52 % / 48 % | 14,746 | 30,766 | 0,536 | no | 5 % / 95 % | 29,325 | 30,766 |

## inyecciones (n = 116, 2 clases)

Listón: 0,95 × máx(L0 0,835, kNN-32 0,800, maestro n/d) = **0,793**.

| capa sola | n | macro-F1 | exactitud | ms/consulta |
|---|---|---|---|---|
| L0 | 116 | 0,835 | 0,836 | 0,006 |
| L1-zs | 116 | 0,326 | 0,483 | 0,166 |
| L1-proto | 116 | 0,853 | 0,853 | 0,166 |
| L2b-sop | 116 | 0,922 | 0,922 | 30,6 |
| L2b | 116 | 0,862 | 0,862 | 30,6 |
| L2c-sop | 116 | 0,957 | 0,957 | 30,6 |
| L2c | 116 | 0,922 | 0,922 | 30,6 |

| cascada | n | mejor capa | oráculo | calidad F1 | pasa | % por capa | ms medio | p99 ms | rápida F1 | pasa | % por capa | ms medio | p99 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| L0 → L2b-sop | 116 | 0,922 | 0,983 | 0,914 | sí | 37 % / 63 % | 19,263 | 30,606 | 0,905 | sí | 39 % / 61 % | 18,735 | 30,606 |
| L0 → L1-zs → L2b-sop | 116 | 0,922 | 0,991 | 0,914 | sí | 37 % / 16 % / 47 % | 14,355 | 30,772 | 0,905 | sí | 39 % / 14 % / 47 % | 14,616 | 30,772 |
| L0 → L1-proto → L2b-sop | 116 | 0,922 | 0,983 | 0,905 | sí | 34 % / 52 % / 15 % | 4,601 | 30,772 | 0,914 | sí | 39 % / 27 % / 34 % | 10,659 | 30,772 |
| L1-proto → L2b-sop | 116 | 0,922 | 0,965 | 0,905 | sí | 78 % / 22 % | 6,761 | 30,766 | 0,905 | sí | 72 % / 28 % | 8,607 | 30,766 |
| L0 → L2b | 116 | 0,862 | 0,974 | 0,870 | sí | 55 % / 45 % | 13,723 | 30,606 | 0,870 | sí | 39 % / 61 % | 18,735 | 30,606 |
| L0 → L1-zs → L2b | 116 | 0,862 | 0,991 | 0,870 | sí | 55 % / 14 % / 31 % | 9,577 | 30,772 | 0,879 | sí | 39 % / 14 % / 47 % | 14,616 | 30,772 |
| L0 → L1-proto → L2b | 116 | 0,862 | 0,983 | 0,870 | sí | 39 % / 48 % / 13 % | 4,065 | 30,772 | 0,888 | sí | 39 % / 27 % / 34 % | 10,659 | 30,772 |
| L1-proto → L2b | 116 | 0,862 | 0,974 | 0,879 | sí | 78 % / 22 % | 6,761 | 30,766 | 0,879 | sí | 72 % / 28 % | 8,607 | 30,766 |
| L0 → L2c-sop | 116 | 0,957 | 0,991 | 0,931 | sí | 34 % / 66 % | 20,318 | 30,606 | 0,922 | sí | 39 % / 61 % | 18,735 | 30,606 |
| L0 → L1-zs → L2c-sop | 116 | 0,957 | 0,991 | 0,931 | sí | 34 % / 16 % / 50 % | 15,416 | 30,772 | 0,922 | sí | 39 % / 14 % / 47 % | 14,616 | 30,772 |
| L0 → L1-proto → L2c-sop | 116 | 0,957 | 0,991 | 0,931 | sí | 34 % / 26 % / 41 % | 12,514 | 30,772 | 0,922 | sí | 39 % / 27 % / 34 % | 10,659 | 30,772 |
| L1-proto → L2c-sop | 116 | 0,957 | 0,974 | 0,957 | sí | 41 % / 59 % | 18,104 | 30,766 | 0,931 | sí | 72 % / 28 % | 8,607 | 30,766 |
| L0 → L2c | 116 | 0,922 | 0,991 | 0,922 | sí | 37 % / 63 % | 19,263 | 30,606 | 0,914 | sí | 39 % / 61 % | 18,735 | 30,606 |
| L0 → L1-zs → L2c | 116 | 0,922 | 0,991 | 0,914 | sí | 34 % / 16 % / 50 % | 15,416 | 30,772 | 0,905 | sí | 39 % / 14 % / 47 % | 14,616 | 30,772 |
| L0 → L1-proto → L2c | 116 | 0,922 | 0,991 | 0,940 | sí | 34 % / 29 % / 37 % | 11,459 | 30,772 | 0,914 | sí | 39 % / 27 % / 34 % | 10,659 | 30,772 |
| L1-proto → L2c | 116 | 0,922 | 0,991 | 0,940 | sí | 57 % / 43 % | 13,356 | 30,766 | 0,922 | sí | 72 % / 28 % | 8,607 | 30,766 |

## Resumen por cascada

| cascada — punto | pasan el listón | superan a su mejor capa | pierden > 1 punto | hipótesis |
|---|---|---|---|---|
| L0 → L2b-sop — calidad | 5/5 | 3/5 | 1/5 | cumple |
| L0 → L2b-sop — rapida | 4/5 | 1/5 | 3/5 | refutada |
| L0 → L1-zs → L2b-sop — calidad | 5/5 | 2/5 | 2/5 | refutada |
| L0 → L1-zs → L2b-sop — rapida | 4/5 | 1/5 | 3/5 | refutada |
| L0 → L1-proto → L2b-sop — calidad | 5/5 | 3/5 | 2/5 | refutada |
| L0 → L1-proto → L2b-sop — rapida | 4/5 | 1/5 | 2/5 | refutada |
| L1-proto → L2b-sop — calidad | 4/5 | 3/5 | 2/5 | refutada |
| L1-proto → L2b-sop — rapida | 3/5 | 1/5 | 2/5 | refutada |
| L0 → L2b — calidad | 5/5 | 2/5 | 1/5 | cumple |
| L0 → L2b — rapida | 2/5 | 1/5 | 3/5 | refutada |
| L0 → L1-zs → L2b — calidad | 5/5 | 2/5 | 2/5 | refutada |
| L0 → L1-zs → L2b — rapida | 2/5 | 1/5 | 3/5 | refutada |
| L0 → L1-proto → L2b — calidad | 5/5 | 3/5 | 1/5 | cumple |
| L0 → L1-proto → L2b — rapida | 2/5 | 1/5 | 3/5 | refutada |
| L1-proto → L2b — calidad | 2/5 | 3/5 | 0/5 | no cumple |
| L1-proto → L2b — rapida | 2/5 | 1/5 | 3/5 | refutada |
| L0 → L2c-sop — calidad | 5/5 | 3/5 | 2/5 | refutada |
| L0 → L2c-sop — rapida | 3/5 | 0/5 | 3/5 | refutada |
| L0 → L1-zs → L2c-sop — calidad | 5/5 | 1/5 | 3/5 | refutada |
| L0 → L1-zs → L2c-sop — rapida | 3/5 | 0/5 | 3/5 | refutada |
| L0 → L1-proto → L2c-sop — calidad | 5/5 | 2/5 | 2/5 | refutada |
| L0 → L1-proto → L2c-sop — rapida | 3/5 | 0/5 | 3/5 | refutada |
| L1-proto → L2c-sop — calidad | 3/5 | 3/5 | 1/5 | no cumple |
| L1-proto → L2c-sop — rapida | 3/5 | 1/5 | 3/5 | refutada |
| L0 → L2c — calidad | 4/5 | 2/5 | 0/5 | cumple |
| L0 → L2c — rapida | 1/5 | 0/5 | 3/5 | refutada |
| L0 → L1-zs → L2c — calidad | 4/5 | 2/5 | 1/5 | cumple |
| L0 → L1-zs → L2c — rapida | 1/5 | 0/5 | 4/5 | refutada |
| L0 → L1-proto → L2c — calidad | 5/5 | 3/5 | 1/5 | cumple |
| L0 → L1-proto → L2c — rapida | 1/5 | 0/5 | 4/5 | refutada |
| L1-proto → L2c — calidad | 2/5 | 1/5 | 0/5 | no cumple |
| L1-proto → L2c — rapida | 1/5 | 1/5 | 4/5 | refutada |
