# T2.2c, cabeza conjunta L0 + L2 (g5.xlarge, 2026-10-28): H1 se cumple y pasa T2.2

- **Montaje.** Cabeza `lr` por tarea sobre log-probs de L0 y similitudes de L2 con soporte.
  - En train, las características son fuera de pliegue: L0 a k = 5 y L2 dejando fuera la propia fila.
  - Checkpoint: T2.1b (`l2-20261028b/ckpt/mejor.pt`).
- **Resultado.** Pasa el listón de T2.2 en las 5 tareas y supera a la mejor capa sola en ≥ 1 punto en 3 de 5.

| tarea | L0 completo | L2+soporte | conjunta | Δ vs mejor capa | listón |
|---|---|---|---|---|---|
| massive | 0,794 | 0,632 | **0,817** | +2,3 | 0,644 |
| clinc150 | 0,877 | 0,775 | **0,890** | +1,2 | 0,771 |
| herramientas | 0,696 | 0,504 | **0,729** | +3,3 | 0,661 |
| inyecciones | 0,843 | 0,922 | **0,931** | +0,9 | 0,793 |
| hatecheck | 0,592 | 0,630 | 0,571 | **−5,9** | 0,550 |

- **Renombrado.** La caída de la conjunta es ≤ 0,1 puntos en todas las tareas, frente a hasta 3,2 de L2 solo. El criterio de T2.2 pide ≤ 5: se cumple.
- **L0 con todo el train.** Las cifras de «L0 completo» salen de entrenar con todo el train, y quedan muy por encima de la línea base de 32 por clase (massive 0,794 frente a 0,678). La cascada de T2.7 usó la línea base de 32 por clase, así que hay que repetirla con L0 completo antes de comparar con (b).
- **hatecheck.** La conjunta pierde frente a L2 solo. HateCheck es de plantillas: lo que aprende la cabeza en train no se traslada bien a test. Pendiente: entrenar la cabeza fuera de pliegue sobre test, como se eligió τ en T2.7.
- **Primer intento.** Solo procesó herramientas: `cargar_tareas` agrupaba el train por el campo `tarea`. Arreglado en el commit anterior.
- **Coste.** Dos g5.xlarge on-demand, unos 5 y 14 min. Menos de 0,5 USD.
