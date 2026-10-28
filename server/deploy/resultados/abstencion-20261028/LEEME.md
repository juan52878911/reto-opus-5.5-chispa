# T4.6, abstención de la cascada con tráfico no adversarial (c6a, 2026-10-28)

Test limpio de cada tarea por `/v1/decide`, en modo cascada, con τ de CALIB (`tau_escalate`).

| tarea | n | escala | precisión en lo contestado | τ para abstención ≤ 20 % | precisión con ese τ |
|---|---|---|---|---|---|
| clinc150 | 5500 | 46 % | 0,984 | 0,791 | 0,949 |
| massive | 2974 | 43 % | 0,969 | 0,687 | 0,928 |
| injection (Arena) | 108 | 50 % | 1,000 | 0,902 | 1,000 |
| spam (Arena) | 108 | 84 % | 1,000 | 0,812 | 1,000 |

- **H1 se refuta.** Con el τ de CALIB, la cascada escala entre el 43 % y el 84 % del tráfico normal.
- **La causa es el τ, no el modelo.** En clinc150 lo contestado tiene una precisión de 0,984, muy por encima del objetivo
  de 0,95. El `tau_escalate` de CALIB sale de la calibración de L2 solo (T2.4), no de la cabeza conjunta que responde de
  verdad. Con un τ elegido para dejar la abstención en el 20 %, clinc150 queda en 0,949: justo el objetivo.
- **H2 se cumple.** Con τ por tarea se baja al 20 % de abstención con una precisión de 0,93 a 1,0.
- **Arreglo.** `chispa train --conjunta` debe fijar el τ de L2c con las probabilidades fuera de pliegue de la cabeza, al
  nivel de precisión 0,95 (T4.6b).
- **Muestra pequeña.** spam e injection de la Arena tienen 108 filas de test: cifras con mucha varianza.
- **Coste:** una c6a de 21 min, ≈ 0,05 USD.
