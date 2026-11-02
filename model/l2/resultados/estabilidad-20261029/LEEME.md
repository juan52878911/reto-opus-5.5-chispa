# Tanda de estabilidad: medidas con el checkpoint de G.8 (c6a.2xlarge, `5f136b6`, 16 min, ≈ 0,1 USD)

| pieza | resultado | ¿listo? |
|---|---|---|
| M2 textos largos | JevBench tiene 82 casos largos. **Gana cabeza** (la de ahora): 0,485 global y 0,366 en los largos. Cola, cabeza+cola y los trozos con máx./media no la superan; todos quedan con IC por debajo o solapado. El contrato sigue siendo «cabeza»: E3 no necesita cambiar el valor por defecto | sí |
| M5 score | **FALLO del script:** falta `model/meta/resultados/conversion-20261027.json` en el paquete | no, repetir |
| M6 L1 frente a L2 | L1/L2 de macro-F1 por tarea: massive 1,39 · hatecheck 1,05 · clinc150 0,91 · inyecciones 2,09 · herramientas 0,93. **Cumple ≥ 0,90 en todas.** Ojo: G.8 se entrenó **sin** massive, hatecheck ni inyecciones (`EXCLUIR` de `general.sh`), así que en esas tareas L2 es zero-shot y L1 tiene su train | sí |
| M1 línea base | **No vale todavía.** La batería da exactitud 0 con un 100 % escalado. `tau_escalate_l2` = 0,93 hace escalar casi todo, y la batería cuenta un escalado como fallo en lugar de medir el argmax de `probs`, como hace `servidor.py`. La línea base guardada es **provisional** | no, la batería tiene que cambiar |
| M3 robustez | Ver abajo | sí |
| M4 español | es − en = **−3,5 puntos** de exactitud [−5,9, −1,1] en 4 pares (massive −5,8, sib200 −6,4, xnli −1,5, paws-x −0,2). Supera el umbral de 3. Plan en `m4/plan.md` | sí |

## M3: porcentaje de decisiones que cambian con cada variante (IC95)
| variante | L1 | L2 |
|---|---|---|
| permutar | 0 % | 0 % |
| renombrar ids | 0 % | **37,6 %** |
| parafrasear la pregunta | 0 % | **9,5 %** |
| erratas | **8,7 %** | **12,8 %** |
| mayúsculas | **46,4 %** | **33,4 %** |
| mezcla es/en | 1,7 % | **6,7 %** |
| largo (frases añadidas) | **71,1 %** | **61,3 %** |
| pregunta en inglés | 0 % | **16,6 %** |
| esquema en inglés | 0 % | **15,0 %** |

En negrita, más del 5 %. Detalle en `m3/robustez.md`.
