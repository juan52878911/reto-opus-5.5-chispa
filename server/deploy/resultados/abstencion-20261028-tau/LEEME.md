# T4.6b medido: abstención y ASR con el τ de L2c sacado de la cabeza conjunta (2 c6a, 2026-10-28)

`chispa train --conjunta` fija el τ de L2c con la cabeza ajustada fuera de pliegue sobre train, para una precisión de 0,95.

| tarea | τ de L2c | escala (antes → ahora) | precisión de lo contestado | objetivo |
|---|---|---|---|---|
| massive | 0,795 | 43 % → **27,8 %** | 0,949 | ≤ 20 %: no llega |
| clinc150 | 0,128 | 46 % → **0,1 %** | **0,859** | la precisión cae por debajo de 0,95 |
| injection (Arena) | — | 50 % → 18,5 % | 1,000 | cumple |
| spam (Arena) | 0,982 | 84 % → 32,4 % | 1,000 | ≤ 20 %: no llega |

- **massive va bien:** la precisión real (0,949) cuadra con la estimada (0,950).
- **clinc150 falla.** Fuera de pliegue sobre train, la cabeza da 0,953 de precisión aceptándolo todo, así que el τ queda
  en 0,128. En test la precisión es 0,859. El train fuera de pliegue es optimista para clinc150, probablemente por la clase
  `oos`/`escalate`, que en test se comporta distinto. El τ tiene que salir de filas que se parezcan al test (dev) o
  llevar un suelo.
- **ASR de la Arena** con el τ nuevo:
  - detector cascada: injection 0,019 / 0,043 y spam 0,063 / 0,100 (solo / enjambre);
  - **sigue ≤ 0,15**;
  - el enjambre: injection 0,172 y spam 0,076.
- **Siguiente paso:** T4.6c, elegir el τ en dev cuando lo haya y, si no, fuera de pliegue con un margen.
- **Coste:** dos c6a de 22 y 27 min, ≈ 0,1 USD.
